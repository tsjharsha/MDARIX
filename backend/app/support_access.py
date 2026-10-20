"""Customer-approved support access: the only way MDARIX staff reach an organization's data (ADR-015).

Platform administrators run the platform: customers, organizations, plans, onboarding, the fleet. An organization's
own data (its products and integrations, its audit trail, its people, a copy of its records) belongs to the
customer. MDARIX staff see or change it only under a **support grant the customer approved**:

1. A platform administrator requests access for a named colleague: which organization, which *areas*, whether
   changes are allowed, why, and for how long (at most 24 hours).
2. A *different* platform administrator approves it for MDARIX (neither the requester nor the recipient: P1).
3. The organization's Customer Administrators are told, and one of them approves it with their authenticator code,
   or denies it. Either side can revoke it at any time; it expires on its own.

Every platform route that reaches an organization's data calls :func:`require_customer_approved_access`. Without a
grant that is approved by the customer, inside its window, for this colleague, covering the area (and changes, when
the route changes something), the request is refused (403 ``CUSTOMER_APPROVAL_REQUIRED``) and the refusal is written
to the organization's own audit trail. With one, the access is written there too (``SUPPORT_ACCESS_USED``), so the
customer sees every use of the access they granted.

Not behind a grant, by design: the platform's own organization; the platform's records about an organization
(registry, lifecycle, plan, subscription, usage counts); legal hold and the final purge (lifecycle duties with their
own safeguards); problem reports a customer chose to send to MDARIX; what MDARIX staff themselves did inside an
organization (staff accountability); and the continuity cases where nobody in the organization could act:
recovering the only active Customer Administrator's authenticator, activating the first one, and recovering the
authenticator of a free trial's people (a trial has no administrator; backend/app/access/platform_customer_admins.py).
In a free trial, its owner (and only its owner) decides on support access in place of a Customer Administrator
(support_access_api.py ``require_decision_maker``). What a grant opens is read through platform routes that call
:func:`require_customer_approved_access`, among them the read-only support workspace (support_workspace.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from backend.app.db.models.customer_lifecycle import SupportAccessGrant
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant

# ------------------------------------------------------------------------------------------- vocabulary

CONFIGURATION = "CONFIGURATION"
AUDIT = "AUDIT"
PEOPLE = "PEOPLE"
RECORDS = "RECORDS"
DATA_EXPORT = "DATA_EXPORT"

#: What a customer can grant, in the words their administrators read when they decide.
AREAS: dict[str, str] = {
    CONFIGURATION: "Configuration: products and versions, integrations, data mappings and AI settings",
    AUDIT: "Audit trail: everything people and systems did in the organization",
    PEOPLE: "People: the user directory, account recovery and erasure of personal data",
    RECORDS: "Quality records: complaints, investigations, decisions and data imports, to read",
    DATA_EXPORT: "A full export: a copy of every record of the organization",
}

PENDING = "PENDING"  # requested; a second platform administrator approves it for MDARIX
AWAITING_CUSTOMER = "AWAITING_CUSTOMER"  # approved by MDARIX; the customer decides
APPROVED = "APPROVED"  # approved by the customer: usable inside its window
DENIED = "DENIED"  # the customer said no
REVOKED = "REVOKED"  # ended early by either side
EXPIRED = "EXPIRED"  # its window passed
OPEN = frozenset({PENDING, AWAITING_CUSTOMER, APPROVED})

ACCESS_USED = "SUPPORT_ACCESS_USED"
ACCESS_REFUSED = "SUPPORT_ACCESS_REFUSED"
# An approved grant whose window passed (the scheduler's support-access-expiry, or the next list that reads it).
ACCESS_EXPIRED = "SUPPORT_ACCESS_EXPIRED"
# Repeated reads of the same page under the same grant within this window are recorded once: paging through a list
# (or the audit trail itself, where every recorded read would shift the pages being read) is one use, not ten.
# Changes (write) are always recorded.
READ_USE_WINDOW = timedelta(minutes=10)


class ScopeInvalid(ValueError):
    """A requested scope names no area, an unknown area, or an unknown setting."""


@dataclass(frozen=True)
class SupportScope:
    """The areas a grant covers, and whether it allows changes there (otherwise it is read-only)."""

    areas: frozenset[str]
    write: bool = False

    @classmethod
    def parse(cls, raw: dict | None) -> "SupportScope":
        """A scope as a platform administrator requests it: ``{"areas": [...], "write": false}``, strictly."""
        if not isinstance(raw, dict):
            raise ScopeInvalid("The scope must name the areas requested")
        unknown_keys = set(raw) - {"areas", "write"}
        if unknown_keys:
            raise ScopeInvalid(f"Unknown scope setting(s): {', '.join(sorted(unknown_keys))}")
        areas = raw.get("areas")
        if not isinstance(areas, list) or not areas or not all(isinstance(item, str) for item in areas):
            raise ScopeInvalid(f"Name at least one area: {', '.join(AREAS)}")
        normalized = {item.strip().upper() for item in areas}
        unknown = normalized - set(AREAS)
        if unknown:
            raise ScopeInvalid(f"Unknown area(s): {', '.join(sorted(unknown))}; the areas are {', '.join(AREAS)}")
        write = raw.get("write", False)
        if not isinstance(write, bool):
            raise ScopeInvalid("write must be true or false")
        return cls(frozenset(normalized), write)

    @classmethod
    def stored(cls, raw) -> "SupportScope":
        """The scope of a stored grant, leniently: a grant from before areas existed covers nothing."""
        try:
            return cls.parse(raw)
        except ScopeInvalid:
            return cls(frozenset(), False)

    def allows(self, area: str, *, write: bool = False) -> bool:
        return area in self.areas and (self.write or not write)

    def as_dict(self) -> dict:
        return {"areas": sorted(self.areas), "write": self.write}

    def describe(self) -> list[dict]:
        """The areas as the customer reads them, in the order of AREAS."""
        return [{"code": code, "label": label} for code, label in AREAS.items() if code in self.areas]


# ------------------------------------------------------------------------------------------- decisions


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def evaluate(grant, *, platform_user_id, tenant_id, area: str, write: bool, now: datetime) -> str:
    """Why ``grant`` does or does not open ``area`` of ``tenant_id`` to ``platform_user_id`` at ``now``:
    ``ALLOWED``, or the first reason it does not. Pure: the rule in one place, and tested on its own."""
    if grant is None:
        return "NO_GRANT"
    if str(grant.tenant_id) != str(tenant_id) or str(grant.platform_user_id) != str(platform_user_id):
        return "NOT_THIS_GRANT"
    if grant.status != APPROVED or getattr(grant, "customer_decided_by", None) is None:
        return "NOT_APPROVED_BY_CUSTOMER"
    starts, expires = _aware(grant.starts_at), _aware(grant.expires_at)
    if starts and now < starts:
        return "NOT_YET_STARTED"
    if expires is None or now >= expires:
        return "EXPIRED"
    scope = SupportScope.stored(grant.scope)
    if area not in scope.areas:
        return "AREA_NOT_GRANTED"
    if write and not scope.write:
        return "READ_ONLY"
    return "ALLOWED"


def platform_tenant_id(db: Session):
    """The platform's own organization (where MDARIX staff accounts live): never behind a grant."""
    from backend.app.auth_router import PLATFORM_TENANT_KEY

    row = db.query(Tenant.id).filter(Tenant.tenant_key == PLATFORM_TENANT_KEY).first()
    return row[0] if row else None


