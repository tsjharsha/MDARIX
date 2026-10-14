"""The sample decision of a free trial: the guided investigation arrives ready for its decision.

On the sample case (SAMPLE-INV-001) a sample author, not the trial's people, has saved the scope, reviewed the three
pieces of evidence and written and submitted the Decision Brief for quality review. The trial user then does what a
quality lead does: reviews the brief, accepts it for decision and signs the decision with password and authenticator
code. Segregation of duties is kept as on every case: the person who wrote a brief never reviews or signs it, and the
sample author is that other person. On the organization's own cases a colleague writes or reviews.

The sample author is an account of the trial organization that cannot sign in (status DISABLED, an unknown password,
no membership) and holds no seat. Every step is written as the product's own endpoints write it (scope version,
evidence review history, brief version, quality-review task, audit trail), inside a savepoint: if the brief would not
pass the submission gate, nothing is kept. Idempotent; flushes but never commits (the caller owns the transaction).
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.trial.sample_decision")

SAMPLE_CASE = "SAMPLE-INV-001"
SAMPLE_AUTHOR_NAME = "MDARIX sample author"
SAMPLE_AUTHOR_ROLE = "Investigator"

# The three pieces of evidence the sample case holds (sample_data.py), as the sample author reviewed them.
EVIDENCE_RELATIONSHIPS = {
    "SAMPLE-EV-001": "SUPPORTING",  # the supplier change record
    "SAMPLE-EV-002": "SUPPORTING",  # incoming inspection results, lots 003-004
    "SAMPLE-EV-003": "CONTEXTUAL",  # the complaint trend summary: quantifies the signal, not the cause
}

NARRATIVE = {
    "problem_statement": (
        "Pressure-alarm complaints on OrbitCare 300 rose from 0.8 a month on Rev A to 5.6 a month after Rev B, mostly "
        "from lots 003 and 004."
    ),
    "proposed_conclusion": (
        "The NovaSense pressure sensors fitted from Rev B, accepted with incoming inspection cut from 32 to 13 units "
        "per lot, are the most likely cause: sampled sensors in lots 003 and 004 read 4-6% high at the upper pressure "
        "range, and the earlier supplier's lots show none. Contain the affected lots, restore 32-unit incoming "
        "inspection, and confirm with a bench test of returned pumps."
    ),
    "recommended_actions": [
        "Contain OrbitCare 300 lots 003 and 004",
        "Restore incoming inspection to 32 units per lot for NovaSense pressure sensors",
        "Bench-test returned pumps from lots 003 and 004 at the upper pressure range",
    ],
    "author_notes": (
        "Sample Decision Brief, written for the free trial: review it as the quality reviewer, then sign the decision."
    ),
}


def _author_email(tenant_id: uuid.UUID) -> str:
    return f"sample-author+{tenant_id.hex[:12]}@sample.invalid"


def sample_author(db: Session, tenant_id: uuid.UUID, now: datetime):
    """The trial's sample author: an account that cannot sign in and holds no seat (created once)."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.trial.service import _hash

    email = _author_email(tenant_id)
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.username == email).first()
    if user is not None:
        return user
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=SAMPLE_AUTHOR_NAME,
        company="MDARIX sample data",
        # A password nobody knows; DISABLED refuses sign-in, activation and reset in any case.
        password_hash=_hash(secrets.token_urlsafe(32)),
        role=SAMPLE_AUTHOR_ROLE,
        status="DISABLED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def is_sample_author(user) -> bool:
    return bool(user is not None and str(user.username or "").startswith("sample-author+"))


def has_sample_decision(db: Session, tenant_id: uuid.UUID) -> bool:
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.models.reviews import DecisionBriefVersion

    return (
        db.query(DecisionBriefVersion.id)
        .join(Investigation, Investigation.id == DecisionBriefVersion.investigation_id)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == SAMPLE_CASE)
        .first()
        is not None
    )


def _review_evidence(db: Session, case, person, now: datetime) -> int:
    """The sample author's review of each piece of the case's evidence, as the evidence review endpoint writes it."""
    from backend.app.access.permissions import EVIDENCE_REVIEW
    from backend.app.db.models.foundation import Evidence, InvestigationEvidence
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow.inventory import review_event

    reviewed = 0
    links = (
        db.query(InvestigationEvidence, Evidence)
        .join(Evidence, Evidence.id == InvestigationEvidence.evidence_id)
        .filter(InvestigationEvidence.tenant_id == case.tenant_id, InvestigationEvidence.investigation_id == case.id)
        .all()
    )
    for link, evidence in links:
        relationship = EVIDENCE_RELATIONSHIPS.get(evidence.evidence_identifier or "", "CONTEXTUAL")
        if link.review_status not in (None, "UNREVIEWED"):
            continue
        before = {"review_status": link.review_status, "relationship": link.relationship}
        link.review_status = "ACCEPTED"
        link.relationship = relationship
        link.reviewed_by = person.user_id
        link.reviewed_at = now
        review_event(
            db,
            tenant_id=case.tenant_id,
            case_id=case.id,
            evidence_id=evidence.id,
            event_type="REVIEWED",
            actor=person,
            permission=EVIDENCE_REVIEW,
            from_status=before["review_status"],
            to_status="ACCEPTED",
            from_relationship=before["relationship"],
            to_relationship=relationship,
            now=now,
        )
        db.add(
            make_audit_event(
                tenant_id=case.tenant_id,
                actor_ref=person.user_id,
                action="EVIDENCE_REVIEWED",
                entity_type="InvestigationEvidence",
                entity_id=link.id,
                old_values=before,
                new_values={"review_status": "ACCEPTED", "relationship": relationship},
                details={
                    "investigation_id": str(case.id),
                    "evidence_id": str(evidence.id),
                    "actor_role": person.role_for(EVIDENCE_REVIEW),
                    "sample": True,
                },
                created_at=now,
            )
        )
        reviewed += 1
    db.flush()
    return reviewed


