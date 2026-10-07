"""Activate customers left in PROVISIONING or PROVISIONED although their tenants are live (one-off repair).

The onboarding wizard (/platform/tenants/provision) used to make the tenant ACTIVE but leave its customer in
PROVISIONING, which kept the customer out of "add a tenant" and the customer status workflow. The wizard now
activates the customer too; this script repairs the customers created before that change.

A customer is moved to ACTIVE when it is PROVISIONING or PROVISIONED and it has at least one tenant and every one of
its tenants is ACTIVE. Each change increments the customer's lock_version and is audited
(CUSTOMER_LIFECYCLE_TRANSITION, entity_type Customer). Run with the database owner's credentials (system scope).

    python scripts/activate_provisioned_customers.py           # dry run: list what would change
    python scripts/activate_provisioned_customers.py --apply   # make the change

Dry run is the default and changes nothing.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.models.customer_lifecycle import Customer  # noqa: E402
from backend.app.db.models.foundation import AuditEvent, Tenant  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402

ACTOR = "system:activate-provisioned-customers"
STUCK_STATUSES = ("PROVISIONING", "PROVISIONED")
REASON = "Repair: the customer's tenants were activated by the onboarding wizard but the customer was not"


def stuck_customers(db) -> list[tuple[Customer, list[Tenant]]]:
    """Customers in PROVISIONING/PROVISIONED whose tenants are all ACTIVE (and that have at least one tenant)."""
    found = []
    for customer in (
        db.query(Customer)
        .filter(Customer.lifecycle_status.in_(STUCK_STATUSES))
        .order_by(Customer.customer_identifier)
        .all()
    ):
        tenants = db.query(Tenant).filter(Tenant.customer_id == customer.id).order_by(Tenant.tenant_key).all()
        if tenants and all(str(tenant.status).upper() == "ACTIVE" for tenant in tenants):
            found.append((customer, tenants))
    return found


def activate(db, customer: Customer, tenants: list[Tenant], now: datetime) -> None:
    previous = customer.lifecycle_status
    customer.lifecycle_status = "ACTIVE"
    customer.lock_version = int(customer.lock_version or 0) + 1
    customer.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            # Recorded under the customer's first tenant, so it appears in the customer's activity.
            tenant_id=tenants[0].id,
            actor_ref=ACTOR,
            action="CUSTOMER_LIFECYCLE_TRANSITION",
            entity_type="Customer",
            entity_id=customer.id,
            details={
                "from": previous,
                "to": "ACTIVE",
                "reason": REASON,
                "customer_identifier": customer.customer_identifier,
                "tenants_access_blocked": [],
                "tenants_access_restored": [],
                "source": "scripts/activate_provisioned_customers.py",
            },
            created_at=now,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="make the change (default: dry run, change nothing)")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        bind_system(db, "activate provisioned customers")
        found = stuck_customers(db)
        now = datetime.now(timezone.utc)
        for customer, tenants in found:
            keys = ", ".join(tenant.tenant_key for tenant in tenants)
            print(f"{customer.customer_identifier} ({customer.lifecycle_status} -> ACTIVE): tenants {keys}")
            if args.apply:
                activate(db, customer, tenants, now)
        if args.apply:
            db.commit()
            print(f"Activated {len(found)} customer(s).")
        else:
            db.rollback()
            print(f"Dry run: {len(found)} customer(s) would be activated. Run with --apply to make the change.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
