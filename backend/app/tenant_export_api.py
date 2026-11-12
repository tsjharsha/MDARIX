"""Request and download full data exports of an organization, export one person's data, and delete an
organization's data (backend/app/tenant_export.py, tenant_purge.py). The legal-hold routes (legal_hold_api.py) are
mounted here with the rest of the data-governance API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app import support_access
from backend.app.access.authz import _admin_tenant, _require_platform_admin, ensure_user_visible
from backend.app.business_ids import business_id_of
from backend.app.db.models.foundation import AuditEvent, AuthUser, PlanDefinition, Tenant, TenantMembership
from backend.app.db.models.stage2 import (
    AuthenticationEvent,
    AuthSession,
    SubscriptionLifecycle,
    TenantExport,
    TrialFeedback,
)
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.legal_hold_api import router as legal_hold_router
from backend.app.tenant_export import ExportInProgress, describe, read_export, request_export

router = APIRouter(prefix="/api/v1", tags=["Data export"])
# The legal-hold routes already carry the /api/v1 prefix, so they are added as they are. (Nesting the router with
# include_router doubled the prefix and the routes never reached the application.)
router.routes.extend(legal_hold_router.routes)

DOWNLOAD_CHUNK = 1024 * 1024
# The most audit events one person's export carries; a longer trail is flagged and continued in the organization
# export, which has every event.
PERSON_AUDIT_LIMIT = 10000


class ExportRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    # A current code from the administrator's authenticator app (confirm_with_authenticator).
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)
    # OD-1: contacts are masked unless asked; the reason above is the reason for unmasking, audited with the export.
    unmask_contacts: bool = False


def confirm_with_authenticator(
    db: Session, user: AuthUser, code: str | None, *, tenant_id, action: str, request: Request | None = None
) -> None:
    """Taking every record of an organization, or deleting them, needs a current authenticator code as well as the
    signed-in session: a session left open on a shared screen, or stolen, is not enough for either.

    An account with an authenticator must give a current code (recovery codes are not accepted; wrong codes count
    towards the sign-in code lock). An account whose role must use MFA but has none set up is refused until it does.
    Only where no MFA policy applies (local development) does an account without an authenticator go ahead. A refusal
    is audited (``{action}_REFUSED_MFA``) and committed. The code is AUTHENTICATOR_CODE_REQUIRED, not MFA_REQUIRED,
    so the browser shows it in the dialog instead of treating the whole session as unverified."""
    from backend.app import mfa

    if not mfa.is_enrolled(user):
        if mfa._normalize(user.role) in mfa.required_roles():
            raise HTTPException(
                403,
                detail={
                    "code": "MFA_ENROLLMENT_REQUIRED",
                    "message": "Set up an authenticator app (My Account > Security) before this operation",
                },
            )
        return
    mfa.ensure_not_locked(db, user)
    if not code or not mfa.check_code(user, code, allow_recovery=False):
        mfa.record_failure(db, user)
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(user.id),
                action=f"{action}_REFUSED_MFA",
                entity_type="Tenant",
                entity_id=tenant_id,
                request=request,
                details={"code_given": bool(code)},
            )
        )
        db.commit()
        raise HTTPException(
            403,
            detail={
                "code": "AUTHENTICATOR_CODE_REQUIRED",
                "message": "Enter the current code from your authenticator app",
            },
        )
    mfa.record_success(db, user)


def _queue(db: Session, tenant_id, actor_ref: str, reason: str, unmask_contacts: bool = False) -> dict:
    try:
        row = request_export(db, tenant_id, actor_ref, reason.strip(), unmask_contacts)
    except ExportInProgress:
        raise HTTPException(
            409, detail={"code": "EXPORT_IN_PROGRESS", "message": "An export is already being prepared"}
        )
    db.commit()
    return describe(row)


def _list(db: Session, tenant_id, actor_ref: str) -> dict:
    rows = (
        db.query(TenantExport)
        .filter(TenantExport.tenant_id == tenant_id)
        .order_by(TenantExport.created_at.desc())
        .limit(20)
        .all()
    )
    # ``yours``: the screen offers the download only to the person who asked for it (RSK-036, _download).
    return {"exports": [{**describe(row), "yours": row.requested_by == actor_ref} for row in rows]}


def _chunks(content: bytes):
    view = memoryview(content)
    for start in range(0, len(view), DOWNLOAD_CHUNK):
        yield bytes(view[start : start + DOWNLOAD_CHUNK])


def _refuse_download(db: Session, tenant_id, row: TenantExport, actor_ref: str, status: int, code: str, message: str):
    """The refusal is audited and committed, so a reviewer sees who tried to take the archive and why it was stopped."""
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TENANT_EXPORT_DOWNLOAD_REFUSED",
            entity_type="TenantExport",
            entity_id=row.id,
            details={"code": code, "requested_by": row.requested_by},
        )
    )
    db.commit()
    raise HTTPException(status, detail={"code": code, "message": message})


def _download(db: Session, tenant_id, export_id: uuid.UUID, actor_ref: str) -> StreamingResponse:
    # RSK-036: only the person who asked for the export takes it, and only inside its download period (the hourly
    # export-expiry job deletes it later; the period is enforced here, not by that job).
    row = (
        db.query(TenantExport)
        .filter(TenantExport.id == export_id, TenantExport.tenant_id == uuid.UUID(str(tenant_id)))
        .first()
    )
    if row is not None and row.status == "READY":
        if row.requested_by != actor_ref:
            _refuse_download(
                db,
                tenant_id,
                row,
                actor_ref,
                403,
                "EXPORT_NOT_REQUESTER",
                "Only the person who asked for this export can download it; prepare your own export",
            )
        if row.expires_at is not None and row.expires_at <= datetime.now(timezone.utc):
            _refuse_download(
                db,
                tenant_id,
                row,
                actor_ref,
                410,
                "EXPORT_EXPIRED",
                "This export's download period has ended; prepare a new export",
            )
    try:
        row, content = read_export(db, tenant_id, export_id)
    except (LookupError, FileNotFoundError):
        raise HTTPException(404, detail={"code": "EXPORT_NOT_AVAILABLE", "message": "This export is not available"})
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TENANT_EXPORT_DOWNLOADED",
            entity_type="TenantExport",
            entity_id=row.id,
            details={"size_bytes": row.size_bytes, "sha256": row.sha256},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    stamp = row.created_at.strftime("%Y%m%d")
    # Streamed in fixed chunks, so the response layer never makes a second copy of a large archive.
    return StreamingResponse(
        _chunks(content),
        media_type="application/zip",
        headers={
            "Content-Disposition": attachment(f"mdarix-export-{stamp}-{str(row.id)[:8]}.zip"),
            "Content-Length": str(len(content)),
            "Cache-Control": "no-store",
        },
    )


@router.post("/admin/exports", status_code=202)
def request_own_export(payload: ExportRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    confirm_with_authenticator(
        db, admin, payload.mfa_code, tenant_id=admin.tenant_id, action="TENANT_EXPORT", request=request
    )
    if payload.unmask_contacts:
        from backend.app.access.permissions import DATA_EXPORT, permissions_for_roles, roles_of_user

        if DATA_EXPORT not in permissions_for_roles(roles_of_user(db, admin)):
            raise HTTPException(
                403, detail={"code": "PERMISSION_DENIED", "message": "Unmasking contacts needs data.export"}
            )
    return _queue(db, admin.tenant_id, str(admin.id), payload.reason, payload.unmask_contacts)


@router.get("/admin/exports")
def list_own_exports(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    return _list(db, admin.tenant_id, str(admin.id))


@router.get("/admin/exports/{export_id}/download")
def download_own_export(export_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    return _download(db, admin.tenant_id, export_id, str(admin.id))


# ------------------------------------------------------------------------------------------- one person


def _account_record(user: AuthUser) -> dict:
    """The account as the person may see it: no credentials, no authenticator material."""
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "tenant_id": str(user.tenant_id),
        "email": user.username,
        "display_name": user.display_name,
        "company": user.company,
        "role": user.role,
        "status": user.status,
        "email_verified": bool(user.email_verified),
        "mfa_enrolled": bool(getattr(user, "mfa_enrolled_at", None)),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def person_export(db: Session, user: AuthUser) -> dict:
    """Everything MDARIX holds about one person in their organization (docs/runbooks/DATA_REQUESTS.md, section 1):
    the account record, their memberships, a summary of their sessions and sign-in events (never the session hashes),
    the audit events they caused, and their feedback. Business records they created are in the organization export,
    keyed by this account id."""
    tenant_id = user.tenant_id
    sessions = db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.tenant_id == tenant_id)
    now = datetime.now(timezone.utc)
    first_session, last_seen = (
        db.query(func.min(AuthSession.created_at), func.max(AuthSession.last_seen_at))
        .filter(AuthSession.user_id == user.id, AuthSession.tenant_id == tenant_id)
        .one()
    )
    sign_ins = (
        db.query(AuthenticationEvent)
        .filter(AuthenticationEvent.user_id == user.id, AuthenticationEvent.tenant_id == tenant_id)
        .order_by(AuthenticationEvent.created_at.desc())
        .all()
    )
    events_query = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.actor_ref == str(user.id))
        .order_by(AuditEvent.created_at)
    )
    total_events = events_query.count()
    events = events_query.limit(PERSON_AUDIT_LIMIT).all()
    feedback = (
        db.query(TrialFeedback).filter(TrialFeedback.user_id == user.id, TrialFeedback.tenant_id == tenant_id).all()
    )
    return {
        "generated_at": now.isoformat(),
        "account": _account_record(user),
        "memberships": [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "status": row.status,
                "is_default": bool(row.is_default),
            }
            for row in db.query(TenantMembership).filter(TenantMembership.user_id == user.id).all()
        ],
        "sessions": {
            "total": sessions.count(),
            "active": sessions.filter(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now).count(),
            "first_signed_in_at": first_session.isoformat() if first_session else None,
            "last_seen_at": last_seen.isoformat() if last_seen else None,
        },
        "sign_in_events": [
            {
                "event_type": row.event_type,
                "outcome": row.outcome,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "metadata": row.metadata_json,
            }
            for row in sign_ins
        ],
        "audit_events": [
            {
                "id": str(row.id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "reason": row.reason,
                "details": row.details,
                "old_values": row.old_values,
                "new_values": row.new_values,
                "source_ip": row.source_ip,
                "user_agent": row.user_agent,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "chain_seq": row.chain_seq,
            }
            for row in events
        ],
        "audit_events_total": total_events,
        "audit_events_truncated": total_events > len(events),
        "feedback": [
            {
                column.name: (value.isoformat() if isinstance(value := getattr(row, column.name), datetime) else value)
                for column in TrialFeedback.__table__.columns
            }
            for row in feedback
        ],
    }


@router.get("/admin/people/{user_id}/export")
def export_person(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """A customer administrator answers one person's access request with this JSON document (audited)."""
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    user = ensure_user_visible(admin, user)
    document = person_export(db, user)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="PERSONAL_DATA_EXPORTED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"audit_events": len(document["audit_events"]), "feedback": len(document["feedback"])},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return JSONResponse(
        document,
        headers={
            "Content-Disposition": attachment(f"mdarix-person-{str(user.id)[:8]}.json"),
            "Cache-Control": "no-store",
        },
    )


