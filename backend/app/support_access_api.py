"""The customer's side of support access (ADR-015, backend/app/support_access.py).

A Customer Administrator sees every request MDARIX approved for their organization: who would get access, to what,
whether changes are allowed, why and until when. They approve it (with their authenticator code: consent to data
access is as strong as a signature), deny it, or revoke it at any time, and see every use made of it, as recorded in
their own audit trail. Platform administrators cannot decide for a customer, even in an organization they belong to.

A free trial has no Customer Administrators: there its owner decides, from Getting started › Team
(backend/app/trial/router.py), through the same functions below and with the same rules (an authenticator code to
approve, a reason for every decision, the same audit events, marked with the source TRIAL_OWNER). Who may decide is
checked in one place for both routes (:func:`require_decision_maker`): in a free trial its owner and nobody else (a
colleague, or any Customer Administrator account in a trial, is refused); elsewhere a Customer Administrator.

The decision makers are emailed when MDARIX asks, when they approve (a confirmation that also says when it ends) and
when an approved access ends early or on its own (backend/app/notifications.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app import support_access as access
from backend.app.access.authz import _authenticated_user
from backend.app.db.models.customer_lifecycle import SupportAccessGrant
from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.role_codes import is_customer_admin_role
from backend.app.tenant_export_api import confirm_with_authenticator

router = APIRouter(prefix="/api/v1", tags=["Support access"])

DECISIONS = {
    "SUPPORT_ACCESS_REQUESTED",
    "SUPPORT_ACCESS_APPROVED",
    "SUPPORT_ACCESS_CUSTOMER_APPROVED",
    "SUPPORT_ACCESS_DENIED",
    "SUPPORT_ACCESS_REVOKED",
    access.ACCESS_USED,
    access.ACCESS_EXPIRED,
}


class CustomerApproval(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    # The approving administrator's current authenticator code (confirm_with_authenticator).
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)


class CustomerDecision(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


def _customer_admin(request: Request, db: Session) -> AuthUser:
    user = _authenticated_user(request, db)
    if not is_customer_admin_role(user.role):
        raise HTTPException(
            403,
            detail={
                "code": "CUSTOMER_ADMIN_REQUIRED",
                "message": "Only the organization's Customer Administrators decide on support access",
            },
        )
    return user


def require_decision_maker(db: Session, user: AuthUser) -> None:
    """Who decides on support access to ``user``'s organization: in a free trial its owner only (a trial has no
    Customer Administrators, and its colleagues never decide); in any other organization one of its Customer
    Administrators. Every approval, denial and revocation passes here, whichever route it came through."""
    from backend.app.trial.service import trial_subscription
    from backend.app.trial.team import require_owner

    if trial_subscription(db, user.tenant_id) is not None:
        require_owner(db, user.tenant_id, user, "Only the person who started this trial decides on support access")
        return
    if not is_customer_admin_role(user.role):
        raise HTTPException(
            403,
            detail={
                "code": "CUSTOMER_ADMIN_REQUIRED",
                "message": "Only the organization's Customer Administrators decide on support access",
            },
        )


def _grant(db: Session, admin: AuthUser, grant_id: uuid.UUID, *, lock: bool = True) -> SupportAccessGrant:
    query = db.query(SupportAccessGrant).filter(
        SupportAccessGrant.id == grant_id,
        SupportAccessGrant.tenant_id == admin.tenant_id,
        # Only what MDARIX approved reaches the customer; a request still inside MDARIX is not theirs to see.
        SupportAccessGrant.approved_at.isnot(None),
    )
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "SUPPORT_ACCESS_NOT_FOUND", "message": "Support access request is not available"}
        )
    return row


def _people(db: Session, ids) -> dict[str, dict]:
    wanted = [value for value in ids if value]
    if not wanted:
        return {}
    rows = db.query(AuthUser).filter(AuthUser.id.in_(wanted)).all()
    return {str(row.id): {"name": row.display_name or row.username, "email": row.username} for row in rows}


def _uses(db: Session, tenant_id, grant_ids) -> dict[str, dict]:
    if not grant_ids:
        return {}
    rows = (
        db.query(AuditEvent.entity_id, func.count(AuditEvent.id), func.max(AuditEvent.created_at))
        .filter(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.action == access.ACCESS_USED,
            AuditEvent.entity_id.in_(grant_ids),
        )
        .group_by(AuditEvent.entity_id)
        .all()
    )
    return {str(grant_id): {"count": count, "last": last} for grant_id, count, last in rows}


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def describe(row: SupportAccessGrant, people: dict, uses: dict, now: datetime) -> dict:
    """A grant as its organization's administrators read it."""
    scope = access.SupportScope.stored(row.scope)
    recipient = people.get(str(row.platform_user_id), {})
    use = uses.get(str(row.id), {})
    awaiting = row.status == access.AWAITING_CUSTOMER and access._aware(row.expires_at) > now
    is_open = row.status in {access.AWAITING_CUSTOMER, access.APPROVED} and access._aware(row.expires_at) > now
    return {
        "id": str(row.id),
        "status": row.status,
        "person": recipient.get("name"),
        "person_email": recipient.get("email"),
        "requested_by": people.get(str(row.requested_by), {}).get("name"),
        "approved_for_mdarix_by": people.get(str(row.approved_by), {}).get("name"),
        "reason": row.reason,
        "areas": scope.describe(),
        "write": scope.write,
        "starts_at": _iso(row.starts_at),
        "expires_at": _iso(row.expires_at),
        "decided_by": people.get(str(row.customer_decided_by), {}).get("name"),
        "decided_at": _iso(row.customer_decided_at),
        "decision_reason": row.customer_decision_reason,
        "revoked_at": _iso(row.revoked_at),
        "uses": use.get("count", 0),
        "last_used_at": _iso(use.get("last")),
        "can_approve": awaiting and bool(scope.areas),
        "can_deny": awaiting,
        "can_revoke": is_open,
    }