def _submit_brief(db: Session, case, person, now: datetime):
    """Version 1 of the brief, composed from the case and submitted for quality review, as ``POST
    .../decision-brief`` and ``.../submit`` write it. Returns (row, gate)."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.db.models.reviews import DecisionBriefVersion
    from backend.app.decision_brief import compose as composer
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.workflow import tasks as task_service

    ctx = SimpleNamespace(correlation_id=None, user_id=person.user_id)
    role = person.role_for(INVESTIGATION_WORK)
    text = brief_rules.with_contributor(dict(NARRATIVE), person.user_id)
    content, state = composer.compose(db, db, case, now=now)
    gate = brief_rules.evaluate_gate(state.get("checks") or [], text, content_complete=not content.get("unavailable"))
    row = DecisionBriefVersion(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        version=1,
        status=brief_rules.READY_FOR_REVIEW,
        title=f"Decision brief {case.business_id} v1",
        content=content,
        narrative=text,
        readiness=state,
        content_hash=brief_rules.content_hash(content, text),
        scope_version=content["context"]["scope_version"] or None,
        created_by=person.user_id,
        created_role=role,
        submitted_by=person.user_id,
        submitted_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    brief_api._audit(db, ctx, row, "BRIEF_CREATED", now, role=role, details={"ai_draft_used": False, "sample": True})
    brief_api._move_case(
        db,
        ctx,
        case,
        "BRIEF_IN_REVIEW",
        f"Brief version {row.version} submitted for quality review",
        now,
        {"brief_version_id": str(row.id), "brief_version": row.version},
    )
    task_service.create_task(
        db,
        case.tenant_id,
        task_type="QUALITY_REVIEW",
        title=brief_api._quality_task_title(case, row),
        source_type=brief_api.SOURCE_TYPE,
        source_id=row.id,
        investigation_id=case.id,
        priority=case.priority,
        created_by=person.user_id,
        actor_role=role,
        details={
            "brief_version": row.version,
            "brief_author_ref": person.user_id,
            "brief_author_refs": brief_api._all_author_refs(row, person.user_id),
        },
    )
    brief_api._audit(
        db,
        ctx,
        row,
        "BRIEF_SUBMITTED",
        now,
        role=role,
        old_values={"status": brief_rules.DRAFT},
        new_values={"status": brief_rules.READY_FOR_REVIEW},
        details={
            "evidence_set_hash": content["context"]["evidence_set_hash"],
            "scope_version": row.scope_version,
            "superseded_versions": [],
            "warnings": [item["key"] for item in gate["warnings"]],
            "sample": True,
        },
    )
    db.flush()
    return row, gate


def stage_sample_decision(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Bring the sample case to "brief submitted for quality review" (see the module docstring). Returns what was done;
    ``{"created": False, ...}`` when the case is missing, already has a brief, or the brief would not pass the gate."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_workflow import scope
    from backend.app.db.models.foundation import Investigation, InvestigationComplaint
    from backend.app.demo_golden_path.context import _person

    now = now or datetime.now(timezone.utc)
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == SAMPLE_CASE)
        .first()
    )
    if case is None:
        return {"created": False, "why": "NO_SAMPLE_CASE"}
    if has_sample_decision(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    savepoint = db.begin_nested()
    try:
        author = sample_author(db, tenant_id, now)
        person = _person(db, author)
        # The steps a few minutes apart, in the order an investigator takes them.
        steps = [now - timedelta(minutes=minutes) for minutes in (30, 20, 10)]
        if scope.latest_version(db, tenant_id, case.id) is None:
            complaint_ids = [
                row.complaint_id
                for row in db.query(InvestigationComplaint).filter(
                    InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id
                )
            ]
            scope.first_version(
                db,
                case,
                complaint_ids=complaint_ids,
                actor_ref=person.user_id,
                actor_role=person.role_for(INVESTIGATION_WORK),
                now=steps[0],
                with_lots=True,
            )
        reviewed = _review_evidence(db, case, person, steps[1])
        row, gate = _submit_brief(db, case, person, steps[2])
        if not gate["can_submit"]:
            savepoint.rollback()
            blocking = [item.get("key") for item in gate["blocking"]]
            logger.warning("Trial sample decision not staged: the brief would not pass the gate: %s", blocking)
            return {"created": False, "why": "GATE", "blocking": blocking}
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample decision could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, "brief_version": row.version, "evidence_reviewed": reviewed, "author": str(author.id)}
