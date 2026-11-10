"""0.10.93 (B2) import leftovers: QMS triage columns (T-D9: TR-14, TR-37, TR-38), the imported backlog (OD-12, TR-21)
and closed QMS complaints with harm (T-D13, TR-23)."""

from __future__ import annotations

import uuid

import pytest

from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.models.intake import TriageRecord, TriageRecordVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.trial.imports import TEMPLATES
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import TRIAGE, _ok, _triage, _upload

pytestmark = pytest.mark.db

HEADER = (
    "complaint_id,product_id,product_name,description,status,awareness_date,death,"
    "triage_date,triage_severity,triage_owner,immediate_action\n"
)


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:import-triage-cleanup")


def _complaint_id(tenant_id, identifier: str) -> uuid.UUID:
    with SessionLocal() as db:
        bind_system(db, "test:import-triage")
        return (
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == identifier)
            .scalar()
        )


def _record(tenant_id, identifier: str) -> TriageRecord | None:
    with SessionLocal() as db:
        bind_system(db, "test:import-triage")
        complaint = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == identifier)
            .one()
        )
        record = (
            db.query(TriageRecord)
            .filter(TriageRecord.tenant_id == tenant_id, TriageRecord.subject_id == complaint.id)
            .one_or_none()
        )
        if record is not None:
            db.expunge(record)
        return record


def test_the_template_offers_the_qms_triage_columns():
    spec = TEMPLATES["complaints"]
    assert spec["optional"][-4:] == ["triage_date", "triage_severity", "triage_owner", "immediate_action"]
    assert all(len(row) == len(spec["required"]) + len(spec["optional"]) for row in spec["example"])


