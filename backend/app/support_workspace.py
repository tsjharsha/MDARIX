"""The read-only support workspace: what a platform administrator sees of an organization under the support access its
decision makers approved (backend/app/support_access.py), for example a free trial's owner.

Why a dedicated set of platform routes, and not the user workspace in a "support mode": support access is enforced
per area on platform routes (``require_customer_approved_access``), never by a session in the customer's
organization. A platform administrator's session stays in the platform's own organization, so no workspace route can
ever act on the customer's data for them. The routes here are all GET, read the organization's data through the same
gate (one area each), and answer only named fields: never a password, an authenticator secret, a recovery code, a
token or a session. So the server, not the screen, keeps the view read-only and inside the areas granted:

- Quality records (``RECORDS``): complaints, investigations, decisions and the data imports.
- People (``PEOPLE``): the team.
- Audit trail (``AUDIT``): what people and systems did in the organization.
- Full export (``DATA_EXPORT``): the organization's export, through the existing export routes
  (backend/app/tenant_export_api.py).

Each page read is written to the organization's own audit trail as a use of the grant (``SUPPORT_ACCESS_USED``, with
the address read), and a read without a grant is refused (403 ``CUSTOMER_APPROVAL_REQUIRED``) and written there too.
The trial owner sees both under Getting started › Team › Support access › History.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app import support_access as access
from backend.app.access.authz import _require_platform_admin, platform_account_clause
from backend.app.db.models.customer_lifecycle import SupportAccessGrant
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["Support workspace"])

PAGE_SIZE = 25
# The pages of the workspace, in reading order: (key, the area that opens it, its title).
SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("complaints", access.RECORDS, "Complaints"),
    ("investigations", access.RECORDS, "Investigations"),
    ("decisions", access.RECORDS, "Decisions"),
    ("imports", access.RECORDS, "Data imports"),
    ("team", access.PEOPLE, "Team"),
    ("audit", access.AUDIT, "Audit trail"),
)
# Audit actions that record a data import (a free trial's file upload; a customer's import run).
IMPORT_ACTIONS = ("TRIAL_DATA_IMPORTED", "DATA_IMPORTED")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _organization(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    if str(tenant.id) == str(access.platform_tenant_id(db)):
        raise HTTPException(
            422,
            detail={"code": "PLATFORM_TENANT", "message": "The platform's own organization has no support workspace"},
        )
    return tenant


def _names(db: Session, refs) -> dict[str, str]:
    ids = set()
    for ref in refs:
        try:
            ids.add(uuid.UUID(str(ref)))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {}
    rows = db.query(AuthUser.id, AuthUser.display_name, AuthUser.username).filter(AuthUser.id.in_(ids)).all()
    return {str(row[0]): row[1] or row[2] for row in rows}


def _who(names: dict[str, str], ref) -> str | None:
    if ref is None:
        return None
    if str(ref).startswith("system:"):
        return "MDARIX (automatic)"
    return names.get(str(ref)) or None


def _support_what(event: AuditEvent) -> str:
    from backend.app.support_access_api import _what

    return _what(event)


def _is_trial(db: Session, tenant_id) -> bool:
    from backend.app.trial.service import trial_subscription

    return trial_subscription(db, tenant_id) is not None


def _open_grants(db: Session, user: AuthUser, tenant_id, now: datetime) -> list[SupportAccessGrant]:
    """The grants that open part of the organization to ``user`` now, longest-running first."""
    rows = access._usable(db, user.id, now).filter(SupportAccessGrant.tenant_id == tenant_id).all()
    return sorted(rows, key=lambda row: access._aware(row.expires_at), reverse=True)


def _grant_view(db: Session, row: SupportAccessGrant) -> dict:
    names = _names(db, [row.customer_decided_by, row.platform_user_id])
    scope = access.SupportScope.stored(row.scope)
    return {
        "id": str(row.id),
        "areas": scope.describe(),
        "write": scope.write,
        "starts_at": _iso(row.starts_at),
        "expires_at": _iso(row.expires_at),
        "approved_by": names.get(str(row.customer_decided_by)),
        "approved_at": _iso(row.customer_decided_at),
        "person": names.get(str(row.platform_user_id)),
    }


# ------------------------------------------------------------------------------------------- where access stands


@router.get("/platform-admin/support-workspace/access")
def support_access_by_organization(request: Request, db: Session = Depends(get_db)):
    """For each organization with open support access (requested, waiting for its decision, or approved): the
    newest open request, and whether it opens the organization to the signed-in administrator now. The platform's
    records about its own requests: nothing of the organization's data."""
    admin = _require_platform_admin(request, db)
    access.expire(db)
    db.commit()
    now = datetime.now(timezone.utc)
    rows = (
        db.query(SupportAccessGrant)
        .filter(SupportAccessGrant.status.in_(sorted(access.OPEN)), SupportAccessGrant.expires_at > now)
        .order_by(SupportAccessGrant.created_at.desc())
        .limit(500)
        .all()
    )
    names = _names(db, [row.platform_user_id for row in rows])
    items: dict[str, dict] = {}
    for row in rows:
        key = str(row.tenant_id)
        mine = row.platform_user_id == admin.id
        usable = (
            mine
            and row.status == access.APPROVED
            and row.customer_decided_by is not None
            and access._aware(row.starts_at) <= now
        )
        item = items.setdefault(key, {"tenant_id": key, "request": None, "open_for_me": False, "expires_at": None})
        if item["request"] is None:
            scope = access.SupportScope.stored(row.scope)
            item["request"] = {
                "id": str(row.id),
                "status": row.status,
                "person": names.get(str(row.platform_user_id)),
                "mine": mine,
                "areas": scope.describe(),
                "write": scope.write,
                "expires_at": _iso(row.expires_at),
            }
        if usable:
            item["open_for_me"] = True
            current = item["expires_at"]
            item["expires_at"] = max(filter(None, [current, _iso(row.expires_at)]))
    return {
        "items": list(items.values()),
        # For the request shortcut: the areas a request may name, and who is asking (the form names them by default).
        "areas": [{"code": code, "label": label} for code, label in access.AREAS.items()],
        "me": str(admin.id),
    }


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace")
def support_workspace(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """What the support workspace of one organization shows the signed-in administrator: the access that opens it
    (for the banner: who approved it, until when, which areas), which pages it opens, and, for a free trial, how far
    into the story it went (the platform's trial records, as in Customers & Tenants › Trials). No page of the
    organization's own data is read here."""
    admin = _require_platform_admin(request, db)
    tenant = _organization(db, tenant_id)
    access.expire(db, tenant.id)
    db.commit()
    now = datetime.now(timezone.utc)
    grants = _open_grants(db, admin, tenant.id, now)
    open_areas = {area for area in access.AREAS if access.find_grant(db, admin, tenant.id, area, now=now) is not None}
    trial = _is_trial(db, tenant.id)
    story = None
    if trial:
        from backend.app.trial import story as trial_story

        progress = trial_story.progress(db, tenant.id)
        story = [
            {"code": code, "title": title, "tried": code in progress["acted"]}
            for code, title, *_ in trial_story.CHAPTERS
        ]
    return {
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.display_name or tenant.name,
            "tenant_key": tenant.tenant_key,
            "business_id": tenant.business_id,
            "is_trial": trial,
        },
        "grant": _grant_view(db, grants[0]) if grants else None,
        "read_only": not any(access.SupportScope.stored(row.scope).write for row in grants),
        "sections": [
            {"key": key, "title": title, "area": area, "open": area in open_areas} for key, area, title in SECTIONS
        ],
        "export": {"open": access.DATA_EXPORT in open_areas},
        "story": story,
    }


