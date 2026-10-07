"""Construction helpers for customer-owned tenants.

Tenant creation is deliberately centralized so a tenant can never be created
without its immutable customer identity and lifecycle metadata.

A Customer is the legal and commercial parent; a Tenant is the operational and
data-isolation boundary. One customer owns one or more tenants, and a tenant
belongs to exactly one customer for its whole life.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import Tenant
from sqlalchemy import text

LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PENDING_APPROVAL"}),
    "PENDING_APPROVAL": frozenset({"DRAFT", "PROVISIONING"}),
    "PROVISIONING": frozenset({"PROVISIONED"}),
    "PROVISIONED": frozenset({"PENDING_CUSTOMER_ACTIVATION", "PROVISIONING"}),
    "PENDING_CUSTOMER_ACTIVATION": frozenset({"ACTIVE", "PROVISIONING"}),
    "ACTIVE": frozenset({"EXPIRING_SOON", "SUSPENDED", "TERMINATED"}),
    "EXPIRING_SOON": frozenset({"ACTIVE", "EXPIRED", "SUSPENDED"}),
    "EXPIRED": frozenset({"ACTIVE", "SUSPENDED", "TERMINATED"}),
    "SUSPENDED": frozenset({"ACTIVE", "TERMINATED"}),
    "TERMINATED": frozenset({"ARCHIVED"}),
    "ARCHIVED": frozenset(),
}


# A new tenant's provisioning status follows its lifecycle status, within the values the database allows
# (DRAFT, QUEUED, RUNNING, FAILED, PROVISIONED, ACTIVE). Onboarding creates tenants as PROVISIONING, which used to
# be copied as is and refused by the database.
PROVISIONING_STATUS_FOR = {
    "DRAFT": "DRAFT",
    "PENDING_APPROVAL": "QUEUED",
    "PROVISIONING": "RUNNING",
    "PROVISIONED": "PROVISIONED",
    "ACTIVE": "PROVISIONED",
}


def allowed_lifecycle_transition(current: str, target: str) -> bool:
    return target.upper() in LIFECYCLE_TRANSITIONS.get(current.upper(), frozenset())


# A tenant whose provisioning finished (PROVISIONED) may also be activated directly by a Platform Administrator, in
# addition to the shared matrix above. Tenants still in DRAFT, PENDING_APPROVAL or PROVISIONING may not.
TENANT_EXTRA_TRANSITIONS: dict[str, frozenset[str]] = {"PROVISIONED": frozenset({"ACTIVE"})}
TENANT_NOT_PROVISIONED_STATUSES = frozenset({"DRAFT", "PENDING_APPROVAL", "PROVISIONING"})


def allowed_tenant_transition(current: str, target: str) -> bool:
    current, target = current.upper(), target.upper()
    return allowed_lifecycle_transition(current, target) or target in TENANT_EXTRA_TRANSITIONS.get(current, frozenset())


def tenant_transition_message(current: str, target: str) -> str:
    if target.upper() == "ACTIVE" and current.upper() in TENANT_NOT_PROVISIONED_STATUSES:
        return f"Provisioning of this tenant is not finished ({current}); it can be activated once it is provisioned"
    return f"Cannot transition {current} to {target}"


# "Customer gates tenants": a customer in one of these states blocks sign-in, the API and background jobs for every
# tenant it owns, without changing the tenants' own status (reactivating the customer restores exactly the tenants
# that are themselves active).
BLOCKING_CUSTOMER_STATUSES = frozenset({"SUSPENDED", "TERMINATED", "ARCHIVED"})
# A tenant can be (re)activated only while its customer is in one of these states.
CUSTOMER_ACTIVE_STATUSES = frozenset({"ACTIVE", "EXPIRING_SOON"})
# Tenant states in which a tenant itself is open for use.
TENANT_OPEN_STATUSES = frozenset({"ACTIVE", "EXPIRING_SOON"})

# What a Platform Administrator may do to a customer's own standing (the customer status route).
CUSTOMER_STATUS_SOURCES: dict[str, frozenset[str]] = {
    "SUSPENDED": frozenset({"ACTIVE", "EXPIRING_SOON", "EXPIRED"}),
    "ACTIVE": frozenset(
        {
            "SUSPENDED",
            "EXPIRED",
            "DRAFT",
            "PENDING_APPROVAL",
            "PROVISIONING",
            "PROVISIONED",
            "PENDING_CUSTOMER_ACTIVATION",
        }
    ),
}
# Customer states before the first activation; the onboarding wizard moves them to ACTIVE with their first tenant.
PRE_ACTIVE_CUSTOMER_STATUSES = frozenset(
    {"DRAFT", "PENDING_APPROVAL", "PROVISIONING", "PROVISIONED", "PENDING_CUSTOMER_ACTIVATION"}
)
OPERATOR_CUSTOMER_IDENTIFIER = "MDARIX-OPERATOR"


def customer_blocks_access(customer_status: str | None) -> bool:
    return str(customer_status or "").upper() in BLOCKING_CUSTOMER_STATUSES


def effective_access(tenant_status: str | None, customer_status: str | None) -> str:
    """ACTIVE when the tenant is open and its customer does not block it; BLOCKED_BY_CUSTOMER when only the customer
    stands in the way; otherwise BLOCKED."""
    if str(tenant_status or "").upper() not in TENANT_OPEN_STATUSES:
        return "BLOCKED"
    if customer_blocks_access(customer_status):
        return "BLOCKED_BY_CUSTOMER"
    return "ACTIVE"


def tenants_of_blocking_customers():
    """SQL subquery: ids of tenants whose customer is suspended, terminated or archived."""
    from sqlalchemy import func, select

    return select(Tenant.id).where(
        Tenant.customer_id.in_(
            select(Customer.id).where(func.upper(Customer.lifecycle_status).in_(sorted(BLOCKING_CUSTOMER_STATUSES)))
        )
    )


def customer_allows_access_clause():
    """SQL filter on Tenant for background jobs: the tenant's customer does not block access."""
    return Tenant.id.not_in(tenants_of_blocking_customers())


