"""Report synthetic validation coverage in the control and tenant data planes.

The command is read-only.  It intentionally reports counts rather than record
contents so it can be attached to local validation evidence without exposing
credentials, prompts, attachments, or other protected values.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import func, inspect, select, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.data_plane import open_tenant_data_session  # noqa: E402
from backend.app.db.models.customer_lifecycle import (  # noqa: E402
    CustomerContact,
    CustomerDomain,
    EntitlementSnapshot,
    IdentityProviderConfiguration,
    PlanVersionAssignment,
    TenantEnvironment,
    TenantHealthRun,
    TenantIsolationEvidence,
    TenantServiceHealthCheck,
    UsageQuotaSnapshot,
)
from backend.app.db.models.foundation import (  # noqa: E402
    AuthUser,
    ConnectorConfiguration,
    MappingConfiguration,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import SubscriptionLifecycle  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402

TENANT_KEYS = tuple(f"R1_TENANT_{number}" for number in range(1, 5))

CONTROL_MODELS = (
    AuthUser,
    TenantMembership,
    TenantEnvironment,
    IdentityProviderConfiguration,
    TenantPlanAssignment,
    PlanVersionAssignment,
    EntitlementSnapshot,
    SubscriptionLifecycle,
    UsageQuotaSnapshot,
    ConnectorConfiguration,
    MappingConfiguration,
    TenantHealthRun,
    TenantServiceHealthCheck,
    TenantIsolationEvidence,
)

DATA_TABLES = (
    "products",
    "product_versions",
    "components",
    "suppliers",
    "lot_batches",
    "changes",
    "complaints",
    "investigations",
    "investigation_complaints",
    "evidence",
    "investigation_evidence",
    "hypotheses",
    "unknowns",
    "failure_chains",
    "failure_chain_nodes",
    "failure_chain_edges",
    "scenarios",
    "risks",
    "failure_modes",
    "controls",
    "capas",
    "ai_executions",
    "decisions",
    "human_reviews",
    "connector_runs",
    "connector_source_records",
    "connector_reconciliations",
    "report_jobs",
)


def _control_counts(db, tenant: Tenant) -> dict[str, int]:
    result: dict[str, int] = {
        CustomerContact.__tablename__: int(
            db.query(func.count())
            .select_from(CustomerContact)
            .filter(CustomerContact.customer_id == tenant.customer_id)
            .scalar()
            or 0
        ),
        CustomerDomain.__tablename__: int(
            db.query(func.count())
            .select_from(CustomerDomain)
            .filter(CustomerDomain.customer_id == tenant.customer_id)
            .scalar()
            or 0
        ),
    }
    for model in CONTROL_MODELS:
        result[model.__tablename__] = int(
            db.query(func.count()).select_from(model).filter(model.tenant_id == tenant.id).scalar() or 0
        )
    return result


def _data_counts(tenant: Tenant) -> dict[str, int | str]:
    with open_tenant_data_session(tenant.id) as data:
        table_names = set(inspect(data.get_bind()).get_table_names(schema="public"))
        result: dict[str, int | str] = {
            "database": str(data.execute(select(func.current_database())).scalar_one())
        }
        for table in DATA_TABLES:
            if table not in table_names:
                result[table] = "MISSING"
                continue
            result[table] = int(
                data.execute(
                    text(f'SELECT count(*) FROM public."{table}" WHERE tenant_id = :tenant'),
                    {"tenant": tenant.id},
                ).scalar_one()
            )
        return result


def main() -> int:
    report: dict[str, object] = {"scope": "local synthetic validation data", "tenants": {}}
    with SessionLocal() as db:
        bind_system(db, "read validation dataset inventory")
        tenants = db.query(Tenant).filter(Tenant.tenant_key.in_(TENANT_KEYS)).order_by(Tenant.tenant_key).all()
        found = {tenant.tenant_key for tenant in tenants}
        missing = sorted(set(TENANT_KEYS) - found)
        if missing:
            raise RuntimeError(f"VALIDATION_TENANTS_MISSING:{','.join(missing)}")
        for tenant in tenants:
            report["tenants"][tenant.tenant_key] = {
                "tenant_id": str(tenant.id),
                "tenant_identifier": tenant.tenant_identifier,
                "display_name": tenant.display_name,
                "status": tenant.status,
                "control_plane": _control_counts(db, tenant),
                "data_plane": _data_counts(tenant),
            }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
