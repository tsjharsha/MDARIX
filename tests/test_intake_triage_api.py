"""0.10.57 through the API, as the trial user, with migration tr04's tables: the first-contact check (T-G32), urgent
intake with the awareness rule and the triage flag (T-G19), duplicates and import history (T-G20), each against its
acceptance lines (TA-32.x, TA-19.x, TA-20.x, TA-R14.2), with tenant isolation and sample removal."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, RecordFieldChange, RecordLink, TriageRecord
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

INTAKE = "/api/v1/intake"
TRIAGE = "/api/v1/triage"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:intake-cleanup")


def _by_ref(user) -> dict:
    return {item["reference"]: item for item in _ok(user.get(INTAKE))["items"]}


def _triage(user, show: str = "open") -> dict:
    return {item["ref"]: item for item in _ok(user.get(TRIAGE, params={"show": show}))["items"]}


def _all_no(**given) -> dict:
    found = {f"Q{n}": {"answer": "NO"} for n in range(1, 10)}
    found.update({key: {"answer": value} if isinstance(value, str) else value for key, value in given.items()})
    return found


def _log(user, **extra):
    body = {
        "kind": "CONTACT",
        "reporter_words": "Caller reports the pump alarmed twice during the night shift.",
        "answers": _all_no(),
    }
    body.update(extra)
    return _ok(user.post(INTAKE, json=body))


def _sign(user, event: dict, classification: str, **extra):
    body = {"classification": classification, "seen_version": event["version"], "password": PASSWORD, **extra}
    return user.post(f"{INTAKE}/{event['id']}/check/sign", json=body)


def test_each_sample_contact_reaches_its_outcome_by_the_table(trial):  # TA-32.1
    found = _by_ref(trial["user"])
    assert found["SAMPLE-CALL-01"]["signed"]["classification"] == "SERVICE_ONLY"
    assert found["SAMPLE-CALL-01"]["state"] == "review"
    assert found["SAMPLE-CALL-02"]["signed"]["classification"] == "BOTH"
    assert found["SAMPLE-CALL-03"]["suggestion"] == "PENDING" and found["SAMPLE-CALL-03"]["flagged"]
    assert found["SAMPLE-CALL-04"]["suggestion"] == "PENDING_CONFIRM" and not found["SAMPLE-CALL-04"]["flagged"]
    assert found["SAMPLE-URG-01"]["kind"] == "URGENT" and found["SAMPLE-URG-01"]["qms_task"]["state"] == "OPEN"
    # Each Unknown raises a dated follow-up with the reporter (until T-G30).
    follow_up = [task for task in found["SAMPLE-CALL-03"]["tasks"] if task["type"] == "FIRST_CONTACT_FOLLOW_UP"]
    assert follow_up and follow_up[0]["open"] and follow_up[0]["due_at"]
    review = [task for task in found["SAMPLE-CALL-01"]["tasks"] if task["type"] == "SERVICE_ONLY_REVIEW"]
    assert review and review[0]["open"]


def test_an_unknown_on_question_5_raises_the_triage_flag_before_signing(trial):  # TA-32.2
    user = trial["user"]
    event = _log(user, answers=_all_no(Q5="UNKNOWN"), reporter_words="Caller unsure whether anyone was hurt by it.")
    assert event["flagged"] and event["signed"] is None and event["suggestion"] == "PENDING"
    item = _triage(user)[event["reference"]]
    assert item["tier"] == "FLAGGED" and any(flag["code"] == "FIRST_CONTACT" for flag in item["flags"])


def test_service_only_is_never_offered_with_not_stated(trial):  # TA-32.3
    user = trial["user"]
    event = _log(
        user,
        answers=_all_no(Q7="YES", Q4="NOT_STATED"),
        reporter_words="Hospital asked for the calibration schedule of the pump.",
    )
    assert event["suggestion"] == "PENDING"
    refused = _sign(user, event, "SERVICE_ONLY", reason="Calibration schedule request only.")
    assert refused.status_code == 422 and "only when the answers give it" in refused.json()["detail"]["message"]


def test_a_reclassified_contact_keeps_the_contact_time_as_awareness(trial):  # TA-32.4
    user = trial["user"]
    contact_time = datetime.now(timezone.utc) - timedelta(hours=6)
    event = _log(
        user,
        answers=_all_no(Q7="YES"),
        received_at=contact_time.isoformat(),
        reporter_words="A clinic asked for a copy of the instructions for use.",
    )
    # 0.10.93 (OD-5): information asked for, nothing wrong alleged: an Inquiry, reviewed like "service only".
    signed = _ok(_sign(user, event, "INQUIRY", reason="Information request only; nothing wrong."))
    assert signed["signed"]["classification"] == "INQUIRY" and signed["status"] == "IN_REVIEW"
    review = _ok(
        user.post(
            f"{INTAKE}/{event['id']}/check/review",
            json={"outcome": "RECLASSIFIED", "note": "The caller later said the display froze.", "password": PASSWORD},
        )
    )
    assert review["signed"]["classification"] == "COMPLAINT" and review["signed"]["version"] == 2
    assert review["history"][0]["review_outcome"] == "RECLASSIFIED" and review["history"][0]["same_person"]
    assert datetime.fromisoformat(review["awareness"]["at"]) == contact_time
    # 0.10.93 (D1): the reclassified Case becomes the Complaint at once; nothing waits for a QMS import.
    assert review["status"] == "ESCALATED" and review["complaint_id"] and review["qms_task"] is None


def test_an_urgent_intake_creates_a_triage_item_at_once_with_its_clock(trial):  # TA-19.1, TA-19.5
    user = trial["user"]
    aware = datetime.now(timezone.utc) - timedelta(hours=3)
    event = _ok(
        user.post(
            INTAKE,
            json={
                "kind": "URGENT",
                "reporter_words": "Service agent reports a patient burned by the warming plate.",
                "awareness_at": aware.isoformat(),
                "awareness_zone": "Europe/London",
            },
        )
    )
    item = _triage(user)[event["reference"]]
    assert {flag["code"] for flag in item["flags"]} >= {"URGENT_INTAKE", "HARM_WORDS"}
    assert datetime.fromisoformat(item["awareness"]["at"]) == aware and not item["awareness"]["unresolved"]
    assert item["triage_clock"]["target_hours"] == 4 and item["speed"] == "FAST" and item["deadlines"]  # B2: fast track
    assert item["delay"]["text"] == "3 hours"
    assert event["qms_task"]["state"] == "OPEN"


def test_without_awareness_the_clock_runs_from_first_knowledge(trial):  # TA-19.2
    item = _triage(trial["user"])["SAMPLE-URG-01"]
    assert (
        item["awareness"]["unresolved"] and item["awareness"]["label"] == "Awareness unresolved: deadline provisional"
    )
    assert item["awareness"]["source"] == "FIRST_KNOWLEDGE"
    assert {flag["code"] for flag in item["flags"]} >= {"URGENT_INTAKE", "HARM_WORDS"}  # "pt" and "ICU"


def test_the_quarantined_harm_row_is_on_the_triage_list(trial):  # TA-R14.2, TA-19.3
    # 0.10.64: the sample author has triaged it (a calm day 0), so it is listed with the finished ones.
    found = _triage(trial["user"], "all")
    assert found["SAMPLE-RJ-02"]["kind"] == "QUARANTINE" and found["SAMPLE-RJ-02"]["problems"]
    assert "SAMPLE-RJ-01" not in found
    # Already-handled and routine sample complaints stay off it; flagged open ones are on it.
    for ref in ("SAMPLE-RT-01", "SAMPLE-RT-03", "SAMPLE-RT-04"):
        assert not any(item.get("ref") == ref or ref in str(item.get("linked")) for item in found.values()), ref


def test_anyone_can_escalate_by_hand_from_any_queue(trial):  # TA-19.4
    user = trial["user"]
    complaint = _ok(user.get("/api/v1/complaints", params={"q": "SAMPLE-RT-01"}))["items"][0]
    refused = user.post(f"{TRIAGE}/escalate", json={"kind": "COMPLAINT", "id": complaint["id"], "reason": "short"})
    assert refused.status_code == 422
    _ok(
        user.post(
            f"{TRIAGE}/escalate",
            json={"kind": "COMPLAINT", "id": complaint["id"], "reason": "The therapist called back about a patient."},
        )
    )
    ref = complaint["complaint_identifier"]  # a screen shows the customer's own reference (0.10.66, J18)
    item = _triage(user)[ref]
    assert any(flag["code"] == "MANUAL" for flag in item["flags"])


def test_triage_record_needs_owners_action_and_awareness(trial):
    user = trial["user"]
    item = _triage(user)["SAMPLE-URG-01"]
    people = _ok(user.get(TRIAGE))["people"]
    me = people[0]["id"]
    url = f"{TRIAGE}/{item['kind']}/{item['id']}/record"
    body = {"severity": "SERIOUS", "event_owner": me, "triage_owner": me, "immediate_action": "Pump quarantined."}
    missing = user.post(url, json=body)
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "AWARENESS_NEEDED"
    done = _ok(user.post(url, json={**body, "awareness_confirmed_at": item["awareness"]["at"]}))
    assert "SAMPLE-URG-01" not in {entry["ref"] for entry in done["items"] if entry["record"] is None}
    assert "SAMPLE-URG-01" not in _triage(user) and "SAMPLE-URG-01" in _triage(user, "done")


def test_the_sample_pair_links_to_the_earliest_awareness_with_a_conflict(trial):  # TA-20.2, TA-20.3
    user = trial["user"]
    duplicates = _ok(user.get(f"{INTAKE}/duplicates"))["items"]
    (pair,) = [item for item in duplicates if {item["left"]["ref"], item["right"]["ref"]} >= {"SAMPLE-CALL-02"}]
    sides = {pair["left"]["kind"]: pair["left"], pair["right"]["kind"]: pair["right"]}
    complaint = sides["COMPLAINT"]
    assert "same lot" in pair["reasons"] and "same country" in pair["reasons"]
    before = _ok(user.get(f"/api/v1/complaints/{complaint['id']}/disposition"))  # opens fine before the link
    assert before
    linked = _ok(
        user.post(
            f"{INTAKE}/links",
            json={
                "left_kind": pair["left"]["kind"],
                "left_id": pair["left"]["id"],
                "right_kind": pair["right"]["kind"],
                "right_id": pair["right"]["id"],
                "decision": "LINKED",
                "reason": "Same battery shutdown on lot 4, reported by the desk and the hospital.",
            },
        )
    )
    assert linked["conflict"] and linked["awareness_after"] < linked["awareness_before"]
    call = _by_ref(user)["SAMPLE-CALL-02"]
    assert call["qms_task"]["state"] == "CLOSED"
    item = next(
        entry
        for entry in _triage(user).values()
        if "SAMPLE-CALL-02" in {entry["ref"]} | {x["ref"] for x in entry["linked"]}
    )
    assert item["conflict"] and item["awareness"]["at"][:10] == call["awareness"]["at"][:10]
    # The reportability watch recomputes from the earlier, linked awareness.
    watch = _ok(user.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 100}))["items"]
    rt05 = next(entry for entry in watch if entry["id"] == complaint["id"])
    assert rt05["aware_source"] == "LINKED_SOURCE" and rt05["aware_date"] == call["awareness"]["at"][:10]
    assert _ok(user.get(f"{INTAKE}/duplicates"))["items"] == [
        entry for entry in _ok(user.get(f"{INTAKE}/duplicates"))["items"] if "SAMPLE-CALL-02" not in str(entry)
    ]
    # Undone with a reason: the link and its audit history stay.
    refused = user.post(f"{INTAKE}/links/{linked['id']}/undo", json={"reason": "no"})
    assert refused.status_code == 422
    _ok(user.post(f"{INTAKE}/links/{linked['id']}/undo", json={"reason": "Two different devices after all."}))
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        link = db.get(RecordLink, uuid.UUID(linked["id"]))
        assert link.state == "UNLINKED" and link.undo_reason
        actions = {
            row.action
            for row in db.query(AuditEvent.action).filter(
                AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.entity_id == link.id
            )
        }
    assert actions == {"RECORDS_LINKED", "RECORD_LINK_UNDONE"}
    watch = _ok(user.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 100}))["items"]
    assert next(entry for entry in watch if entry["id"] == complaint["id"])["aware_source"] != "LINKED_SOURCE"


def _upload(user, csv: str) -> dict:
    return _ok(
        user.post(
            "/api/v1/trial/imports/complaints",
            params={"on_problems": "skip", "file_name": "QMS export.csv", "date_column": "none"},
            content=csv,
            headers={"Content-Type": "text/csv"},
        )
    )


def test_a_reupload_keeps_field_changes(trial):  # TA-20.1
    # 0.10.93 (D1): a Case signed a complaint becomes the Complaint at once, so the trial (complaints owned in MDARIX)
    # has no QMS task. The QMS ID task and the import's merge by QMS ID (TA-20.4) belong to the Connect escalation step.
    user = trial["user"]
    first = _upload(user, "complaint_id,product_id,product_name,description\nQMS-77,OWN-PUMP,Own Pump,Alarm at start\n")
    assert first["field_changes"] == 0
    event = _log(
        user,
        answers=_all_no(Q3="YES"),
        reporter_words="Caller says the own pump alarmed at start-up and would not run.",
    )
    event = _ok(_sign(user, event, "COMPLAINT"))
    assert event["status"] == "ESCALATED" and event["qms_task"] is None
    second = _upload(
        user,
        "complaint_id,product_id,product_name,description\n"
        "QMS-77,OWN-PUMP,Own Pump,Alarm at start; device returned\n"
        "QMS-78,OWN-PUMP,Own Pump,Pump would not run after the start-up alarm\n",
    )
    assert second["field_changes"] == 1 and second["qms_tasks_closed"] == 0
    (change,) = _ok(user.get(f"{INTAKE}/changes", params={"import_ref": second["import_ref"]}))["items"]
    assert (change["field"], change["before"], change["after"]) == (
        "description",
        "Alarm at start",
        "Alarm at start; device returned",
    )
    escalated = _ok(user.get(f"{INTAKE}/{event['id']}"))
    assert escalated["links"][0]["other"]["ref"] and escalated["complaint_id"] == event["complaint_id"]


def test_another_organization_reads_none_of_it(trial):  # TA-32.5, TA-20 isolation
    other, _, _ = _approved_trial_client()
    mine = _by_ref(trial["user"])["SAMPLE-CALL-03"]
    assert other.get(f"{INTAKE}/{mine['id']}").status_code == 404
    assert (
        other.post(
            f"{TRIAGE}/escalate", json={"kind": "INTAKE", "id": mine["id"], "reason": "Not ours at all."}
        ).status_code
        == 404
    )
    theirs = _by_ref(other)
    assert mine["id"] not in {item["id"] for item in theirs.values()}
    # Row-level security: under the runtime role, a session bound to another organization reads none of the rows.
    if runtime_role_active():
        for model in (IntakeEvent, FirstContactCheck, TriageRecord, RecordLink, RecordFieldChange):
            for tenant, expected in ((uuid.uuid4(), False), (trial["tenant_id"], True)):
                runtime = RuntimeSessionLocal()
                try:
                    bind_tenant(runtime, tenant)
                    count = runtime.query(model).filter(model.tenant_id == trial["tenant_id"]).count()
                    assert (count > 0) == expected, model.__tablename__
                finally:
                    runtime.close()


def test_removing_the_sample_removes_its_contacts_checks_and_triage():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    own = _log(user, answers=_all_no(Q5="UNKNOWN"), reporter_words="Own caller, no product named, unsure of harm.")
    _ok(user.post("/api/v1/trial/sample-data/removal", json={"confirm": True}))
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        left = [row.reference for row in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)]
        assert left == [own["reference"]]
        assert db.query(FirstContactCheck).filter(FirstContactCheck.tenant_id == tenant_id).count() == 1
        assert db.query(TriageRecord).filter(TriageRecord.tenant_id == tenant_id).count() == 0
    assert set(_triage(user)) == {own["reference"]}
