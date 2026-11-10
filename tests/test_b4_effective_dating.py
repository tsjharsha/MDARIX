# ruff: noqa: F811  (the organization fixture is imported from the market assessment tests)
"""B4 step 6: effective dating on market conclusions (spec 4.2, 4.3; R-D3 to R-D6, R-D14), with the database.

A fixture register (the real files plus a test-only US-floor-2 from a recent day, or a correction US-floor-3) is put in
place with ``register._DIRECTORY``; the real register is never changed.
"""

from __future__ import annotations

import copy
import json
import shutil
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.rule_register import register
from tests.test_market_assessment_api import (
    US_SERIOUS,
    _acknowledge,
    _answers,
    _market,
    _save,
    _sign,
    _url,
    org,  # noqa: F401
)
from tests.test_reporting_capa_api import _complaint

pytestmark = pytest.mark.db

TODAY = datetime.now(timezone.utc).date()
CHANGE = TODAY - timedelta(days=3)  # the test-only law change: complaints aware 5 days ago stay on version 1


def _floor(version: int, start, end, kind: str, corrects: str | None = None, days: int = 30) -> dict:
    entry = copy.deepcopy(register._load(str(register.DATA))["US-floor-1"])
    entry.update(code=f"US-floor-{version}", version=version, effective_from=start, effective_to=end)
    entry["change"] = {"kind": kind, "reason": "test only", **({"corrects": corrects} if corrects else {})}
    entry["content"]["report_types"]["US_30_DAY"]["days"] = days
    entry["content_hash"] = register.content_hash(entry["content"])
    return entry


@pytest.fixture
def fixture_register(tmp_path, monkeypatch):
    """Copy the real register to a folder and replace or add US floor versions there."""

    def use(*entries: dict) -> None:
        folder = tmp_path / f"register{len(list(tmp_path.iterdir()))}"
        shutil.copytree(register.DATA, folder)
        for entry in entries:
            (folder / f"{entry['code']}.json").write_text(json.dumps(entry), encoding="utf-8")
        monkeypatch.setattr(register, "_DIRECTORY", folder)

    return use


def _law_change(use) -> None:
    """US-floor-1 to the change day, US-floor-2 (a 20-day "30-day report") from it."""
    use(_floor(1, None, CHANGE.isoformat(), "INITIAL"), _floor(2, CHANGE.isoformat(), None, "LAW_CHANGE", days=20))


def _row(tenant_id, complaint_id: str, market: str = "US") -> ComplaintMarketAssessment:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return (
            db.query(ComplaintMarketAssessment)
            .filter_by(complaint_id=complaint_id, market=market)
            .order_by(ComplaintMarketAssessment.version.desc())
            .first()
        )


def test_save_and_sign_keep_the_floor_the_rules_applied_and_the_date_calculation(org):
    """RR-15 (RG-12): the floor in force at awareness is kept on the conclusion, in what is signed and in the audit."""
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert item["rules_used"]["at_event"]["code"] == "US-floor-1" and item["rules_used"]["today"]["same"] is True
    draft = _row(org["tenant_id"], complaint)
    assert draft.floor_code == "US-floor-1"
    assert {"id": "F-US-1", "state": "APPLIES"} in draft.rules_applied["rules"]
    assert draft.rules_applied["type_row"] == "T-US-1"
    assert draft.date_calc["authority_zone"] == "America/New_York" and draft.date_calc["counting_rule"]
    signed = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    row = _row(org["tenant_id"], complaint)
    assert row.floor_code == "US-floor-1" and row.date_calc["due_date"] == row.due_on.isoformat()
    with SessionLocal() as db:
        bind_system(db, "test:b4-audit-read")
        event = db.query(AuditEvent).filter_by(action="COMPLAINT_MARKET_CONCLUSION_SIGNED", entity_id=complaint).one()
    assert event.details["floor_code"] == "US-floor-1"
    decided = _market(regulatory.get(_url(complaint)).json(), "US")["rules_used"]["decided"]
    assert decided["floor_code"] == "US-floor-1" and decided["before_register"] is False


