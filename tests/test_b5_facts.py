"""B5 step 2: the facts of an investigation (spec 2.2). The sample case reads as the sample tells it; PV-1 holds: a
complaint with no version stays "version unknown", a complaint's lot never lends it a version; units shipped, released
and unknown are told apart; change dates are kept."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.case_challenge import facts as facts_module
from backend.app.db.models.foundation import Complaint, Investigation, InvestigationComplaint, LotBatch, ProductVersion
from backend.app.db.models.lot_impact import LotDistribution
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    _, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield tenant_id
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b5-facts-cleanup")


def _case(db, tenant_id, ref="SAMPLE-INV-001"):
    return (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == ref)
        .one()
    )


def test_the_sample_case_reads_as_the_sample_tells_it(trial):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, trial)
        facts = facts_module.read(db, _case(db, trial), now)
    versions = {item["ref"]: item for item in facts["versions"].values()}
    rev_a, rev_b = versions["Rev A"], versions["Rev B"]
    assert rev_b["in_scope"] and not rev_a["in_scope"]
    assert rev_b["predecessor_id"] == rev_a["id"]
    # Every scope complaint is on Rev B (the sample links those after the Rev B release), each with its own lot.
    assert facts["complaints"] and all(item["version_id"] == rev_b["id"] for item in facts["complaints"])
    assert all(item["lot_id"] and item["problem"] == "PRESSURE_ALARM" for item in facts["complaints"])
    assert facts["problems"] == ["PRESSURE_ALARM"]
    # The same problem on Rev A is read outside the scope, never added to it.
    assert facts["outside"] and {item["version_id"] for item in facts["outside"]} <= {rev_a["id"], rev_b["id"]}
    assert any(item["version_id"] == rev_a["id"] for item in facts["outside"])
    (change,) = [item for item in facts["changes"] if item["ref"] == "SAMPLE-CHG-014"]
    assert change["version_ids"] == [rev_b["id"]] and change["effective_on"] == (now - timedelta(days=80)).date()
    sensor = facts["components"][change["component_ids"][0]]
    assert [s["name"] for s in sensor["suppliers"]] == ["NovaSense Components (Sample)"]
    # Rev A is built without the changed sensor, with the earlier supplier's part.
    assert rev_a["components"] and sensor["id"] not in rev_a["components"]
    rev_a_suppliers = {s["name"] for c in rev_a["components"] for s in facts["components"][c]["suppliers"]}
    assert "Precision Sensors Ltd (Sample)" in rev_a_suppliers
    lots = {item["ref"].rsplit("-", 1)[-1]: item for item in facts["lots"].values()}
    assert lots["003"]["version_id"] == rev_b["id"] and lots["003"]["units_released"] == 150
    assert len(facts["hypotheses"]) == 2 and all(item["draft_rule"] is None for item in facts["hypotheses"])
    assert len(facts["unknowns"]) == 2 and all(item["open"] for item in facts["unknowns"])
    assert all(item["origin"] == "SAMPLE" for item in facts["complaints"])
    assert facts["conclusion"] and "NovaSense" in facts["conclusion"]
    assert len(facts_module.fingerprint(facts)) == 16


def test_pv1_unknown_version_kept_apart_and_lot_never_lends_a_version(trial):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, trial)
        sample = _case(db, trial)
        rev_b = (
            db.query(ProductVersion)
            .filter(ProductVersion.tenant_id == trial, ProductVersion.product_id == sample.product_id)
            .filter(ProductVersion.version_identifier == "Rev B")
            .one()
        )
        # A Rev B lot with no units released recorded, shipped 40 units.
        lot = LotBatch(
            id=uuid.uuid4(),
            tenant_id=trial,
            lot_identifier=f"B5-LOT-{uuid.uuid4().hex[:6]}",
            product_version_id=rev_b.id,
            created_at=now,
            updated_at=now,
        )
        db.add(lot)
        case = Investigation(
            id=uuid.uuid4(),
            tenant_id=trial,
            product_id=sample.product_id,
            investigation_identifier=f"B5-FACTS-{uuid.uuid4().hex[:6]}",
            investigation_question="Why do these alarms happen?",
            created_at=now,
            updated_at=now,
        )
        db.add(case)
        db.flush()
        stamp = {"created_at": now, "updated_at": now}
        rows = [
            # A complaint naming a Rev B lot but no version: it stays "version unknown".
            Complaint(
                id=uuid.uuid4(),
                tenant_id=trial,
                complaint_identifier=f"B5-C1-{uuid.uuid4().hex[:6]}",
                product_id=sample.product_id,
                product_version_id=None,
                lot_batch_id=lot.id,
                event_timestamp=now - timedelta(days=3),
                description="x",
                problem_code="PRESSURE_ALARM",
                **stamp,
            ),
            Complaint(
                id=uuid.uuid4(),
                tenant_id=trial,
                complaint_identifier=f"B5-C2-{uuid.uuid4().hex[:6]}",
                product_id=sample.product_id,
                product_version_id=None,
                lot_batch_id=None,
                complaint_timestamp=now - timedelta(days=2),
                description="x",
                problem_code="No fault found",
                **stamp,
            ),
        ]
        db.add_all(rows)
        db.flush()
        for row in rows:
            db.add(
                InvestigationComplaint(
                    id=uuid.uuid4(), tenant_id=trial, investigation_id=case.id, complaint_id=row.id, created_at=now
                )
            )
        db.add(
            LotDistribution(
                tenant_id=trial,
                lot_batch_id=lot.id,
                consignee="Ward 1",
                country="US",
                quantity=40,
                ship_date=date.today(),
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
        facts = facts_module.read(db, case, now)
        lot_id, refs = str(lot.id), [row.complaint_identifier for row in rows]
        db.rollback()
    by_ref = {item["ref"]: item for item in facts["complaints"]}
    first, second = by_ref[refs[0]], by_ref[refs[1]]
    assert first["version_id"] is None and first["lot_id"] == lot_id
    assert second["version_id"] is None and second["lot_id"] is None
    # The event date falls back to the complaint date; the NFF code is read from the code, not from text.
    assert second["event_on"] == (now - timedelta(days=2)).date() and second["code_class"] == "NO_FAULT_FOUND"
    assert facts["scope_version"] == 0 and not any(v["in_scope"] for v in facts["versions"].values())
    shipped = facts["lots"][lot_id]
    assert shipped["units_shipped"] == 40 and shipped["units_released"] is None
    released_only = [item for item in facts["lots"].values() if item["units_shipped"] is None]
    assert released_only and all(item["units_released"] for item in released_only)
    assert len(facts_module.by_version(facts["complaints"])[None]) == 2
