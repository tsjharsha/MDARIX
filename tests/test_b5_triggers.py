"""B5 step 11: reopen triggers (closed_loop/triggers.py). The pure rule: each of the six triggers fires at its
condition and not below it. On the sample investigation (SAMPLE-INV-001), decided with SAMPLE-CAPA-02: a NOT_EFFECTIVE
check opens one impact assessment with its task and a REOPEN_TRIGGER_FIRED audit, and only once; a later serious-harm
complaint fires LATER_SERIOUS_HARM; on a customer case the sample complaints never count (R6); a superseded decision
fires nothing; the decision itself is never changed."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.closed_loop import triggers
from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
from backend.app.db.models.decision_outcomes import ImpactAssessment
from backend.app.db.models.foundation import AuditEvent, Capa, Complaint, Decision, Investigation
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.db.models.workflow import WorkflowTask
from tests.test_b5_loop_api import _read, _sign
from tests.test_free_trial import _approved_trial_client

D = date(2026, 6, 1)


# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = pytest.mark.requirement("B5-05", "B5-07")


def _complaint(ref, *, version="v1", lot=None, on=D, harm=False):
    return {"ref": ref, "id": ref, "version_id": version, "lot_id": lot, "event_on": on, "harm": harm}


def _view(**changes):
    view = {
        "decision": {"id": "d1"},
        "capas": [],
        "actions": [],
        "scope": {"new_versions": []},
        "field_actions": [],
        "later": {"complaints": [], "version_unknown": {"complaints": []}},
    }
    view.update(changes)
    return view


def _kinds(view):
    return [item["trigger"] for item in triggers.fired(view)]


@pytest.mark.unit
def test_nothing_signed_fires_nothing():
    assert triggers.fired({"decision": None}) == []
    assert _kinds(_view()) == []


@pytest.mark.unit
def test_capa_rounds():
    signed = datetime(2026, 5, 1, tzinfo=timezone.utc)
    capa = {
        "ref": "CAPA-1",
        "checks": [
            {"round": 1, "status": "NOT_EFFECTIVE", "signed_at": signed},
            {"round": 2, "status": "EFFECTIVE", "signed_at": signed},
            {"round": 3, "status": "PLANNED", "signed_at": None},
        ],
    }
    one = {"complaints": [_complaint("C1")], "version_unknown": {"complaints": []}}
    found = triggers.fired(_view(capas=[capa], later=one))
    assert [(item["trigger"], item["group"]) for item in found] == [("CAPA_NOT_EFFECTIVE", "CAPA-1 round 1")]
    # A version-unknown complaint counts as "again" too (it is the same product and problem).
    two = {"complaints": [_complaint("C1")], "version_unknown": {"complaints": [_complaint("C2", version=None)]}}
    found = triggers.fired(_view(capas=[capa], later=two))
    assert ("RECURRENCE_AFTER_EFFECTIVE", "CAPA-1 round 2") in [(item["trigger"], item["group"]) for item in found]
    # Complaints before the effective signature are not "again".
    early = {"complaints": [_complaint("C1", on=date(2026, 4, 1)), _complaint("C2", on=date(2026, 4, 2))]}
    early["version_unknown"] = {"complaints": []}
    assert "RECURRENCE_AFTER_EFFECTIVE" not in _kinds(_view(capas=[capa], later=early))


@pytest.mark.unit
def test_more_on_a_version_or_a_lot_cohort():
    def group(name, result):
        return {"name": name, "result": result, "before": 2, "after": 9, "after_complaints": [_complaint("C9")]}

    action = {
        "kind": "CAPA",
        "ref": "CAPA-1",
        "by_version": [group("Rev A", "NO_CHANGE"), group("Rev B", "MORE")],
        "lot_cohorts": group("Lots released after the action vs before", "MORE"),
    }
    found = triggers.fired(_view(actions=[action]))
    assert [item["group"] for item in found] == [
        "capa CAPA-1 · Rev B",
        "capa CAPA-1 · Lots released after the action vs before",
    ]
    assert found[0]["records"] == ["C9"] and "9 after" in found[0]["summary"]
    action["by_version"][1]["result"] = "FEWER"
    action["lot_cohorts"]["result"] = "TOO_EARLY"
    assert _kinds(_view(actions=[action])) == []


@pytest.mark.unit
def test_new_version_actioned_lot_and_serious_harm():
    new = {"new_versions": [{"id": "v2", "ref": "Rev C"}]}
    one = {"complaints": [_complaint("C1", version="v2")], "version_unknown": {"complaints": []}}
    assert _kinds(_view(scope=new, later=one)) == []
    two = {"complaints": [_complaint("C1", version="v2"), _complaint("C2", version="v2")]}
    two["version_unknown"] = {"complaints": []}
    assert _kinds(_view(scope=new, later=two)) == ["PROBLEM_ON_NEW_VERSION"]

    field = {"reference": "FSCA-7", "follow_up": "FU1", "lot_ids": ["L1"], "effective_on": D}
    on_lot = {"complaints": [_complaint("C1", lot="L1", on=D)], "version_unknown": {"complaints": []}}
    assert _kinds(_view(field_actions=[field], later=on_lot)) == []  # not after the effective date
    on_lot["complaints"][0]["event_on"] = D + timedelta(days=1)
    assert [item["group"] for item in triggers.fired(_view(field_actions=[field], later=on_lot))] == ["FSCA-7"]

    harm = {"complaints": [], "version_unknown": {"complaints": [_complaint("C5", version=None, harm=True)]}}
    found = triggers.fired(_view(later=harm))
    assert [(item["trigger"], item["group"]) for item in found] == [("LATER_SERIOUS_HARM", "C5")]


# ------------------------------------------------------------------------------------------------- the database


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = db.query(Investigation).filter(Investigation.investigation_identifier == "SAMPLE-INV-001").one()
        case.workflow_state = "DECIDED"
        db.commit()
        case_id = case.id
    try:
        yield {"user": user, "tenant_id": tenant_id, "case_id": case_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b5-triggers-cleanup")


def _sweep(trial) -> int:
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        made = triggers.sweep_tenant(db, db, trial["tenant_id"])
        db.commit()
        return made


def _assessments(trial, trigger=None):
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        query = db.query(ImpactAssessment).filter(ImpactAssessment.investigation_id == trial["case_id"])
        if trigger:
            query = query.filter(ImpactAssessment.trigger == trigger)
        return query.all()


@pytest.mark.db
def test_not_effective_opens_one_assessment_with_task_and_audit(trial):
    decided = datetime.now(timezone.utc) - timedelta(days=40)
    decision_id = _sign(trial, decided)
    assert _sweep(trial) == 0  # signed, CAPA too early: nothing fires
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        capa_id = db.query(Capa.id).filter(Capa.capa_identifier == "SAMPLE-CAPA-02").scalar()
        db.add(
            CapaEffectivenessCheck(
                tenant_id=trial["tenant_id"],
                capa_id=capa_id,
                round=1,
                status="NOT_EFFECTIVE",
                criteria="No pressure alarms on lots built after the change",
                planned_on=date.today(),
                measured_from=decided.date(),
                planned_by="test",
                result_summary="Pressure alarms continue",
                signed_by="test",
                signed_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    assert _sweep(trial) == 1
    assert _sweep(trial) == 0  # idempotent per decision, trigger and group
    (row,) = _assessments(trial, "CAPA_NOT_EFFECTIVE")
    assert row.status == "OPEN" and row.decision_id == decision_id and row.evidence_id is None
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        task = db.query(WorkflowTask).filter(WorkflowTask.id == row.task_id).one()
        assert task.task_type == "IMPACT_ASSESSMENT" and "SAMPLE-CAPA-02 round 1" in task.title
        (event,) = db.query(AuditEvent).filter(AuditEvent.action == "REOPEN_TRIGGER_FIRED").all()
        assert event.details["group"] == "SAMPLE-CAPA-02 round 1" and event.details["records"] == ["SAMPLE-CAPA-02"]
        decision = db.query(Decision).filter(Decision.id == decision_id).one()
        assert decision.decision_status == "SIGNED" and decision.superseded_by_decision_id is None
        case = db.query(Investigation).filter(Investigation.id == trial["case_id"]).one()
        assert case.workflow_state == "DECIDED"  # never reopened by the rule


@pytest.mark.db
def test_later_serious_harm_counts_on_the_sample_but_never_on_a_customer_case(trial):
    scope = _read(trial)["scope"]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        source = (
            db.query(Complaint)
            .filter(
                Complaint.problem_code == scope["problems"][0],
                Complaint.product_version_id == uuid.UUID(scope["versions"][0]["id"]),
            )
            .first()
        )
        values = {column.key: getattr(source, column.key) for column in Complaint.__table__.columns}
        values.pop("business_id")
        now = datetime.now(timezone.utc)
        values.update(
            id=uuid.uuid4(),
            complaint_identifier="TRIGGER-HARM-1",
            serious_injury=True,
            event_timestamp=now - timedelta(days=2),
            complaint_timestamp=now - timedelta(days=2),
            created_at=now,
        )
        db.add(Complaint(**values))
        case = db.query(Investigation).filter(Investigation.id == trial["case_id"]).one()
        sample_source = case.source_system
        case.source_system = None  # read as a customer's own case: the sample complaint must not count (R6)
        db.commit()
    assert _sweep(trial) == 0 and _assessments(trial, "LATER_SERIOUS_HARM") == []
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.query(Investigation).filter(Investigation.id == trial["case_id"]).one().source_system = sample_source
        db.commit()
    assert _sweep(trial) == 1 and _sweep(trial) == 0
    (row,) = _assessments(trial, "LATER_SERIOUS_HARM")
    assert row.trigger == "LATER_SERIOUS_HARM"


@pytest.mark.db
def test_a_superseded_decision_fires_nothing(trial):
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        old = db.query(Decision).filter(Decision.investigation_id == trial["case_id"]).one()
    new_id = _sign(trial, datetime.now(timezone.utc) - timedelta(hours=1), capa=False)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.query(Decision).filter(Decision.id == old.id).one().superseded_by_decision_id = new_id
        db.commit()
    before = len(_assessments(trial))
    # The CAPA round and the harm complaint belong to the old decision; the new one has neither.
    assert _sweep(trial) == 0 and len(_assessments(trial)) == before


@pytest.mark.db
def test_switched_off_the_sweep_does_nothing(trial, monkeypatch):
    monkeypatch.setenv("MDARIX_CLOSED_LOOP", "off")
    assert _sweep(trial) == 0