def _usable(db: Session, platform_user_id, now: datetime):
    """The customer-approved grants of one colleague that are inside their window right now."""
    return db.query(SupportAccessGrant).filter(
        SupportAccessGrant.platform_user_id == platform_user_id,
        SupportAccessGrant.status == APPROVED,
        SupportAccessGrant.customer_decided_by.isnot(None),
        SupportAccessGrant.starts_at <= now,
        SupportAccessGrant.expires_at > now,
    )


def find_grant(db: Session, user: AuthUser, tenant_id, area: str, *, write: bool = False, now=None):
    """The grant that lets ``user`` reach ``area`` of ``tenant_id`` now (the longest-running one), or None."""
    now = now or datetime.now(timezone.utc)
    candidates = _usable(db, user.id, now).filter(SupportAccessGrant.tenant_id == tenant_id).all()
    usable = [
        grant
        for grant in candidates
        if evaluate(grant, platform_user_id=user.id, tenant_id=tenant_id, area=area, write=write, now=now) == "ALLOWED"
    ]
    return max(usable, key=lambda grant: _aware(grant.expires_at), default=None)


def _grants_by_tenant(db: Session, user: AuthUser, area: str, *, write: bool, now: datetime, within=None) -> dict:
    """For each organization (of ``within``, when given) whose ``area`` ``user`` may reach now, the grant that opens
    it (the longest-running one)."""
    chosen: dict = {}
    for grant in _usable(db, user.id, now).all():
        if within is not None and grant.tenant_id not in within:
            continue
        verdict = evaluate(grant, platform_user_id=user.id, tenant_id=grant.tenant_id, area=area, write=write, now=now)
        if verdict != "ALLOWED":
            continue
        current = chosen.get(grant.tenant_id)
        if current is None or _aware(grant.expires_at) > _aware(current.expires_at):
            chosen[grant.tenant_id] = grant
    return chosen


