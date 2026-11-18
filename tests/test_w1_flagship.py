"""W1: the flagship story, OrbitCare 300 Rev B (SAMPLE-INV-001) in seven steps (backend/app/trial/flagship.py).

Ticks come from saved records: the first three steps are marks kept with the story (in order, team-wide, refused
out of turn or on a moved story); the AI step ticks only on a person's review; the brief on its acceptance for
decision; the decision on a signed BRIEF decision (with whether an authenticator code was checked); the action on a
planned effectiveness check, while "Did it work?" stays too early. The version rule, the recorded flag, the sample's
consistency, restart, the refresh of older trials and the sample clock are checked too.

The module's tests share one trial and run in file order (the walk-through moves it on).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

STORY = "/api/v1/trial/one-story"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _flag(user) -> dict:
    return _ok(user.get(STORY))["flagship"]


def _mark(user, step: str, status: int = 200, run: str = "flagship", subject: str | None = None):
    subject = subject or _flag(user)["investigation"]["id"]
    return _ok(user.post(f"{STORY}/marks", json={"run": run, "step": step, "complaint_id": subject}), status)


def _done(run: dict) -> list[str]:
    return [step["key"] for step in run["steps"] if step["done"]]


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:w1-flagship-cleanup")


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "tenant_key": approval["tenant_key"]}
    finally:
        _purge(tenant_id)


def _intel(user, case_id: str, path: str) -> list[dict]:
    return _ok(user.get(f"/api/v1/investigations/{case_id}/intelligence/{path}"))["items"]


# 1 ------------------------------------------------------------------------------------------------ the fresh run


def test_a_fresh_trial_starts_the_flagship_on_orbitcare_300_rev_b(trial):
    run = _flag(trial["user"])
    assert run["run"] == "flagship"
    assert run["product"]["ref"] == "SAMPLE-ORBIT-300" and run["product"]["version"] == "Rev B"
    assert run["product"]["version_state"] == "KNOWN" and run["product"]["unverified"] == 0
    assert run["investigation"]["ref"] == "SAMPLE-INV-001"
    assert "OrbitCare 300 Rev B" in run["investigation"]["question"]
    assert run["change"]["ref"] == "SAMPLE-CHG-014" and "32 to 13" in run["change"]["description"]
    assert run["capa"]["ref"] == "SAMPLE-CAPA-02" and run["capa"]["check_planned"] is False
    assert run["branch"]["ref"] == "SAMPLE-RV-06"
    assert [step["key"] for step in run["steps"]] == [
        "signal",
        "product",
        "evidence",
        "ai",
        "brief",
        "decision",
        "action",
    ]
    # Seeding never ticks a step: the recorded AI proposal waits for a person.
    assert (_done(run), run["current"], run["finished"], run["ai_proposals"]) == ([], 0, False, 1)


# 2 --------------------------------------------------------------------------------------------------------- marks


def test_marks_count_in_order_for_the_whole_team_and_never_on_a_moved_story(trial):
    user = trial["user"]
    assert _mark(user, "product", 409)["detail"]["code"] == "STEP_NOT_YET"
    assert _mark(user, "evidence", 409)["detail"]["code"] == "STEP_NOT_YET"
    assert _mark(user, "brief", 409)["detail"]["code"] == "STEP_NOT_YET"
    assert _mark(user, "signal", 409, subject=str(uuid.uuid4()))["detail"]["code"] == "STORY_MOVED"
    # A ten-step mark on the flagship run, or a flagship mark on the ten-step run, is no step of that story.
    assert _mark(user, "trends", 422)["detail"]["code"] == "NOT_A_STORY_STEP"
    assert (
        user.post(
            f"{STORY}/marks", json={"run": "sample", "step": "signal", "complaint_id": str(uuid.uuid4())}
        ).status_code
        == 422
    )
    run = _mark(user, "signal")["flagship"]
    assert _done(run) == ["signal"] and run["current"] == 1
    _mark(user, "product")
    run = _mark(user, "evidence")["flagship"]
    assert _done(run) == ["signal", "product", "evidence"] and run["current"] == 3
    # Team-wide: the marks are kept on the trial's request under the person, and read for everyone.
    from backend.app.db.models.stage2 import OnboardingRequest

    with SessionLocal() as db:
        request = db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == trial["tenant_id"]).one()
        people = request.profile["one_story"]
        (mine,) = people.values()
        assert set(mine["flagship"]) >= {"complaint_id", "signal", "product", "evidence"}
        # A colleague's earlier mark counts for everyone, at the earliest time.
        from backend.app.trial.one_story import team_marks

        request.profile = {
            **request.profile,
            "one_story": {**people, "colleague": {"flagship": dict(mine["flagship"])}},
        }
        assert set(team_marks(request, "flagship", uuid.UUID(mine["flagship"]["complaint_id"]))) == {
            "signal",
            "product",
            "evidence",
        }


# 3 ---------------------------------------------------------------------------------------------------- the AI tick


def test_the_ai_step_ticks_only_on_a_persons_review_and_the_recorded_flag_says_so(trial):
    user = trial["user"]
    case_id = _flag(user)["investigation"]["id"]
    observations = [row for row in _intel(user, case_id, "observations") if row.get("ai_execution_id")]
    assert len(observations) == 2
    assert all(row["recorded"] and row["ai_label"] == "AI proposal, not reviewed" for row in observations)
    hypotheses = _intel(user, case_id, "hypotheses")
    assert [row["recorded"] for row in hypotheses if row["origin"] == "AI"] == [True]
    assert not any(row["recorded"] for row in hypotheses if row["origin"] == "HUMAN")
    assert _flag(user)["current"] == 3
    _ok(user.post(f"/api/v1/ai-outputs/{observations[0]['id']}/review", json={"decision": "ACCEPTED"}))
    run = _flag(user)
    assert run["steps"][3]["done"] and run["current"] == 4


# 4 ------------------------------------------------------------------------------------- the brief and the decision


def test_the_brief_ticks_when_read_and_the_decision_on_its_signature_with_mfa(trial, monkeypatch):
    from auth import totp

    user = trial["user"]
    case_id = _flag(user)["investigation"]["id"]
    # UX1: the sample reviewer accepted the brief for decision; the step ticks when the person reads it.
    brief = _ok(user.get(f"/api/v1/investigations/{case_id}/decision"))["brief"]
    assert brief["status"] == "APPROVED_FOR_DECISION" and brief["quality_reviewer_name"] == "MDARIX sample reviewer"
    run = _flag(user)
    assert not run["steps"][4]["done"] and run["current"] == 4
    run = _mark(user, "brief")["flagship"]
    assert run["steps"][4]["done"] and run["current"] == 5
    # MFA required for signing (D11): the trial user enrols, then signs with the code.
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    started = _ok(user.post("/api/v1/auth/mfa/enroll"))
    _ok(user.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(started["secret"])}))
    signed = user.post(
        f"/api/v1/investigations/{case_id}/decision/sign",
        json={
            "brief_version_id": brief["id"],
            "brief_content_hash": brief["content_hash"],
            "outcome": "ACCEPT_CONCLUSION",
            "rationale": "The evidence shows a time and lot association after the supplier and inspection changes. We will start a CAPA and verify the supplier and inspection controls. The cause is not yet confirmed.",
            "root_cause_attribution": "DEVICE_RELATED",
            "root_cause_category": "MATERIAL",
            "residual_unknowns_acknowledged": True,
            "password": PASSWORD,
            "mfa_code": totp.code_at(started["secret"], int(time.time() // 30) + 1),
        },
    )
    assert signed.status_code == 200, signed.text
    run = _flag(user)
    assert run["steps"][5]["done"] and run["current"] == 6
    assert run["mfa_verified"] is True and run["steps"][5]["note"] == "Signed with password and authenticator code"


# 5 ------------------------------------------------------------------------------------------------------ the action


def test_the_action_ticks_on_a_planned_check_and_did_it_work_stays_too_early(trial):
    user = trial["user"]
    run = _flag(user)
    capa = run["capa"]
    today = date.today().isoformat()
    _ok(
        user.put(
            f"/api/v1/capas/{capa['id']}/effectiveness/plan",
            json={
                "criteria": "No pressure-alarm complaint from lots made after the 32-unit inspection is restored.",
                "planned_on": today,
                "measured_from": today,
            },
        )
    )
    run = _flag(user)
    assert run["finished"] and run["capa"]["check_planned"] and run["capa"]["check_status"] is None
    assert run["steps"][6]["note"].startswith("Did it work? Too early")
    # Did it work? The check is planned, not signed: the recurrence since the measurement start is too early to read,
    # and nothing says the action worked.
    detail = _ok(user.get(f"/api/v1/capas/{capa['id']}/effectiveness"))
    assert '"too_early": true' in json.dumps(detail) and "EFFECTIVE" not in json.dumps(detail.get("rounds", ""))


# 6 ------------------------------------------------------------------------------------------------ the version rule


def test_the_version_comes_from_the_complaint_then_the_lot_and_a_date_never_picks_one():
    from backend.app.trial.flagship import version_state

    assert version_state([]) == (None, "UNVERIFIED", 0)
    # No version on the complaint and none on its lot: unverified, whatever was released by then.
    assert version_state([(None, None), (None, None)]) == (None, "UNVERIFIED", 2)
    # From the lot when the complaint names none.
    assert version_state([(None, "B"), ("B", None)]) == ("B", "KNOWN", 0)
    # The complaint's own version wins over its lot's.
    assert version_state([("A", "B")]) == ("A", "KNOWN", 0)
    assert version_state([("B", None), ("B", None), ("A", None)]) == ("B", "MIXED", 0)
    assert version_state([("B", None), (None, None)]) == ("B", "MIXED", 1)


# 7 --------------------------------------------------------------------------------------------- the recorded flag


def test_a_live_ai_result_is_never_marked_recorded(trial):
    from backend.app.case_intelligence.router import _recorded
    from backend.app.db.models.foundation import AIExecution

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        sample = db.query(AIExecution).filter(AIExecution.tenant_id == trial["tenant_id"]).one()
        assert _recorded(db, trial["tenant_id"], [sample.id, None, "not-an-id"]) == {str(sample.id)}
        sample.provider = "vertex"  # as a live run would have saved it
        db.flush()
        assert _recorded(db, trial["tenant_id"], [sample.id]) == set()
        db.rollback()


# 8 ---------------------------------------------------------------------------------- the sample's own consistency


def test_the_sample_is_consistent_and_the_brief_passes_its_gate_with_the_fourth_action():
    from backend.app.db.models.foundation import Complaint, InvestigationComplaint, LotBatch, ProductVersion
    from backend.app.db.models.reviews import DecisionBriefVersion
    from backend.app.trial.flagship import find_case
    from backend.app.trial.sample_decision import NARRATIVE

    assert NARRATIVE["recommended_actions"][3] == (
        "Reassess risk file entries SAMPLE-RSK-01 and SAMPLE-RSK-02 for the NovaSense pressure sensor"
    )
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            case = find_case(db, tenant_id)
            brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == case.id).one()
            # Staged only when the gate passes: the fourth action is in the submitted brief, which the sample reviewer
            # accepted for decision (UX1).
            assert brief.status == "APPROVED_FOR_DECISION"
            assert "SAMPLE-RSK-01" in str(brief.narrative) or "SAMPLE-RSK-01" in str(brief.content)
            rows = (
                db.query(
                    Complaint,
                    LotBatch.lot_identifier,
                    ProductVersion.version_identifier,
                    ProductVersion.release_timestamp,
                )
                .join(InvestigationComplaint, InvestigationComplaint.complaint_id == Complaint.id)
                .join(LotBatch, LotBatch.id == Complaint.lot_batch_id)
                .join(ProductVersion, ProductVersion.id == Complaint.product_version_id)
                .filter(InvestigationComplaint.investigation_id == case.id)
                .all()
            )
            assert rows and {version for _, _, version, _ in rows} == {"Rev B"}
            assert {lot[-3:] for _, lot, _, _ in rows} <= {"003", "004"}
            # No complaint's event comes before its version's release.
            assert all(c.event_timestamp is None or c.event_timestamp >= released for c, _, _, released in rows)
    finally:
        _purge(tenant_id)


# 9 ----------------------------------------------------------------------------------------------------- restart


def test_restarting_the_sample_starts_the_flagship_again():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _mark(user, "signal")
        assert _done(_flag(user)) == ["signal"]
        _ok(user.post("/api/v1/trial/sample-data/restart", json={"confirm": True}))
        run = _flag(user)
        assert _done(run) == [] and run["current"] == 0
    finally:
        _purge(tenant_id)


# 10 ---------------------------------------------------------------------------------- the other runs unchanged


def test_the_sample_and_your_data_runs_are_unchanged(trial):
    body = _ok(trial["user"].get(STORY))
    assert set(body) == {"sample", "yours", "flagship", "more_cases"}
    sample = body["sample"]
    assert sample["complaint"]["ref"] == "SAMPLE-RV-11" and len(sample["steps"]) == 10 and body["yours"] is None
    # The flagship's marks never tick the ten-step story.
    assert not any(step["done"] for step in sample["steps"][8:])


# 11 ------------------------------------------------------------------------------- the refresh of older trials


def _script():
    import importlib.util

    spec = importlib.util.spec_from_file_location("refresh_trial_story", "scripts/refresh_trial_story.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script


def test_the_refresh_adds_the_ai_proposals_and_canada_once_and_skips_a_decided_case(trial):
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import AIExecution, Hypothesis, HypothesisEvidence, SignedApprovalRecord
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.trial.sample_ai import PROVIDER

    script = _script()
    user, approval, _ = _approved_trial_client()
    tenant_id, key = uuid.UUID(approval["tenant_id"]), approval["tenant_key"]
    try:
        # An older trial: no recorded AI proposal and no Canada example.
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            execution = db.query(AIExecution).filter(AIExecution.tenant_id == tenant_id).one()
            hypothesis = db.query(Hypothesis).filter(Hypothesis.source_identifier == str(execution.id)).one()
            db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id == hypothesis.id).delete()
            db.delete(hypothesis)
            db.query(EvidenceObservation).filter(EvidenceObservation.ai_execution_id == execution.id).delete()
            db.delete(execution)
            canada = (
                db.query(ComplaintMarketAssessment)
                .filter(ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.market == "CA")
                .one()
            )
            record = canada.signed_record_id
            db.delete(canada)
            db.query(SignedApprovalRecord).filter(SignedApprovalRecord.id == record).delete()
            db.commit()
        with SessionLocal() as db:
            planned = {item["tenant"]: item for item in script.refresh(db, apply=False)}[key]
        assert "SAMPLE-RV-07's signed Canada example (W1)" in planned["sample"]
        assert "the recorded AI proposals on SAMPLE-INV-001 (W1)" in planned["sample"]
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert db.query(AIExecution).filter(AIExecution.tenant_id == tenant_id).count() == 0  # dry run
        with SessionLocal() as db:
            script.refresh(db, apply=True)
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert (
                db.query(AIExecution)
                .filter(AIExecution.tenant_id == tenant_id, AIExecution.provider == PROVIDER)
                .count()
                == 1
            )
            assert (
                db.query(ComplaintMarketAssessment)
                .filter(ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.market == "CA")
                .one()
                .conclusion
                == "NOT_REPORTABLE"
            )
        # Once: run again, it is already there.
        with SessionLocal() as db:
            assert {item["tenant"]: item["result"] for item in script.refresh(db, apply=False)}[
                key
            ] == "already has the story"
        assert _flag(user)["ai_proposals"] == 1 and not _flag(user)["steps"][3]["done"]
    finally:
        _purge(tenant_id)
    # A case with a signed decision (the module's trial) is never given proposals it was not decided on.
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.query(AIExecution).filter(AIExecution.tenant_id == trial["tenant_id"]).update(
            {"provider": "removed-for-test"}
        )
        assert script.sample_ai_owed(db, trial["tenant_id"]) is False
        db.rollback()


# 12 ----------------------------------------------------------------------------------------------- the sample clock


def test_reviewing_a_sample_ai_proposal_stops_the_sample_clock():
    from backend.app.trial import sample_clock

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert sample_clock.worked_on(db, tenant_id) is False
        case_id = _flag(user)["investigation"]["id"]
        (proposal, *_) = [row for row in _intel(user, case_id, "observations") if row.get("ai_execution_id")]
        _ok(
            user.post(
                f"/api/v1/ai-outputs/{proposal['id']}/review", json={"decision": "REJECTED", "reason": "Not shown."}
            )
        )
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            assert sample_clock.worked_on(db, tenant_id) is True
    finally:
        _purge(tenant_id)


# 13 ------------------------------------------------------------------------------------------------ query budget


def test_the_flagship_read_stays_in_its_query_budget(trial):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from backend.app.trial import flagship
    from backend.app.trial.team import trial_request

    seen = {"count": 0}

    def count(*_args, **_kwargs):
        seen["count"] += 1

    with SessionLocal() as data, SessionLocal() as control:
        bind_tenant(data, trial["tenant_id"])
        bind_tenant(control, trial["tenant_id"])
        request = trial_request(control, trial["tenant_id"])
        event.listen(Engine, "before_cursor_execute", count)
        started = datetime.now(timezone.utc)
        try:
            run = flagship.run_progress(data, control, trial["tenant_id"], request)
        finally:
            event.remove(Engine, "before_cursor_execute", count)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    assert run is not None and seen["count"] <= 16 and elapsed < 0.5, (seen["count"], elapsed)
