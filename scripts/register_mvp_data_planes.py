"""Register the four local synthetic customer data planes in the control DB."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system

PLANES = {
    "R1_TENANT_1": "mdarix-tenant-a-data",
    "R1_TENANT_2": "mdarix-tenant-b-data",
    "R1_TENANT_3": "mdarix-tenant-c-data",
    "R1_TENANT_4": "mdarix-tenant-d-data",
}


def main() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "register the validation organizations' data planes")
        tenants = {row.tenant_key: row for row in db.query(Tenant).filter(Tenant.tenant_key.in_(PLANES)).all()}
        if set(tenants) != set(PLANES):
            raise SystemExit(f"Expected four provisioned validation tenants; found {sorted(tenants)}")
        for tenant_key, database_ref in PLANES.items():
            plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenants[tenant_key].id).first()
            if plane is None:
                plane = TenantDataPlane(
                    id=uuid.uuid4(),
                    tenant_id=tenants[tenant_key].id,
                    database_ref=database_ref,
                    connection_secret_ref=f"MDARIX_DATA_PLANE_{tenant_key}_DATABASE_URL",
                    region="LOCAL",
                    residency_region="LOCAL",
                    schema_version="mvp-1",
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                )
                db.add(plane)
            else:
                plane.status = "ACTIVE"
                plane.updated_at = now
        db.commit()
        print(f"REGISTERED {len(PLANES)} synthetic customer data planes")


if __name__ == "__main__":
    main()
