"""0.10.88, owner decision OD-4: re-signing a market conclusion asks why it changes, as a disposition does."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import _save
from tests.test_release_c3_0_10_75 import _flagship, _ok, _purge, _us_answers

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "complaint": _flagship(user)}
    finally:
        _purge(tenant_id)


def _sign(user, complaint, saved: dict, conclusion: str, **extra):
    draft = saved["draft"]
    body = {"conclusion": conclusion, "version": draft["version"], "saved_at": draft["saved_at"], "password": PASSWORD}
    return user.post(f"/api/v1/complaints/{complaint}/market-assessments/US/sign", json={**body, **extra})


def test_a_re_signed_conclusion_needs_its_change_reason_and_keeps_it_with_the_new_version(trial):
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    answers, level = _us_answers(user, complaint, True)
    first = _ok(_sign(user, complaint, _save(user, complaint, "US", answers, harm_level=level), "REPORTABLE"))
    signed = next(item for item in first["markets"] if item["market"] == "US")["current"]
    # The first signature needs no change reason, and keeps none.
    assert signed["change_reason"] is None

    answers, level = _us_answers(user, complaint, False)
    saved = _save(user, complaint, "US", answers, harm_level=level)
    refused = _sign(user, complaint, saved, "NOT_REPORTABLE")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "CHANGE_REASON_NEEDED"
    short = _sign(user, complaint, saved, "NOT_REPORTABLE", change_reason="New info")
    assert short.status_code == 422 and short.json()["detail"]["code"] == "CHANGE_REASON_NEEDED"

    reason = "Service found the sensor drift was a calibration error; a recurrence would not harm."
    again = _ok(_sign(user, complaint, saved, "NOT_REPORTABLE", change_reason=reason))
    current = next(item for item in again["markets"] if item["market"] == "US")["current"]
    assert current["change_reason"] == reason and current["version"] == signed["version"] + 1
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(ComplaintMarketAssessment)
            .filter(ComplaintMarketAssessment.complaint_id == uuid.UUID(complaint))
            .filter(ComplaintMarketAssessment.market == "US")
            .order_by(ComplaintMarketAssessment.version)
            .all()
        )
        assert [row.change_reason for row in rows if row.signed_at] == [None, reason]