def granted_tenant_ids(db: Session, user: AuthUser, area: str, *, write: bool = False, now=None) -> set:
    """Every organization whose ``area`` ``user`` may reach now: those the customer granted, and the platform's own.
    A check only; a route that shows the data uses :func:`open_tenants`, which records the use."""
    now = now or datetime.now(timezone.utc)
    own = platform_tenant_id(db)
    return set(_grants_by_tenant(db, user, area, write=write, now=now)) | ({own} if own else set())


def open_tenants(
    db: Session, user: AuthUser, area: str, *, within=None, write: bool = False, request: Request | None = None
) -> set:
    """The organizations a list may show ``area`` of: the platform's own, and each one whose customer granted it;
    the use is recorded in each granted organization's audit trail (committed). ``within`` limits the candidates
    (for example the organizations of one customer). Organizations not returned are simply left out of the list."""
    now = datetime.now(timezone.utc)
    candidates = set(within) if within is not None else None
    grants = _grants_by_tenant(db, user, area, write=write, now=now, within=candidates)
    recorded = False
    for tenant_id, grant in grants.items():
        recorded |= _record_use(
            db, tenant_id=tenant_id, user=user, grant=grant, area=area, write=write, request=request
        )
    if recorded:
        db.commit()
    own = platform_tenant_id(db)
    include_own = own is not None and (candidates is None or own in candidates)
    return set(grants) | ({own} if include_own else set())


def _path(request: Request | None) -> str | None:
    return request.url.path if request is not None else None


def _record_use(db: Session, *, tenant_id, user: AuthUser, grant, area: str, write: bool, request) -> bool:
    """Record a use of ``grant`` in the organization's audit trail; False when it is a repeated read of the same page
    within :data:`READ_USE_WINDOW` (already recorded). The caller commits."""
    path = _path(request)
    if not write:
        since = datetime.now(timezone.utc) - READ_USE_WINDOW
        same_path = (
            AuditEvent.details["path"].astext.is_(None) if path is None else AuditEvent.details["path"].astext == path
        )
        repeated = (
            db.query(AuditEvent.id)
            .filter(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action == ACCESS_USED,
                AuditEvent.actor_ref == str(user.id),
                AuditEvent.entity_id == grant.id,
                AuditEvent.created_at >= since,
                AuditEvent.details["area"].astext == area,
                AuditEvent.details["write"].astext == "false",
                same_path,
            )
            .first()
        )
        if repeated is not None:
            return False
    _record(
        db,
        tenant_id=tenant_id,
        user=user,
        action=ACCESS_USED,
        grant_id=grant.id,
        details={
            "grant_id": str(grant.id),
            "area": area,
            "write": write,
            "method": request.method if request is not None else None,
            "path": path,
        },
        request=request,
    )
    return True


def _record(db: Session, *, tenant_id, user: AuthUser, action: str, grant_id, details: dict, request) -> None:
    from backend.app.enterprise_audit import make_audit_event

    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(user.id),
            action=action,
            entity_type="SupportAccessGrant",
            entity_id=grant_id,
            details={"source": "PLATFORM_ADMIN", **details},
            request=request,
            created_at=datetime.now(timezone.utc),
        )
    )


def require_customer_approved_access(
    db: Session, user: AuthUser, tenant_id, area: str, *, write: bool = False, request: Request | None = None
):
    """Refuse unless ``user`` holds a customer-approved grant for ``area`` of ``tenant_id`` (changes too, when
    ``write``); record the use or the refusal in the organization's audit trail, committed either way.

    Returns the grant used, or None for the platform's own organization. Call it once per request, before the route
    reads or stages anything: it commits."""
    if area not in AREAS:
        raise ValueError(f"Unknown support access area {area}")
    if tenant_id is None or db.get(Tenant, tenant_id) is None:
        # Before anything is recorded: an audit event must name an organization that exists.
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    if str(tenant_id) == str(platform_tenant_id(db)):
        return None
    now = datetime.now(timezone.utc)
    grant = find_grant(db, user, tenant_id, area, write=write, now=now)
    method = request.method if request is not None else None
    if grant is None:
        _record(
            db,
            tenant_id=tenant_id,
            user=user,
            action=ACCESS_REFUSED,
            grant_id=None,
            details={"area": area, "write": write, "method": method, "path": _path(request)},
            request=request,
        )
        db.commit()
        raise HTTPException(
            403,
            detail={
                "code": "CUSTOMER_APPROVAL_REQUIRED",
                "message": (
                    "This is the customer's data. It needs support access the customer approved: "
                    f"{AREAS[area].split(':')[0].lower()}{', with changes' if write else ''}. "
                    "Request it under Security > Support access."
                ),
                "area": area,
                "write": write,
            },
        )
    if _record_use(db, tenant_id=tenant_id, user=user, grant=grant, area=area, write=write, request=request):
        db.commit()
    return grant