CUSTOMER_ADMIN = "CUSTOMER_ADMIN"


def _audit(
    db: Session,
    admin: AuthUser,
    row: SupportAccessGrant,
    action: str,
    reason: str,
    request,
    details=None,
    source: str = CUSTOMER_ADMIN,
):
    db.add(
        make_audit_event(
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action=action,
            entity_type="SupportAccessGrant",
            entity_id=row.id,
            details={"source": source, **(details or {})},
            reason=reason,
            request=request,
        )
    )


@router.get("/admin/support-access")
def list_support_access(request: Request, db: Session = Depends(get_db)):
    """Every request MDARIX approved for this organization, newest first, and how many waits for a decision."""
    admin = _customer_admin(request, db)
    require_decision_maker(db, admin)
    return grants_of(db, admin.tenant_id)


def grants_of(db: Session, tenant_id) -> dict:
    """Every request MDARIX approved for ``tenant_id``, as its decision makers read them (expired ones closed first;
    commits)."""
    access.expire(db, tenant_id)
    db.commit()
    rows = (
        db.query(SupportAccessGrant)
        .filter(SupportAccessGrant.tenant_id == tenant_id, SupportAccessGrant.approved_at.isnot(None))
        .order_by(SupportAccessGrant.created_at.desc())
        .limit(200)
        .all()
    )
    people = _people(
        db,
        {
            value
            for row in rows
            for value in (row.platform_user_id, row.requested_by, row.approved_by, row.customer_decided_by)
        },
    )
    uses = _uses(db, tenant_id, [row.id for row in rows])
    now = datetime.now(timezone.utc)
    items = [describe(row, people, uses, now) for row in rows]
    return {
        "items": items,
        "awaiting_decision": sum(1 for item in items if item["can_approve"] or item["can_deny"]),
        "areas": [{"code": code, "label": label} for code, label in access.AREAS.items()],
    }


def _decided(db: Session, admin: AuthUser, row: SupportAccessGrant) -> dict:
    people = _people(db, {row.platform_user_id, row.requested_by, row.approved_by, row.customer_decided_by})
    return describe(row, people, _uses(db, admin.tenant_id, [row.id]), datetime.now(timezone.utc))


def _awaiting(row: SupportAccessGrant, now: datetime) -> None:
    if row.status != access.AWAITING_CUSTOMER or access._aware(row.expires_at) <= now:
        raise HTTPException(
            409,
            detail={
                "code": "SUPPORT_ACCESS_NOT_AWAITING",
                "message": "This request is no longer waiting for a decision (decided, revoked or expired)",
            },
        )