def operator_customer_ids(db) -> set:
    """The platform operator's own customer(s): the MDARIX-OPERATOR customer and every customer owning a tenant in
    which an active Platform Administrator account lives. Suspending them would lock the platform out."""
    from backend.app.db.models.foundation import AuthUser

    ids = {
        row.customer_id
        for row in db.query(Tenant.customer_id)
        .join(AuthUser, AuthUser.tenant_id == Tenant.id)
        .filter(AuthUser.role == "PLATFORM_ADMIN", AuthUser.status == "ACTIVE")
        .distinct()
        .all()
    }
    ids.update(
        row.id
        for row in db.query(Customer.id).filter(Customer.customer_identifier == OPERATOR_CUSTOMER_IDENTIFIER).all()
    )
    return ids


def is_operator_customer(db, customer_id) -> bool:
    return customer_id in operator_customer_ids(db)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:100]


def _lock_identifiers(db) -> None:
    # Customer and tenant identifiers are platform-issued, sequential, and never
    # derived from customer input. The transaction advisory lock prevents
    # concurrent provisioning requests from selecting the same next number.
    db.execute(text("SELECT pg_advisory_xact_lock(73192841)"))


def _next_tenant_identifier(db) -> str:
    issued_tenants = [
        str(value)
        for (value,) in db.query(Tenant.tenant_identifier).filter(Tenant.tenant_identifier.op("~")("^TEN[0-9]+$")).all()
    ]
    next_tenant_number = max((int(value[3:]) for value in issued_tenants), default=0) + 1
    return f"TEN{next_tenant_number:04d}"


