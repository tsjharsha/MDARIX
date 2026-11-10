"""B7 step 6 (spec 3.3): the Cases export and the export for QMS entry (BK-10, BK-11, BK-12)."""

from __future__ import annotations

import csv
import hashlib
import io
import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.intake import case_export
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok, _sign

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-export-cleanup")


def _rows(response) -> list[dict]:
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")  # UTF-8 with BOM: opens in Excel
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def _last_audit(tenant_id, action: str) -> dict:
    with SessionLocal() as db:
        bind_system(db, "test:case-export")
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
        return dict(event.details)


def test_cases_export_masks_contacts_escapes_formulas_and_audits_the_hash(trial):  # BK-10, BK-11
    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _ok(
        user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": "=HYPERLINK(evil) the pump alarm sounded"})
    )
    _ok(user.put(f"{INTAKE}/{event['id']}/contact", json={"organisation": "Asha Clinic", "phone": "+91 98450 12345"}))
    response = user.get(f"{INTAKE}/cases/export.csv")
    rows = _rows(response)
    row = next(item for item in rows if item["reference"] == event["reference"])
    assert row["contact"] == "Contact held: yes" and "98450" not in response.text  # BK-10: masked by default
    assert row["words"].startswith("'=")  # BK-11: a formula never runs in a spreadsheet
    assert event["reference"] and "mdarix-cases-" in response.headers["content-disposition"]
    audit = _last_audit(tenant_id, "CASES_EXPORTED")
    assert audit["sha256"] == hashlib.sha256(response.content).hexdigest() and audit["rows"] == len(rows)
    assert audit["contacts"] == "MASKED"
    # A trial is always masked, even with a reason.
    asked = user.get(f"{INTAKE}/cases/export.csv", params={"unmask_reason": "The QMS needs the reporter to reply"})
    assert "98450" not in asked.text and _last_audit(tenant_id, "CASES_EXPORTED")["contacts"] == "MASKED"
    flagged_only = _rows(user.get(f"{INTAKE}/cases/export.csv", params={"flagged": "true"}))
    assert event["reference"] not in {item["reference"] for item in flagged_only}


def test_an_export_over_the_limit_asks_to_narrow_the_filter(trial, monkeypatch):
    monkeypatch.setattr(case_export, "MAX_ROWS", 0)
    _ok(trial["user"].post(INTAKE, json={"kind": "CONTACT", "reporter_words": "Display flickered at start"}))
    response = trial["user"].get(f"{INTAKE}/cases/export.csv")
    assert response.status_code == 422 and "Narrow the filter" in response.text


def test_export_for_qms_entry_lists_case_complaints_without_a_qms_id(trial):  # BK-12
    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _ok(
        user.post(
            INTAKE, json={"kind": "CONTACT", "reporter_words": "Pump stopped mid-dose.", "answers": _all_no(Q3="YES")}
        )
    )
    complaint_id = _ok(_sign(user, event, "COMPLAINT"))["complaint_id"]
    with SessionLocal() as db:
        bind_system(db, "test:case-export")
        business_id = db.get(Complaint, uuid.UUID(complaint_id)).business_id
    response = user.get(f"{INTAKE}/qms-entry/export.csv")
    rows = _rows(response)
    assert list(rows[0])[:3] == ["complaint_id", "product_id", "description"] and list(rows[0])[-1] == "mdarix_ref"
    row = next(item for item in rows if item["mdarix_ref"] == business_id)
    assert row["complaint_id"] == "" and row["description"] == "Pump stopped mid-dose."
    audit = _last_audit(tenant_id, "QMS_ENTRY_EXPORTED")
    assert audit["sha256"] == hashlib.sha256(response.content).hexdigest()


def test_outside_a_trial_contacts_are_unmasked_only_with_data_export_and_a_reason(trial, monkeypatch):  # BK-10
    from tests.test_release_c1_0_10_73 import _invite

    user, tenant_id = trial["user"], trial["tenant_id"]
    monkeypatch.setattr(case_export, "is_trial", lambda *_: False)  # as a pilot or paying organisation
    event = _ok(user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": "The monitor display went blank twice"}))
    _ok(user.put(f"{INTAKE}/{event['id']}/contact", json={"organisation": "Ravi Clinic", "phone": "+91 98450 67890"}))
    masked = user.get(f"{INTAKE}/cases/export.csv")
    assert "67890" not in masked.text  # still masked without a reason
    short = user.get(f"{INTAKE}/cases/export.csv", params={"unmask_reason": "QMS"})
    assert short.status_code == 422 and short.json()["detail"]["code"] == "REASON_TOO_SHORT"
    reason = "The QMS complaint needs the reporter's phone for the reply"
    rows = _rows(user.get(f"{INTAKE}/cases/export.csv", params={"unmask_reason": reason}))
    row = next(item for item in rows if item["reference"] == event["reference"])
    assert "+91 98450 67890" in row["contact"]
    audit = _last_audit(tenant_id, "CASES_EXPORTED")
    assert audit["contacts"] == "UNMASKED" and audit["unmask_reason"] == reason
    # Without data.export the export is refused, reason or not.
    _, executive, _ = _invite(user, "executive", "Esha Executive")
    refused = executive.get(f"{INTAKE}/cases/export.csv", params={"unmask_reason": reason})
    assert refused.status_code == 403, refused.text