def test_qms_triage_is_accepted_without_a_flag_and_confirmed_by_a_person_with_one(trial):  # TR-37, TR-14, TR-38
    user, tenant_id = trial["user"], trial["tenant_id"]
    result = _upload(
        user,
        HEADER
        + "QT-1,QT-PUMP,QT Pump,Display text was hard to read,open,2026-11-01,N,2026-11-02,Negligible,Complaint unit,\n"
        + "QT-2,QT-PUMP,QT Pump,Patient died after the infusion stopped,open,2026-11-01,Y,2026-11-02,Minor,"
        + "Complaint unit,Pump taken out of use\n",
    )
    assert result["created"] >= 2, result
    # TR-37: no flag, accepted as the QMS recorded it, version 1, no person's click; not on the triage list.
    accepted = _record(tenant_id, "QT-1")
    assert accepted.source_system == "QMS" and accepted.completed_at is not None and accepted.confirmed_by is None
    assert accepted.severity == "NEGLIGIBLE" and accepted.qms_owner_text == "Complaint unit"
    with SessionLocal() as db:
        bind_system(db, "test:import-triage")
        versions = db.query(TriageRecordVersion).filter(TriageRecordVersion.triage_record_id == accepted.id).all()
        assert [row.version for row in versions] == [1]
    assert "QT-1" not in _triage(user, "all")
    # TR-14 / TR-38: a death waits for a person, on the fast track, with no one-click routine card.
    item = _triage(user)["QT-2"]
    assert item["qms_to_confirm"] is True and item["speed"] == "FAST" and item["routine_prefill"] is None
    assert item["record"]["source_system"] == "QMS" and item["record"]["severity"] == "MINOR"
    me = _ok(user.get(TRIAGE))["people"][0]["id"]
    url = f"{TRIAGE}/COMPLAINT/{item['id']}/confirm-qms"
    body = {
        "severity": "MINOR",
        "event_owner": me,
        "triage_owner": me,
        "immediate_action": "Pump taken out of use and quarantined.",
        "public_health_threat": False,
        "threat_reason": "One device, one patient; no sign of a wider problem.",
        "awareness_confirmed_at": item["awareness"]["at"],
        "seen_version": item["record"]["version"],
    }
    below = user.post(url, json=body)
    assert below.status_code == 422 and below.json()["detail"]["code"] == "BELOW_FLOOR"
    _ok(user.post(url, json={**body, "severity": "CATASTROPHIC"}))
    confirmed = _record(tenant_id, "QT-2")
    assert confirmed.completed_at is not None and confirmed.confirmed_by is not None
    assert "QT-2" in _triage(user, "done") and "QT-2" not in _triage(user)
    with SessionLocal() as db:
        bind_system(db, "test:import-triage")
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == confirmed.id, AuditEvent.action == "TRIAGE_QMS_CONFIRMED")
            .count()
            == 1
        )
    # Nothing left to confirm, on either record; a re-upload never changes a person's triage.
    again = user.post(url, json={**body, "severity": "CATASTROPHIC"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "NOT_QMS_TO_CONFIRM"
    other = user.post(f"{TRIAGE}/COMPLAINT/{accepted.subject_id}/confirm-qms", json=body)
    assert other.status_code == 409
    _upload(
        user,
        HEADER + "QT-2,QT-PUMP,QT Pump,Patient died after the infusion stopped,open,2026-11-01,Y,"
        "2026-11-03,Negligible,Other unit,\n",
    )
    assert _record(tenant_id, "QT-2").severity == "CATASTROPHIC"


def test_old_unflagged_imports_go_to_the_imported_backlog_with_one_click(trial):  # TR-21, OD-12
    user, tenant_id = trial["user"], trial["tenant_id"]
    _upload(
        user,
        HEADER
        + "BL-OLD,BL-PUMP,BL Pump,Label smudged on the box,open,2025-01-10,N,,,,\n"
        + "BL-NEW,BL-PUMP,BL Pump,Label smudged on the lid,open,2026-11-05,N,,,,\n"
        + "BL-HARM,BL-PUMP,BL Pump,Patient died after use,open,2025-01-10,Y,,,,\n"
        + "BL-SHUT,BL-PUMP,BL Pump,Label smudged on the case,closed,2025-01-10,N,,,,\n",
    )
    backlog = _ok(user.get(f"{TRIAGE}/backlog", params={"page_size": 100}))
    refs = {item["ref"]: item for item in backlog["items"]}
    assert "BL-OLD" in refs and not {"BL-NEW", "BL-HARM", "BL-SHUT"} & set(refs)
    assert backlog["summary"]["backlog_days"] == 30 and backlog["summary"]["target_days"] == 10
    old = refs["BL-OLD"]
    assert old["due_at"] > old["imported_at"] and old["overdue"] is False
    assert "BL-HARM" in _triage(user)  # a flagged one is on "To triage" at its own speed
    _ok(user.post(f"{TRIAGE}/COMPLAINT/{old['id']}/confirm", json={"seen_version": 0}))
    record = _record(tenant_id, "BL-OLD")
    assert record.completed_at is not None and record.severity == "NEGLIGIBLE"
    after = _ok(user.get(f"{TRIAGE}/backlog", params={"page_size": 100}))
    assert "BL-OLD" not in {item["ref"] for item in after["items"]}
    # A recent unflagged one is in neither queue, so the one click refuses it.
    recent = user.post(f"{TRIAGE}/COMPLAINT/{_complaint_id(tenant_id, 'BL-NEW')}/confirm", json={"seen_version": 0})
    assert recent.status_code == 409 and recent.json()["detail"]["code"] == "NOT_ROUTINE"


def test_a_closed_qms_complaint_with_harm_gets_a_second_look(trial):  # TR-23, T-D13
    user = trial["user"]
    _upload(
        user,
        HEADER
        + "CL-DEATH,CL-PUMP,CL Pump,Patient died; complaint closed in the QMS,Closed,2026-10-01,Y,,,,\n"
        + "CL-PLAIN,CL-PUMP,CL Pump,Box dented; complaint closed in the QMS,Closed,2026-10-01,N,,,,\n",
    )
    look = _ok(user.get("/api/v1/complaints/second-look", params={"state": "open", "page_size": 100}))
    found = {item["complaint_identifier"]: item for item in look["items"]}
    assert "CL-PLAIN" not in found
    reasons = {reason["code"]: reason["label"] for reason in found["CL-DEATH"]["reasons"]}
    assert reasons == {"CLOSED_NO_DECISION": "Closed without a reportability decision?"}
    assert look["summary"]["by_reason"]["CLOSED_NO_DECISION"] >= 1
    assert "CL-DEATH" not in _triage(user, "all")  # closed: no triage
    # A signed market conclusion answers the question (the rule; the service sets market_concluded).
    record = {"status": "closed", "death": True}
    assert review_rules.closed_without_decision(record)
    assert not review_rules.closed_without_decision({**record, "market_concluded": True})
    assert not review_rules.closed_without_decision({**record, "status": "open"})
