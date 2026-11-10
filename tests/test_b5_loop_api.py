"""B5 step 9: Did it work? (GET /api/v1/investigations/{id}/did-it-work) on the sample investigation (SAMPLE-INV-001).
Nothing signed: no decision. Signed with SAMPLE-CAPA-02 as its CAPA follow-up: the decision's scope read from its
signed brief, the CAPA action "too early" (B5-D10), version rows with their units; a later complaint with no version
is listed apart and counted in no version (B5-02); a lot with units unknown leaves its version with counts only and no
rate (B5-01); a superseding decision is read instead of the one it superseded; per-lot rows for a trial; off: 404."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import Capa, Complaint, Decision, Investigation, LotBatch
from backend.app.db.models.reviews import DecisionBriefVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case_id = (
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .scalar()
        )
    try:
        yield {"user": user, "tenant_id": tenant_id, "case_id": case_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b5-loop-cleanup")


def _read(trial):
    response = trial["user"].get(f"/api/v1/investigations/{trial['case_id']}/did-it-work")
    assert response.status_code == 200, response.text
    return response.json()


def _sign(trial, decided: datetime, *, capa: bool = True) -> uuid.UUID:
    """A signed brief decision on the sample brief, as the signing step stores it, with SAMPLE-CAPA-02 as its CAPA."""
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == trial["case_id"]).one()
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=trial["tenant_id"],
            investigation_id=trial["case_id"],
            decision_identifier=f"LOOP-D-{uuid.uuid4().hex[:8]}",
            decision_type="CASE_DECISION",
            disposition="ACCEPT_CONCLUSION",
            rationale="The supplier change explains the pressure alarms.",
            decision_status="SIGNED",
            authorized_by_ref="approver@example.invalid",
            updated_at=decided,
            decision_timestamp=decided,
            created_at=decided,
            decision_kind="BRIEF",
            brief_version_id=brief.id,
            outcome="ACCEPT_CONCLUSION",
            follow_up_actions=[{"action_type": "CAPA_REQUIRED", "title": "CAPA"}],
            decided_at=decided,
        )
        db.add(decision)
        db.flush()
        if capa:
            capa_id = db.query(Capa.id).filter(Capa.capa_identifier == "SAMPLE-CAPA-02").scalar()
            db.add(
                DecisionFollowUp(
                    id=uuid.uuid4(),
                    tenant_id=trial["tenant_id"],
                    decision_id=decision.id,
                    investigation_id=trial["case_id"],
                    action_type="CAPA_REQUIRED",
                    title="Restore incoming inspection",
                    status="IN_PROGRESS",
                    capa_id=capa_id,
                    created_by="test",
                    created_at=decided,
                    updated_at=decided,
                )
            )
        db.commit()
        return decision.id


def test_nothing_signed_reads_no_decision(trial):
    body = _read(trial)
    assert body["decision"] is None and body["notice"].startswith("Counts from your records; not a verdict")


def test_the_signed_decision_reads_its_scope_and_the_capa_is_too_early(trial):
    _sign(trial, datetime.now(timezone.utc) - timedelta(days=20))
    body = _read(trial)
    assert body["decision"]["ref"] and body["scope"]["complaints"] >= 14 and body["scope"]["problems"]
    assert [item["ref"] for item in body["scope"]["versions"]] == ["Rev B"]
    assert [item["ref"] for item in body["capas"]] == ["SAMPLE-CAPA-02"]
    action = body["actions"][0]
    assert action["kind"] == "CAPA" and action["ref"] == "SAMPLE-CAPA-02"
    row = action["by_version"][0]
    assert row["name"] == "Rev B" and row["result"] == "TOO_EARLY" and row["word"].startswith("Too early")
    assert row["before"] >= 1 and len(row["before_complaints"]) == row["before"]
    assert "lots" in action and action["lot_cohorts"]["name"]  # a trial sees its lots
    assert all(word not in str(body).lower() for word in ("eliminated", "proven", "confirmed"))


def test_a_later_complaint_with_no_version_is_listed_apart(trial):
    body = _read(trial)
    problem = body["scope"]["problems"][0]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        source = (
            db.query(Complaint)
            .filter(Complaint.problem_code == problem, Complaint.product_version_id.isnot(None))
            .first()
        )
        values = {column.key: getattr(source, column.key) for column in Complaint.__table__.columns}
        values.pop("business_id")
        now = datetime.now(timezone.utc)
        values.update(
            id=uuid.uuid4(),
            complaint_identifier="LOOP-NOVERSION-1",
            product_version_id=None,
            lot_batch_id=None,
            event_timestamp=now - timedelta(days=2),
            complaint_timestamp=now - timedelta(days=2),
            created_at=now,
        )
        db.add(Complaint(**values))
        db.commit()
    after = _read(trial)
    unknown = after["later"]["version_unknown"]
    assert unknown["count"] == 1 and unknown["complaints"][0]["ref"] == "LOOP-NOVERSION-1"
    assert "LOOP-NOVERSION-1" not in str(after["later"]["complaints"])
    assert "LOOP-NOVERSION-1" not in str(after["actions"][0]["by_version"])


def test_one_lot_with_units_unknown_leaves_its_version_with_counts_only(trial):
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        version_id = uuid.UUID(_read(trial)["scope"]["versions"][0]["id"])
        lot = (
            db.query(LotBatch)
            .filter(LotBatch.product_version_id == version_id)
            .order_by(LotBatch.lot_identifier)
            .first()
        )
        lot.quantity = None
        db.commit()
    row = _read(trial)["actions"][0]["by_version"][0]
    assert row["counts_only"] and row["rate_before"] is None and row["rate_after"] is None
    assert row["word"].endswith("(by calendar days)") and row["unknown_lots"] >= 1


def test_a_superseding_decision_is_read_and_the_old_one_listed(trial):
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        old = db.query(Decision).filter(Decision.investigation_id == trial["case_id"]).one()
    new_id = _sign(trial, datetime.now(timezone.utc) - timedelta(days=1), capa=False)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.query(Decision).filter(Decision.id == old.id).one().superseded_by_decision_id = new_id
        db.commit()
    body = _read(trial)
    assert body["decision"]["id"] == str(new_id) and body["actions"] == []
    assert [item["id"] for item in body["superseded"]] == [str(old.id)]


def test_switched_off_the_view_is_not_found(trial, monkeypatch):
    monkeypatch.setenv("MDARIX_CLOSED_LOOP", "off")
    response = trial["user"].get(f"/api/v1/investigations/{trial['case_id']}/did-it-work")
    assert response.status_code == 404
    assert trial["user"].get("/api/v1/session/context").json()["closed_loop"] is False