def _tenant(
    *,
    customer_id: uuid.UUID,
    tenant_identifier: str,
    tenant_key: str,
    name: str,
    lifecycle_status: str,
    now: datetime,
    region: str,
    residency_region: str,
) -> Tenant:
    tenant_id = uuid.uuid4()
    normalized_key = tenant_key.strip().upper()
    return Tenant(
        id=tenant_id,
        customer_id=customer_id,
        tenant_key=normalized_key,
        tenant_identifier=tenant_identifier,
        name=name.strip(),
        display_name=name.strip(),
        tenant_slug=f"{_slug(normalized_key)}-{tenant_id.hex[:8]}",
        tenant_type="STANDARD",
        deployment_model="SHARED",
        primary_region=region,
        residency_region=residency_region,
        cross_border_processing_allowed=False,
        provisioning_status=PROVISIONING_STATUS_FOR.get(lifecycle_status, "PROVISIONED"),
        status=lifecycle_status,
        activated_at=now if lifecycle_status == "ACTIVE" else None,
        lock_version=1,
        created_at=now,
        updated_at=now,
    )


def build_tenant_for_customer(
    *,
    db,
    customer: Customer,
    tenant_key: str,
    name: str,
    status: str,
    now: datetime,
    region: str = "UNSPECIFIED",
    residency_region: str = "UNSPECIFIED",
) -> Tenant:
    """A further tenant (another region, business unit or environment) for an existing customer."""
    _lock_identifiers(db)
    return _tenant(
        customer_id=customer.id,
        tenant_identifier=_next_tenant_identifier(db),
        tenant_key=tenant_key,
        name=name,
        lifecycle_status=status.strip().upper(),
        now=now,
        region=region,
        residency_region=residency_region,
    )


def shared_data_plane(tenant: Tenant, now: datetime):
    """Register a new tenant's business data in the shared database (rows keyed by tenant, row-level security).

    Every tenant needs a data plane before its products, complaints or connector imports can be stored; without one
    those requests fail closed. A dedicated database is set up later by replacing this registry row.
    """
    from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE
    from backend.app.db.models.customer_lifecycle import TenantDataPlane

    return TenantDataPlane(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        database_ref=f"shared-control:{tenant.tenant_key}",
        connection_secret_ref=SHARED_CONTROL_DATA_PLANE,
        region=tenant.primary_region or "UNSPECIFIED",
        residency_region=tenant.residency_region or "UNSPECIFIED",
        schema_version="control-plane",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )


def build_customer_tenant(
    *,
    db,
    tenant_key: str,
    name: str,
    status: str,
    now: datetime,
    region: str = "UNSPECIFIED",
    residency_region: str = "UNSPECIFIED",
    customer_type: str = "CUSTOMER",
    country: str = "UNSPECIFIED",
) -> tuple[Customer, Tenant]:
    customer_id = uuid.uuid4()
    _lock_identifiers(db)
    issued_customers = [
        str(value)
        for (value,) in db.query(Customer.customer_identifier)
        .filter(Customer.customer_identifier.op("~")("^CUS[0-9]+$"))
        .all()
    ]
    next_customer_number = max((int(value[3:]) for value in issued_customers), default=0) + 1
    generated_customer_identifier = f"CUS{next_customer_number:04d}"
    generated_tenant_identifier = _next_tenant_identifier(db)
    lifecycle_status = status.strip().upper()
    customer = Customer(
        id=customer_id,
        customer_identifier=generated_customer_identifier,
        legal_name=name.strip(),
        display_name=name.strip(),
        customer_type=customer_type,
        country=country,
        lifecycle_status=lifecycle_status,
        lock_version=1,
        created_at=now,
        updated_at=now,
    )
    tenant = _tenant(
        customer_id=customer_id,
        tenant_identifier=generated_tenant_identifier,
        tenant_key=tenant_key,
        name=name,
        lifecycle_status=lifecycle_status,
        now=now,
        region=region,
        residency_region=residency_region,
    )
    return customer, tenant
