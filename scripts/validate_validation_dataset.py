"""Validate completeness and tenant boundaries of the local MVP dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.data_plane import open_tenant_data_session  # noqa: E402
from backend.app.db.models.foundation import Tenant  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from scripts.seed_validation_dataset import TENANT_PROFILES  # noqa: E402

MINIMUM_COUNTS = {
    "products": 4,
    "product_versions": 7,
    "components": 9,
    "suppliers": 2,
    "lot_batches": 15,
    "complaints": 29,
    "investigations": 2,
    "evidence": 4,
    "hypotheses": 3,
    "unknowns": 3,
    "failure_chains": 1,
    "risks": 1,
    "capas": 1,
    "ai_executions": 1,
    "decisions": 1,
    "human_reviews": 1,
    "connector_runs": 4,
    "connector_source_records": 8,
    "connector_reconciliations": 4,
    "report_jobs": 3,
}


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> int:
    report: dict[str, object] = {"status": "PASS", "tenants": {}}
    with SessionLocal() as control:
        bind_system(control, "validate local synthetic tenant dataset")
        tenants = (
            control.query(Tenant)
            .filter(Tenant.tenant_key.in_(TENANT_PROFILES))
            .order_by(Tenant.tenant_key)
            .all()
        )
        if len(tenants) != len(TENANT_PROFILES):
            raise RuntimeError("VALIDATION_TENANT_REGISTRY_INCOMPLETE")

        for tenant in tenants:
            with open_tenant_data_session(tenant.id) as data:
                connection = data.connection()
                inspector = inspect(connection)
                tables = inspector.get_table_names(schema="public")
                tenant_tables: list[str] = []
                invalid: dict[str, int] = {}
                for table in tables:
                    columns = {column["name"] for column in inspector.get_columns(table, schema="public")}
                    if "tenant_id" not in columns:
                        continue
                    tenant_tables.append(table)
                    invalid_count = connection.execute(
                        text(
                            f"SELECT count(*) FROM public.{_quoted(table)} "
                            "WHERE tenant_id IS DISTINCT FROM :tenant_id"
                        ),
                        {"tenant_id": tenant.id},
                    ).scalar_one()
                    if invalid_count:
                        invalid[table] = int(invalid_count)

                counts: dict[str, int] = {}
                below_minimum: dict[str, dict[str, int]] = {}
                for table, minimum in MINIMUM_COUNTS.items():
                    count = int(
                        connection.execute(
                            text(
                                f"SELECT count(*) FROM public.{_quoted(table)} "
                                "WHERE tenant_id = :tenant_id"
                            ),
                            {"tenant_id": tenant.id},
                        ).scalar_one()
                    )
                    counts[table] = count
                    if count < minimum:
                        below_minimum[table] = {"actual": count, "minimum": minimum}

                identity = connection.execute(
                    text(
                        "SELECT tenant_key, customer_id FROM tenants "
                        "WHERE id = :tenant_id"
                    ),
                    {"tenant_id": tenant.id},
                ).one_or_none()
                identity_matches = bool(
                    identity
                    and identity.tenant_key == tenant.tenant_key
                    and identity.customer_id == tenant.customer_id
                )
                passed = not invalid and not below_minimum and identity_matches
                report["tenants"][tenant.tenant_key] = {
                    "database": connection.execute(text("SELECT current_database()" )).scalar_one(),
                    "identity_matches_control_plane": identity_matches,
                    "tenant_owned_tables_checked": len(tenant_tables),
                    "foreign_tenant_rows": invalid,
                    "coverage": counts,
                    "below_minimum": below_minimum,
                    "status": "PASS" if passed else "FAIL",
                }
                if not passed:
                    report["status"] = "FAIL"

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
