"""0.10.93 (B2) step 3 and 4 leftovers through the API: addenda (IN-17, IN-18) and fact correction (spec 2.5) with
the reopening hook (T-D7), bulk assign (CI-36), "Triage first" before a disposition (TR-22), and the bounded duplicate
check at escalation."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.intake import RecordFieldChange
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok, _sign
from tests.test_release_c1_0_10_73 import _invite

pytestmark = pytest.mark.db

WORDS = "Clinic says the analyser needs its annual calibration; nothing else wrong with it."


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-addenda-cleanup")


def _log(user, **extra) -> dict:
    body = {"kind": "CONTACT", "reporter_words": WORDS, "answers": _all_no(), **extra}
    return _ok(user.post(INTAKE, json=body))


def _audits(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test:case-addenda")
        return db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action).all()


def test_an_addendum_is_kept_masked_with_who_said_it_and_the_words_stay(trial):  # IN-17
    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _log(user)
    body = {
        "kind": "TECHNICIAN_FINDING",
        "said_by_role": "TECHNICIAN",
        "text": "Technician found the seal worn; call back on jane.doe@example.com for the part.",
    }
    detail = _ok(user.post(f"{INTAKE}/{event['id']}/addenda", json=body))
    (added,) = detail["addenda"]
    assert (added["kind"], added["said_by_role"], added["masked"]) == ("TECHNICIAN_FINDING", "TECHNICIAN", True)
    assert "jane.doe@example.com" not in added["text"] and detail["reporter_words"] == WORDS
    (audit,) = [row for row in _audits(tenant_id, "CASE_ADDENDUM_ADDED") if row.entity_id == uuid.UUID(event["id"])]
    assert audit.details["kind"] == "TECHNICIAN_FINDING" and "jane" not in str(audit.details)
    refused = user.post(f"{INTAKE}/{event['id']}/addenda", json={**body, "said_by_role": "NEIGHBOUR"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "ADDENDUM_INCOMPLETE"


def test_a_corrected_fact_keeps_its_history_reason_and_version(trial):  # spec 2.5
    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _log(user, serial_number="SN-100")
    body = {"field": "serial_number", "value": "SN-1001", "reason": "Read again from the label photo."}
    stale = user.post(f"{INTAKE}/{event['id']}/correct", json={**body, "seen_version": event["row_version"] + 5})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "CASE_CHANGED"
    fixed = _ok(user.post(f"{INTAKE}/{event['id']}/correct", json={**body, "seen_version": event["row_version"]}))
    assert fixed["row_version"] == event["row_version"] + 1 and fixed["reporter_words"] == WORDS
    with SessionLocal() as db:
        bind_system(db, "test:case-addenda")
        (change,) = db.query(RecordFieldChange).filter(RecordFieldChange.record_id == uuid.UUID(event["id"])).all()
        assert (change.field, change.before, change.after, change.source) == (
            "serial_number",
            "SN-100",
            "SN-1001",
            "CORRECTION",
        )
    (audit,) = [row for row in _audits(tenant_id, "CASE_FACT_CORRECTED") if row.entity_id == uuid.UUID(event["id"])]
    assert (audit.details["old"], audit.details["new"], audit.details["reason"]) == (
        "SN-100",
        "SN-1001",
        body["reason"],
    )
    same = user.post(f"{INTAKE}/{event['id']}/correct", json=body)
    assert same.status_code == 422 and same.json()["detail"]["code"] == "NO_CHANGE"
    words = user.post(f"{INTAKE}/{event['id']}/correct", json={**body, "field": "reporter_words"})
    assert words.status_code == 422 and words.json()["detail"]["code"] == "FIELD_NOT_CORRECTABLE"


def test_a_closed_case_reopens_on_an_addendum_with_a_harm_word(trial):  # spec 3.1, T-D7
    user = trial["user"]
    event = _log(user, answers=_all_no(Q7="YES"), requested="CALIBRATION")
    _ok(_sign(user, event, "SERVICE_ONLY", reason="Annual calibration due; nothing wrong with it."))
    review = {
        "outcome": "AGREED",
        "note": "Checked: routine calibration only.",
        "password": PASSWORD,
        "resolution_summary": "Calibrated on site; within limits.",
    }
    assert _ok(user.post(f"{INTAKE}/{event['id']}/check/review", json=review))["status"] == "CLOSED"
    calm = {"kind": "STATEMENT", "said_by_role": "REPORTER", "text": "Thanks, the calibration certificate arrived."}
    assert _ok(user.post(f"{INTAKE}/{event['id']}/addenda", json=calm))["status"] == "CLOSED"
    harm = {
        "kind": "STATEMENT",
        "said_by_role": "REPORTER",
        "text": "Later the patient was injured by a wrong reading.",
    }
    assert _ok(user.post(f"{INTAKE}/{event['id']}/addenda", json=harm))["status"] == "OPEN"


def test_bulk_assign_sets_the_owner_of_many_cases_and_is_audited(trial):  # CI-36
    user, tenant_id = trial["user"], trial["tenant_id"]
    _invite(user, "quality", "Quality Colleague")
    people = _ok(user.get("/api/v1/triage"))["people"]
    me = next(person["id"] for person in people if person["name"] == "Quality Colleague")
    ids = [_log(user)["id"] for _ in range(2)]
    assert _ok(user.post(f"{INTAKE}/bulk-assign", json={"ids": ids, "owner_id": me})) == {"assigned": 2, "unchanged": 0}
    assert _ok(user.post(f"{INTAKE}/bulk-assign", json={"ids": ids, "owner_id": me}))["unchanged"] == 2
    assert all(_ok(user.get(f"{INTAKE}/{item}"))["owner"] for item in ids)
    assert any(row.details["count"] == 2 for row in _audits(tenant_id, "CASE_BULK_ASSIGNED"))
    too_many = user.post(f"{INTAKE}/bulk-assign", json={"ids": [str(uuid.uuid4()) for _ in range(201)], "owner_id": me})
    assert too_many.status_code == 422
    unknown = user.post(f"{INTAKE}/bulk-assign", json={"ids": [str(uuid.uuid4())], "owner_id": me})
    assert unknown.status_code == 404
    stranger = user.post(f"{INTAKE}/bulk-assign", json={"ids": ids, "owner_id": str(uuid.uuid4())})
    assert stranger.status_code == 422 and stranger.json()["detail"]["code"] == "OWNER_UNKNOWN"


def test_a_flagged_complaint_is_triaged_before_its_disposition(trial):  # TR-22
    from backend.app.intake import service

    user, tenant_id = trial["user"], trial["tenant_id"]
    with SessionLocal() as db:
        bind_system(db, "test:case-addenda")
        items = service.triage(db, None, tenant_id, "open")["items"]
    flagged = next(item for item in items if item["kind"] == service.COMPLAINT and item["tier"] != "UNFLAGGED")
    body = {
        "branch": "SERVICE_LEVEL",
        "classification": {"use_environment": "HOSPITAL", "user_type": "HEALTHCARE_PROFESSIONAL"},
        "password": PASSWORD,
    }
    refused = user.post(f"/api/v1/complaints/{flagged['id']}/disposition/sign", json=body)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "TRIAGE_FIRST", refused.text


def test_the_duplicate_check_at_escalation_is_one_products_bounded_read():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.orm import Session

    from backend.app.intake import service

    query = service.same_product_complaints(Session(), uuid.uuid4(), uuid.uuid4())
    sql = str(query.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "complaints.tenant_id =" in sql and "complaints.product_id =" in sql
    assert f"LIMIT {service.DUPLICATE_SCAN}" in sql and service.DUPLICATE_SCAN <= 200


def test_the_qms_id_task_asks_to_decide_after_ten_working_days():  # spec 5.4 (L3)
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from backend.app.intake import router, service

    now = datetime(2026, 11, 30, 12, tzinfo=timezone.utc)
    task = SimpleNamespace(
        task_type=service.QMS,
        status="OPEN",
        completion_outcome=None,
        details={"decide_by": (now - timedelta(hours=1)).isoformat()},
    )
    view = {"open": True}
    original = service.task_view
    service.task_view = lambda *_: view
    try:
        assert router._qms_state([task], now)["state"] == "DECIDE"
        task.details = {"decide_by": (now + timedelta(days=1)).isoformat()}
        assert router._qms_state([task], now)["state"] == "OPEN"
        task.details = {}
        assert router._qms_state([task], now)["state"] == "OPEN"
    finally:
        service.task_view = original


def test_an_automatic_reopening_is_an_item_due_at_once_for_the_escalation_chain(monkeypatch):  # T-D7
    from datetime import datetime, timezone

    from backend.app.intake import service as intake
    from backend.app.oversight import rules as oversight_rules
    from backend.app.oversight import service as oversight

    now = datetime(2026, 11, 10, 9, tzinfo=timezone.utc)
    reopened = "2026-11-10T08:00:00+00:00"
    item = {
        "key": "COMPLAINT:c1",
        "kind": intake.COMPLAINT,
        "id": str(uuid.uuid4()),
        "ref": "CMP-1",
        "product_name": "PulseWatch 410",
        "tier_label": "Flagged",
        "triage_clock": {"due_at": "2026-11-10T12:00:00+00:00"},
        "acknowledgement": {"required": False},
        "deadlines": [],
        "sample": False,
        "record": {"triage_owner": "u1", "backup_owner": "u2", "reopened_at": reopened, "reopen_trigger": "DEATH"},
    }
    monkeypatch.setattr(intake, "triage", lambda *_args, **_kw: {"items": [item]})
    found = oversight._triage_items(None, None, uuid.uuid4(), now)
    (alert,) = [entry for entry in found if entry["key"].startswith("reopened:")]
    assert alert["key"].endswith(reopened) and "death" in alert["title"]
    assert oversight_rules.state_of(alert["due_at"], now, 4) == oversight_rules.OVERDUE
    item["sample"] = True
    assert not [entry for entry in oversight._triage_items(None, None, uuid.uuid4(), now) if "reopened" in entry["key"]]


def test_an_export_masks_contacts_unless_unmasked_and_a_trial_always_masks():  # OD-1, CI-43
    from backend.app.tenant_export import CONTACT_HELD, masked_row

    row = {"id": 1, "party_type": "REPORTER", "contact_email": "biomed@example.invalid", "contact_phone": None}
    assert masked_row("external_parties", row) == {**row, "contact_email": CONTACT_HELD}
    assert masked_row("complaints", row) == row


def test_a_closed_service_cases_contact_is_erased_twelve_months_later(trial):  # OD-1
    from datetime import timedelta

    from backend.app.db.models.guides_communications import ExternalParty
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.intake import service
    from backend.app.tenant_export import MASKED, request_export

    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _log(user, answers=_all_no(Q7="YES"), requested="CALIBRATION")
    contact = {"organisation": "City Hospital", "contact_role": "Biomedical engineer", "email": "bm@example.invalid"}
    _ok(user.put(f"{INTAKE}/{event['id']}/contact", json=contact))
    _ok(_sign(user, event, "SERVICE_ONLY", reason="Annual calibration due; nothing wrong with it."))
    review = {
        "outcome": "AGREED",
        "note": "Checked: routine calibration only.",
        "password": PASSWORD,
        "resolution_summary": "Calibrated on site; within limits.",
    }
    _ok(user.post(f"{INTAKE}/{event['id']}/check/review", json=review))
    with SessionLocal() as db:
        bind_system(db, "test:case-addenda")
        now = service.now_utc()
        assert service.erase_expired_contacts(db, tenant_id, now) == 0  # closed today: kept
        row = db.get(IntakeEvent, uuid.UUID(event["id"]))
        row.updated_at = now - timedelta(days=service.CONTACT_KEEP_DAYS + 1)
        db.flush()
        assert service.erase_expired_contacts(db, tenant_id, now) == 1
        party = db.query(ExternalParty).filter(ExternalParty.intake_event_id == row.id).one()
        assert party.contact_email is None and party.contact_erased_by == service.RETENTION_ACTOR
        assert service.erase_expired_contacts(db, tenant_id, now) == 0
        # A trial's export stays masked even when unmasking is asked.
        export = request_export(db, tenant_id, "test", "Test: OD-1 trial export", unmask_contacts=True)
        assert export.summary == {"contacts": MASKED}
        db.rollback()
