"""B7 step 5 (spec 3.2): the "Cases" import template, call logs into Cases to check (BK-01..09, 12, 13)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, TRIAGE, _all_no, _ok, _sign

pytestmark = pytest.mark.db

CASES = "/api/v1/data/import/cases"


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-import-cleanup")


def _post(user, csv: str, path: str = CASES, **params):
    params = {"on_problems": "skip", "file_name": "calls.csv", **params}
    return user.post(path, params=params, content=csv, headers={"Content-Type": "text/csv"})


def _cases(tenant_id) -> dict[str, IntakeEvent]:
    with SessionLocal() as db:
        bind_system(db, "test:case-import")
        rows = db.query(IntakeEvent).filter(
            IntakeEvent.tenant_id == tenant_id, IntakeEvent.source_system == "CASE_IMPORT"
        )
        found = {row.source_identifier: row for row in rows}
        db.expunge_all()
        return found


def _recent(hours: int = 2) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


def test_template_is_offered_with_contacts_and_answers_left_out(trial):  # BK-01
    user = trial["user"]
    listed = _ok(user.get("/api/v1/data/import/templates"))
    cases = next(item for item in listed["templates"] if item["entity"] == "cases")
    assert cases["required"] == ["case_id", "received_at", "words"]
    columns = cases["required"] + cases["optional"]
    assert not {"name", "phone", "email", "Q1", "answers"} & set(columns)
    template = user.get("/api/v1/data/import/templates/cases.csv")
    assert template.status_code == 200 and template.text.startswith("case_id,received_at,words")


def test_import_masks_refuses_contacts_flags_and_signs_nothing(trial):  # BK-02, 03, 06, 07, 13
    user, tenant_id = trial["user"], trial["tenant_id"]
    csv = (
        "Call ID,Date received,Call notes,Caller phone,product_id,lot_id,received_zone\n"
        f"CC-1,{_recent()},Mr. John Smith called: the pump alarm sounded with no occlusion,98450 12345,,LOT-NOT-HERE,UTC\n"
        f"CC-2,{_recent(1)},The patient died after the pump stopped during the infusion,,,,UTC\n"
    )
    checked = _ok(_post(user, csv, CASES + "/check"))
    assert checked["ready"] and checked["mask_personal_data"] is True
    assert any("Caller phone" in note and "Contacts stay in your source system" in note for note in checked["notes"])
    result = _ok(_post(user, csv))
    assert result["created"] == 2 and result["masked_values"] >= 1
    cases = _cases(tenant_id)
    first, second = cases["CC-1"], cases["CC-2"]
    assert "John Smith" not in first.reporter_words and "98450" not in str(first.__dict__)  # BK-02, BK-03
    assert first.lot_text == "LOT-NOT-HERE" and first.lot_batch_id is None  # BK-06: kept as typed
    assert first.identifiers["lot"] == {"not_sure": False, "status": "UNCONFIRMED", "source": "IMPORTED"}
    assert first.late_entry_reason.startswith("Imported from a Cases file")
    assert first.status == "OPEN" and first.owner_id is None
    with SessionLocal() as db:  # BK-13: nothing signed, nothing escalated
        bind_system(db, "test:case-import")
        checks = db.query(FirstContactCheck).filter(FirstContactCheck.intake_event_id.in_([first.id, second.id])).all()
        assert len(checks) == 2 and all(check.signed_at is None and check.answers == {} for check in checks)
        audit = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "CASES_IMPORTED")
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
        assert audit.details["to_check"] == 2 and audit.details["flagged"] == 1 and audit.details["backlog"] == 0
    assert second.complaint_id is None
    triage = user.get(TRIAGE)
    assert triage.status_code == 200 and str(second.id) in triage.text  # BK-07: the death word, triaged at once


def test_reupload_fills_empty_facts_and_never_changes_words_or_time(trial):  # BK-04, BK-05
    user, tenant_id = trial["user"], trial["tenant_id"]
    received = _recent(3)
    _ok(_post(user, f"case_id,received_at,words,received_zone\nCC-10,{received},Display flickered at start,UTC\n"))
    again = _ok(
        _post(
            user,
            "case_id,received_at,words,received_zone,serial_number\n"
            f"CC-10,{received},Display flickered at start,UTC,SN-555\n"
            f"CC-10B,{received},Battery icon stuck at full,UTC,\n",
        )
    )
    assert again["created"] == 1 and again["updated"] == 1 and again["field_changes"] == 1  # BK-04
    case = _cases(tenant_id)["CC-10"]
    assert case.serial_number == "SN-555" and case.version == 2
    changed = _ok(
        _post(
            user,
            "case_id,received_at,words,received_zone\n"
            f"CC-10,{received},Display went blank at start,UTC\n"
            f"CC-10C,{received},Cuff did not inflate,UTC\n",
        )
    )
    assert changed["rejected_rows"] == 1 and "never changes them" in str(changed)  # BK-05
    assert _cases(tenant_id)["CC-10"].reporter_words == "Display flickered at start"


def test_an_old_call_is_imported_backlog_with_no_check_due(trial):  # BK-08, RT-30
    user, tenant_id = trial["user"], trial["tenant_id"]
    old = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d 10:00")
    _ok(
        _post(user, f"case_id,received_at,words,received_zone\nCC-OLD,{old},The patient died during the infusion,UTC\n")
    )
    case = _cases(tenant_id)["CC-OLD"]
    detail = _ok(user.get(f"{INTAKE}/{case.id}"))
    assert detail["backlog_note"] == "Imported: check what was decided in your source system"
    assert detail["check_due_at"] is None and detail["header"]["overdue"] is False
    listed = _ok(user.get(f"{INTAKE}/cases", params={"view": "overdue"}))
    assert str(case.id) not in str(listed["items"])
    # Flagged, it stays on the triage list as imported backlog work (as an imported complaint does): no alarm.
    item = next(item for item in _ok(user.get(TRIAGE))["items"] if item["id"] == str(case.id))
    assert item["backlog"] is True


def test_bad_rows_and_an_oversized_file_are_refused(trial):  # BK-09
    user = trial["user"]
    future = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    bad = _ok(
        _post(
            user,
            "case_id,received_at,words,channel,received_zone\n"
            f"CC-20,{future},Pump alarm,PHONE,UTC\n"
            "CC-21,yesterday,Pump alarm,PHONE,UTC\n"
            f"CC-22,{_recent()},Pump alarm,CARRIER PIGEON,UTC\n"
            f"CC-23,{_recent()},Pump alarm,PHONE,Mars/Olympus\n"
            f"CC-24,{_recent()},Pump alarm,PHONE,UTC\n",
        )
    )
    assert bad["rejected_rows"] == 4 and bad["created"] == 1
    rows = "".join(f"X-{n},{_recent()},Alarm {n}\n" for n in range(5001))
    whole = _post(user, "case_id,received_at,words\n" + rows)
    assert whole.status_code == 422 and "up to 5,000" in whole.text


def test_export_for_qms_entry_merges_back_by_mdarix_ref(trial):  # BK-12
    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _ok(
        user.post(
            INTAKE,
            json={"kind": "CONTACT", "reporter_words": "The pump stopped mid-dose.", "answers": _all_no(Q3="YES")},
        )
    )
    complaint_id = _ok(_sign(user, event, "COMPLAINT"))["complaint_id"]
    with SessionLocal() as db:
        bind_system(db, "test:case-import")
        business_id = db.get(Complaint, uuid.UUID(complaint_id)).business_id
    _ok(
        _post(
            user,
            "complaint_id,product_id,product_name,description,mdarix_ref\n"
            f"QMS-4242,RT-PUMP,Round Trip Pump,The pump stopped mid-dose.,{business_id}\n",
            "/api/v1/data/import/complaints",
            date_column="none",
        )
    )
    with SessionLocal() as db:
        bind_system(db, "test:case-import")
        merged = db.get(Complaint, uuid.UUID(complaint_id))
        assert merged.qms_ref == "QMS-4242"
        assert (
            not db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.qms_ref == "QMS-4242", Complaint.id != merged.id)
            .count()
        )
