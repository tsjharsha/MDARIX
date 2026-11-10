"""Adversarial cross-tenant reads on real PostgreSQL under the runtime role (row-level security on), H1 / DB-14.

Tenant A's people ask for Tenant B's complaints, investigations, evidence (and its download), CAPAs, exports, audit
trail and signed decisions: by id, through list filters and through every export. Each answer is a refusal (403/404)
or carries none of Tenant B's data. The requests run as ``mdarix_runtime`` (tests/runtime_role.py), so this checks
the database's own isolation as production runs it, not only the application's filters.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db.models.foundation import Tenant
from backend.app.db.models.stage2 import TenantExport
from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.trial.sample_data import seed_story_examples
from tests.runtime_role import runtime_role_requests  # noqa: F401 (fixture)
from tests.test_cross_tenant_routes import tenants  # noqa: F401 (fixture: Tenant A's investigator, Tenant B's data)
from tests.test_export_purge_mfa import _enrolled_client

pytestmark = pytest.mark.db

# Tenant B's records asked for by id: each must be refused.
BY_ID = [
    "/api/v1/complaints/{complaint_id}/disposition",
    "/api/v1/complaints/{complaint_id}/market-assessments",
    "/api/v1/oversight/events/{complaint_id}",
    "/api/v1/oversight/events/{complaint_id}/decision-record.pdf",
    "/api/v1/investigations/{investigation_id}/workspace",
    "/api/v1/investigations/{investigation_id}/decision-brief",
    "/api/v1/investigations/{investigation_id}/trust/export",
    "/api/v1/stage3/investigations/{investigation_id}/record",
    "/api/v1/story/{investigation_id}",
    "/api/v1/evidence/{evidence_id}",
    "/api/v1/evidence/{evidence_id}/content",
    "/api/v1/investigations/{investigation_id}/evidence/{evidence_id}/provenance",
    "/api/v1/capas/{capa_id}/effectiveness",
    "/api/v1/investigations/decisions/{decision_id}",
    "/api/v1/governance/decisions/{decision_id}/signature-history",
    "/api/v1/governance/decisions/{decision_id}/signature-verification",
]
# Asked by id, these answer 200 with nothing, by design (reviewed): still never a single value of Tenant B.
EMPTY_ANSWER = {
    "/api/v1/story/{investigation_id}": "the story screen's own empty state: status NOT_FOUND in the body",
    "/api/v1/governance/decisions/{decision_id}/signature-history": "a list filtered by organization: []",
}
# Lists and exports, with Tenant B's ids as filters: they may answer, but never with Tenant B's data.
LISTS = [
    "/api/v1/complaints?product_id={product_id}&investigation_id={investigation_id}",
    "/api/v1/complaints/backlog",
    "/api/v1/complaints/dispositions",
    "/api/v1/evidence?investigation_id={investigation_id}&product_id={product_id}",
    "/api/v1/products/{product_id}/investigations",
    "/api/v1/data-plane/investigations",
    "/api/v1/data-plane/evidence",
    "/api/v1/data-plane/capas",
    "/api/v1/data-plane/search?q=SAMPLE",
    "/api/v1/capas/effectiveness",
    "/api/v1/oversight/latest-signed",
    "/api/v1/documents",
    "/api/v1/oversight/export.csv",
    "/api/v1/risk/export.csv",
    "/api/v1/data-plane/export.csv",
]
# The organization's administrator: audit trail and exports.
ADMIN_BY_ID = ["/api/v1/admin/exports/{export_id}/download"]
ADMIN_LISTS = [
    "/api/v1/admin/audit-history",
    "/api/v1/admin/audit-history?entity_type=Investigation",
    "/api/v1/admin/audit-history/export",
    "/api/v1/admin/audit-chain",
    "/api/v1/admin/exports",
]


@pytest.fixture(scope="module")
def world(tenants):  # noqa: F811
    """Tenant B's CAPA, finished export and audit event, and Tenant A's administrator, beside ``tenants``."""
    b_ids = dict(tenants["b_ids"])
    tenant_b = uuid.UUID(b_ids["tenant_id"])
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        if db.execute(text("SELECT 1 FROM capas WHERE tenant_id = :t"), {"t": tenant_b}).first() is None:
            seed_story_examples(db, tenant_b, now)
        export = TenantExport(
            id=uuid.uuid4(),
            tenant_id=tenant_b,
            requested_by="someone@tenant-b.invalid",
            reason="Tenant B export",
            status="DONE",
            object_key=f"exports/{tenant_b}/x.zip",
            created_at=now,
            completed_at=now,
            expires_at=now + timedelta(days=1),
        )
        db.add(export)
        db.commit()
        b_ids["capa_id"] = str(db.execute(text("SELECT id FROM capas WHERE tenant_id = :t"), {"t": tenant_b}).scalar())
        b_ids["export_id"] = str(export.id)
        audit = db.execute(text("SELECT id FROM audit_events WHERE tenant_id = :t LIMIT 1"), {"t": tenant_b}).scalar()
        tenant_a = (
            db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        )
        tenant_a_id = str(tenant_a.id)
    markers = set(tenants["markers"]) | {b_ids["capa_id"], b_ids["export_id"]} | ({str(audit)} if audit else set())
    return {"b_ids": b_ids, "markers": markers, "token": tenants["token"], "tenant_a": tenant_a_id}


def _empty(body) -> bool:
    return body == [] or (isinstance(body, dict) and body.get("status") == "NOT_FOUND")


def _leaks(client: TestClient, paths: list[str], world: dict, *, refuse: bool) -> list[str]:
    problems = []
    for path in paths:
        url = path.format(**world["b_ids"])
        response = client.get(url)
        found = sorted(marker for marker in world["markers"] if marker and marker in response.text)
        if response.status_code >= 500:
            problems.append(f"{path} -> {response.status_code}")
        elif refuse and response.status_code not in (403, 404) and path not in EMPTY_ANSWER:
            problems.append(f"{path} -> {response.status_code}, expected a refusal")
        elif path in EMPTY_ANSWER and response.status_code < 400 and not _empty(response.json()):
            problems.append(f"{path} -> {response.status_code}, expected an empty answer")
        elif response.status_code < 400 and set(found) - {value for value in world["b_ids"].values() if value in url}:
            problems.append(f"{path} -> {response.status_code} contains {found[:3]}")
    return problems


def test_tenant_a_reads_nothing_of_tenant_b_under_row_level_security(world, runtime_role_requests):  # noqa: F811
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("mdarix_session", world["token"])
    problems = _leaks(client, BY_ID, world, refuse=True) + _leaks(client, LISTS, world, refuse=False)
    assert problems == [], "Tenant B reached Tenant A:\n" + "\n".join(problems)


def test_tenant_a_administrator_reads_no_audit_or_export_of_tenant_b(world, runtime_role_requests):  # noqa: F811
    admin, _ = _enrolled_client("CUSTOMER_ADMIN", world["tenant_a"])
    problems = _leaks(admin, ADMIN_BY_ID, world, refuse=True) + _leaks(admin, ADMIN_LISTS, world, refuse=False)
    assert problems == [], "Tenant B reached Tenant A's administrator:\n" + "\n".join(problems)


def test_the_markers_are_tenant_b_data(world):
    """Guard against a vacuous pass: the ids are Tenant B's real rows."""
    with SessionLocal() as db:
        tenant_b = uuid.UUID(world["b_ids"]["tenant_id"])
        for table, key in (("capas", "capa_id"), ("tenant_exports", "export_id"), ("complaints", "complaint_id")):
            row = db.execute(text(f"SELECT tenant_id FROM {table} WHERE id = :i"), {"i": world["b_ids"][key]}).first()
            assert row is not None and row[0] == tenant_b, table
