"""Give every tenant without a data plane the shared one (business data in the control DB, isolated by tenant).

Tenants created before onboarding registered a data plane have none, so their imports and business screens fail
closed with DATA_PLANE_UNAVAILABLE. This registers the shared plane for them; tenants that already have a plane
(a dedicated database, a trial or the demo) are left alone.

Dry run by default (lists what would change); pass --apply to write.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.customer_lifecycle import shared_data_plane
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the registrations (default: dry run)")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "register shared data planes for tenants without one")
        registered = {tenant_id for (tenant_id,) in db.query(TenantDataPlane.tenant_id)}
        missing = [tenant for tenant in db.query(Tenant).order_by(Tenant.tenant_key) if tenant.id not in registered]
        for tenant in missing:
            print(f"{'register' if args.apply else 'would register'} shared data plane: {tenant.tenant_key}")
            if args.apply:
                db.add(shared_data_plane(tenant, now))
        if args.apply:
            db.commit()
        print(f"{len(missing)} tenant(s) {'registered' if args.apply else 'without a data plane (dry run)'}.")


if __name__ == "__main__":
    main()
