"""Validate the synthetic multi-customer MVP integration matrix.

This script is intentionally limited to local synthetic tenants and provider
simulators. It never contacts customer systems. It verifies provider-token
enforcement, tenant-scoped reads, durable ingestion, replay idempotency, and
the MDARIX tenant partition counts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sqlalchemy import func

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.models.enterprise import ConnectorRun, ConnectorSourceRecord
from backend.app.db.models.foundation import Tenant
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from integration.simulator_ingestion import persist_provider_ingestion, read_provider
from source_simulator.provider_catalog import PROVIDER_CATALOG, PROVIDER_PORTS

TENANTS = {
    "R1_TENANT_1": ("TENANT_A", "sim-a"),
    "R1_TENANT_2": ("TENANT_B", "sim-b"),
    "R1_TENANT_3": ("TENANT_C", "sim-c"),
    "R1_TENANT_4": ("TENANT_D", "sim-d"),
}


def assert_provider_authentication() -> None:
    """A valid token works and a different tenant token is rejected."""
    url = f"http://127.0.0.1:{PROVIDER_PORTS['TRACKWISE']}/records/Complaint?tenant=TENANT_A"
    with urlopen(Request(url, headers={"X-Provider-Token": "sim-a"}), timeout=10) as response:
        body = json.loads(response.read().decode())
    assert body["tenant_key"] == "TENANT_A"
    try:
        urlopen(Request(url, headers={"X-Provider-Token": "sim-b"}), timeout=10)
    except HTTPError as error:
        assert error.code == 403
    else:
        raise AssertionError("provider accepted a token belonging to another tenant")


def main() -> int:
    assert_provider_authentication()
    matrix: list[dict[str, object]] = []
    with SessionLocal() as db:
        tenant_rows = {row.tenant_key: row for row in db.query(Tenant).filter(Tenant.tenant_key.in_(TENANTS)).all()}
        if set(tenant_rows) != set(TENANTS):
            raise RuntimeError(f"expected four validation tenants, found {sorted(tenant_rows)}")

        for tenant_key, (provider_tenant, token) in TENANTS.items():
            tenant = tenant_rows[tenant_key]
            for provider, entities in PROVIDER_CATALOG.items():
                entity = next(iter(entities))
                records = read_provider(provider, provider_tenant, token, entity)
                if not records:
                    raise AssertionError(f"no seeded records for {provider}/{entity}/{provider_tenant}")
                first = persist_provider_ingestion(
                    db,
                    tenant.id,
                    f"{provider.lower()}-{provider_tenant.lower()}",
                    provider,
                    entity,
                    records,
                    correlation_id=f"MVP-{tenant_key}-{provider}",
                )
                db.commit()
                replay = persist_provider_ingestion(
                    db,
                    tenant.id,
                    f"{provider.lower()}-{provider_tenant.lower()}",
                    provider,
                    entity,
                    records,
                    correlation_id=f"MVP-REPLAY-{tenant_key}-{provider}",
                )
                db.commit()
                if replay["accepted"] != 0 or replay["duplicates"] != len(records):
                    raise AssertionError(f"replay was not idempotent: {provider}/{entity}: {replay}")
                matrix.append(
                    {
                        "tenant": tenant_key,
                        "provider": provider,
                        "entity": entity,
                        "records": len(records),
                        "accepted": first["accepted"],
                        "replay_duplicates": replay["duplicates"],
                    }
                )

        counts = {}
        for tenant_key, tenant in tenant_rows.items():
            counts[tenant_key] = {
                "connector_runs": db.query(func.count(ConnectorRun.id))
                .filter(ConnectorRun.tenant_id == tenant.id)
                .scalar(),
                "source_records": db.query(func.count(ConnectorSourceRecord.id))
                .filter(ConnectorSourceRecord.tenant_id == tenant.id)
                .scalar(),
                "outbox_events": db.query(func.count(OutboxEvent.id))
                .filter(OutboxEvent.tenant_id == tenant.id)
                .scalar(),
            }

    print(
        json.dumps(
            {
                "status": "PASS",
                "tenants": list(TENANTS),
                "provider_matrix_rows": len(matrix),
                "provider_matrix": matrix,
                "durable_tenant_counts": counts,
                "checks": [
                    "provider token isolation",
                    "tenant-scoped provider reads",
                    "durable connector ingestion",
                    "replay/idempotency protection",
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
