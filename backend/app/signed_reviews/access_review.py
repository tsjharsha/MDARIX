"""G14 periodic access review (B6a 5.3, owner D5).

One row per active user (MDARIX staff accounts are never listed to a customer): account role, the other roles held,
MFA on, last active, invited by and when, and the role and status changes since the last signed access review. A
customer administrator marks each row Keep, Change or Remove (an ``ACCESS_REVIEW_MARKED`` audit event; the latest mark
per person since the last signed review counts). Change and Remove are done with today's user administration routes
(audited as now); the review records what was decided. A reviewer's own row is marked by another administrator, or
by a Leader when the organization has only one administrator. Every row must be marked before the customer
administrator signs. Due every 90 days.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.models.stage2 import AuthSession, UserInvitation
from backend.app.signed_reviews.signing import error, signed_events

DUE_DAYS = 90
MARKS = ("KEEP", "CHANGE", "REMOVE")
MARKED = "ACCESS_REVIEW_MARKED"
CHANGE_ACTIONS = ("ROLE_GRANTED", "ROLE_REVOKED", "USER_STATUS_CHANGED", "USER_REACTIVATED", "USER_MFA_RESET")


def last_signed_at(control_db: Session, tenant_id) -> datetime | None:
    found = signed_events(control_db, tenant_id, "access", limit=1)
    return found[0].created_at if found else None


def active_users(control_db: Session, viewer: AuthUser) -> list[AuthUser]:
    from backend.app.access.authz import visible_user_filters

    return (
        control_db.query(AuthUser)
        .filter(AuthUser.tenant_id == viewer.tenant_id, AuthUser.status == "ACTIVE", *visible_user_filters(viewer))
        .order_by(AuthUser.username)
        .all()
    )


def administrators(users: list[AuthUser]) -> list[AuthUser]:
    from backend.app.role_codes import is_customer_admin_role

    return [user for user in users if is_customer_admin_role(user.role)]


def is_leader(control_db: Session, user: AuthUser) -> bool:
    from backend.app.access.permissions import normalize_role, roles_of_user

    return "LEADER" in {normalize_role(role) for role in roles_of_user(control_db, user)}


def marks(control_db: Session, tenant_id, since: datetime | None) -> dict[str, dict]:
    """user id -> the latest mark since the last signed review."""
    query = control_db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == MARKED)
    if since is not None:
        query = query.filter(AuditEvent.created_at > since)
    found: dict[str, dict] = {}
    for row in query.order_by(AuditEvent.created_at.asc(), AuditEvent.chain_seq.asc()):
        details = row.details or {}
        found[str(row.entity_id)] = {
            "mark": details.get("mark"),
            "note": row.reason,
            "by": row.actor_ref,
            "at": row.created_at.isoformat(),
        }
    return found


def rows(control_db: Session, viewer: AuthUser, now: datetime) -> dict:
    from backend.app.access.permissions import normalize_role, roles_of_user
    from backend.app.mfa import is_enrolled
    from backend.app.role_codes import role_label

    tenant_id = viewer.tenant_id
    since = last_signed_at(control_db, tenant_id)
    period_start = since or (now - timedelta(days=DUE_DAYS))
    users = active_users(control_db, viewer)
    ids = [user.id for user in users]
    last_seen = (
        dict(
            control_db.query(AuthSession.user_id, func.max(AuthSession.last_seen_at))
            .filter(AuthSession.tenant_id == tenant_id, AuthSession.user_id.in_(ids))
            .group_by(AuthSession.user_id)
        )
        if ids
        else {}
    )
    invited: dict = {}
    for user_id, by, at in (
        (
            control_db.query(UserInvitation.user_id, UserInvitation.created_by, UserInvitation.created_at)
            .filter(UserInvitation.tenant_id == tenant_id, UserInvitation.user_id.in_(ids))
            .order_by(UserInvitation.created_at.asc())
        )
        if ids
        else []
    ):
        invited.setdefault(user_id, (by, at))
    changes: dict[str, list] = {}
    for row in (
        control_db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_type == "AuthUser",
            AuditEvent.action.in_(CHANGE_ACTIONS),
            AuditEvent.created_at > period_start,
        )
        .order_by(AuditEvent.created_at.asc())
    ):
        changes.setdefault(str(row.entity_id), []).append(
            {
                "action": row.action,
                "role": (row.details or {}).get("role"),
                "old": row.old_values,
                "new": row.new_values,
                "by": row.actor_ref,
                "at": row.created_at.isoformat(),
            }
        )
    marked = marks(control_db, tenant_id, since)
    listed = []
    for user in users:
        held = roles_of_user(control_db, user)
        base = normalize_role(user.role)
        by, at = invited.get(user.id, (None, None))
        seen = last_seen.get(user.id)
        listed.append(
            {
                "user_id": str(user.id),
                "business_id": user.business_id,
                "name": user.display_name,
                "email": user.username,
                "role": user.role,
                "role_label": role_label(user.role),
                "other_roles": [role_label(role) for role in held if normalize_role(role) != base],
                "mfa_on": is_enrolled(user),
                "last_active": seen.isoformat() if seen else None,
                "invited_by": str(by) if by else None,
                "invited_at": at.isoformat() if at else None,
                "changes": changes.get(str(user.id), []),
                "mark": marked.get(str(user.id)),
            }
        )
    return {
        "since": since.isoformat() if since else None,
        "next_due": ((since + timedelta(days=DUE_DAYS)).date().isoformat() if since else now.date().isoformat()),
        "administrators": len(administrators(users)),
        "rows": listed,
        "unmarked": sum(1 for row in listed if not row["mark"]),
    }


def check_marker(control_db: Session, marker: AuthUser, target: AuthUser, users: list[AuthUser]) -> str:
    """Who may mark this row (D5). Returns the marker's role for the record; raises 403 otherwise."""
    from backend.app.role_codes import is_customer_admin_role

    if marker.id == target.id:
        raise error(
            403,
            "OWN_ROW",
            "Another administrator marks your own row (a Leader when you are the only administrator)",
        )
    if is_customer_admin_role(marker.role):
        return "CUSTOMER_ADMIN"
    admins = administrators(users)
    if is_leader(control_db, marker) and len(admins) == 1 and admins[0].id == target.id:
        return "LEADER"
    raise error(
        403,
        "ACCESS_REVIEW_MARK_REFUSED",
        "A customer administrator marks the rows; a Leader marks only the only administrator's own row",
    )


def check_ready_to_sign(review: dict, signer: AuthUser) -> None:
    if review["unmarked"]:
        raise error(409, "ROWS_UNMARKED", f"Mark every row before signing: {review['unmarked']} not marked yet")
    for row in review["rows"]:
        if row["user_id"] == str(signer.id) and row["mark"]["by"] == str(signer.id):
            raise error(403, "OWN_ROW", "Your own row must be marked by another person")


def target_of(users: list[AuthUser], user_id: uuid.UUID) -> AuthUser:
    for user in users:
        if user.id == user_id:
            return user
    raise error(404, "USER_NOT_FOUND", "No such active user in your organization")
