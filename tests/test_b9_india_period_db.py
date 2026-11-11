"""B9 step 2 on the API (B9-03, B9-04, B9-28): turning ``MDARIX_B9_INDIA`` on is the moment IN-floor-2 arrives. An India
draft saved under IN-floor-1 is refused at signing (409 FLOOR_CHANGED) until saved again; a conclusion signed under
IN-floor-1 keeps its floor, due date and fingerprint."""

from __future__ import annotations

import pytest

from tests.test_b4_effective_dating import _row
from tests.test_market_assessment_api import _acknowledge, _answers, _market, _save, _sign, org  # noqa: F401
from tests.test_reporting_capa_api import REASON, SETTINGS, _complaint

pytestmark = pytest.mark.db

IN_SERIOUS = dict(IN1="YES", IN2A="NO", IN2B="NO", IN2C="YES", IN2D="NO", IN2E="NO", IN2F="NO", IN3="NO")


@pytest.fixture
def india(org, monkeypatch):  # noqa: F811
    """India's 30-day window (longer than the law) and the India training; B9 India off until the test turns it on."""
    regulatory = org["regulatory"]
    settings = regulatory.get(SETTINGS).json()
    window = {"name": "India 30 days", "markets": ["India"], "triggers": ["DEATH", "SERIOUS_INJURY"], "days": 30}
    windows = [w for w in settings["windows"] if w["name"] != window["name"]] + [{**window, "day_basis": "CALENDAR"}]
    saved = regulatory.put(SETTINGS, json={"windows": windows, "lookback_days": 365, "reason": REASON})
    assert saved.status_code == 200 or saved.json()["detail"]["code"] == "NOTHING_TO_CHANGE", saved.text
    _acknowledge(regulatory, "IN")
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    return regulatory


def _saved(org, regulatory) -> tuple[str, dict]:  # noqa: F811
    complaint = _complaint(org["tenant_id"], org["product"], country="India", serious_injury=True)
    return complaint, _save(regulatory, complaint, "IN", _answers(**IN_SERIOUS), harm_level="SERIOUS")


def test_a_draft_saved_under_version_one_is_refused_then_saved_again_under_version_two(org, india, monkeypatch):  # noqa: F811
    complaint, item = _saved(org, india)
    assert _row(org["tenant_id"], complaint, "IN").floor_code == "IN-floor-1"
    monkeypatch.setenv("MDARIX_B9_INDIA", "on")
    refused = _sign(india, complaint, "IN", item, "REPORTABLE")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FLOOR_CHANGED"
    assert "IN-floor-1" in refused.json()["detail"]["message"] and "IN-floor-2" in refused.json()["detail"]["message"]
    item = _save(india, complaint, "IN", _answers(**IN_SERIOUS), harm_level="SERIOUS")
    signed = _sign(india, complaint, "IN", item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    row = _row(org["tenant_id"], complaint, "IN")
    assert row.floor_code == "IN-floor-2"
    # 15 days from the regulation, not the 30-day window (B9-01 on the API).
    assert (row.date_calc["source"], row.date_calc["days"]) == ("REGULATION", 15)
    # Step 15: the conclusion names the floor's period (B9-01 on screen).
    label = _market(signed.json(), "IN")["current"]["report_type_label"]
    assert label == "Serious adverse event: 15 days (India MDR 2017 Rule 26, starter)"


def test_a_conclusion_signed_under_version_one_never_changes(org, india, monkeypatch):  # noqa: F811
    complaint, item = _saved(org, india)
    assert _sign(india, complaint, "IN", item, "REPORTABLE").status_code == 200
    before = _row(org["tenant_id"], complaint, "IN")
    assert before.floor_code == "IN-floor-1" and before.date_calc["days"] == 30
    monkeypatch.setenv("MDARIX_B9_INDIA", "on")
    india.get(f"/api/v1/complaints/{complaint}/market-assessments")
    after = _row(org["tenant_id"], complaint, "IN")
    fields = ("floor_code", "due_on", "content_fingerprint", "rules_applied", "date_calc", "answers")
    assert [getattr(after, name) for name in fields] == [getattr(before, name) for name in fields]
    current = _market(india.get(f"/api/v1/complaints/{complaint}/market-assessments").json(), "IN")["current"]
    assert current["report_type_label"] == "Serious adverse event (India MDR 2017 Rule 26)"  # its own floor's words
