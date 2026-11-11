"""B4 step 8 (RR-19, RR-20): the rule register's read-only API. Every signed-in member reads it; it holds no
organization's data; an unknown code is 404; there is no write route; switched off it answers 404."""

from __future__ import annotations

import pytest

from backend.app import feature_set
from tests.test_reporting_capa_api import _client, _organization

pytestmark = pytest.mark.db

URL = "/api/v1/rule-register"


@pytest.fixture(scope="module")
def viewer():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    tenant_id = _organization("RR")
    try:
        yield {"client": _client(tenant_id, "VIEWER"), "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:rule-register-cleanup")


def test_every_member_reads_every_rule_with_its_source_and_starter_mark(viewer):
    found = viewer["client"].get(URL)
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["summary"]["markets"] == 5 and body["summary"]["rules"] == len({item["rule"] for item in body["items"]})
    floors = [item for item in body["items"] if item["kind"] == "REPORTABILITY_FLOOR"]
    india = ["IN-floor-1", "IN-floor-2"] if feature_set.switched_on("MDARIX_B9_INDIA") else ["IN-floor-1"]
    canada = ["CA-floor-1", "CA-floor-2"] if feature_set.switched_on("MDARIX_B9_CANADA") else ["CA-floor-1"]
    # B9 Part C: the US role floors, each while its switch is on (user facility: off by default).
    roles = [
        code
        for code, switch in (
            ("US-IMP-floor-1", "MDARIX_B9_US_IMPORTER"),
            ("US-UF-floor-1", "MDARIX_B9_US_USER_FACILITY"),
        )
        if feature_set.switched_on(switch)
    ]
    assert [item["code"] for item in floors] == [*canada, "EU-floor-1", "GB-floor-1", *india, *roles, "US-floor-1"]
    assert all(item["starter_mark"] == body["summary"]["starter_mark"] for item in body["items"])
    # B9: IN-floor-2 corrects IN-floor-1 from the start, so version 1 reads Replaced while India's switch is on.
    # B9 step 5: emdr-rule-book-2 corrects version 1 (adds the importer and user facility rows), from the start.
    replaced = ({"IN-floor-1"} if len(india) == 2 else set()) | {"emdr-rule-book-1"}
    replaced |= {"CA-floor-1"} if len(canada) == 2 else set()  # B9 step 20: CA-floor-2 corrects it from the start
    assert all(item["state"] == ("REPLACED" if item["code"] in replaced else "IN_FORCE") for item in body["items"])
    assert all(item["source"] is not None for item in body["items"])
    # No organization's data, and no implementation detail for customers.
    assert str(viewer["tenant_id"]) not in found.text and "implementation" not in found.text
    us = viewer["client"].get(f"{URL}?market=US&kind=REPORTABILITY_FLOOR").json()["items"]
    assert [item["code"] for item in us] == [*roles, "US-floor-1"]


def test_one_floor_reads_as_if_then_lines_with_its_history(viewer):
    found = viewer["client"].get(f"{URL}/US-floor-1").json()
    assert found["logic"]["reportable"][0].startswith("F-US-1: IF ((US1 (")
    assert "THEN reportable (21 CFR 803.50(a)(1))" in found["logic"]["reportable"][0]
    assert found["logic"]["report_type"][-1] == "T-US-2: OTHERWISE 5-work-day report (21 CFR 803.53)"
    assert [item["code"] for item in found["history"]] == ["US-floor-1"]
    assert viewer["client"].get(f"{URL}/routine-basis-1").json()["logic"] is None


def test_as_at_a_day_unknown_codes_and_no_write_route(viewer):
    dated = viewer["client"].get(f"{URL}?as_at=2020-01-01").json()
    assert dated["as_at"] == "2020-01-01" and len(dated["items"]) == dated["summary"]["rules"]
    assert viewer["client"].get(f"{URL}/NOPE-1").status_code == 404
    assert viewer["client"].post(URL, json={}).status_code == 405
    assert viewer["client"].put(f"{URL}/US-floor-1", json={}).status_code == 405


def test_switched_off_the_register_answers_404(viewer, monkeypatch):
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "off")
    assert viewer["client"].get(URL).status_code == 404
    assert viewer["client"].get(f"{URL}/US-floor-1").status_code == 404


def test_the_session_says_whether_the_register_shows(viewer, monkeypatch):
    """Step 10: the session flag the Rules tab and the Rules used panel follow."""
    assert viewer["client"].get("/api/v1/session/context").json()["rule_register"] is True
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "off")
    assert viewer["client"].get("/api/v1/session/context").json()["rule_register"] is False
