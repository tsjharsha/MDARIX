"""Accounts as the platform administrator sees them, kept apart by who they belong to.

- Platform users: every account with the platform administrator role, whichever organization it signs in to.
- Customer users: every other account of a customer organization (Customer Administrators have their own list,
  /platform-admin/customer-admins, with the actions a platform administrator may take for them). Customer users are
  managed by their own organization's administrators, so this list is read-only.

Both lists are for platform administrators only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app import support_access
from backend.app.access.authz import _require_platform_admin
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.workflow import UserAdditionalRole
from backend.app.db.session import get_db
from backend.app.sorting import order_query
from backend.app.role_codes import CUSTOMER_ADMIN_ALIASES, PLATFORM_ADMIN_ALIASES, WORKFLOW_ROLES, role_code, role_label

router = APIRouter(prefix="/api/v1", tags=["Access Control"])

# Retired and offboarded accounts are history, not people to manage; ask for them by status to see them.
RETIRED = ("INACTIVE", "OFFBOARDED")
MAX_PAGE_SIZE = 200


def _role_key():
    """The stored role as a comparable code: upper case, spaces and hyphens as underscores."""
    return func.upper(func.replace(func.replace(func.trim(AuthUser.role), " ", "_"), "-", "_"))


def _is_platform_role():
    return _role_key().in_(sorted(PLATFORM_ADMIN_ALIASES))


def _is_customer_admin_role():
    return _role_key().in_(sorted(CUSTOMER_ADMIN_ALIASES))


def _search(query, q: str | None):
    if not (q and q.strip()):
        return query
    like = f"%{q.strip().lower()}%"
    return query.filter(
        or_(
            func.lower(AuthUser.username).like(like),
            func.lower(AuthUser.display_name).like(like),
            func.lower(AuthUser.business_id).like(like),
            func.lower(AuthUser.role).like(like),
            func.lower(func.coalesce(Tenant.display_name, Tenant.name)).like(like),
            func.lower(Tenant.business_id).like(like),
            func.lower(func.coalesce(Customer.display_name, Customer.legal_name, "")).like(like),
            func.lower(func.coalesce(Customer.business_id, "")).like(like),
        )
    )


def _status(query, status: str | None):
    if status and status.strip():
        return query.filter(func.upper(AuthUser.status) == status.strip().upper())
    return query.filter(func.upper(AuthUser.status).notin_(RETIRED))


def _row(user: AuthUser, tenant: Tenant | None, customer: Customer | None) -> dict:
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "email": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "role_label": role_label(user.role),
        "status": (user.status or "").upper(),
        "mfa_enrolled": user.mfa_enrolled_at is not None,
        "tenant_id": str(user.tenant_id),
        "tenant_business_id": tenant.business_id if tenant else None,
        "tenant_name": (tenant.display_name or tenant.name) if tenant else None,
        "customer_id": str(customer.id) if customer else None,
        "customer_business_id": customer.business_id if customer else None,
        "customer_name": (customer.display_name or customer.legal_name) if customer else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _base(db: Session):
    return (
        db.query(AuthUser, Tenant, Customer)
        .join(Tenant, Tenant.id == AuthUser.tenant_id)
        .outerjoin(Customer, Customer.id == Tenant.customer_id)
    )


@router.get("/platform-admin/platform-users")
def list_platform_users(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Every account with the platform administrator role, in any organization. No customer accounts."""
    _require_platform_admin(request, db)
    query = _status(_search(_base(db).filter(_is_platform_role()), q), status)
    rows = query.order_by(func.lower(AuthUser.display_name), AuthUser.username).limit(500).all()
    items = [_row(user, tenant, customer) for user, tenant, customer in rows]
    return {"items": items, "total": len(items)}


