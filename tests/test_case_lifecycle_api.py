"""0.10.93 (B2) through the API, as the trial user, with migration tr19: a Case signed a complaint becomes the Complaint
at once (D1) with its awareness carried (H1); one function sets the Case's state and refuses a move down (B2-08);
the Case check v2 keeps unanswered apart and keeps every recalculation (X1); idempotent create (A4, B2-01); ID-1,
S-1, S-2 and S-3."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok, _sign

pytestmark = pytest.mark.db

WORDS = "Clinic reports the oximeter read 6 points high against a blood gas."


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-lifecycle-cleanup")


def _log(user, **extra) -> dict:
    return _ok(user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": WORDS, "answers": _all_no(), **extra}))


def _audits(tenant_id, event_id) -> list[str]:
    with SessionLocal() as db:
        bind_system(db, "test:case-lifecycle")
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(str(event_id)))
            .order_by(AuditEvent.created_at)
            .all()
        )
        return [row.action for row in rows]


def test_a_case_signed_complaint_becomes_the_complaint_at_once_with_its_awareness(trial):  # D1, H1, IN-01
    user, tenant_id = trial["user"], trial["tenant_id"]
    received = datetime.now(timezone.utc) - timedelta(hours=2)
    knew = received - timedelta(days=1)
    event = _log(
        user,
        answers=_all_no(Q2="YES"),
        received_at=received.isoformat(),
        first_knowledge_at=knew.isoformat(),
        first_knowledge_party="DISTRIBUTOR",
        first_knowledge_basis="ACTS_FOR_MANUFACTURER",
    )
    assert event["status"] == "OPEN" and event["suggestion"] == "COMPLAINT"
    assert datetime.fromisoformat(event["times"]["awareness"]["at"]) == knew
    signed = _ok(_sign(user, event, "COMPLAINT"))
    assert signed["status"] == "ESCALATED" and signed["escalation"] == "CREATED" and signed["complaint_id"]
    assert signed["qms_task"] is None  # the complaint exists: nothing waits for an import
    with SessionLocal() as db:
        bind_system(db, "test:case-lifecycle")
        complaint = db.get(Complaint, uuid.UUID(signed["complaint_id"]))
        assert complaint.tenant_id == tenant_id and complaint.complaint_identifier == event["reference"]
        assert complaint.source_system == "MDARIX_CASE" and complaint.record_owner == "MDARIX"
        assert complaint.description == WORDS and complaint.awareness_timestamp == knew
        assert complaint.patient_involved is False and complaint.serious_injury is False and complaint.death is False
        row = db.get(IntakeEvent, uuid.UUID(event["id"]))
        assert row.complaint_id == complaint.id and row.status == "ESCALATED" and row.version == 2
    actions = _audits(tenant_id, event["id"])
    assert {"COMPLAINT_CREATED_FROM_CASE", "CASE_STATE_CHANGED", "CASE_ESCALATED"} <= set(actions)
    trial["escalated"] = signed


def test_an_escalated_case_is_never_signed_down_and_the_refusal_is_audited(trial):  # B2-08
    user, event = trial["user"], trial["escalated"]
    saved = _ok(
        user.put(
            f"{INTAKE}/{event['id']}/check",
            json={"answers": _all_no(Q7="YES"), "seen_version": event["version"]},
        )
    )
    assert saved["suggestion"] == "INQUIRY"  # information or nothing asked for (OD-5)
    refused = _sign(user, saved, "INQUIRY", reason="Asked only for a copy of the IFU.")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "CASE_STATE_REFUSED"
    assert "CASE_STATE_REFUSED" in _audits(trial["tenant_id"], event["id"])
    assert _ok(user.get(f"{INTAKE}/{event['id']}"))["status"] == "ESCALATED"


def test_a_case_that_says_the_device_malfunctioned_escalates_to_a_complaint_flagged_malfunction(trial):
    # Case-check question 3 is "did the device malfunction"; question 6 (serious harm if it recurred) answered No.
    user = trial["user"]
    event = _log(user, answers=_all_no(Q3="YES"))
    signed = _ok(_sign(user, event, "COMPLAINT"))
    assert signed["escalation"] == "CREATED", signed
    with SessionLocal() as db:
        bind_system(db, "test:case-lifecycle")
        assert db.get(Complaint, uuid.UUID(signed["complaint_id"])).malfunction is True
    # On the reportability watch, so the routine basis ("no ... malfunction recorded") is never offered to sign.
    screen = _ok(user.get(f"/api/v1/complaints/{signed['complaint_id']}/disposition"))
    assert screen["routine"]["offered"] is False
    assert any(reason.startswith("On the reportability watch") for reason in screen["routine"]["blocked"]), screen


def test_a_retried_log_with_the_same_key_creates_one_case(trial):  # A4, B2-01
    user = trial["user"]
    key = f"retry-{uuid.uuid4()}"
    first = _log(user, request_key=key)
    second = _log(user, request_key=key)
    assert first["id"] == second["id"]
    with SessionLocal() as db:
        bind_system(db, "test:case-lifecycle")
        assert db.query(IntakeEvent).filter(IntakeEvent.request_key == key).count() == 1


def test_unanswered_gives_no_outcome_and_every_recalculation_is_kept(trial):  # X1, B2-13, B2-14
    user = trial["user"]
    answers = _all_no()
    del answers["Q9"]
    event = _log(user, answers=answers)
    assert event["suggestion"] == "UNANSWERED" and event["unanswered"] == ["Q9"] and event["outcome_row"] is None
    assert not [task for task in event["tasks"] if task["type"] == "FIRST_CONTACT_FOLLOW_UP"]
    refused = _sign(user, event, "PENDING")
    assert refused.status_code == 422 and "question 9" in refused.json()["detail"]["message"]
    saved = _ok(user.put(f"{INTAKE}/{event['id']}/check", json={"answers": _all_no(Q9="UNKNOWN"), "seen_version": 1}))
    assert saved["suggestion"] == "PENDING"
    with SessionLocal() as db:
        bind_system(db, "test:case-lifecycle")
        check = db.query(FirstContactCheck).filter(FirstContactCheck.intake_event_id == uuid.UUID(event["id"])).one()
        assert check.guide_version == "case-check-starter-2"
        assert [(entry["before"], entry["after"], entry["changed"]) for entry in check.history] == [
            (None, "UNANSWERED", [f"Q{n}" for n in range(1, 9)]),
            ("UNANSWERED", "PENDING", ["Q9"]),
        ]
        assert all(item["question_version"] == 1 for item in check.answers.values())


def test_a_service_only_case_closes_only_with_its_resolution_summary(trial):  # S-2
    user = trial["user"]
    event = _log(user, answers=_all_no(Q7="YES"), requested="CALIBRATION")
    assert event["suggestion"] == "SERVICE_ONLY"
    signed = _ok(_sign(user, event, "SERVICE_ONLY", reason="Annual calibration due; nothing wrong with it."))
    assert signed["status"] == "IN_REVIEW"
    review = {"outcome": "AGREED", "note": "Checked: routine calibration only.", "password": PASSWORD}
    refused = user.post(f"{INTAKE}/{event['id']}/check/review", json=review)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "RESOLUTION_SUMMARY_NEEDED"
    closed = _ok(
        user.post(
            f"{INTAKE}/{event['id']}/check/review",
            json={**review, "resolution_summary": "Calibrated on site on 10 Nov; within limits."},
        )
    )
    assert closed["status"] == "CLOSED" and closed["resolution_summary"].startswith("Calibrated on site")


def test_identifiers_category_and_missing_information_are_saved(trial):  # ID-1, S-1, S-3, A3
    user = trial["user"]
    event = _log(
        user,
        serial_number="PW410-77812",
        firmware_version="4.2.1",
        hardware_revision="Rev C",
        issue_category="connectivity",
        identifiers={
            "serial": {"status": "CONFIRMED", "source": "LABEL_OR_PHOTO"},
            "firmware_version": {"status": "CONFIRMED", "source": "SERVICE_RECORD"},
            "hardware_revision": {"source": "CALLER"},
            "lot": {"not_sure": True, "source": "CALLER"},
        },
    )
    assert event["issue_category"] == "CONNECTIVITY" and event["issue_category_label"] == "Connectivity"
    assert event["identifiers"] == {
        "hardware_revision": {"not_sure": False, "status": "UNCONFIRMED", "source": "CALLER"},
        "firmware_version": {"not_sure": False, "status": "CONFIRMED", "source": "SERVICE_RECORD"},
        "lot": {"not_sure": True, "status": "UNCONFIRMED", "source": "CALLER"},
        "serial": {"not_sure": False, "status": "CONFIRMED", "source": "LABEL_OR_PHOTO"},
    }
    assert [item["label"] for item in event["missing"]] == ["Hardware revision: unconfirmed", "Lot: not sure"]
