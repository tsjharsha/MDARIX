# ruff: noqa: F811  (the trial fixture is imported from the authority report tests)
"""B6a G20 "Trace this value" (scenario rows B6-39, B6-40, B6-45 for the route): a report value traced to its
complaint field, the field's change, the import row of the sample file and the snapshot it is frozen in; read only;
another organization and the switch off get 404."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_authority_reports_api import REPORTS, _fields, _ok, _ready_us, _start_rv06, trial  # noqa: F401
from tests.test_free_trial import _approved_trial_client
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

pytestmark = pytest.mark.db


def _state(tenant_id, report_id: str) -> tuple:
    with SessionLocal() as db:
        bind_system(db, "test: trace is read only")
        events = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id).count()
        row = db.get(ReportObligation, uuid.UUID(report_id))
        return events, row.updated_at, row.state, dict(row.entries or {})


def _approved(trial) -> dict:
    user, colleague = trial["user"], trial["colleague"]
    detail = _start_rv06(trial)
    if detail["state"] == "DRAFT":
        # A fact of the complaint changed with a reason before approval: the trace shows who, when, why and the values.
        complaint = detail["complaint"]["id"]
        event_day = date.fromisoformat(_fields(detail)["B3"]["value"])
        day = event_day + timedelta(days=1)
        if detail["complaint"]["aware_date"] == day.isoformat():
            day = event_day
        changed = user.put(
            f"/api/v1/complaints/{complaint}/reporting-facts",
            json={"awareness_date": day.isoformat(), "reason": "The nurse's call log shows the first contact"},
        )
        assert changed.status_code == 200, changed.text
        _ready_us(user, detail["id"])
        detail = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
        snapshot = detail["pending_snapshot"]
        detail = _ok(
            colleague.post(
                f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": COLLEAGUE_PASSWORD}
            )
        )
    assert detail["approved_snapshot"], detail["state"]
    return detail


def test_a_value_is_traced_to_its_field_its_change_its_import_row_and_its_snapshot(trial):  # B6-39
    user = trial["user"]
    detail = _approved(trial)
    report = detail["id"]

    # The event date (B3): the complaint field, the import row of the sample file, the approved snapshot.
    found = _ok(user.get(f"{REPORTS}/{report}/trace/B3"))
    assert found["field"]["id"] == "B3" and found["field"]["value"] == _fields(detail)["B3"]["value"]
    assert found["origin"]["type"] == "Complaint" and found["origin"]["id"] == detail["complaint"]["id"]
    assert found["imports"], "the sample file's row"
    row = found["imports"][0]
    assert row["line"] >= 1 and row["mapping_version"].startswith("complaints-template:")
    snapshot = found["snapshot"]
    assert snapshot["state"] == "APPROVED" and snapshot["approved_by"] == "Rahul Colleague"
    assert len(snapshot["sha256"]) == 64 and snapshot["approved_at"]
    assert (
        snapshot["sha256"]
        == next(item for item in detail["snapshots"] if item["state"] == "APPROVED")["content_fingerprint"]
    )
    assert snapshot["frozen_value"] == found["field"]["value"]

    # The awareness date (G3): the change with its reason, its values (that field's only) and who made it.
    aware = _ok(user.get(f"{REPORTS}/{report}/trace/G3"))
    change = next(item for item in aware["record_events"] if item["action"] == "COMPLAINT_REPORTING_FACTS_SET")
    assert change["reason"] == "The nurse's call log shows the first contact"
    assert set(change["values"]["after"]) == {"awareness_date"} and change["by"] not in ("MDARIX", None)
    # The event date's trace never shows the awareness values of that same event.
    same = next(item for item in found["record_events"] if item["action"] == "COMPLAINT_REPORTING_FACTS_SET")
    assert same["values"] is None

    # A value typed on the report: who entered it and when, from the report's own audit trail.
    typed = _ok(user.get(f"{REPORTS}/{report}/trace/MFR_REPORT"))
    assert typed["origin"] is None or typed["origin"]["type"] != "Complaint"
    assert any(item["action"] == "REPORT_FIELD_SET" for item in typed["entered_on_report"])


def test_trace_is_read_only_and_refused_elsewhere(trial, monkeypatch):  # B6-40, B6-45
    user = trial["user"]
    report = _approved(trial)["id"]
    before = _state(trial["tenant_id"], report)
    for field in ("B3", "B5", "G3"):
        _ok(user.get(f"{REPORTS}/{report}/trace/{field}"))
    assert _state(trial["tenant_id"], report) == before
    # No write method on the route.
    assert user.post(f"{REPORTS}/{report}/trace/B3").status_code == 405
    # A field the form does not have, a report that does not exist.
    assert user.get(f"{REPORTS}/{report}/trace/NOPE").json()["detail"]["code"] == "FIELD_UNKNOWN"
    assert user.get(f"{REPORTS}/{uuid.uuid4()}/trace/B3").status_code == 404
    # Another organization: 404, the same as a report that does not exist.
    other, _, _ = _approved_trial_client()
    refused = other.get(f"{REPORTS}/{report}/trace/B3")
    assert refused.status_code == 404 and refused.json()["detail"]["code"] == "REPORT_NOT_FOUND"
    # Switched off: 404, and the session hides the links.
    monkeypatch.setenv("MDARIX_B6_TRACE", "off")
    assert user.get(f"{REPORTS}/{report}/trace/B3").status_code == 404
    assert user.get("/api/v1/session/context").json()["b6"]["trace"] is False
    monkeypatch.setenv("MDARIX_B6_TRACE", "on")
    assert user.get(f"{REPORTS}/{report}/trace/B3").status_code == 200
    assert user.get("/api/v1/session/context").json()["b6"]["trace"] is True