# ------------------------------------------------------------------------------------------- pages (one area each)


def _gate(db: Session, admin: AuthUser, tenant_id: uuid.UUID, area: str, request: Request) -> Tenant:
    """The organization, once the administrator's grant for ``area`` (to read) is checked and its use recorded."""
    tenant = _organization(db, tenant_id)
    access.require_customer_approved_access(db, admin, tenant.id, area, request=request)
    return tenant


def _paged(query, page: int) -> tuple[list, int]:
    total = query.order_by(None).count()
    return query.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all(), total


def _page_of(items: list, total: int, page: int) -> dict:
    return {"items": items, "total": total, "page": page, "pages": max(1, -(-total // PAGE_SIZE))}


def _product_names(data: Session, tenant_id, ids) -> dict[str, str]:
    from backend.app.db.models.foundation import Product

    wanted = {value for value in ids if value}
    if not wanted:
        return {}
    rows = data.query(Product.id, Product.name).filter(Product.tenant_id == tenant_id, Product.id.in_(wanted)).all()
    return {str(row[0]): row[1] for row in rows}


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace/complaints")
def support_complaints(
    tenant_id: uuid.UUID, request: Request, page: int = Query(1, ge=1, le=10000), db: Session = Depends(get_db)
):
    from backend.app.db.data_plane import tenant_data_session
    from backend.app.db.models.foundation import Complaint

    admin = _require_platform_admin(request, db)
    tenant = _gate(db, admin, tenant_id, access.RECORDS, request)
    with tenant_data_session(tenant.id) as data:
        query = (
            data.query(Complaint)
            .filter(Complaint.tenant_id == tenant.id)
            .order_by(Complaint.complaint_timestamp.desc().nullslast(), Complaint.created_at.desc())
        )
        rows, total = _paged(query, page)
        products = _product_names(data, tenant.id, [row.product_id for row in rows])
        items = [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "identifier": row.complaint_identifier,
                "received_at": _iso(row.complaint_timestamp),
                "product": products.get(str(row.product_id)),
                "status": row.status,
                "severity": row.severity,
                "type": row.complaint_type,
                "description": row.description,
                "serious_injury": row.serious_injury,
                "death": row.death,
                "malfunction": row.malfunction,
            }
            for row in rows
        ]
    return _page_of(items, total, page)


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace/investigations")
def support_investigations(
    tenant_id: uuid.UUID, request: Request, page: int = Query(1, ge=1, le=10000), db: Session = Depends(get_db)
):
    from backend.app.db.data_plane import tenant_data_session
    from backend.app.db.models.foundation import Investigation

    admin = _require_platform_admin(request, db)
    tenant = _gate(db, admin, tenant_id, access.RECORDS, request)
    with tenant_data_session(tenant.id) as data:
        query = (
            data.query(Investigation)
            .filter(Investigation.tenant_id == tenant.id)
            .order_by(Investigation.opened_at.desc().nullslast(), Investigation.created_at.desc())
        )
        rows, total = _paged(query, page)
        products = _product_names(data, tenant.id, [row.product_id for row in rows])
        names = _names(db, [row.owner_ref for row in rows])
        items = [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "identifier": row.investigation_identifier,
                "question": row.investigation_question,
                "product": products.get(str(row.product_id)),
                "state": row.workflow_state,
                "priority": row.priority,
                "owner": names.get(str(row.owner_ref)),
                "opened_at": _iso(row.opened_at),
                "closed_at": _iso(row.closed_at),
            }
            for row in rows
        ]
    return _page_of(items, total, page)


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace/decisions")
def support_decisions(
    tenant_id: uuid.UUID, request: Request, page: int = Query(1, ge=1, le=10000), db: Session = Depends(get_db)
):
    from backend.app.db.data_plane import tenant_data_session
    from backend.app.db.models.foundation import Decision, Investigation

    admin = _require_platform_admin(request, db)
    tenant = _gate(db, admin, tenant_id, access.RECORDS, request)
    with tenant_data_session(tenant.id) as data:
        query = (
            data.query(Decision, Investigation.investigation_identifier)
            .outerjoin(
                Investigation,
                (Investigation.id == Decision.investigation_id) & (Investigation.tenant_id == Decision.tenant_id),
            )
            .filter(Decision.tenant_id == tenant.id)
            .order_by(Decision.decision_timestamp.desc().nullslast(), Decision.created_at.desc())
        )
        total = data.query(func.count(Decision.id)).filter(Decision.tenant_id == tenant.id).scalar() or 0
        rows = query.limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE).all()
        names = _names(db, [row.authorized_by_ref for row, _ in rows])
        items = [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "identifier": row.decision_identifier,
                "investigation": investigation,
                "type": row.decision_type,
                "outcome": row.outcome or row.selected_action or row.disposition,
                "status": row.decision_status,
                "decided_by": names.get(str(row.authorized_by_ref)),
                "decided_at": _iso(row.decision_timestamp),
            }
            for row, investigation in rows
        ]
    return _page_of(items, int(total), page)


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace/imports")
def support_imports(
    tenant_id: uuid.UUID, request: Request, page: int = Query(1, ge=1, le=10000), db: Session = Depends(get_db)
):
    """The data imports, from the organization's audit trail: when, who, what kind of record and how many rows
    (counts only; the rows themselves are the complaints, products and lots they created)."""
    admin = _require_platform_admin(request, db)
    tenant = _gate(db, admin, tenant_id, access.RECORDS, request)
    query = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant.id, AuditEvent.action.in_(IMPORT_ACTIONS))
        .order_by(AuditEvent.created_at.desc())
    )
    rows, total = _paged(query, page)
    names = _names(db, [row.actor_ref for row in rows])
    items = []
    for row in rows:
        details = row.details or {}
        items.append(
            {
                "id": str(row.id),
                "at": _iso(row.created_at),
                "who": _who(names, row.actor_ref),
                "entity": details.get("entity"),
                "created": details.get("created") if isinstance(details.get("created"), int) else None,
                "rows": details.get("rows") if isinstance(details.get("rows"), int) else None,
                "updated": details.get("updated") if isinstance(details.get("updated"), int) else None,
                "set_aside": details.get("rejected_rows") if isinstance(details.get("rejected_rows"), int) else None,
            }
        )
    return _page_of(items, total, page)


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace/team")
def support_team(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """The organization's people: name, email, role, status and whether they use an authenticator. Never a
    credential: no password, authenticator secret, recovery code or session."""
    from backend.app.trial.team import trial_request

    admin = _require_platform_admin(request, db)
    tenant = _gate(db, admin, tenant_id, access.PEOPLE, request)
    owner = trial_request(db, tenant.id)
    owner_email = (owner.email if owner else "").strip().lower()
    rows = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant.id, ~platform_account_clause())
        .order_by(AuthUser.created_at)
        .limit(500)
        .all()
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "name": row.display_name,
                "email": row.username,
                "role": row.role,
                "status": row.status,
                "is_owner": bool(owner_email) and (row.username or "").strip().lower() == owner_email,
                "uses_authenticator": row.mfa_enrolled_at is not None,
                "joined_at": _iso(row.created_at),
            }
            for row in rows
            if not str(row.username or "").startswith("sample-author+")
        ]
    }


@router.get("/platform-admin/tenants/{tenant_id}/support-workspace/audit")
def support_audit(
    tenant_id: uuid.UUID, request: Request, page: int = Query(1, ge=1, le=10000), db: Session = Depends(get_db)
):
    """The organization's audit trail, newest first: when, who, what and why (no before and after values and no
    network addresses)."""
    admin = _require_platform_admin(request, db)
    tenant = _gate(db, admin, tenant_id, access.AUDIT, request)
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant.id).order_by(AuditEvent.chain_seq.desc())
    rows, total = _paged(query, page)
    names = _names(db, [row.actor_ref for row in rows])
    items = [
        {
            "id": str(row.id),
            "at": _iso(row.created_at),
            "who": _who(names, row.actor_ref),
            "action": row.action,
            "entity_type": row.entity_type,
            "reason": row.reason,
            "support": row.entity_type == "SupportAccessGrant",
            # A support access event in the organization's words ("Read the complaints"), as its History says it.
            "support_what": _support_what(row) if row.entity_type == "SupportAccessGrant" else None,
        }
        for row in rows
    ]
    return _page_of(items, total, page)
