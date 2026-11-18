"""UX1 (Persona Blueprint waves A and B): every persona has real work in a free trial's sample, one access concept.

- The sample brief of SAMPLE-INV-001 is accepted for decision by the sample reviewer (segregation of duties: the
  sample author wrote it, neither sample account can sign in) and waits in the Decision Maker's approvals queue; a
  risk review is requested and waits in the Risk Reviewer's queue. Staging is idempotent and never touches a decided
  case. The flagship's step 5 ticks when the person reads the accepted brief, step 6 when a person signs.
- The session says who owns the trial, so only they ask for what only they are shown (no background 403).
- One role list: the role names are the workspace persona names, and a customer administrator may give Service Desk.
"""

from __future__ import annotations

import uuid

import pytest

from access_control.personas import WORKSPACE_PERSONAS
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_release_c1_0_10_73 import _invite, _ok
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

STORY = "/api/v1/trial/one-story"


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:ux1-cleanup")


@pytest.fixture(scope="module")
def trial():
    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"owner": owner, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def _case_id(user) -> str:
    return _ok(user.get(STORY))["flagship"]["investigation"]["id"]


def test_the_sample_brief_waits_for_a_signature_checked_by_a_second_sample_person(trial):
    owner = trial["owner"]
    case_id = _case_id(owner)
    screen = _ok(owner.get(f"/api/v1/investigations/{case_id}/decision"))
    brief = screen["brief"]
    assert brief["status"] == "APPROVED_FOR_DECISION"
    assert brief["quality_reviewer_name"] == "MDARIX sample reviewer"
    assert brief["created_by_name"] != brief["quality_reviewer_name"]
    from backend.app.db.models.foundation import AuthUser
    from backend.app.db.models.reviews import BriefReviewAction

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        sample = db.query(AuthUser).filter(AuthUser.username.like("sample-author+%")).all()
        # Nobody signs in as the sample: every sample account is disabled.
        assert sample and {user.status for user in sample} == {"DISABLED"}
        actions = [
            row.action
            for row in db.query(BriefReviewAction)
            .filter(BriefReviewAction.tenant_id == trial["tenant_id"])
            .order_by(BriefReviewAction.created_at)
        ]
    assert actions == ["START_REVIEW", "ACCEPT_FOR_DECISION"]
    # The Decision Maker finds it in their approvals queue and may sign it (they did not write it).
    _, approver, _ = _invite(owner, "decision", "Dev Decision")
    queue = _ok(approver.get("/api/v1/decisions/queue"))
    assert [item["investigation"]["id"] for item in queue["items"]] == [case_id]
    assert queue["items"][0]["actions"]["can_decide"] is True
    assert queue["items"][0]["investigation"]["identifier"] == "SAMPLE-INV-001"
    # The Executive (view only) may not read the queue at all.
    _, executive, _ = _invite(owner, "executive", "Esha Executive")
    assert executive.get("/api/v1/decisions/queue").status_code == 403


def test_a_risk_review_is_requested_from_the_risk_reviewers(trial):
    owner = trial["owner"]
    case_id = _case_id(owner)
    _, risk, _ = _invite(owner, "risk", "Ria Risk")
    queue = _ok(risk.get("/api/v1/case-reviews?type=RISK&box=queue"))["items"]
    assert len(queue) == 1
    review = queue[0]
    assert review["investigation"]["id"] == case_id and review["status"] == "REQUESTED"
    assert review["investigation"]["identifier"] == "SAMPLE-INV-001"
    assert "risk file" in review["request_reason"] and review["due_at"]
    # The reviewer starts it from the queue in one step.
    started = risk.post(f"/api/v1/case-reviews/{review['id']}/start", json={})
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"


