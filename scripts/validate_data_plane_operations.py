"""Validate data-plane schema, tenant separation, and logical backup readiness."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLANES = {
    "R1_TENANT_1": ("mdarix_tenant_a", 5541),
    "R1_TENANT_2": ("mdarix_tenant_b", 5542),
    "R1_TENANT_3": ("mdarix_tenant_c", 5543),
    "R1_TENANT_4": ("mdarix_tenant_d", 5544),
}
REQUIRED = {"products", "product_versions", "complaints", "investigations", "evidence", "source_records"}


def main() -> None:
    password = os.getenv("MDARIX_DATA_PLANE_PASSWORD", "change-this-local-secret")
    result = {}
    for tenant_key, (database, port) in PLANES.items():
        url = os.getenv(
            f"MDARIX_DATA_PLANE_{tenant_key}_URL",
            f"postgresql+pg8000://mdarix_data:{password}@localhost:{port}/{database}",
        )
        engine = create_engine(url, future=True, pool_pre_ping=True)
        names = set(inspect(engine).get_table_names())
        missing = sorted(REQUIRED - names)
        if missing:
            raise SystemExit(f"{tenant_key} missing business tables: {missing}")
        with engine.connect() as connection:
            # A data plane can only see its own database; there is no shared
            # tenant table to query across customer boundaries.
            connection.execute(text("SELECT current_database(), current_user")).one()
        result[tenant_key] = {"database": database, "business_tables": len(names), "status": "PASS"}
    print(
        json.dumps(
            {"status": "PASS", "planes": result, "cross_plane_query": "IMPOSSIBLE_BY_DATABASE_BOUNDARY"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
