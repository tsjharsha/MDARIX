"""B9 review items 1-2 (B9-D8): an approved US importer's report keeps the role and recipients it was signed and
frozen with. Switching the importer role off afterwards never turns it into a manufacturer's report, and its routes
read the recipient list frozen at Send for approval, never the live conclusion."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from backend.app.db.models.authority_reports import ReportSnapshot
from backend.app.db.session import SessionLocal
from tests.report_fill import fill
from tests.test_authority_reports_api import REPORTS, _ok, _sign_rv06, _start_rv06
from tests.test_b9_us_importer_report import IMPORTER, MAKER, PARTIES, trial  # noqa: F401 (fixture)
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

pytestmark = pytest.mark.db


def test_an_approved_importers_report_keeps_its_signed_role_and_frozen_recipients(trial, monkeypatch):  # noqa: F811
    monkeypatch.delenv("MDARIX_B9_US_IMPORTER", raising=False)
    user, colleague = trial["user"], trial["colleague"]
    _ok(
        user.put(
            "/api/v1/complaints/reportability-roles",
            json={"market": "US", "role": "IMPORTER", "reason": "We import this device into the US from its maker."},
        )
    )
    complaint = _sign_rv06(trial)
    detail = _start_rv06(trial)
    # Review 5: the conclusion card names the floor and the role it was decided under.
    card = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    us = next(item for item in card["markets"] if item["market"] == "US")["current"]
    assert us["floor_code"] == "US-IMP-floor-1" and us["role"] == "IMPORTER", us
    _ok(user.put(PARTIES, json=IMPORTER))
    _ok(user.put(PARTIES, json=MAKER))
    _ok(user.put(f"{REPORTS}/{detail['id']}/fields/F2", json={"value": f"1234567-{date.today().year}-00002"}))
    detail = fill(user, REPORTS, detail["id"], ["D2A", "F10_CLINICAL", "F10_IMPACT", "F10_PROBLEM", "F10_COMPONENT"])
    sent = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    _ok(
        colleague.post(
            f"{REPORTS}/{detail['id']}/snapshots/{sent['pending_snapshot']['id']}/approve",
            json={"password": COLLEAGUE_PASSWORD},
        )
    )
    with SessionLocal() as db:
        row = db.query(ReportSnapshot).filter(ReportSnapshot.obligation_id == uuid.UUID(detail["id"])).one()
        assert row.state == "APPROVED"
        assert row.fields["us_role"] == "IMPORTER" and row.fields["us_recipients"] == ["FDA", "MANUFACTURER"]

    # Item 1: the importer role switched off after approval: still an importer's report with both recipients.
    monkeypatch.setenv("MDARIX_B9_US_IMPORTER", "off")
    after = _ok(user.get(f"{REPORTS}/{detail['id']}"))
    assert [route["code"] for route in after["routes"]] == ["EMDR", "MFR_COPY"]
    assert [item["recipient"] for item in after["recipients"]] == ["FDA", "MANUFACTURER"]

    # Item 2: the routes read the frozen list (here edited in the database to prove it), not the live conclusion.
    with SessionLocal() as db:
        row = db.query(ReportSnapshot).filter(ReportSnapshot.obligation_id == uuid.UUID(detail["id"])).one()
        row.fields = {**row.fields, "us_recipients": ["MANUFACTURER"]}
        db.commit()
    frozen = _ok(user.get(f"{REPORTS}/{detail['id']}"))
    assert [route["code"] for route in frozen["routes"]] == ["MFR_COPY"]
    refused = user.post(
        f"{REPORTS}/{detail['id']}/submissions",
        json={
            "route": "EMDR",
            "submitted_at": "2026-01-02T10:00:00+00:00",
            "content_note": "Sent.",
            "no_differences": True,
        },
    )
    assert refused.json()["detail"]["code"] == "ROUTE_NOT_A_RECIPIENT", refused.text