def test_a_signed_conclusion_never_changes_when_a_new_floor_version_arrives(org, fixture_register):
    """ED-5, ED-9, RR-09: signed under v1, v2 deployed: the row, its due date and fingerprint are unchanged; the panel
    says today's floor differs."""
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _sign(regulatory, complaint, "US", item, "REPORTABLE").status_code == 200
    before = _row(org["tenant_id"], complaint)
    _law_change(fixture_register)
    used = _market(regulatory.get(_url(complaint)).json(), "US")["rules_used"]
    after = _row(org["tenant_id"], complaint)
    assert (after.floor_code, after.due_on, after.content_fingerprint, after.rules_applied, after.date_calc) == (
        before.floor_code,
        before.due_on,
        before.content_fingerprint,
        before.rules_applied,
        before.date_calc,
    )
    assert used["at_event"]["code"] == "US-floor-1" and used["today"] == {"code": "US-floor-2", "same": False}


def test_the_awareness_day_picks_the_floor_and_an_edited_awareness_re_picks_it(org, fixture_register):
    """ED-1/ED-2 on the API, ED-7, RR-07, RR-11: aware before the change: v1; after it: v2 (its 20-day period)."""
    regulatory = org["regulatory"]
    _law_change(fixture_register)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-1"
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        row = db.get(Complaint, complaint)
        row.awareness_timestamp = row.complaint_timestamp = row.recorded_timestamp = datetime.combine(
            TODAY - timedelta(days=1), datetime.min.time().replace(hour=12), timezone.utc
        )
        db.commit()
    _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    draft = _row(org["tenant_id"], complaint)
    assert draft.floor_code == "US-floor-2" and draft.date_calc["floor_day"] == (TODAY - timedelta(days=1)).isoformat()
    # v2's 20-day period: no organization window matches it, so the regulation's clock applies.
    assert (draft.date_calc["source"], draft.date_calc["days"]) == ("REGULATION", 20)


def test_a_correction_refuses_signing_until_the_answers_are_saved_again(org, fixture_register):
    """ED-6, RR-10 (R-D6): saved under v1; a correction v3 (same period) arrives; sign: 409 FLOOR_CHANGED; re-save picks
    v3; sign succeeds with v3. Answers are kept."""
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    fixture_register(_floor(1, None, None, "INITIAL"), _floor(3, None, None, "CORRECTION", corrects="US-floor-1"))
    refused = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FLOOR_CHANGED"
    assert "US-floor-1" in refused.json()["detail"]["message"] and "US-floor-3" in refused.json()["detail"]["message"]
    assert _row(org["tenant_id"], complaint).answers  # kept
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _sign(regulatory, complaint, "US", item, "REPORTABLE").status_code == 200
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-3"


def test_a_draft_saved_before_the_register_is_never_refused_for_having_no_floor(org):
    """Spec 4.2: a draft without a floor code signs, and gets the floor at signing."""
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        db.query(ComplaintMarketAssessment).filter_by(complaint_id=complaint).update(
            {"floor_code": None, "rules_applied": None, "date_calc": None}
        )
        db.commit()
    assert _sign(regulatory, complaint, "US", item, "REPORTABLE").status_code == 200
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-1"


def test_switched_off_nothing_is_recorded_and_signing_is_never_refused_for_a_floor(org, monkeypatch):
    """Step 10, RR-20: off, the floor columns stay empty and the panel is absent; on again, the draft signs."""
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "off")
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert item["rules_used"] is None and _row(org["tenant_id"], complaint).floor_code is None
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "on")
    assert _sign(regulatory, complaint, "US", item, "REPORTABLE").status_code == 200
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-1"


def test_a_draft_saved_on_then_signed_off_keeps_no_floor_from_the_earlier_save(org, monkeypatch):
    """Review finding 1: saved with the register on, signed with it off: the signed row holds no floor, rules or
    date calculation from the earlier save (the signed material holds none either)."""
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-1"
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "off")
    assert _sign(regulatory, complaint, "US", item, "REPORTABLE").status_code == 200
    row = _row(org["tenant_id"], complaint)
    assert row.conclusion and (row.floor_code, row.rules_applied, row.date_calc) == (None, None, None)


def test_the_watch_clock_counts_by_the_floor_at_awareness_not_today_s(org, fixture_register):
    """Review finding 2, ED-10 for the watch: aware before a law change that shortens the 30-day report to 20 days,
    the market's clock still counts 30 days (version 1), as the draft's own due date does."""
    regulatory = org["regulatory"]
    _law_change(fixture_register)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-1"
    assert (
        item["clock"]["days"] == 30
        and item["clock"]["due_date"] == _row(org["tenant_id"], complaint).due_on.isoformat()
    )
