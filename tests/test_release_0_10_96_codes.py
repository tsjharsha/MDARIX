"""0.10.96 (B3, A7): Confirm all codes (D8), against the database.

On the new navigation a mapped code is a suggestion a person confirms (0.10.77). One click confirms every code that
waits, each through the same step as its own Confirm and with its own audit event; a code a person chose and a field
with no suggestion stay as they are; only a draft is changed."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.code_lists import ensure_loaded
from tests.test_free_trial import _approved_trial_client
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok, _purge, _reports, _sign_us

pytestmark = pytest.mark.db


def _fields(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


def _confirm_all(user, report: str):
    return user.post(f"{REPORTS}/{report}/codes/confirm")


@pytest.fixture(scope="module")
def trial():
    ensure_loaded()
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        _ok(_sign_us(user, complaint, "REPORTABLE"))
        (report,) = _reports(user, complaint)
        yield {"user": user, "tenant_id": tenant_id, "complaint": complaint, "report": report["id"]}
    finally:
        _purge(tenant_id)


def test_b3_confirm_all_confirms_each_suggested_code_and_audits_each(trial):
    user, report = trial["user"], trial["report"]
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    assert detail["codes_confirmed"]  # the new navigation: a mapped code waits for a person
    waiting = {key: item["suggestion"] for key, item in _fields(detail).items() if item["status"] == "SUGGESTED"}
    assert "H6_PROBLEM" in waiting, waiting
    detail = _ok(_confirm_all(user, report))
    fields = _fields(detail)
    for key, suggestion in waiting.items():
        assert (fields[key]["status"], fields[key]["value"]) == ("CONFIRMED", suggestion), key
    assert not [key for key, item in fields.items() if item["status"] == "SUGGESTED"]
    # One audit event per field, as its own Confirm writes, marked as one "Confirm all".
    with SessionLocal() as db:
        events = [
            row.details
            for row in db.query(AuditEvent).filter(
                AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "REPORT_FIELD_SET"
            )
            if (row.details or {}).get("all_codes")
        ]
    assert sorted(event["field"] for event in events) == sorted(waiting)
    assert all(event["code_state"] == "CONFIRMED" and event["confirmed"] for event in events)
    # Nothing waits any more: a second click says so.
    again = _confirm_all(user, report)
    assert again.status_code == 422 and again.json()["detail"]["code"] == "NOTHING_SUGGESTED"


def test_b3_confirm_all_leaves_chosen_codes_and_fields_without_a_suggestion(trial):
    user, report = trial["user"], trial["report"]
    # The suggestion waits again; a person chose another field's code in the picker.
    _ok(user.put(f"{REPORTS}/{report}/fields/H6_PROBLEM", json={"clear": True}))
    _ok(user.put(f"{REPORTS}/{report}/fields/H6_CLINICAL", json={"codes": ["E2403"]}))
    before = _fields(_ok(user.get(f"{REPORTS}/{report}")))
    assert before["H6_PROBLEM"]["status"] == "SUGGESTED" and before["H6_CLINICAL"]["status"] == "ENTERED"
    empty = [
        key
        for key, item in before.items()
        if item.get("code_annex") and not item["value"] and not item.get("suggestion")
    ]
    assert empty, "a code field with no suggestion"
    after = _fields(_ok(_confirm_all(user, report)))
    assert after["H6_PROBLEM"]["status"] == "CONFIRMED"
    assert (after["H6_CLINICAL"]["status"], after["H6_CLINICAL"]["value"]) == (
        "ENTERED",
        before["H6_CLINICAL"]["value"],
    )
    assert all(not after[key]["value"] for key in empty), empty


def test_b3_confirm_all_is_refused_on_a_non_draft(trial):
    user, report = trial["user"], trial["report"]
    _ok(user.put(f"{REPORTS}/{report}/fields/H6_PROBLEM", json={"clear": True}))  # a suggestion waits
    for state in ("APPROVED", "CANCELLED"):  # approved, or cancelled by a later conclusion: nothing on it changes
        with SessionLocal() as db:
            bind_tenant(db, trial["tenant_id"])
            db.get(ReportObligation, uuid.UUID(report)).state = state
            db.commit()
        refused = _confirm_all(user, report)
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_A_DRAFT", refused.text
        assert _fields(_ok(user.get(f"{REPORTS}/{report}")))["H6_PROBLEM"]["value"] is None