# ------------------------------------------------------------------------------------------- platform


def _tenant(db: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    return tenant_id


@router.post("/platform-admin/tenants/{tenant_id}/exports", status_code=202)
def request_tenant_export(
    tenant_id: uuid.UUID, payload: ExportRequest, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    tenant_id = _tenant(db, tenant_id)
    # A copy of every record of the organization: only under the full-export access its administrators approved.
    support_access.require_customer_approved_access(
        db, platform_admin, tenant_id, support_access.DATA_EXPORT, request=request
    )
    confirm_with_authenticator(
        db, platform_admin, payload.mfa_code, tenant_id=tenant_id, action="TENANT_EXPORT", request=request
    )
    return _queue(db, tenant_id, str(platform_admin.id), payload.reason)


@router.get("/platform-admin/tenants/{tenant_id}/exports")
def list_tenant_exports(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    platform_admin = _require_platform_admin(request, db)
    return _list(db, _tenant(db, tenant_id), str(platform_admin.id))


@router.get("/platform-admin/tenants/{tenant_id}/exports/{export_id}/download")
def download_tenant_export(tenant_id: uuid.UUID, export_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    platform_admin = _require_platform_admin(request, db)
    tenant_id = _tenant(db, tenant_id)
    # Checked again at download: the access may have been revoked or have expired since the export was made.
    support_access.require_customer_approved_access(
        db, platform_admin, tenant_id, support_access.DATA_EXPORT, request=request
    )
    return _download(db, tenant_id, export_id, str(platform_admin.id))


class PurgeRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    password: str = Field(min_length=1, max_length=128)
    # A current code from the administrator's authenticator app, after the password (confirm_with_authenticator).
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)
    # The organization's key typed back, so the wrong organization is never deleted by a slip.
    confirm_tenant_key: str = Field(min_length=1, max_length=80)
    # A paying customer's data is handed back before it is deleted: a READY export newer than the suspension is
    # required, unless the administrator records here why none is (for example the customer declined in writing).
    export_waiver_reason: str | None = Field(default=None, min_length=10, max_length=1000)


def is_free_trial(db: Session, tenant_id) -> bool:
    return (
        db.query(SubscriptionLifecycle.id)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .filter(SubscriptionLifecycle.tenant_id == tenant_id, PlanDefinition.code == "FREE_TRIAL")
        .first()
        is not None
    )


def export_evidence(db: Session, tenant: Tenant, waiver: str | None) -> dict:
    """What goes into the purge's surviving records about the hand-back: the export that was prepared after the
    organization was suspended or terminated, or the recorded reason none was. Free trials are told in advance that
    their data is deleted, so none is required for them."""
    if is_free_trial(db, tenant.id):
        return {"export": "NOT_REQUIRED_FREE_TRIAL"}
    since = tenant.suspended_at or tenant.terminated_at
    query = db.query(TenantExport).filter(TenantExport.tenant_id == tenant.id, TenantExport.status == "READY")
    if since is not None:
        query = query.filter(TenantExport.completed_at >= since)
    latest = query.order_by(TenantExport.completed_at.desc()).first()
    if latest is not None:
        return {
            "export": {
                "id": str(latest.id),
                "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
                "sha256": latest.sha256,
                "size_bytes": latest.size_bytes,
            }
        }
    if waiver:
        return {"export": "WAIVED", "export_waiver_reason": waiver.strip()}
    raise HTTPException(
        409,
        detail={
            "code": "EXPORT_REQUIRED",
            "message": (
                "Prepare and hand back an export made after the organization was suspended, or record in "
                "export_waiver_reason why the data is not being returned"
            ),
        },
    )


@router.post("/platform-admin/tenants/{tenant_id}/purge")
def purge_tenant_data(tenant_id: uuid.UUID, payload: PurgeRequest, request: Request, db: Session = Depends(get_db)):
    """Delete everything an organization stored and archive it (end of a pilot, or an erasure request).

    Irreversible. The organization must be suspended or terminated first and not under a legal hold; the
    administrator re-enters their password and a current authenticator code, types the organization's key and gives
    the reason
    (docs/runbooks/DATA_REQUESTS.md). The data is exported first unless a waiver reason is recorded. The database
    rows are deleted all-or-nothing; if the stored files or a dedicated database cannot then be removed, the
    organization stays PURGING and the response says what remains."""
    from auth.service import _verify
    from backend.app.tenant_purge import PurgeFailed, purge_tenant

    platform_admin = _require_platform_admin(request, db)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    if tenant.id == platform_admin.tenant_id:
        raise HTTPException(
            409, detail={"code": "OWN_ORGANIZATION", "message": "The operator organization cannot be deleted"}
        )
    if str(tenant.status).upper() not in {"SUSPENDED", "TERMINATED", "PURGING"}:
        raise HTTPException(
            409,
            detail={
                "code": "TENANT_NOT_SUSPENDED",
                "message": "Suspend or terminate the organization before deleting its data",
            },
        )
    if tenant.legal_hold:
        # The refusal is part of the hold's record: a reviewer sees that deletion was attempted and stopped.
        db.add(
            make_audit_event(
                tenant_id=tenant.id,
                actor_ref=str(platform_admin.id),
                action="TENANT_PURGE_REFUSED_LEGAL_HOLD",
                entity_type="Tenant",
                entity_id=tenant.id,
                request=request,
                reason=payload.reason.strip(),
                details={
                    "legal_hold_set_at": tenant.legal_hold_set_at.isoformat() if tenant.legal_hold_set_at else None
                },
            )
        )
        db.commit()
        raise HTTPException(
            409,
            detail={"code": "LEGAL_HOLD", "message": "This organization is under a legal hold; nothing can be deleted"},
        )
    if payload.confirm_tenant_key.strip() != tenant.tenant_key:
        raise HTTPException(
            422, detail={"code": "CONFIRMATION_MISMATCH", "message": "Type the organization's key exactly to confirm"}
        )
    actor = db.query(AuthUser).filter(AuthUser.id == platform_admin.id).first()
    if actor is None or not _verify(payload.password, actor.password_hash):
        raise HTTPException(
            403, detail={"code": "INVALID_REAUTHENTICATION", "message": "Your current password is required"}
        )
    confirm_with_authenticator(db, actor, payload.mfa_code, tenant_id=tenant.id, action="TENANT_PURGE", request=request)
    busy = (
        db.query(TenantExport)
        .filter(TenantExport.tenant_id == tenant_id, TenantExport.status.in_(["QUEUED", "RUNNING"]))
        .first()
    )
    if busy is not None:
        raise HTTPException(409, detail={"code": "EXPORT_IN_PROGRESS", "message": "Wait for the export to finish"})
    # Resuming a purge left PURGING: its export evidence is already in the erasure log, and the export rows it
    # pointed to were deleted with the rest of the organization's data, so the requirement is not asked again.
    resuming = str(tenant.status).upper() == "PURGING"
    evidence = None if resuming else export_evidence(db, tenant, payload.export_waiver_reason)
    try:
        result = purge_tenant(db, tenant_id, str(platform_admin.id), reason=payload.reason.strip(), evidence=evidence)
    except PurgeFailed as exc:
        if str(exc) == "LEGAL_HOLD":
            raise HTTPException(
                409, detail={"code": "LEGAL_HOLD", "message": "This organization is under a legal hold"}
            )
        raise HTTPException(
            409,
            detail={"code": "PURGE_INCOMPLETE", "message": f"Nothing was deleted: {exc}. See the server log."},
        )
    return {"tenant_id": str(tenant_id), "tenant_business_id": business_id_of(db, Tenant, tenant_id), **result}
