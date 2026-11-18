"""Work waiting for the Approver and the Risk Reviewer in a free trial's sample (UX1, Persona Blueprint wave B).

Every persona's Home opens on its own part of the OrbitCare 300 story, so the sample holds pending work for the two
personas that had none:

- the Decision Brief of SAMPLE-INV-001 is accepted for decision by a second sample account, the sample reviewer: it
  waits in the approvals queue for a signature (the Decision Maker, or the trial owner on the flagship's step 6).
  Segregation of duties holds: the sample author wrote it, the sample reviewer checked it, and neither can sign in;
  a person signs;
- a risk review of SAMPLE-INV-001 is requested by the sample author: it waits in the risk reviewers' queue.

Both are written as the brief review and review request endpoints write them (status, history, queue tasks, audit),
inside the caller's transaction. Idempotent: a brief a person already started reviewing, a case already decided or
closed, and a case that already has a risk review are left as they are.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SAMPLE_REVIEWER_NAME = "MDARIX sample reviewer"
SAMPLE_REVIEWER_ROLE = "Reviewer"
ACCEPT_COMMENT = (
    "Sample quality review: the brief states what is known, what is contradicted and what is still unknown, and its "
    "proposed actions follow from them. Accepted for decision."
)
RISK_REASON = (
    "Sample request: the evidence touches the pressure-sensor hazard rows (SAMPLE-RSK-01, SAMPLE-RSK-02) after the "
    "NovaSense supplier change. Does the risk file need updating?"
)
RISK_DUE_DAYS = 5


def sample_reviewer(db: Session, tenant_id: uuid.UUID, now: datetime):
    """The sample account that checks the sample brief: it cannot sign in and holds no seat (its username starts as
    the sample author's does, so every list that leaves out the sample author leaves it out)."""
    from auth.service import NO_PASSWORD
    from backend.app.db.models.foundation import AuthUser

    email = f"sample-author+reviewer-{tenant_id.hex[:12]}@sample.invalid"
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.username == email).first()
    if user is not None:
        return user
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=SAMPLE_REVIEWER_NAME,
        company="MDARIX sample data",
        password_hash=NO_PASSWORD,
        role=SAMPLE_REVIEWER_ROLE,
        status="DISABLED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def _case(db: Session, tenant_id):
    from backend.app.trial.flagship import find_case

    return find_case(db, tenant_id)


def _decided(db: Session, case) -> bool:
    from backend.app.db.models.foundation import Decision

    return (
        db.query(Decision.id)
        .filter(
            Decision.tenant_id == case.tenant_id,
            Decision.investigation_id == case.id,
            Decision.decision_status == "SIGNED",
        )
        .first()
        is not None
    )


def _brief_waiting(db: Session, case):
    """The sample author's brief, submitted and untouched by any reviewer, or None."""
    from backend.app.db.models.reviews import BriefReviewAction, DecisionBriefVersion
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.trial.sample_decision import _author_email

    row = (
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version.desc())
        .first()
    )
    if row is None or row.status != brief_rules.READY_FOR_REVIEW:
        return None
    from backend.app.db.models.foundation import AuthUser

    author = (
        db.query(AuthUser.id)
        .filter(AuthUser.tenant_id == case.tenant_id, AuthUser.username == _author_email(case.tenant_id))
        .scalar()
    )
    if author is None or str(row.submitted_by or row.created_by) != str(author):
        return None
    touched = (
        db.query(BriefReviewAction.id)
        .filter(BriefReviewAction.tenant_id == case.tenant_id, BriefReviewAction.brief_version_id == row.id)
        .first()
    )
    return None if touched is not None else row


def _no_risk_review(db: Session, case) -> bool:
    from backend.app.db.models.reviews import CaseReview

    return (
        db.query(CaseReview.id)
        .filter(
            CaseReview.tenant_id == case.tenant_id,
            CaseReview.investigation_id == case.id,
            CaseReview.review_type == "RISK",
        )
        .first()
        is None
    )


def owed(db: Session, tenant_id) -> list[str]:
    """What ``stage`` would add, in words (the refresh script's list); empty when nothing is owed."""
    from backend.app.case_reviews.service import case_is_open

    case = _case(db, tenant_id)
    if case is None or not case_is_open(case) or _decided(db, case):
        return []
    wanted = []
    if _brief_waiting(db, case) is not None:
        wanted.append("the sample brief accepted for decision, waiting for a signature (UX1)")
    if _no_risk_review(db, case):
        wanted.append("a risk review of SAMPLE-INV-001 requested from the risk reviewers (UX1)")
    return wanted