# ------------------------------------------------------------------------------------------- audit visibility


def staff_actor_refs():
    """SQL: the ids of MDARIX staff accounts, as audit events store their actor."""
    from backend.app.access.authz import platform_account_clause

    return select(cast(AuthUser.id, String)).where(platform_account_clause())


def visible_audit_clause(opened: set):
    """Which audit events a platform administrator reads: those of the organizations ``opened`` for Audit (the
    platform's own, and those whose customer granted it: :func:`open_tenants`), and, anywhere, what MDARIX staff
    themselves did (staff accountability: their own actions are never hidden from the platform)."""
    return or_(AuditEvent.tenant_id.in_(sorted(opened, key=str)), AuditEvent.actor_ref.in_(staff_actor_refs()))


def _by_staff(db: Session, event: AuditEvent) -> bool:
    from backend.app.access.authz import _is_platform_role

    try:
        actor = db.get(AuthUser, uuid.UUID(str(event.actor_ref))) if event.actor_ref else None
    except ValueError:
        actor = None
    return actor is not None and _is_platform_role(actor.role)


def require_audit_event_access(db: Session, user: AuthUser, event: AuditEvent, request: Request | None = None) -> None:
    """One audit event: the platform's own and staff's own are open; any other needs the customer's Audit grant."""
    if str(event.tenant_id) == str(platform_tenant_id(db)) or _by_staff(db, event):
        return
    require_customer_approved_access(db, user, event.tenant_id, AUDIT, request=request)


# ------------------------------------------------------------------------------------------- continuity


def other_active_customer_admins(db: Session, tenant_id, *, excluding=None) -> int:
    """How many active Customer Administrators of the organization could act themselves (other than ``excluding``)."""
    from sqlalchemy import func

    normalized = func.upper(func.replace(func.trim(func.coalesce(AuthUser.role, "")), " ", "_"))
    query = db.query(func.count(AuthUser.id)).filter(
        AuthUser.tenant_id == tenant_id, normalized == "CUSTOMER_ADMIN", func.upper(AuthUser.status) == "ACTIVE"
    )
    if excluding is not None:
        query = query.filter(AuthUser.id != excluding)
    return int(query.scalar() or 0)


def require_people_access(db: Session, user: AuthUser, target: AuthUser, *, continuity: bool, request=None):
    """Acting on an organization's person: MDARIX staff accounts are the platform's own; a Customer Administrator
    nobody else in the organization could help (``continuity``: the only active one, or the first one not yet
    activated) is MDARIX's to recover; everyone else needs PEOPLE access with changes, approved by the customer."""
    from backend.app.access.authz import _is_platform_role
    from backend.app.role_codes import is_customer_admin_role

    if _is_platform_role(target.role):
        return None
    if continuity and is_customer_admin_role(target.role):
        if other_active_customer_admins(db, target.tenant_id, excluding=target.id) == 0:
            return None
    return require_customer_approved_access(db, user, target.tenant_id, PEOPLE, write=True, request=request)


# ------------------------------------------------------------------------------------------- lifecycle


def expire(db: Session, tenant_id=None, now: datetime | None = None) -> int:
    """Close every open grant whose window has passed (requested, awaiting the customer or approved). An approved one
    is written to its organization's audit trail (``SUPPORT_ACCESS_EXPIRED``) and its decision makers are emailed
    that it ended (backend/app/notifications.py). The caller commits.

    Closing it changes nothing about what it opens: :func:`evaluate` refuses a grant past its window whatever its
    status says, so access ends at the second it expires, before this runs."""
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.notifications import notify_support_access_ended

    now = now or datetime.now(timezone.utc)
    query = db.query(SupportAccessGrant).filter(
        SupportAccessGrant.status.in_(sorted(OPEN)), SupportAccessGrant.expires_at <= now
    )
    if tenant_id is not None:
        query = query.filter(SupportAccessGrant.tenant_id == tenant_id)
    rows = query.with_for_update(skip_locked=True).all()
    for row in rows:
        was_active = row.status == APPROVED and row.customer_decided_by is not None
        row.status = EXPIRED
        row.updated_at = now
        if was_active:
            db.add(
                make_audit_event(
                    tenant_id=row.tenant_id,
                    actor_ref="system:support-access-expiry",
                    action=ACCESS_EXPIRED,
                    entity_type="SupportAccessGrant",
                    entity_id=row.id,
                    details={"source": "SYSTEM", "expires_at": _aware(row.expires_at).isoformat()},
                    created_at=now,
                )
            )
            notify_support_access_ended(db, row.tenant_id, grant_id=row.id, ended="EXPIRED")
    if rows:
        db.flush()
    return len(rows)
