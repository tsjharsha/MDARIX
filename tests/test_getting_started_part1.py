"""0.10.93 (B2 step 7, spec 4.8, 9.3, OD-2): Getting started Part 1 on persisted records.

- The sample's SAMPLE-CASE-11 is the call behind SAMPLE-RV-11, unsigned, with its answers pre-filled (Q6 Unknown).
- Step 1 ticks only once all nine answers are saved by a person; step 2 once that Case check is signed and the Case
  escalated (attached) to the complaint. The duplicate rule finds RV-11 at signing; RV-11 is on the fast track.
- A trial whose RV-11 was already triaged reads steps 1 and 2 as done (progress never goes backwards).
- Branches: a pending Case keeps step 2 open, waiting for the reporter; an inquiry skips steps 3 to 8 ("Not needed:
  not a complaint") with the QA review; an imported complaint with no Case is "Classified in your QMS".
- The refresh step adds SAMPLE-CASE-11 once (idempotent). Progress reads the same after signing out and in (B2-10).
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

STORY = "/api/v1/trial/one-story"
INTAKE = "/api/v1/intake"
CASE_11 = "SAMPLE-CASE-11"
# Spec 4.8: Q6 Unknown is the one question left for the person.
SEEDED = dict(Q1="YES", Q2="YES", Q3="YES", Q4="NO", Q5="NO", Q6="UNKNOWN", Q7="NO", Q8="YES", Q9="NO")


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _data(tenant_id):
    db = SessionLocal()
    bind_tenant(db, tenant_id)
    return db


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:getting-started-part1-cleanup")


def _done(run: dict) -> list[str]:
    return [step["key"] for step in run["steps"] if step["done"]]


def _answers(**given) -> dict:
    return {question: {"answer": answer} for question, answer in given.items()}


def _save(user, event_id: str, answers: dict) -> dict:
    version = _ok(user.get(f"{INTAKE}/{event_id}"))["version"]
    return _ok(user.put(f"{INTAKE}/{event_id}/check", json={"answers": answers, "seen_version": version}))


def _sign(user, event_id: str, classification: str, **extra):
    version = _ok(user.get(f"{INTAKE}/{event_id}"))["version"]
    body = {"classification": classification, "seen_version": version, "password": PASSWORD, **extra}
    return user.post(f"{INTAKE}/{event_id}/check/sign", json=body)


@pytest.fixture(scope="module")
def sample():
    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield SimpleNamespace(user=user, tenant_id=tenant_id, email=email)
    finally:
        _purge(tenant_id)


def test_the_seed_adds_sample_case_11_unsigned_from_rv11s_own_facts(sample):
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
    from backend.app.db.models.workflow import WorkflowTask

    with _data(sample.tenant_id) as db:
        rv11 = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == sample.tenant_id, Complaint.complaint_identifier == "SAMPLE-RV-11")
            .one()
        )
        case = (
            db.query(IntakeEvent)
            .filter(IntakeEvent.tenant_id == sample.tenant_id, IntakeEvent.reference == CASE_11)
            .one()
        )
        assert (case.product_id, case.product_version_id, case.lot_batch_id) == (
            rv11.product_id,
            rv11.product_version_id,
            rv11.lot_batch_id,
        )
        assert case.country == "US" and case.source_system == "MDARIX_SAMPLE" and case.status == "OPEN"
        # The same event day; received when RV-11's awareness starts, so no awareness conflict.
        assert case.event_at == rv11.event_timestamp
        assert case.received_at == case.awareness_at == rv11.awareness_timestamp
        assert case.complaint_id is None
        (check,) = db.query(FirstContactCheck).filter(FirstContactCheck.intake_event_id == case.id).all()
        assert check.signed_at is None and check.suggestion == "BOTH" and check.guide_version == "case-check-starter-2"
        assert {question: item["answer"] for question, item in check.answers.items()} == SEEDED
        # No task: day 0 stays calm.
        assert (
            db.query(WorkflowTask)
            .filter(WorkflowTask.tenant_id == sample.tenant_id, WorkflowTask.source_entity_id == case.id)
            .count()
            == 0
        )
    story = _ok(sample.user.get(STORY))
    run = story["sample"]
    assert run["case"]["ref"] == CASE_11 and run["current"] == 0 and _done(run) == []
    assert [step["label"] for step in run["steps"][:2]] == ["Review the case", "Classify service or complaint"]
    # More cases to try: the other sample calls, with their outcome as the record says (records never renamed).
    more = {item["ref"]: item["label"] for item in story["more_cases"]}
    assert list(more) == ["SAMPLE-CALL-01", "SAMPLE-CALL-03", "SAMPLE-CALL-04", "SAMPLE-URG-01", "SAMPLE-RT-01"]
    assert more["SAMPLE-RT-01"] == "Routine: resolve and close"  # B7a: the routine complaint, one screen
    assert more["SAMPLE-CALL-03"] == "Pending" and more["SAMPLE-CALL-04"] == "Pending: confirm no deficiency"
    assert more["SAMPLE-URG-01"].startswith("Urgent")
    # CASE-11's own triage item raises no alert while it stands apart: RV-11's item already does (day 0 calm).
    bell = _ok(sample.user.get("/api/v1/oversight/alerts"))["items"]
    assert not any(item["ref"] == CASE_11 for item in bell)


def test_step_1_ticks_only_once_all_nine_answers_are_saved(sample):
    case_id = _ok(sample.user.get(STORY))["sample"]["case"]["id"]
    # Question 6 left unanswered: saved, but not every question is answered.
    partial = {key: value for key, value in _answers(**SEEDED).items() if key != "Q6"}
    _save(sample.user, case_id, partial)
    run = _ok(sample.user.get(STORY))["sample"]
    assert _done(run) == [] and run["current"] == 0
    # All nine saved; question 6 answered Yes ("a reading 4 to 6 points high could hide low oxygen").
    _save(sample.user, case_id, _answers(**{**SEEDED, "Q6": "YES"}))
    run = _ok(sample.user.get(STORY))["sample"]
    assert _done(run) == ["case"] and run["current"] == 1
    assert run["steps"][1]["note"] is None


def test_step_2_ticks_once_signed_and_attached_to_rv11_which_goes_to_the_fast_track(sample):
    user = sample.user
    run = _ok(user.get(STORY))["sample"]
    case_id, rv11 = run["case"]["id"], run["complaint"]["id"]
    # The duplicate rule finds RV-11 first, the only match on the case's event day: the escalation panel pre-selects
    # "Attach this case to SAMPLE-RV-11" (RT-02, the same lot and country three days earlier, is offered too).
    refused = _ok(_sign(user, case_id, "BOTH"), 422)["detail"]
    assert refused["code"] == "DUPLICATE_CHOICE_NEEDED"
    candidates = refused["candidates"]
    assert candidates[0]["ref"] == "SAMPLE-RV-11" and candidates[0]["same_day"] is True
    assert [item["ref"] for item in candidates if item["same_day"]] == ["SAMPLE-RV-11"]
    assert _ok(user.get(STORY))["sample"]["current"] == 1
    _ok(_sign(user, case_id, "BOTH", attach_to=rv11))
    run = _ok(user.get(STORY))["sample"]
    assert _done(run) == ["case", "classify"] and run["current"] == 2
    # The story stays on RV-11 and its Case (found by the escalation now).
    assert run["complaint"]["ref"] == "SAMPLE-RV-11" and run["case"]["ref"] == CASE_11
    assert run["case"]["classification"] == "BOTH" and run["case"]["state"] == "ESCALATED"
    # RV-11 shows "From case SAMPLE-CASE-11".
    assert _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-11"))["case"]["reference"] == CASE_11
    # TR-41: RV-11 (with its Case, one item) is on the fast track.
    items = _ok(user.get("/api/v1/triage"))["items"]
    (item,) = [i for i in items if "SAMPLE-RV-11" in {i["ref"], *(x["ref"] for x in i["linked"])}]
    assert item["speed"] == "FAST"
    # Now one item, it alerts again under its own reference.
    assert any(
        row["ref"] in (CASE_11, "SAMPLE-RV-11") and row["category"] == "TRIAGE"
        for row in _ok(user.get("/api/v1/oversight"))["items"]
    )
    # Its More cases to try does not offer CASE-11 (it is a complaint now).
    assert CASE_11 not in {item["ref"] for item in _ok(user.get(STORY))["more_cases"]}


def test_progress_reads_the_same_after_signing_out_and_in(sample):
    before = _ok(sample.user.get(STORY))
    _ok(sample.user.post("/api/v1/auth/signout"))
    assert sample.user.get(STORY).status_code == 401
    again = TestClient(sample.user.app)
    _ok(again.post("/api/v1/auth/signin", json={"email": sample.email, "password": PASSWORD}))
    after = _ok(again.get(STORY))
    assert after["sample"]["steps"] == before["sample"]["steps"]
    assert after["sample"]["current"] == before["sample"]["current"] == 2


def _refresh_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "refresh_trial_story.py"
    spec = importlib.util.spec_from_file_location("refresh_trial_story_0_10_93", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_trial_triaged_before_0_10_93_reads_steps_1_and_2_done_and_the_refresh_adds_case_11_once(monkeypatch):
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
    from tests.test_release_c3_0_10_75 import _flagship

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        # A trial running before 0.10.93: no CASE-11 yet, RV-11 already triaged.
        with _data(tenant_id) as db:
            case = (
                db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == CASE_11).one()
            )
            db.query(FirstContactCheck).filter(FirstContactCheck.intake_event_id == case.id).delete()
            db.delete(case)
            db.commit()
        _flagship(user)
        run = _ok(user.get(STORY))["sample"]
        assert run["case"] is None and run["steps"][0]["skipped"]
        refresh = _refresh_module()
        with SessionLocal() as db:
            key, name = db.query(Tenant.tenant_key, Tenant.name).filter(Tenant.id == tenant_id).one()
        monkeypatch.setattr(refresh, "trials", lambda db: [(tenant_id, key, name)])
        with SessionLocal() as db:
            (listed,) = refresh.refresh(db, apply=False)
        assert listed["result"] == "would add SAMPLE-CASE-11, the call behind SAMPLE-RV-11, unsigned (0.10.93)"
        with _data(tenant_id) as db:
            assert (
                db.query(IntakeEvent)
                .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == CASE_11)
                .count()
                == 0
            )
        with SessionLocal() as db:
            (added,) = refresh.refresh(db, apply=True)
        assert "'story_case': 1" in added["result"]
        with SessionLocal() as db:
            (again,) = refresh.refresh(db, apply=True)
        assert again["result"] == "already has the story"
        with _data(tenant_id) as db:
            assert (
                db.query(IntakeEvent)
                .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == CASE_11)
                .count()
                == 1
            )
        # Later work on RV-11 (its triage) says steps 1 and 2 were taken: progress never goes backwards.
        story = _ok(user.get(STORY))
        run = story["sample"]
        assert _done(run) == ["case", "classify", "triage"] and run["current"] == 3
        # CASE-11, unsigned, sits under More cases to try.
        assert CASE_11 in {item["ref"] for item in story["more_cases"]}
    finally:
        _purge(tenant_id)


CSV = (
    "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
    "serious_injury,death,malfunction\n"
    "P1-1001,P1-NEB,The customer asked how to clean the mask.,2026-10-28,2026-10-29,2026-10-29,US,N,N,N,N\n"
)


def test_your_data_branches_pending_waits_and_an_inquiry_skips_to_the_qa_review():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _ok(user.post("/api/v1/data/import/complaints?file_name=own.csv", content=CSV.encode()))
        yours = _ok(user.get(STORY))["yours"]
        # No Case behind the imported complaint: steps 1 and 2 are classified in your QMS.
        assert yours["case"] is None
        assert [step["note"] for step in yours["steps"][:2]] == ["Classified in your QMS"] * 2
        # "Check it as a case" opens a Case check linked to it; the story now reads that Case.
        case_id = _ok(user.post(f"{INTAKE}/from-complaint/{yours['complaint']['id']}"))["id"]
        yours = _ok(user.get(STORY))["yours"]
        assert yours["case"]["id"] == case_id and yours["current"] == 0
        # Pending: step 2 stays open, waiting for the reporter, with its owner and due date.
        unknown = dict(Q1="NO", Q2="NO", Q3="NO", Q4="UNKNOWN", Q5="NO", Q6="NO", Q7="NO", Q8="NO", Q9="NO")
        _save(user, case_id, _answers(**unknown))
        _ok(_sign(user, case_id, "PENDING"))
        yours = _ok(user.get(STORY))["yours"]
        assert _done(yours) == ["case"] and yours["current"] == 1
        note = yours["steps"][1]["note"]
        assert note.startswith("Waiting for the reporter · ") and " · due " in note and "No owner" not in note
        # The reporter answered: only information was asked for. An inquiry skips the reporting steps.
        inquiry = dict(Q1="NO", Q2="NO", Q3="NO", Q4="NO", Q5="NO", Q6="NO", Q7="YES", Q8="NO", Q9="NO")
        _save(user, case_id, _answers(**inquiry))
        _ok(_sign(user, case_id, "INQUIRY", reason="The customer only asked how to clean the mask."))
        yours = _ok(user.get(STORY))["yours"]
        assert _done(yours) == ["case", "classify"] and yours["current"] == 8
        assert [step["skipped"] for step in yours["steps"][2:8]] == [True] * 6
        assert {step["note"] for step in yours["steps"][2:8]} == {"Not needed: not a complaint"}
        assert yours["branch"]["label"] == "QA review" and yours["branch"]["who"] == "Quality Leader"
        assert yours["branch"]["done"] is False
        # The check of an imported record is its second look: an inquiry dismisses it, never confirms a complaint.
        from backend.app.db.models.complaint_review import ComplaintSecondLook

        with _data(tenant_id) as db:
            look = db.query(ComplaintSecondLook).filter_by(complaint_id=uuid.UUID(yours["complaint"]["id"])).one()
            assert look.decision == "DISMISSED"
    finally:
        _purge(tenant_id)


@pytest.mark.unit
def test_the_branch_rules_on_their_own():
    from backend.app.trial.one_story import step_notes, steps_done

    # Signed service only: steps 3-8 not needed, records and trends still to do.
    service = {"answered": True, "classification": "SERVICE_ONLY", "escalated": False}
    done = steps_done({}, False, [], None, case=service)
    assert done == [True, True, *["skip"] * 6, False, False]
    assert step_notes(done, service, None)[2:8] == ["Not needed: not a complaint"] * 6
    # Pending: step 2 open with what it waits for.
    pending = {"answered": True, "classification": "PENDING", "escalated": False}
    done = steps_done({}, False, [], None, case=pending)
    assert done[:3] == [True, False, False]
    assert step_notes(done, pending, "Waiting for the reporter · A · due 1 Dec 2026")[1].startswith("Waiting")
    # Signed a complaint but not escalated yet (signed before 0.10.93): step 2 waits for the escalation.
    assert steps_done({}, False, [], None, case={**pending, "classification": "BOTH"})[:2] == [True, False]
    # Saved by nobody yet (the sample's pre-filled answers): step 1 open.
    assert steps_done({}, False, [], None, case={"answered": False, "classification": None})[:2] == [False, False]
    # Later work on the complaint ticks steps 1 and 2 whatever the Case says (never backwards).
    assert steps_done({}, True, [], None, case={"answered": False, "classification": None})[:3] == [True] * 3
    # No Case: classified in your QMS.
    done = steps_done({}, False, [], None, case=None)
    assert done[:2] == ["skip", "skip"] and step_notes(done, None, None)[:2] == ["Classified in your QMS"] * 2
