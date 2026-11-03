"""0.10.81: the Critical, High and Medium findings of the functional review of 0.10.79.

- F1: re-signing a market conclusion with another report type moves the open report with it (type, due date,
  provisional flag), audited; a submitted report is never changed, only flagged.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from tests.test_flagship_walkthrough import _answers_from_record
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import _save, _sign
from tests.test_release_c3_0_10_75 import _flagship, _purge, _reports
from tests.test_sample_story_days import FLAGSHIP_US

pytestmark = pytest.mark.db

REPORTS = "/api/v1/reports"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _audit(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
            .all()
        )


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        yield {"user": user, "tenant_id": tenant_id, "complaint": complaint}
    finally:
        _purge(tenant_id)


def _sign_us(user, complaint, remedial: str):
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    answers, _ = _answers_from_record(detail, "US", {**FLAGSHIP_US, "US6": remedial})
    saved = _save(user, complaint, "US", answers, harm_level=detail["severity_level"])
    signed = _ok(_sign(user, complaint, "US", saved, "REPORTABLE", password=PASSWORD))
    return next(item for item in signed["markets"] if item["market"] == "US")["current"]


def test_f1_a_re_signed_shorter_report_type_moves_the_open_report_and_a_submitted_one_is_only_flagged(trial):
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    first = _sign_us(user, complaint, "NO")
    (report,) = _reports(user, complaint)
    assert report["due_on"] == first["due_on"]
    # Remedial action needed: the 5-work-day report (21 CFR 803.53), due earlier.
    second = _sign_us(user, complaint, "YES")
    assert second["due_on"] < first["due_on"]
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert (detail["report_type"], detail["deadline"]["due_on"], detail["deadline"]["provisional"]) == (
        "US_5_WORK_DAY",
        second["due_on"],
        False,
    )
    assert detail["assessment"]["version"] == second["version"] and detail["conclusion_changed"] is None
    (event,) = _audit(tenant_id, "REPORT_RETYPED_BY_CONCLUSION")
    assert event.old_values == {"report_type": "US_30_DAY", "due_on": first["due_on"], "provisional": False}
    assert event.new_values == {"report_type": "US_5_WORK_DAY", "due_on": second["due_on"], "provisional": False}
    # Submitted: a later conclusion never changes it; it is flagged so a follow-up report can be considered.
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.tenant_scope import bind_tenant

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(ReportObligation, uuid.UUID(report["id"])).state = "SUBMITTED_PENDING"
        db.commit()
    _sign_us(user, complaint, "NO")
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert (detail["report_type"], detail["deadline"]["due_on"]) == ("US_5_WORK_DAY", second["due_on"])
    assert "consider a follow-up report" in detail["conclusion_changed"]
    (flagged,) = _audit(tenant_id, "REPORT_CONCLUSION_CHANGED_AFTER_SUBMISSION")
    assert flagged.old_values["report_type"] == "US_5_WORK_DAY" and flagged.new_values["report_type"] == "US_30_DAY"
