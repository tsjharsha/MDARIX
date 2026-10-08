"""Legal hold on an organization: while set, nothing of it is purged, erased or retired.

A customer, regulator or court may require an organization's data to be preserved (a recall investigation,
litigation). A platform administrator with a fully verified session records the hold with its reason; the purge
(backend/app/tenant_purge.py), personal-data erasure, trial retention (backend/app/trial/retention.py), completing an
unfinished purge and re-applying erasures after a restore then refuse until the hold is cleared. A refused purge
(``TENANT_PURGE_REFUSED_LEGAL_HOLD``) and a skipped trial retention run (``TRIAL_RETENTION_SKIPPED_LEGAL_HOLD``) are
recorded in the organization's audit trail. Setting and clearing are audited with the reason
(``LEGAL_HOLD_SET`` / ``LEGAL_HOLD_CLEARED``). Procedure: docs/runbooks/DATA_REQUESTS.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.cookies import read_session_token
from auth.durable import hash_token
from backend.app import mfa
from backend.app.access.authz import _require_platform_admin
from backend.app.business_ids import business_id_of
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event

router = APIRouter(prefix="/api/v1", tags=["Legal hold"])


class LegalHoldRequest(BaseModel):
    hold: bool
    # Who asked, the reference and the scope: this is the record the runbook relies on.
    reason: str = Field(min_length=10, max_length=2000)


def require_mfa_complete_session(request: Request, db: Session, user: AuthUser) -> AuthSession:
    """The caller's session has completed every sign-in step: the second factor is verified (sessions still owing it
    never get this far, but the check is explicit for operations that must not run on a half-signed-in session), and
    an administrator whose role must use MFA has enrolled."""
    token = read_session_token(request)
    row = (
        db.query(AuthSession)
        .filter(AuthSession.session_hash == hash_token(token or ""), AuthSession.revoked_at.is_(None))
        .first()
    )
    if row is None or row.mfa_state:
        raise HTTPException(
            403, detail={"code": "MFA_REQUIRED", "message": "Complete multi-factor authentication first"}
        )
    if mfa._normalize(user.role) in mfa.required_roles() and not mfa.is_enrolled(user):
        raise HTTPException(
            403,
            detail={"code": "MFA_ENROLLMENT_REQUIRED", "message": "Set up an authenticator app before this operation"},
        )
    return row


def legal_hold_summary(tenant: Tenant) -> dict:
    """The hold fields as the platform tenant screens show them (additive to the tenant record)."""
    return {
        "legal_hold": bool(tenant.legal_hold),
        "legal_hold_reason": tenant.legal_hold_reason,
        "legal_hold_set_at": tenant.legal_hold_set_at.isoformat() if tenant.legal_hold_set_at else None,
        "legal_hold_set_by": tenant.legal_hold_set_by,
    }


def set_legal_hold(
    db: Session, tenant: Tenant, *, hold: bool, reason: str, actor_ref: str, request: Request | None = None
) -> dict:
    """Set or clear the hold and audit it. Does not commit. Clearing a hold that is not set is refused, so a stray
    call never produces a misleading LEGAL_HOLD_CLEARED record; setting one that is already set records the new
    reason (for example a second requester for the same data)."""
    now = datetime.now(timezone.utc)
    if not hold and not tenant.legal_hold:
        raise HTTPException(409, detail={"code": "LEGAL_HOLD_NOT_SET", "message": "No legal hold is set"})
    before = legal_hold_summary(tenant)
    tenant.legal_hold = hold
    tenant.legal_hold_reason = reason if hold else None
    tenant.legal_hold_set_at = now if hold else None
    tenant.legal_hold_set_by = actor_ref if hold else None
    tenant.updated_at = now
    after = legal_hold_summary(tenant)
    db.add(
        make_audit_event(
            tenant_id=tenant.id,
            actor_ref=actor_ref,
            action="LEGAL_HOLD_SET" if hold else "LEGAL_HOLD_CLEARED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={"previous_reason": before["legal_hold_reason"]} if not hold else {},
            request=request,
            reason=reason,
            old_values=before,
            new_values=after,
            created_at=now,
        )
    )
    return after


def _identifiers(db: Session, tenant: Tenant) -> dict:
    """The organization's business identifier and that of the administrator who set the hold (response only: the
    audited hold fields stay those of ``legal_hold_summary``)."""
    return {
        "tenant_business_id": tenant.business_id,
        "legal_hold_set_by_business_id": business_id_of(db, AuthUser, tenant.legal_hold_set_by),
    }


def _tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    return tenant


@router.get("/platform-admin/tenants/{tenant_id}/legal-hold")
def get_legal_hold(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    tenant = _tenant(db, tenant_id)
    return {"tenant_id": str(tenant_id), **legal_hold_summary(tenant), **_identifiers(db, tenant)}


@router.put("/platform-admin/tenants/{tenant_id}/legal-hold")
def put_legal_hold(tenant_id: uuid.UUID, payload: LegalHoldRequest, request: Request, db: Session = Depends(get_db)):
    """Set (``hold: true``) or clear (``hold: false``) the organization's legal hold, with the reason."""
    admin = _require_platform_admin(request, db)
    require_mfa_complete_session(request, db, admin)
    tenant = _tenant(db, tenant_id)
    state = set_legal_hold(
        db, tenant, hold=payload.hold, reason=payload.reason.strip(), actor_ref=str(admin.id), request=request
    )
    db.commit()
    return {"tenant_id": str(tenant.id), **state, **_identifiers(db, tenant)}