def _accept_brief(db: Session, case, row, reviewer, now: datetime) -> None:
    """The sample reviewer starts the review and accepts the brief for decision, as ``POST .../review`` writes it:
    the actions and their audit, the case ready for decision, the review task done and the approvers' task."""
    from backend.app.access.permissions import QUALITY_REVIEW
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.demo_golden_path.context import _person
    from backend.app.workflow import tasks as task_service
    from backend.app.case_workflow import states

    person = _person(db, reviewer)
    ctx = SimpleNamespace(correlation_id=None, user_id=person.user_id)
    role = person.role_for(QUALITY_REVIEW) or SAMPLE_REVIEWER_ROLE
    brief_api._start_review(db, ctx, person, row, None, role, now - timedelta(minutes=5))
    before = row.status
    action = brief_rules.ACCEPT_FOR_DECISION
    row.status = brief_rules.status_after(row.status, action)
    row.updated_at = now
    row.reviewed_by = person.user_id
    row.reviewed_at = now
    brief_api._record_action(
        db, ctx, row, action, ACCEPT_COMMENT, role, now, from_status=before, to_status=row.status, sample=True
    )
    brief_api._move_case(
        db,
        ctx,
        case,
        brief_rules.case_state_after(action),
        f"Brief version {row.version}: {brief_rules.action_label(action).lower()}",
        now,
        {"brief_version_id": str(row.id), "brief_version": row.version, "quality_action": action},
    )
    task_service.complete_tasks(
        db,
        case.tenant_id,
        source_type=brief_api.SOURCE_TYPE,
        source_id=row.id,
        task_types=["QUALITY_REVIEW"],
        outcome=action,
        actor_ref=person.user_id,
        actor_role=role,
        reason=ACCEPT_COMMENT,
        correlation_id=None,
    )
    task_service.create_task(
        db,
        case.tenant_id,
        task_type="DECISION_APPROVAL",
        title=f"Decide on {case.business_id} (brief v{row.version})",
        source_type=brief_api.SOURCE_TYPE,
        source_id=row.id,
        investigation_id=case.id,
        priority=states.normalize_priority(case.priority),
        created_by=person.user_id,
        actor_role=role,
        details={
            "brief_version": row.version,
            "brief_author_ref": row.submitted_by or row.created_by,
            "brief_author_refs": brief_api._all_author_refs(row),
        },
        correlation_id=None,
    )


def _request_risk_review(db: Session, case, now: datetime):
    """The sample author asks the risk reviewers for a risk review of the case, as ``POST .../reviews`` writes it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_reviews import hooks, service
    from backend.app.demo_golden_path.context import _person
    from backend.app.trial.sample_decision import sample_author

    person = _person(db, sample_author(db, case.tenant_id, now))
    role = person.role_for(INVESTIGATION_WORK)
    review = service.create_review(
        db,
        case,
        review_type="RISK",
        actor_ref=person.user_id,
        actor_role=role,
        reason=RISK_REASON,
        due_at=now + timedelta(days=RISK_DUE_DAYS),
        now=now,
    )
    hooks._queue_task(
        db, review, case_reference=case.business_id, priority=case.priority, actor=person.user_id, actor_role=role
    )
    return review


def stage(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Add what ``owed`` lists, in a savepoint of the caller's transaction (the caller commits). Never fatal: a
    failure is logged and nothing of it is kept."""
    now = now or datetime.now(timezone.utc)
    case = _case(db, tenant_id)
    if case is None or not owed(db, tenant_id):
        return {"created": False}
    done: dict = {"created": True}
    savepoint = db.begin_nested()
    try:
        row = _brief_waiting(db, case)
        if row is not None:
            _accept_brief(db, case, row, sample_reviewer(db, tenant_id, now), now)
            done["brief_accepted"] = row.version
        if _no_risk_review(db, case):
            done["risk_review"] = _request_risk_review(db, case, now).business_id
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("The sample's pending persona work could not be staged")
        return {"created": False, "why": "ERROR"}
    return done