def approve_grant(
    db: Session, admin: AuthUser, grant_id: uuid.UUID, reason: str, mfa_code: str | None, request, source: str
) -> dict:
    """The organization's approval (one of its Customer Administrators, or a trial's owner): with a current
    authenticator code, for a request MDARIX approved that names at least one area and is still inside its window."""
    from backend.app.notifications import notify_support_access_granted

    require_decision_maker(db, admin)
    row = _grant(db, admin, grant_id)
    now = datetime.now(timezone.utc)
    _awaiting(row, now)
    if not access.SupportScope.stored(row.scope).areas:
        raise HTTPException(
            409,
            detail={
                "code": "SUPPORT_SCOPE_EMPTY",
                "message": "This request names no area of your data: deny it, and MDARIX can ask again",
            },
        )
    confirm_with_authenticator(
        db, admin, mfa_code, tenant_id=admin.tenant_id, action="SUPPORT_ACCESS_APPROVE", request=request
    )
    row.status = access.APPROVED
    row.customer_decided_by = admin.id
    row.customer_decided_at = now
    row.customer_decision_reason = reason.strip()
    row.updated_at = now
    _audit(
        db,
        admin,
        row,
        "SUPPORT_ACCESS_CUSTOMER_APPROVED",
        row.customer_decision_reason,
        request,
        {**access.SupportScope.stored(row.scope).as_dict(), "expires_at": row.expires_at.isoformat()},
        source=source,
    )
    notify_support_access_granted(db, admin.tenant_id, grant_id=row.id)
    db.commit()
    return _decided(db, admin, row)


def deny_grant(db: Session, admin: AuthUser, grant_id: uuid.UUID, reason: str, request, source: str) -> dict:
    require_decision_maker(db, admin)
    row = _grant(db, admin, grant_id)
    now = datetime.now(timezone.utc)
    _awaiting(row, now)
    row.status = access.DENIED
    row.customer_decided_by = admin.id
    row.customer_decided_at = now
    row.customer_decision_reason = reason.strip()
    row.updated_at = now
    _audit(db, admin, row, "SUPPORT_ACCESS_DENIED", row.customer_decision_reason, request, source=source)
    db.commit()
    return _decided(db, admin, row)


def revoke_grant(db: Session, admin: AuthUser, grant_id: uuid.UUID, reason: str, request, source: str) -> dict:
    """End a request or an approved access at once, whatever its window says. Ending an approved access is emailed
    to the decision makers (the one who revoked it included: it is also a security notice)."""
    from backend.app.notifications import notify_support_access_ended

    require_decision_maker(db, admin)
    row = _grant(db, admin, grant_id)
    now = datetime.now(timezone.utc)
    if row.status not in {access.AWAITING_CUSTOMER, access.APPROVED} or access._aware(row.expires_at) <= now:
        raise HTTPException(
            409,
            detail={"code": "SUPPORT_ACCESS_NOT_OPEN", "message": "This access has already ended"},
        )
    was_active = row.status == access.APPROVED
    row.status = access.REVOKED
    row.revoked_at = now
    row.revoked_by = admin.id
    row.updated_at = now
    _audit(db, admin, row, "SUPPORT_ACCESS_REVOKED", reason.strip(), request, source=source)
    if was_active:
        notify_support_access_ended(db, admin.tenant_id, grant_id=row.id, ended="REVOKED_BY_CUSTOMER")
    db.commit()
    return _decided(db, admin, row)


@router.post("/admin/support-access/{grant_id}/approve")
def approve_support_access(
    grant_id: uuid.UUID, payload: CustomerApproval, request: Request, db: Session = Depends(get_db)
):
    admin = _customer_admin(request, db)
    return approve_grant(db, admin, grant_id, payload.reason, payload.mfa_code, request, CUSTOMER_ADMIN)


@router.post("/admin/support-access/{grant_id}/deny")
def deny_support_access(
    grant_id: uuid.UUID, payload: CustomerDecision, request: Request, db: Session = Depends(get_db)
):
    admin = _customer_admin(request, db)
    return deny_grant(db, admin, grant_id, payload.reason, request, CUSTOMER_ADMIN)


@router.post("/admin/support-access/{grant_id}/revoke")
def revoke_support_access(
    grant_id: uuid.UUID, payload: CustomerDecision, request: Request, db: Session = Depends(get_db)
):
    """End a request or an approved access at once, whatever its window says."""
    admin = _customer_admin(request, db)
    return revoke_grant(db, admin, grant_id, payload.reason, request, CUSTOMER_ADMIN)


