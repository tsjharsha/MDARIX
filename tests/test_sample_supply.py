"""W1 (0.10.94), the sample's supply chain (backend/app/trial/sample_supply.py, spec 5.2 S1-S2) on a new free trial:
Rev A configurations (the OrbitCare sensor from Precision Sensors, NovaSense on Rev B), no change on any Rev A, the
inspection evidence on Supplier 360, idempotence, sample removal and the clock reaching the new rows, and the refresh
of a running trial adding only what is missing (P360-05 data, P360-13, S360-10, S360-11)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

ORBIT = "SAMPLE-ORBIT-300"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:sample-supply-cleanup")


def _session(tenant_id):
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    db = SessionLocal()
    bind_tenant(db, tenant_id)
    return db


def _suppliers_by_part(view) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for row in view["configuration"]["suppliers"]:
        found.setdefault(row["component_identifier"], []).append(row["name"])
    return found


def test_rev_a_has_its_own_configuration_and_rev_b_keeps_novasense(trial):
    user = trial["user"]
    rev_a = _ok(user.get(f"/api/v1/products/{ORBIT}/product-360", params={"version_id": "Rev A", "light": "1"}))
    rev_b = _ok(user.get(f"/api/v1/products/{ORBIT}/product-360", params={"version_id": "Rev B", "light": "1"}))
    a_parts = {(c["component_identifier"], c["revision"]) for c in rev_a["configuration"]["components"]}
    assert a_parts == {(f"{ORBIT}-C1", "Rev A"), (f"{ORBIT}-C2", "Rev B"), (f"{ORBIT}-C3", "Rev B")}
    assert [name[:9] for name in _suppliers_by_part(rev_a)[f"{ORBIT}-C1"]] == ["Precision"]
    assert [name[:9] for name in _suppliers_by_part(rev_b)[f"{ORBIT}-C1"]] == ["NovaSense"]
    sensor_a = next(s for s in rev_a["configuration"]["suppliers"] if s["component_identifier"] == f"{ORBIT}-C1")
    assert sensor_a["supplied_from"] < rev_b["selected_version"]["release_timestamp"]
    # The flagship SAMPLE-RV-11 is on PulseWatch Rev A: its product page has a configuration.
    pulse_a = _ok(
        user.get("/api/v1/products/SAMPLE-PULSE-410/product-360", params={"version_id": "Rev A", "light": "1"})
    )
    assert len(pulse_a["configuration"]["components"]) == 3
    # No Rev A lot gets a genealogy; no lot, complaint or change moves (the trend's numbers stay).
    assert all(lot["genealogy"] == [] for lot in rev_a["manufacturing"]["lots"])


def test_no_change_shows_on_any_rev_a(trial):
    from backend.app.db.models.foundation import ProductVersion
    from backend.app.signals.insight import version_changes

    db = _session(trial["tenant_id"])
    try:
        versions = {
            str(v.id): v.version_identifier
            for v in db.query(ProductVersion).filter(ProductVersion.tenant_id == trial["tenant_id"])
        }
        changes = version_changes(db, trial["tenant_id"], list(versions))
    finally:
        db.close()
    assert {versions[key] for key in changes} == {"Rev B"}
    assert [c["identifier"] for found in changes.values() for c in found] == ["SAMPLE-CHG-014"]


def test_novasense_lists_the_inspection_evidence_and_its_story(trial):
    page = _ok(trial["user"].get("/api/v1/suppliers/SAMPLE-SUP-B"))
    evidence = {row["evidence_identifier"]: row for row in page["evidence"]}
    assert set(evidence) == {"SAMPLE-EV-001", "SAMPLE-EV-002"}
    inspection = evidence["SAMPLE-EV-002"]
    assert inspection["title"].startswith("Incoming inspection results, lots 003-004")
    assert inspection["investigation_identifier"] == "SAMPLE-INV-001" and inspection["reliability_status"]
    assert inspection["basis"] == "Linked to the supplier and its part"
    # Still one version: the Rev A sensor is Precision's, not NovaSense's.
    assert page["pattern"]["case"] == "ONE_VERSION" and page["counts"]["versions"] == 1
    precision = _ok(trial["user"].get("/api/v1/suppliers/SAMPLE-SUP-A"))
    assert precision["counts"]["versions"] == 6 and precision["pattern"]["found"] is False


def test_the_seed_is_idempotent_and_removal_and_the_clock_reach_its_rows(trial):
    from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
    from backend.app.db.models.foundation import Component
    from backend.app.trial import sample_removal, sample_supply

    tenant_id = trial["tenant_id"]
    db = _session(tenant_id)
    try:
        now = datetime.now(timezone.utc)
        assert sample_supply.refresh(db, tenant_id, apply=False, now=now) == 0
        assert sample_supply.stage_sample_supply(db, tenant_id, now) == {"created": False, "rows": 0}
        sensor_a = (
            db.query(Component)
            .filter(Component.tenant_id == tenant_id, Component.component_identifier == f"{ORBIT}-C1")
            .filter(Component.revision == "Rev A")
            .one()
        )
        links = [
            row.id
            for row in db.query(EvidenceEntityLink).filter(
                EvidenceEntityLink.tenant_id == tenant_id, EvidenceEntityLink.entity_type.in_(["Supplier", "Component"])
            )
        ]
        assert len(links) == 4
        planned = sample_removal.plan(db, tenant_id, owned_only=True)["rows"]
        assert sensor_a.id in planned["components"]
        assert set(links) <= set(planned["evidence_entity_links"])
        assert len(planned["product_components"]) >= 9 + 9  # Rev B's nine and Rev A's nine
    finally:
        db.rollback()
        db.close()


def test_a_running_trial_gets_only_the_missing_rows(trial):
    from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
    from backend.app.db.models.foundation import ProductComponent, ProductVersion
    from backend.app.trial import sample_supply

    tenant_id = trial["tenant_id"]
    db = _session(tenant_id)
    try:
        rev_a = [
            v.id
            for v in db.query(ProductVersion).filter(
                ProductVersion.tenant_id == tenant_id, ProductVersion.version_identifier == "Rev A"
            )
        ]
        one_link = db.query(ProductComponent).filter(ProductComponent.product_version_id.in_(rev_a)).first()
        one_evidence = (
            db.query(EvidenceEntityLink)
            .filter(EvidenceEntityLink.tenant_id == tenant_id, EvidenceEntityLink.entity_type == "Supplier")
            .first()
        )
        db.delete(one_link)
        db.delete(one_evidence)
        db.flush()
        now = datetime.now(timezone.utc)
        assert sample_supply.refresh(db, tenant_id, apply=False, now=now) == 2
        assert sample_supply.refresh(db, tenant_id, apply=True, now=now) == 2
        assert sample_supply.refresh(db, tenant_id, apply=False, now=now) == 0
        db.commit()
    finally:
        db.close()