def test_staging_is_idempotent_and_the_flagship_brief_ticks_when_read(trial):
    from backend.app.trial import sample_persona_work

    owner = trial["owner"]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert sample_persona_work.owed(db, trial["tenant_id"]) == []
        assert sample_persona_work.stage(db, trial["tenant_id"]) == {"created": False}
    run = _ok(owner.get(STORY))["flagship"]
    # Accepted by the sample reviewer: not the person's step until they read it, and only in its place.
    assert not run["steps"][4]["done"]
    marked = owner.post(
        f"{STORY}/marks", json={"run": "flagship", "step": "brief", "complaint_id": run["investigation"]["id"]}
    )
    assert marked.status_code == 409 and marked.json()["detail"]["code"] == "STEP_NOT_YET"


def test_a_decided_or_reviewed_case_is_left_alone():
    from backend.app.trial import sample_persona_work
    from backend.app.trial.flagship import find_case

    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            case = find_case(db, tenant_id)
            case.workflow_state, case.status = "CLOSED", "CLOSED"
            db.commit()
            assert sample_persona_work.owed(db, tenant_id) == []
    finally:
        _purge(tenant_id)


def test_the_session_says_who_owns_the_trial(trial):
    owner = trial["owner"]
    assert _ok(owner.get("/api/v1/session/context"))["trial_owner"] is True
    _, colleague, _ = _invite(owner, "regulatory", "Rekha Regulatory")
    context = _ok(colleague.get("/api/v1/session/context"))
    assert context["trial_owner"] is False
    # What only the owner is shown stays refused for a colleague (the screen no longer asks for it).
    assert colleague.get("/api/v1/admin/validation-evidence").status_code == 403


def test_one_role_list_with_the_persona_names():
    from backend.app.role_codes import ROLE_LABELS

    for persona in WORKSPACE_PERSONAS:
        if persona.code in ("admin", "quality"):
            continue
        assert ROLE_LABELS[persona.role] == persona.label, persona.code
    assert ROLE_LABELS["LEADER"] == "Quality Leader"
    from backend.app.access.identity import STANDARD_ROLES

    assert "SERVICE_DESK" in STANDARD_ROLES


def test_the_refresh_gives_an_older_trial_the_pending_work_once():
    from backend.app.db.models.reviews import BriefReviewAction, CaseReview, DecisionBriefVersion
    from backend.app.trial.flagship import find_case
    from tests.test_w1_flagship import _script

    script = _script()
    owner, approval, _ = _approved_trial_client()
    tenant_id, key = uuid.UUID(approval["tenant_id"]), approval["tenant_key"]
    try:
        # A trial seeded before UX1: the brief submitted and untouched, no risk review.
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            case = find_case(db, tenant_id)
            db.query(BriefReviewAction).filter(BriefReviewAction.tenant_id == tenant_id).delete()
            db.query(CaseReview).filter(CaseReview.tenant_id == tenant_id).delete()
            brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == case.id).one()
            brief.status, brief.reviewed_by, brief.reviewed_at = "READY_FOR_REVIEW", None, None
            db.commit()
        with SessionLocal() as db:
            planned = {item["tenant"]: item for item in script.refresh(db, apply=False)}[key]
        assert planned["sample"] == [
            "the sample brief accepted for decision, waiting for a signature (UX1)",
            "a risk review of SAMPLE-INV-001 requested from the risk reviewers (UX1)",
        ]
        lines = script.count_lines([planned])
        assert lines == ["Trial 1 of 1: would add 2 sample item(s): " + "; ".join(planned["sample"])]
        with SessionLocal() as db:
            script.refresh(db, apply=True)
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            case = find_case(db, tenant_id)
            brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == case.id).one()
            assert brief.status == "APPROVED_FOR_DECISION"
            assert db.query(CaseReview).filter(CaseReview.investigation_id == case.id).count() == 1
        with SessionLocal() as db:
            assert {item["tenant"]: item["result"] for item in script.refresh(db, apply=False)}[
                key
            ] == "already has the story"
    finally:
        _purge(tenant_id)