@router.get("/platform-admin/customer-users")
def list_customer_users(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    customer_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "",
    order: str = "",
    db: Session = Depends(get_db),
):
    """The people of customer organizations: every account that is neither a platform administrator nor a Customer
    Administrator, one page at a time. Read-only: each customer's administrators manage them. Only organizations
    whose administrators approved People access are listed (backend/app/support_access.py); ``withheld`` counts the
    organizations left out. ``sort``/``order`` order every page by a column (backend/app/sorting.py); by default by
    customer, tenant, name."""
    admin = _require_platform_admin(request, db)
    opened = sorted(support_access.open_tenants(db, admin, support_access.PEOPLE, request=request), key=str)
    query = _base(db).filter(~_is_platform_role(), ~_is_customer_admin_role())
    withheld = query.filter(AuthUser.tenant_id.not_in(opened)).with_entities(AuthUser.tenant_id).distinct().count()
    query = query.filter(AuthUser.tenant_id.in_(opened))
    query = _status(_search(query, q), status)
    if role and role.strip():
        wanted = "_".join(role.strip().upper().replace("-", " ").split())
        query = query.filter(_role_key() == wanted)
    if customer_id:
        query = query.filter(Tenant.customer_id == customer_id)
    if tenant_id:
        query = query.filter(AuthUser.tenant_id == tenant_id)
    size = max(1, min(int(page_size or 50), MAX_PAGE_SIZE))
    total = query.count()
    pages = max(1, -(-total // size))
    current = max(1, min(int(page or 1), pages))
    tenant_name = func.coalesce(Tenant.display_name, Tenant.name)
    customer_name = func.coalesce(Customer.display_name, Customer.legal_name)
    query = order_query(
        query,
        sort,
        order,
        columns={
            "business_id": [AuthUser.business_id],
            "user": [func.coalesce(AuthUser.display_name, AuthUser.username), AuthUser.username],
            "display_name": [AuthUser.display_name],
            "email": [AuthUser.username],
            "organization": [func.coalesce(customer_name, tenant_name), tenant_name],
            "customer_name": [customer_name],
            "tenant_name": [tenant_name],
            "tenant_business_id": [Tenant.business_id],
            "customer_business_id": [Customer.business_id],
            "role": [_role_key()],
            "role_label": [_role_key()],
            "status": [func.upper(AuthUser.status)],
            "created_at": [AuthUser.created_at],
        },
        default=[
            func.lower(func.coalesce(Customer.display_name, Customer.legal_name, "")),
            func.lower(tenant_name),
            func.lower(AuthUser.display_name),
            AuthUser.username,
        ],
        tiebreak=[AuthUser.id],
    )
    rows = query.offset((current - 1) * size).limit(size).all()
    return {
        "items": [_row(user, tenant, customer) for user, tenant, customer in rows],
        "total": total,
        "page": current,
        "pages": pages,
        "page_size": size,
        "withheld": withheld,
    }


# ---- The built-in roles and what they allow --------------------------------------------------------------------

# Each permission in plain words (backend/app/access/permissions.py holds what each role grants).
PERMISSION_TEXT: dict[str, tuple[str, str]] = {
    "records.write": ("Change records", "Create and edit quality records: complaints, evidence, investigations."),
    "ai.run": ("Use AI assistance", "Ask MDARIX and AI drafting, where the organization has switched AI on."),
    "data.export": ("Export data", "Download lists, reports and audit exports."),
    "regulatory.approve": ("Approve regulatory documents", "Approve regulatory drafts and reports."),
    "signal.triage": ("Triage signals", "Start triage, set priority, record a disposition and tune detection rules."),
    "investigation.create": ("Open investigations", "Open a case, from a signal or on its own."),
    "investigation.assign": ("Assign investigations", "Give a case or its tasks to a person, or reassign them."),
    "investigation.work": ("Work on investigations", "Scope, intelligence and the Decision Brief of a case."),
    "evidence.review": ("Review evidence", "Accept, limit or reject evidence on a case."),
    "evidence.request": ("Request evidence", "Ask colleagues or suppliers for evidence."),
    "risk.review": ("Record risk reviews", "Assess a case against the risk file and record the outcome."),
    "regulatory.review": ("Record regulatory reviews", "Assess reportability and record the outcome."),
    "quality.review": ("Review Decision Briefs", "Accept a brief for decision, return it, reject it or escalate."),
    "decision.sign": (
        "Sign decisions",
        "Sign the human decision on an approved brief. Also needs approval authority, and never on a brief the "
        "person helped write.",
    ),
}

# What each role is for, and where it works.
ROLE_TEXT: dict[str, tuple[str, str]] = {
    "PLATFORM_ADMIN": (
        "Platform",
        "MDARIX staff. Runs the platform: customers, tenants, plans, accounts and platform settings, with full access "
        "to their own organization's records.",
    ),
    "CUSTOMER_ADMIN": (
        "Customer administration",
        "Manages their organization's people, roles and settings. Can work on cases with an investigator's rights; "
        "never signs decisions.",
    ),
    "TRIAGE_LEAD": ("Workspace", "Triages signals, decides what needs an investigation, and opens and assigns cases."),
    "INVESTIGATOR": (
        "Workspace",
        "Owns cases: scope, evidence, hypotheses and unknowns, and writes the Decision Brief.",
    ),
    "RISK_REVIEWER": (
        "Workspace",
        "Records the risk review of a case. Reads and asks for evidence; changes no records.",
    ),
    "REGULATORY_REVIEWER": ("Workspace", "Records the regulatory review of a case and approves regulatory documents."),
    "REVIEWER": ("Workspace", "Reviews Decision Briefs before a decision, and can assign cases."),
    "APPROVER": ("Workspace", "Makes and signs the human decision on an approved Decision Brief."),
    "LEADER": ("Workspace", "Quality manager: every workspace permission, and receives escalations."),
    "VIEWER": ("Workspace", "Reads everything their organization holds; changes nothing."),
}
ROLE_ORDER = ("PLATFORM_ADMIN", "CUSTOMER_ADMIN", *WORKFLOW_ROLES, "VIEWER")


@router.get("/platform-admin/role-catalog")
def role_catalog(request: Request, db: Session = Depends(get_db)):
    """The built-in roles, what each allows, and how many current accounts hold each, across every organization.
    Read-only: the roles are part of the product (custom roles of an organization are listed separately)."""
    _require_platform_admin(request, db)
    from backend.app.access.permissions import ROLE_PERMISSIONS

    current = func.upper(AuthUser.status).notin_(RETIRED)
    by_role: dict[str, int] = {}
    for stored, count in db.query(AuthUser.role, func.count(AuthUser.id)).filter(current).group_by(AuthUser.role):
        by_role[role_code(stored)] = by_role.get(role_code(stored), 0) + int(count)
    extra = dict(
        db.query(func.upper(UserAdditionalRole.role_code), func.count(UserAdditionalRole.id))
        .join(AuthUser, AuthUser.id == UserAdditionalRole.user_id)
        .filter(func.upper(UserAdditionalRole.status) == "ACTIVE", current)
        .group_by(func.upper(UserAdditionalRole.role_code))
        .all()
    )
    roles = []
    for code in ROLE_ORDER:
        scope, description = ROLE_TEXT[code]
        granted = sorted(ROLE_PERMISSIONS.get(code, frozenset()), key=list(PERMISSION_TEXT).index)
        roles.append(
            {
                "code": code,
                "label": role_label(code),
                "scope": scope,
                "description": description,
                "permissions": granted,
                "account_holders": by_role.get(code, 0),
                "additional_holders": int(extra.get(code, 0)),
                "can_be_additional": code in WORKFLOW_ROLES,
            }
        )
    permissions = [
        {
            "code": code,
            "label": label,
            "description": description,
            "roles": [role["code"] for role in roles if code in role["permissions"]],
        }
        for code, (label, description) in PERMISSION_TEXT.items()
    ]
    return {"roles": roles, "permissions": permissions}
