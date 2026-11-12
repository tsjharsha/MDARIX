# ruff: noqa: F811  (the organization fixture is imported from the market assessment tests)
"""B6a C5, G10 (owner D3): a reason on every edit of a complaint's country or awareness date; a signed conclusion whose
facts changed reads "Facts changed after signing: re-check" and is never rewritten. Scenario rows B6-36, B6-37."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_b4_effective_dating import _row
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

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.db, pytest.mark.requirement("B6-36", "B6-37")]
TODAY = datetime.now(timezone.utc).date()


def _facts(user, complaint_id: str, **body):
    return user.put(f"/api/v1/complaints/{complaint_id}/reporting-facts", json=body)


def _signed(org) -> tuple[str, object]:
    regulatory = org["regulatory"]
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _sign(regulatory, complaint, "US", item, "REPORTABLE").status_code == 200
    return complaint, _row(org["tenant_id"], complaint)


def test_reporting_facts_need_a_reason_kept_in_the_audit(org, monkeypatch):  # B6-36
    regulatory = org["regulatory"]
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    new_day = (TODAY - timedelta(days=2)).isoformat()
    for body in ({"awareness_date": new_day}, {"country": "Germany", "reason": "   "}):
        refused = _facts(regulatory, complaint, **body)
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "CHANGE_REASON_REQUIRED"
    saved = _facts(regulatory, complaint, awareness_date=new_day, reason="Reporter's e-mail of 3 Nov")
    assert saved.status_code == 200, saved.text
    with SessionLocal() as db:
        bind_system(db, "test: reason audited")
        event = db.query(AuditEvent).filter_by(action="COMPLAINT_REPORTING_FACTS_SET", entity_id=complaint).one()
    assert event.reason == "Reporter's e-mail of 3 Nov" and event.new_values == {"awareness_date": new_day}
    # Switched off: today's behaviour (no reason asked).
    monkeypatch.setenv("MDARIX_B6_CHANGE_REASON", "off")
    assert _facts(regulatory, complaint, country="Germany").status_code == 200


def test_a_signed_conclusion_is_flagged_never_rewritten_when_its_facts_change(org):  # B6-37
    regulatory = org["regulatory"]
    complaint, before = _signed(org)
    assert before.date_calc["country"] == "US"
    current = _market(regulatory.get(_url(complaint)).json(), "US")["current"]
    assert current["facts_changed"] == [] and current["facts_changed_label"] is None
    # The clock counts from the earliest of awareness, received and recorded (5 days ago here): a later awareness day
    # changes no input of the signed conclusion, so nothing is flagged.
    later = _facts(regulatory, complaint, awareness_date=(TODAY - timedelta(days=3)).isoformat(), reason="Later day")
    assert later.status_code == 200, later.text
    assert _market(later.json(), "US")["current"]["facts_changed"] == []
    moved = _facts(
        regulatory, complaint, awareness_date=(TODAY - timedelta(days=6)).isoformat(), reason="Correct awareness day"
    )
    assert moved.status_code == 200, moved.text
    current = _market(moved.json(), "US")["current"]
    assert current["facts_changed"] == ["awareness"]
    assert current["facts_changed_label"] == "Facts changed after signing: re-check"
    assert _facts(regulatory, complaint, country="Germany", reason="Event happened in Germany").status_code == 200
    current = _market(regulatory.get(_url(complaint)).json(), "US")["current"]
    assert current["facts_changed"] == ["awareness", "country"]
    after = _row(org["tenant_id"], complaint)
    assert (after.id, after.content_fingerprint, after.date_calc, after.due_on, after.signed_at) == (
        before.id,
        before.content_fingerprint,
        before.date_calc,
        before.due_on,
        before.signed_at,
    )
