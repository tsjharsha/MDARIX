"""Construction helpers for customer-owned tenants.

Tenant creation is deliberately centralized so a tenant can never be created
without its immutable customer identity and lifecycle metadata.
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


def allowed_lifecycle_transition(current: str, target: str) -> bool:
    return target.upper() in LIFECYCLE_TRANSITIONS.get(current.upper(), frozenset())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:100]


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
    tenant_id = uuid.uuid4()
    # Tenant identifiers are platform-issued, sequential, and never derived
    # from customer input. The transaction advisory lock prevents concurrent
    # provisioning requests from selecting the same next number.
    db.execute(text("SELECT pg_advisory_xact_lock(73192841)"))
    issued_customers = [
        str(value)
        for (value,) in db.query(Customer.customer_identifier)
        .filter(Customer.customer_identifier.op("~")("^CUS[0-9]+$"))
        .all()
    ]
    next_customer_number = max((int(value[3:]) for value in issued_customers), default=0) + 1
    generated_customer_identifier = f"CUS{next_customer_number:04d}"
    issued_tenants = [
        str(value)
        for (value,) in db.query(Tenant.tenant_identifier).filter(Tenant.tenant_identifier.op("~")("^TEN[0-9]+$")).all()
    ]
    next_tenant_number = max((int(value[3:]) for value in issued_tenants), default=0) + 1
    generated_tenant_identifier = f"TEN{next_tenant_number:04d}"
    normalized_key = tenant_key.strip().upper()
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
    tenant = Tenant(
        id=tenant_id,
        customer_id=customer_id,
        tenant_key=normalized_key,
        tenant_identifier=generated_tenant_identifier,
        name=name.strip(),
        display_name=name.strip(),
        tenant_slug=f"{_slug(normalized_key)}-{tenant_id.hex[:8]}",
        tenant_type="STANDARD",
        deployment_model="SHARED",
        primary_region=region,
        residency_region=residency_region,
        cross_border_processing_allowed=False,
        provisioning_status="PROVISIONED" if lifecycle_status == "ACTIVE" else lifecycle_status,
        status=lifecycle_status,
        activated_at=now if lifecycle_status == "ACTIVE" else None,
        lock_version=1,
        created_at=now,
        updated_at=now,
    )
    return customer, tenant
