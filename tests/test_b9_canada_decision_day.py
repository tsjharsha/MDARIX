# ruff: noqa: F811  (the organization fixture is imported from the market assessment tests)
"""B9 step 20 (B9-D6): the corrective-action decision day of a Canada foreign incident. Entered after the conclusion is
signed, as its own audited entry (who, when, reason), never on the signed row (byte for byte unchanged); a correction
is a new entry and the latest counts. Once entered, the foreign clock is due by the end of the day after it and is no
longer provisional. Only on a signed reportable foreign conclusion; off with MDARIX_B9_CANADA."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_b4_effective_dating import _row
from tests.test_b9_canada_chain import trial  # noqa: F401
from tests.test_free_trial import PASSWORD as TRIAL_PASSWORD
from tests.test_release_c3_0_10_75 import _flagship, _reports
from tests.test_market_assessment_api import (  # noqa: F401
    REASON as WINDOWS_REASON,
    SETTINGS,
    WHY,
    _acknowledge,
    _market,
    _save,
    _sign,
    _url,
    org,
)
from tests.test_reporting_capa_api import _complaint

pytestmark = pytest.mark.db

FOREIGN = dict(CA1="YES", CA2="YES", CA3="YES", CA4="YES", CA5="NO", CA6="YES")
REASON = "The maker told the foreign regulator of its recall decision on this day."


def _answers() -> dict:
    return {
        key: {"answer": value, "rationale": WHY, "evidence": ["Complaint description"]}
        for key, value in FOREIGN.items()
    }


def _enter(client, complaint: str, day: date, reason: str = REASON):
    return client.post(
        _url(complaint, "CA", "/corrective-action-day"), json={"decision_day": day.isoformat(), "reason": reason}
    )


def _columns(row) -> dict:
    return {column.name: getattr(row, column.key) for column in row.__mapper__.columns}


def _canada(detail: dict) -> dict:
    return _market(detail, "CA")


def test_the_decision_day_is_its_own_audited_entry_and_moves_the_foreign_clock(org, monkeypatch):
    monkeypatch.delenv("MDARIX_B9_CANADA", raising=False)  # its default: on
    regulatory = org["regulatory"]
    settings = regulatory.get(SETTINGS).json()
    canada = [item for item in settings["templates"] if "Canada" in item["markets"]]
    windows = {"windows": settings["windows"] + canada, "lookback_days": 365, "reason": WINDOWS_REASON}
    assert regulatory.put(SETTINGS, json=windows).status_code == 200
    _acknowledge(regulatory, "CA")
    complaint = _complaint(org["tenant_id"], org["product"], country="Canada", serious_injury=True, aware_days_ago=3)
    saved = _save(regulatory, complaint, "CA", _answers(), harm_level="SERIOUS")
    assert saved["evaluation"]["report_type"] == "CA_FOREIGN", saved["evaluation"]
    # Refused before a signed foreign conclusion exists.
    today = datetime.now(timezone.utc).date()
    early = _enter(regulatory, complaint, today - timedelta(days=1))
    assert early.status_code == 409 and early.json()["detail"]["code"] == "NOT_FOREIGN_REPORT"
    signed = _sign(regulatory, complaint, "CA", saved, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    row = _row(org["tenant_id"], complaint, "CA")
    before = _columns(row)

    # Provisional: counted from awareness (day 0), due by the end of the next day.
    current = _canada(regulatory.get(_url(complaint)).json())["current"]
    assert current["decision_day"] is None and current["due_provisional"] is True
    assert current["due_now"] == current["due_on"]

    # Refusals: a short reason, a future day, a viewer.
    assert _enter(regulatory, complaint, today - timedelta(days=1), reason="short").json()["detail"]["code"] == (
        "REASON_REQUIRED"
    )
    assert _enter(regulatory, complaint, today + timedelta(days=1)).json()["detail"]["code"] == "DAY_IN_FUTURE"
    assert _enter(org["viewer"], complaint, today - timedelta(days=1)).status_code == 403

    # Entered: due by the end of the day after it, no longer provisional; the watch's clock says the same.
    entered = _enter(regulatory, complaint, today - timedelta(days=1))
    assert entered.status_code == 200, entered.text
    item = _canada(entered.json())
    current = item["current"]
    assert current["decision_day"]["day"] == (today - timedelta(days=1)).isoformat()
    assert current["decision_day"]["by"] == "Rita Regulatory" and current["decision_day"]["reason"] == REASON
    assert current["due_provisional"] is False and current["due_now"] == today.isoformat() == item["clock"]["due_date"]
    assert _enter(regulatory, complaint, today - timedelta(days=1)).json()["detail"]["code"] == "NOTHING_TO_CHANGE"

    # Corrected by a new entry: the latest counts, the first stays in the trail.
    corrected = _canada(_enter(regulatory, complaint, today).json())["current"]
    assert corrected["due_now"] == (today + timedelta(days=1)).isoformat()
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        events = (
            db.query(AuditEvent)
            .filter_by(tenant_id=org["tenant_id"], action="CA_CORRECTIVE_ACTION_DAY_SET")
            .order_by(AuditEvent.created_at)
            .all()
        )
    assert [(e.old_values, e.new_values["decision_day"]) for e in events] == [
        ({}, (today - timedelta(days=1)).isoformat()),  # the audit keeps "no old value" as {}
        ({"decision_day": (today - timedelta(days=1)).isoformat()}, today.isoformat()),
    ]
    assert all(e.reason == REASON and e.details["assessment_id"] == str(row.id) for e in events)

    # The signed conclusion is untouched, byte for byte.
    assert _columns(_row(org["tenant_id"], complaint, "CA")) == before

    # Off: the route is gone.
    monkeypatch.setenv("MDARIX_B9_CANADA", "off")
    assert _enter(regulatory, complaint, today - timedelta(days=2)).status_code == 404


def test_a_us_conclusion_takes_no_decision_day(org, monkeypatch):
    monkeypatch.delenv("MDARIX_B9_CANADA", raising=False)  # on: off, the route is 404 (above)
    regulatory = org["regulatory"]
    complaint = _complaint(org["tenant_id"], org["product"], country="US", aware_days_ago=1)
    refused = _enter(regulatory, complaint, datetime.now(timezone.utc).date())
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_FOREIGN_REPORT"


def test_an_unsent_canada_report_takes_the_date(trial, monkeypatch):
    monkeypatch.delenv("MDARIX_B9_CANADA", raising=False)
    user = trial["user"]
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    level = user.get(_url(complaint)).json()["severity_level"]
    saved = _save(user, complaint, "CA", _answers(), harm_level=level)
    signed = _sign(user, complaint, "CA", saved, "REPORTABLE", password=TRIAL_PASSWORD)
    assert signed.status_code == 200, signed.text
    (report,) = [row for row in _reports(user, complaint) if row["market"] == "CA"]
    day = datetime.now(timezone.utc).date() - timedelta(days=3)  # before awareness: an earlier date
    entered = _enter(user, complaint, day)
    assert entered.status_code == 200, entered.text
    (after,) = [row for row in _reports(user, complaint) if row["market"] == "CA"]
    assert after["due_on"] == (day + timedelta(days=1)).isoformat() != report["due_on"], (report, after)
    assert after["provisional"] is False