@router.get("/admin/support-access/{grant_id}/activity")
def support_access_activity(grant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """The life of one grant, from the organization's own audit trail: the request, MDARIX's approval, the
    customer's decision, and every use of the access (what was opened, when, by whom)."""
    admin = _customer_admin(request, db)
    require_decision_maker(db, admin)
    return grant_activity(db, admin, grant_id)


def grant_activity(db: Session, admin: AuthUser, grant_id: uuid.UUID) -> dict:
    """One grant's life in ``admin``'s organization's audit trail (for its Customer Administrators, or a trial's
    owner): the request, MDARIX's approval, the decision, every use (each page read, each export) and its end."""
    row = _grant(db, admin, grant_id, lock=False)
    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == admin.tenant_id,
            AuditEvent.entity_type == "SupportAccessGrant",
            AuditEvent.entity_id == row.id,
            AuditEvent.action.in_(sorted(DECISIONS)),
        )
        .order_by(AuditEvent.chain_seq)
        .limit(500)
        .all()
    )
    people = _people(db, {uuid.UUID(event.actor_ref) for event in events if _is_uuid(event.actor_ref)})
    covers = scope_text(access.SupportScope.stored(row.scope))
    return {
        "grant_id": str(row.id),
        "items": [
            {
                "at": _iso(event.created_at),
                "action": event.action,
                "who": people.get(str(event.actor_ref), {}).get("name") or _someone(event.actor_ref),
                "what": _what(event),
                "area": (event.details or {}).get("area"),
                "write": (event.details or {}).get("write"),
                "method": (event.details or {}).get("method"),
                "path": (event.details or {}).get("path"),
                "reason": event.reason or (event.details or {}).get("reason"),
                # What was asked for and approved, in the words of the decision (read-only wording when read-only).
                "covers": covers if event.action in _COVERS else None,
            }
            for event in events
        ],
    }


# What a use of the access opened, in the words the organization reads (the support workspace's pages and the export;
# support_workspace.py). Any other address is named by its area.
_USE_PAGES = {
    "complaints": "Read the complaints",
    "investigations": "Read the investigations",
    "decisions": "Read the decisions",
    "imports": "Read the data imports",
    "team": "Read the team",
    "audit": "Read the audit trail",
}
_ACTIONS = {
    "SUPPORT_ACCESS_REQUESTED": "MDARIX asked for access",
    "SUPPORT_ACCESS_APPROVED": "Approved inside MDARIX",
    "SUPPORT_ACCESS_CUSTOMER_APPROVED": "Access approved",
    "SUPPORT_ACCESS_DENIED": "Request denied",
    "SUPPORT_ACCESS_REVOKED": "Access revoked",
    access.ACCESS_EXPIRED: "Access ended on its own",
}


_COVERS = frozenset({"SUPPORT_ACCESS_REQUESTED", "SUPPORT_ACCESS_CUSTOMER_APPROVED"})


def scope_text(scope: access.SupportScope) -> str:
    """A grant's scope in one line: "Read only. Audit trail: ...; People: the user directory, to read"."""
    areas = "; ".join(item["label"] for item in scope.describe()) or "no area"
    return f"{'Read and change' if scope.write else 'Read only'}. {areas}"


def _what(event: AuditEvent) -> str:
    if event.action != access.ACCESS_USED:
        return _ACTIONS.get(event.action, event.action)
    details = event.details or {}
    path = str(details.get("path") or "").rstrip("/")
    last = path.rsplit("/", 1)[-1]
    if "/support-workspace" in path:
        return _USE_PAGES.get(last, "Opened the read-only workspace")
    if path.endswith("/download"):
        return "Downloaded a full export"
    if path.endswith("/exports"):
        return "Asked for a full export"
    area = access.AREAS.get(str(details.get("area") or ""), "")
    label = area.split(":")[0] if area else "the data"
    return f"{'Changed' if details.get('write') else 'Read'}: {label.lower()}"


def _someone(actor_ref) -> str:
    """Who did it, when their account is not one the organization can read: MDARIX staff accounts live in the
    platform's organization, so a customer's session reads them as "MDARIX support", never as an account id."""
    if str(actor_ref or "").startswith("system:"):
        return "MDARIX (automatic)"
    return "MDARIX support" if _is_uuid(actor_ref) else str(actor_ref or "")


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False
