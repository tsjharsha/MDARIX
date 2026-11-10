"""0.10.93 (B2) import leftovers: QMS triage columns (T-D9: TR-14, TR-37, TR-38), the imported backlog (OD-12, TR-21)
and closed QMS complaints with harm (T-D13, TR-23)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

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
    assert "BL-OLD" in refs and not {"BL-NEW", "BL-SHUT"} & set(refs)
    assert backlog["summary"]["backlog_days"] == 30 and backlog["summary"]["target_days"] == 10
    old = refs["BL-OLD"]
    assert old["due_at"] > old["imported_at"] and old["overdue"] is False and not old["flags"]
    # Owner, 10 Nov (OD-12 + 3a): an old flagged one is backlog too, listed first, its flag kept, off "To triage".
    assert list(refs).index("BL-HARM") < list(refs).index("BL-OLD") and refs["BL-HARM"]["flags"]
    assert _triage(user)["BL-HARM"]["backlog"] is True
    _ok(user.post(f"{TRIAGE}/COMPLAINT/{old['id']}/confirm", json={"seen_version": 0}))
    record = _record(tenant_id, "BL-OLD")
    assert record.completed_at is not None and record.severity == "NEGLIGIBLE"
    after = _ok(user.get(f"{TRIAGE}/backlog", params={"page_size": 100}))
    assert "BL-OLD" not in {item["ref"] for item in after["items"]}
    # A recent unflagged one is not backlog: it is routine on "To triage" (owner Q3, below).
    assert _triage(user)["BL-NEW"]["speed"] == "ROUTINE"


def test_recent_unflagged_imports_are_routine_on_to_triage_from_0_10_93_only(trial):  # owner Q3, 10 Nov
    user, tenant_id = trial["user"], trial["tenant_id"]
    _upload(
        user,
        HEADER
        + "RQ-NEW,RQ-PUMP,RQ Pump,Label smudged on the tray,open,2026-11-05,N,,,,\n"
        + "RQ-OLD,RQ-PUMP,RQ Pump,Label smudged on the cover,open,2026-11-05,N,,,,\n",
    )
    # RQ-OLD as a 0.10.92 import holds it: before 0.10.93 no import set last_synced_at.
    with SessionLocal() as db:
        bind_system(db, "test:import-triage")
        db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == "RQ-OLD").update(
            {"last_synced_at": None}
        )
        db.commit()
    listed = _triage(user)
    assert "RQ-OLD" not in _triage(user, "all")  # an existing trial's list does not change
    item = listed["RQ-NEW"]
    assert item["speed"] == "ROUTINE" and item["routine_prefill"] and not item["flags"]
    # A re-upload keeps the older one off the list.
    _upload(user, HEADER + "RQ-OLD,RQ-PUMP,RQ Pump,Label smudged on the cover,open,2026-11-05,N,,,,\n")
    assert "RQ-OLD" not in _triage(user, "all")
    old = user.post(f"{TRIAGE}/COMPLAINT/{_complaint_id(tenant_id, 'RQ-OLD')}/confirm", json={"seen_version": 0})
    assert old.status_code == 409 and old.json()["detail"]["code"] == "NOT_ROUTINE"
    _ok(user.post(f"{TRIAGE}/COMPLAINT/{item['id']}/confirm", json={"seen_version": 0}))
    assert "RQ-NEW" not in _triage(user) and "RQ-NEW" in _triage(user, "done")
    assert _record(tenant_id, "RQ-NEW").severity == "NEGLIGIBLE"


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


@pytest.fixture(scope="module")
def fresh():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:import-backlog-cleanup")


def _counts(user, tenant_id) -> dict:
    """What a trial sees: To triage (not backlog), the Imported backlog, Oversight, the bell and the watch."""
    from backend.app.db.models.oversight import OversightSettings

    with SessionLocal() as db:  # the bell is brought up to date by the next read
        bind_system(db, "test:import-triage")
        db.query(OversightSettings).filter(OversightSettings.tenant_id == tenant_id).update({"swept_at": None})
        db.commit()
    listed = _ok(user.get(TRIAGE, params={"show": "open"}))
    to_triage = [item for item in listed["items"] if not item.get("backlog")]
    backlog = _ok(user.get(f"{TRIAGE}/backlog", params={"page_size": 100}))["summary"]
    oversight = _ok(user.get("/api/v1/oversight", params={"show": "all"}))
    bell = _ok(user.get("/api/v1/oversight/alerts"))["items"]
    watch = _ok(user.get("/api/v1/complaints/reportability", params={"show": "open", "page_size": 200}))["summary"]
    return {
        "to_triage": len(to_triage),
        "to_triage_overdue": sum(1 for item in to_triage if item["triage_clock"]["state"] == "OVERDUE"),
        "to_triage_past_clock": sum(
            1 for item in to_triage if any(entry.get("state") == "OVERDUE" for entry in item["deadlines"])
        ),
        "open": listed["summary"]["open"],
        "backlog": backlog["total"],
        "backlog_flagged": backlog.get("flagged", 0),
        "backlog_overdue": backlog["overdue"],
        "oversight": oversight["total"],
        "oversight_imported": sum(1 for item in oversight["items"] if (item.get("ref") or "").startswith("OB-")),
        "oversight_overdue": oversight["overdue"],
        "oversight_due_soon": oversight["due_soon"],
        "bell": len(bell),
        "watch": watch["open"],
        "watch_overdue": watch["overdue"],
    }


def test_old_flagged_imports_wait_in_the_backlog_and_raise_no_overdue_items(fresh):  # OD-12 + 3a, owner 10 Nov
    """The gap-matrix P import: 50 complaints known of 60-400 days before the import, 10 malfunctions, 10 serious
    injuries, 30 with no flag. All 50 are Imported backlog (the 20 flagged first, flag kept, the backlog target and the
    QMS note); none is on To triage, overdue, in Oversight, on the bell or overdue on the watch."""
    user, tenant_id = fresh["user"], fresh["tenant_id"]
    before = _counts(user, tenant_id)
    today = date.today()
    words = {
        "M": "Pump stopped during the infusion",
        "S": "Patient injured by the pump",
        "-": "Label smudged on the box",
    }
    rows = []
    for n in range(50):
        kind = "M" if n < 10 else "S" if n < 20 else "-"
        aware = (today - timedelta(days=60 + n * 340 // 49)).isoformat()
        country = ("US", "DE", "GB", "CA", "IN")[n % 5]
        injury, malfunction = ("Y" if kind == "S" else "N"), ("Y" if kind == "M" else "N")
        rows.append(f"OB-{n:02d},OB-PUMP,OB Pump,{words[kind]},open,{aware},{country},N,{injury},{malfunction}\n")
    header = "complaint_id,product_id,product_name,description,status,awareness_date,country,death,serious_injury,"
    result = _upload(user, header + "malfunction\n" + "".join(rows))
    assert result["rows"] == 50 and result["created"] >= 50, result
    after = _counts(user, tenant_id)
    print("\nbefore", before, "\nafter ", after)
    added = {key: after[key] - before[key] for key in after}
    assert (added["backlog"], added["backlog_flagged"], added["backlog_overdue"]) == (50, 20, 0), added
    assert (added["to_triage"], added["to_triage_past_clock"], added["open"]) == (0, 0, 0), added
    assert (added["oversight_imported"], added["bell"], added["watch_overdue"]) == (0, 0, 0), added
    items = _ok(user.get(f"{TRIAGE}/backlog", params={"page_size": 100}))["items"]
    flagged, plain = items[:20], items[20:]
    assert all(
        item["flags"] and item["note"] == "Imported: check the reportability decision in your QMS" for item in flagged
    )
    assert not any(item["flags"] or item["note"] for item in plain)
    # Flag kept: no one-click routine triage; the full form reads its facts, the backlog target and no market clock.
    first = flagged[0]
    refused = user.post(f"{TRIAGE}/COMPLAINT/{first['id']}/confirm", json={"seen_version": 0})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_ROUTINE"
    item = _triage(user)[first["ref"]]
    assert item["backlog"] and item["flags"] and item["speed"] == "FAST" and item["deadlines"] == []
    assert item["triage_clock"]["due_at"] == first["due_at"] and item["triage_clock"]["state"] != "OVERDUE"
    assert item["backlog_note"] == first["note"] and not item["acknowledgement"]["required"]
    watched = _ok(user.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 200}))["items"]
    clocks = [entry["binding"] for entry in watched if (entry.get("complaint_identifier") or "").startswith("OB-")]
    assert clocks and all(clock["window"] == first["note"] and clock["state"] != "OVERDUE" for clock in clocks)
