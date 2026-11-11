"""B8 step 16 (B8-28, B8-29; B8-D4): an EU report whose incident is in Northern Ireland goes to MHRA through MORE with
the EU MIR file ("MHRA MORE (EU form)", version to confirm with MHRA), 1.1a asked; an incident elsewhere in the EU never
offers MORE."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.authority_reports import forms
from backend.app.authority_reports import router as reports
from tests.test_authority_reports_api import REPORTS, _fields, _ok, trial  # noqa: F401
from tests.test_b8_mir_freeze import _approve_pending, _fill, _send, eu_parties, report  # noqa: F401

pytestmark = pytest.mark.db


def _in(monkeypatch, country: str) -> None:
    """The complaint's event country as the report reads it."""
    original = reports._context

    def context(db, control_db, obligation):
        found = original(db, control_db, obligation)
        found["record"] = {**found["record"], "country": country}
        return found

    monkeypatch.setattr(reports, "_context", context)


def _routes(trial, report_id: str) -> list[dict]:  # noqa: F811
    return _ok(trial["user"].get(f"{REPORTS}/{report_id}"))["routes"]


def _record(trial, report_id: str, route: str):  # noqa: F811
    return trial["user"].post(
        f"{REPORTS}/{report_id}/submissions",
        json={
            "route": route,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "content_note": "Uploaded (sample).",
            "no_differences": True,
        },
    )


def test_b8_a_northern_ireland_incident_routes_to_more_with_the_eu_form(trial, eu_parties, report, monkeypatch):  # noqa: F811
    _in(monkeypatch, "Northern Ireland")
    routes = _routes(trial, report)
    assert [route["code"] for route in routes] == ["MHRA_MORE_EU"]
    assert routes[0]["label"].startswith("MHRA MORE (EU form)") and "to confirm with MHRA" in routes[0]["note"]
    detail = _ok(trial["user"].get(f"{REPORTS}/{report}"))
    assert detail["form"]["code"] == forms.EU_MIR.code and _fields(detail)["1_1A"]["value"] is None  # 1.1a asked
    _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "1_1A": "MHRA (Northern Ireland)", "2_4": "MDR class IIb"})
    _ok(_send(trial, report))
    frozen = _approve_pending(trial, report)
    assert "incident-Initial-v7.3.1.xsd" in frozen.fields["mir_xml"]  # the EU file, for upload in MORE
    assert _record(trial, report, "EU_NCA").json()["detail"]["code"] == "ROUTE_NOT_A_RECIPIENT"
    assert _record(trial, report, "MHRA_MORE_EU").status_code == 200


def test_b8_an_eu_incident_never_offers_more(trial, eu_parties, report, monkeypatch):  # noqa: F811
    _in(monkeypatch, "France")
    assert [route["code"] for route in _routes(trial, report)] == ["EU_NCA"]
    _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "2_4": "MDR class IIb"})
    _ok(_send(trial, report))
    _approve_pending(trial, report)
    assert _record(trial, report, "MHRA_MORE_EU").json()["detail"]["code"] == "ROUTE_NOT_A_RECIPIENT"
    # With the EU switch off, the report keeps today's single route: MORE is never offered.
    monkeypatch.setenv("MDARIX_B8_EU_MIR", "off")
    _in(monkeypatch, "Northern Ireland")
    assert [route["code"] for route in _routes(trial, report)] == ["EU_NCA"]
