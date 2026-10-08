"""Decision Brief API: the controlled, versioned brief of a case, its quality review and the quality dashboard.

- ``GET  /api/v1/investigations/{id}/decision-brief``: the latest version, every version, the submission gate and
  what the signed-in person may do;
- ``GET  /api/v1/investigations/{id}/decision-brief/versions/{n}``: one version in full, with its review actions;
- ``POST /api/v1/investigations/{id}/decision-brief`` (``investigation.work``): start version 1, or a new version
  after a return or an approval;
- ``PUT  .../decision-brief/draft`` and ``POST .../decision-brief/draft/refresh`` (``investigation.work``): the
  author's narrative, and the content composed again from the case's records (a DRAFT only);
- ``POST .../decision-brief/submit`` (``investigation.work``): to quality review, once the gate allows it;
- ``POST .../decision-brief/versions/{n}/start-review`` and ``.../review`` (``quality.review``; never by whoever
  wrote or submitted the version): start the review, accept for decision, return, reject the proposed conclusion,
  escalate;
- ``GET  /api/v1/decision-briefs/summary`` and ``GET /api/v1/decision-briefs`` (``quality.review``): the quality
  dashboard.

Reading a case's brief needs only a signed-in session; everything is limited to the signed-in organization (another
organization's case is "not found"). Every change locks the case row (then the version row), is audited (``BRIEF_*``,
``INVESTIGATION_STATE_CHANGED``) and moves workflow tasks in the same transaction. A version is frozen once
submitted: only its status and review fields change after that, and its content keeps its SHA-256 fingerprint.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import case as sql_case
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_WORK, QUALITY_REVIEW, require_permission
from backend.app.case_workflow import states
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.case_scope import OPEN_INVESTIGATION_STATES
from backend.app.db.models.foundation import Investigation
from backend.app.db.models.reviews import BRIEF_STATUSES, BriefReviewAction, DecisionBriefVersion
from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
from backend.app.db.session import get_db
from backend.app.decision_brief import compose as composer
from backend.app.decision_brief import rules
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.inventory import error, load_case
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.workflow import tasks as task_service
from backend.app.workflow.labels import role_label

logger = logging.getLogger("mdarix.decision_brief")

router = APIRouter(tags=["Decision Brief"])
CASE_BASE = "/api/v1/investigations/{investigation_id}/decision-brief"
LIST_BASE = "/api/v1/decision-briefs"
SOURCE_TYPE = "DecisionBriefVersion"
ENTITY_TYPE = "DecisionBriefVersion"
# The decision step does not take a new brief once the case is decided, closed or cancelled.
NOT_SUBMITTABLE_STATES = ("DECIDED", *states.CLOSED_STATES)
# The quality dashboard reads the readiness of at most this many open cases (most urgent first).
BLOCKED_SCAN_LIMIT = 50
DASHBOARD_LIST_LIMIT = 100
_PRIORITY_ORDER = sql_case(states.PRIORITY_RANK, value=Investigation.priority, else_=len(states.PRIORITY_RANK))


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _refuse_closed(case: Investigation) -> None:
    if states.case_state(case) in states.CLOSED_STATES:
        raise error(409, "CASE_CLOSED", "The case is closed; its brief can no longer change")


def _versions(db: Session, case: Investigation) -> list[DecisionBriefVersion]:
    return (
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version.desc())
        .all()
    )


def _version(db: Session, case: Investigation, version: int, *, lock: bool = False) -> DecisionBriefVersion:
    query = db.query(DecisionBriefVersion).filter(
        DecisionBriefVersion.tenant_id == case.tenant_id,
        DecisionBriefVersion.investigation_id == case.id,
        DecisionBriefVersion.version == version,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise error(404, "BRIEF_VERSION_NOT_FOUND", "This version of the brief does not exist")
    return row


def _latest(db: Session, case: Investigation, *, lock: bool = False) -> DecisionBriefVersion | None:
    query = (
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version.desc())
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _draft(db: Session, case: Investigation) -> DecisionBriefVersion:
    row = _latest(db, case, lock=True)
    if row is None:
        raise error(404, "BRIEF_NOT_FOUND", "This case has no brief yet")
    if row.status != rules.DRAFT:
        raise error(
            409,
            "BRIEF_NOT_EDITABLE",
            f"Version {row.version} is {rules.status_label(row.status).lower()}; only a draft changes",
        )
    return row


def _names(control_db: Session, tenant_id, refs) -> dict[str, str]:
    return composer._names(control_db, tenant_id, refs)


def _author_refs(row: DecisionBriefVersion) -> tuple[str | None, str | None, list[str]]:
    narrative = rules.normalize_narrative(row.narrative)
    return row.created_by, row.submitted_by, narrative["contributors"]


def _all_author_refs(row: DecisionBriefVersion, *extra: str | None) -> list[str]:
    """Everyone who wrote this version (creator, editors, submitter): kept on its review tasks so My Work never offers
    them the review of their own brief."""
    created_by, submitted_by, contributors = _author_refs(row)
    refs = [created_by, submitted_by, *contributors, *extra]
    return sorted({str(ref).strip() for ref in refs if ref and str(ref).strip()})


def _is_author(person: Person, row: DecisionBriefVersion | None) -> bool:
    if row is None:
        return False
    created_by, submitted_by, contributors = _author_refs(row)
    return rules.sod_denied(person.user_id, created_by=created_by, submitted_by=submitted_by, contributors=contributors)


def _audit(
    db: Session,
    ctx: AuthenticatedRequestContext,
    row: DecisionBriefVersion,
    action: str,
    now: datetime,
    *,
    role: str | None,
    reason: str | None = None,
    details: dict | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=str(ctx.user_id),
            action=action,
            entity_type=ENTITY_TYPE,
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
            details={
                "investigation_id": str(row.investigation_id),
                "version": row.version,
                "status": row.status,
                "content_hash": row.content_hash,
                "actor_role": role,
                **dict(details or {}),
            },
            created_at=now,
        )
    )


def _move_case(
    db: Session, ctx: AuthenticatedRequestContext, case: Investigation, target: str, reason: str, now, details: dict
) -> None:
    """Put the case in ``target`` (status kept in step), audited as INVESTIGATION_STATE_CHANGED. Nothing happens
    when it is already there."""
    current = states.case_state(case)
    if current == target:
        return
    before = {"workflow_state": current, "status": case.status}
    states.set_state(case, target, now)
    states.audit_state_change(
        db,
        case,
        actor_ref=str(ctx.user_id),
        before=before,
        reason=reason,
        correlation_id=ctx.correlation_id,
        details=details,
        now=now,
    )


# ---------------------------------------------------------------------------------------------- serializing


def _actions_view(db: Session, control_db: Session, row: DecisionBriefVersion) -> list[dict]:
    actions = (
        db.query(BriefReviewAction)
        .filter(BriefReviewAction.tenant_id == row.tenant_id, BriefReviewAction.brief_version_id == row.id)
        .order_by(BriefReviewAction.created_at, BriefReviewAction.id)
        .all()
    )
    names = _names(control_db, row.tenant_id, (item.actor_ref for item in actions))
    return [
        {
            "action": item.action,
            "action_label": rules.action_label(item.action),
            "comment": item.comment,
            "actor_name": names.get(str(item.actor_ref)),
            "actor_role": item.actor_role,
            "actor_role_label": role_label(item.actor_role),
            "created_at": _iso(item.created_at),
        }
        for item in actions
    ]


def version_summary(row: DecisionBriefVersion, names: dict[str, str]) -> dict:
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "version": row.version,
        "status": row.status,
        "status_label": rules.status_label(row.status),
        "title": row.title,
        "created_by_name": names.get(str(row.created_by)),
        "created_at": _iso(row.created_at),
        "submitted_by_name": names.get(str(row.submitted_by)) if row.submitted_by else None,
        "submitted_at": _iso(row.submitted_at),
        "reviewed_by_name": names.get(str(row.reviewed_by)) if row.reviewed_by else None,
        "reviewed_at": _iso(row.reviewed_at),
        "content_hash": row.content_hash,
    }


def version_view(db: Session, control_db: Session, row: DecisionBriefVersion) -> dict:
    """A version in full: content, the author's narrative (with the names of who wrote it), the readiness snapshot,
    its fingerprint (and whether the stored content still matches it) and its review actions."""
    narrative = rules.normalize_narrative(row.narrative)
    names = _names(
        control_db,
        row.tenant_id,
        [row.created_by, row.submitted_by, row.reviewed_by, *narrative["contributors"]],
    )
    shown = {key: value for key, value in narrative.items() if key != "contributors"}
    shown["contributor_names"] = sorted({names[ref] for ref in narrative["contributors"] if ref in names})
    return {
        **version_summary(row, names),
        "investigation_id": str(row.investigation_id),
        "created_role": row.created_role,
        "updated_at": _iso(row.updated_at),
        "editable": row.status == rules.DRAFT,
        "content": row.content or {},
        "narrative": shown,
        "readiness": row.readiness or {},
        "hash_verified": bool(row.content_hash) and rules.content_hash(row.content, row.narrative) == row.content_hash,
        "scope_version": row.scope_version,
        "source_ai_brief_id": str(row.source_ai_brief_id) if row.source_ai_brief_id else None,
        "review_actions": _actions_view(db, control_db, row),
    }


# -------------------------------------------------------------------------------------------------- reading


def _brief_payload(db: Session, control_db: Session, person: Person, case: Investigation) -> dict:
    rows = _versions(db, case)
    current = rows[0] if rows else None
    names = _names(control_db, case.tenant_id, [ref for row in rows for ref in (row.created_by, row.submitted_by)])
    is_draft = current is not None and current.status == rules.DRAFT
    checks = composer.case_readiness(db, case).get("checks") or []
    # The narrative is judged only on a draft (the version that can be submitted); without one nothing is submitted.
    gate = rules.evaluate_gate(checks, current.narrative if is_draft else None, check_narrative=is_draft)
    if not is_draft:
        gate["can_submit"] = False
    return {
        "investigation": composer.investigation_section(case),
        "current": version_view(db, control_db, current) if current is not None else None,
        "versions": [version_summary(row, names) for row in rows],
        "gate": gate,
        "actions": rules.brief_actions(
            status=current.status if current is not None else None,
            can_work=person.holds(INVESTIGATION_WORK),
            can_quality_review=person.holds(QUALITY_REVIEW),
            is_author=_is_author(person, current),
            case_open=states.case_state(case) not in states.CLOSED_STATES,
            gate_ok=bool(gate["can_submit"]),
        ),
    }


@router.get(CASE_BASE)
def get_decision_brief(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's latest brief version, every version (newest first), the submission gate and the person's actions."""
    person = current_person(control_db, ctx)
    case = load_case(db, _tenant(ctx), investigation_id)
    return _brief_payload(db, control_db, person, case)


@router.get(CASE_BASE + "/versions/{version}")
def get_decision_brief_version(
    investigation_id: uuid.UUID,
    version: int = Path(ge=1, le=100000),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    case = load_case(db, _tenant(ctx), investigation_id)
    return version_view(db, control_db, _version(db, case, version))


# ------------------------------------------------------------------------------------------------- writing


def _ai_draft(db: Session, case: Investigation) -> tuple[dict, uuid.UUID]:
    brief = composer.latest_ai_brief(db, case)
    text = rules.ai_draft_text(brief.content if brief is not None else None)
    if brief is None or not text:
        raise error(
            409, "AI_DRAFT_NOT_AVAILABLE", "This case has no generated brief to start from; write the narrative"
        )
    return (
        {
            "ai_draft_used": True,
            "ai_draft_text": text,
            "ai_draft_label": rules.AI_DRAFT_LABEL,
            "ai_draft_source": {
                "brief_id": str(brief.id),
                "business_id": brief.business_id,
                "brief_version": brief.brief_version,
                "ai_execution_id": str(brief.ai_execution_id) if brief.ai_execution_id else None,
            },
        },
        brief.id,
    )


@router.post(CASE_BASE, status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def create_decision_brief(
    investigation_id: uuid.UUID,
    payload: rules.ComposePayload | None = None,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Start version 1 of the case's brief, or a new version once the latest is returned or approved (its narrative
    is copied, its content composed afresh). Refused while a version is being written or reviewed."""
    payload = payload or rules.ComposePayload()
    person = current_person(control_db, ctx)
    case = load_case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    latest = _latest(db, case, lock=True)
    if latest is not None and latest.status in rules.IN_PROGRESS_STATUSES:
        raise error(
            409,
            "BRIEF_ALREADY_OPEN",
            f"Version {latest.version} is {rules.status_label(latest.status).lower()}; finish it first",
        )
    narrative = rules.normalize_narrative(latest.narrative if latest is not None else None)
    source_ai_brief_id = latest.source_ai_brief_id if latest is not None else None
    if payload.use_ai_draft:
        draft, source_ai_brief_id = _ai_draft(db, case)
        narrative.update(draft)
    narrative = rules.with_contributor(narrative, person.user_id)
    now = states.now_utc()
    content, state = composer.compose(db, control_db, case, now=now, ai_draft_used=narrative["ai_draft_used"])
    number = (latest.version if latest is not None else 0) + 1
    role = person.role_for(INVESTIGATION_WORK)
    row = DecisionBriefVersion(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        version=number,
        status=rules.DRAFT,
        title=f"Decision brief {case.business_id} v{number}",
        content=content,
        narrative=narrative,
        readiness=state,
        content_hash=rules.content_hash(content, narrative),
        scope_version=content["context"]["scope_version"] or None,
        source_ai_brief_id=source_ai_brief_id,
        created_by=person.user_id,
        created_role=role,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        ctx,
        row,
        "BRIEF_CREATED",
        now,
        role=role,
        details={
            "previous_version": latest.version if latest is not None else None,
            "previous_status": latest.status if latest is not None else None,
            "ai_draft_used": narrative["ai_draft_used"],
        },
    )
    db.commit()
    return version_view(db, control_db, row)


@router.put(CASE_BASE + "/draft", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def update_decision_brief_draft(
    investigation_id: uuid.UUID,
    payload: rules.DraftPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The author's narrative of the draft (only the fields given change)."""
    person = current_person(control_db, ctx)
    case = load_case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    row = _draft(db, case)
    changes = {key: getattr(payload, key) for key in payload.model_fields_set}
    narrative, changed = rules.merge_narrative(row.narrative, changes)
    if not changed:
        return version_view(db, control_db, row)
    narrative = rules.with_contributor(narrative, person.user_id)
    now = states.now_utc()
    row.narrative = narrative
    row.content_hash = rules.content_hash(row.content, narrative)
    row.updated_at = now
    _audit(
        db, ctx, row, "BRIEF_DRAFT_UPDATED", now, role=person.role_for(INVESTIGATION_WORK), details={"fields": changed}
    )
    db.commit()
    return version_view(db, control_db, row)


@router.post(CASE_BASE + "/draft/refresh", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def refresh_decision_brief_draft(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Compose the draft's content again from the case's records as they stand now."""
    person = current_person(control_db, ctx)
    case = load_case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    row = _draft(db, case)
    narrative = rules.with_contributor(row.narrative, person.user_id)
    now = states.now_utc()
    before = row.content_hash
    content, state = composer.compose(db, control_db, case, now=now, ai_draft_used=narrative["ai_draft_used"])
    row.content = content
    row.readiness = state
    row.narrative = narrative
    row.scope_version = content["context"]["scope_version"] or None
    row.content_hash = rules.content_hash(content, narrative)
    row.updated_at = now
    _audit(
        db,
        ctx,
        row,
        "BRIEF_REFRESHED",
        now,
        role=person.role_for(INVESTIGATION_WORK),
        old_values={"content_hash": before},
        new_values={"content_hash": row.content_hash},
        details={"evidence_set_hash": content["context"]["evidence_set_hash"]},
    )
    db.commit()
    return version_view(db, control_db, row)


def _quality_task_title(case: Investigation, row: DecisionBriefVersion) -> str:
    return f"Quality review of {case.business_id} brief v{row.version}"


@router.post(CASE_BASE + "/submit", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def submit_decision_brief(
    investigation_id: uuid.UUID,
    payload: rules.SubmitPayload | None = None,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Send the draft to quality review. Its content is composed one last time and the gate checked on it: a
    blocked or pending required check, an empty problem statement or proposed conclusion, or records that could not
    be read refuse it (409 BRIEF_NOT_READY with the blocking checks). Once submitted the version is frozen with its
    fingerprint; an earlier approved version is superseded, the case moves to "brief in review" and the reviewers'
    queue gets a QUALITY_REVIEW task."""
    payload = payload or rules.SubmitPayload()
    person = current_person(control_db, ctx)
    case = load_case(db, _tenant(ctx), investigation_id, lock=True)
    if states.case_state(case) in NOT_SUBMITTABLE_STATES:
        raise error(
            409,
            "CASE_NOT_OPEN_FOR_BRIEF",
            f"The case is {states.state_label(states.case_state(case)).lower()}; a brief can no longer be submitted",
        )
    row = _draft(db, case)
    narrative = rules.normalize_narrative(row.narrative)
    now = states.now_utc()
    content, state = composer.compose(db, control_db, case, now=now, ai_draft_used=narrative["ai_draft_used"])
    gate = rules.evaluate_gate(state.get("checks") or [], narrative, content_complete=not content.get("unavailable"))
    if not gate["can_submit"]:
        raise error(
            409,
            "BRIEF_NOT_READY",
            "The brief cannot go to quality review yet",
            blocking=gate["blocking"],
            warnings=gate["warnings"],
        )
    role = person.role_for(INVESTIGATION_WORK)
    actor = person.user_id
    row.content = content
    row.narrative = narrative
    row.readiness = state
    row.scope_version = content["context"]["scope_version"] or None
    row.content_hash = rules.content_hash(content, narrative)
    row.status = rules.READY_FOR_REVIEW
    row.submitted_by = actor
    row.submitted_at = now
    row.updated_at = now
    earlier = (
        db.query(DecisionBriefVersion)
        .filter(
            DecisionBriefVersion.tenant_id == case.tenant_id,
            DecisionBriefVersion.investigation_id == case.id,
            DecisionBriefVersion.id != row.id,
        )
        .order_by(DecisionBriefVersion.version)
        .with_for_update()
        .all()
    )
    superseded = []
    for old in earlier:
        if old.status == rules.APPROVED_FOR_DECISION:
            old.status = rules.SUPERSEDED
            old.updated_at = now
            superseded.append(old)
            _audit(
                db,
                ctx,
                old,
                "BRIEF_SUPERSEDED",
                now,
                role=role,
                reason=f"Version {row.version} was submitted",
                old_values={"status": rules.APPROVED_FOR_DECISION},
                new_values={"status": rules.SUPERSEDED},
                details={"superseded_by_version": row.version},
            )
            task_service.supersede_tasks(
                db,
                case.tenant_id,
                source_type=SOURCE_TYPE,
                source_id=old.id,
                task_types=["DECISION_APPROVAL"],
                outcome="BRIEF_RESUBMITTED",
                actor_ref=actor,
                actor_role=role,
                correlation_id=ctx.correlation_id,
            )
        if old.status == rules.RETURNED:
            # The author has acted on the return: its follow-up is done.
            task_service.complete_tasks(
                db,
                case.tenant_id,
                source_type=SOURCE_TYPE,
                source_id=old.id,
                task_types=["FOLLOW_UP"],
                outcome="RESUBMITTED",
                actor_ref=actor,
                actor_role=role,
                correlation_id=ctx.correlation_id,
            )
    _move_case(
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
        title=_quality_task_title(case, row),
        source_type=SOURCE_TYPE,
        source_id=row.id,
        investigation_id=case.id,
        priority=states.normalize_priority(case.priority),
        created_by=actor,
        actor_role=role,
        details={
            "brief_version": row.version,
            "brief_author_ref": actor,
            "brief_author_refs": _all_author_refs(row, actor),
        },
        correlation_id=ctx.correlation_id,
    )
    _audit(
        db,
        ctx,
        row,
        "BRIEF_SUBMITTED",
        now,
        role=role,
        reason=payload.comment,
        old_values={"status": rules.DRAFT},
        new_values={"status": rules.READY_FOR_REVIEW},
        details={
            "evidence_set_hash": content["context"]["evidence_set_hash"],
            "scope_version": row.scope_version,
            "superseded_versions": [old.version for old in superseded],
            "warnings": [item["key"] for item in gate["warnings"]],
        },
    )
    db.commit()
    return version_view(db, control_db, row)


# ------------------------------------------------------------------------------------------- quality review


def _reviewable(db: Session, person: Person, ctx, investigation_id: uuid.UUID, version: int):
    case = load_case(db, _tenant(ctx), investigation_id, lock=True)
    _refuse_closed(case)
    row = _version(db, case, version, lock=True)
    if _is_author(person, row):
        raise error(403, "SOD_DENIED", "You wrote or submitted this version of the brief; someone else reviews it")
    return case, row


def _review_tasks(db: Session, row: DecisionBriefVersion) -> list[WorkflowTask]:
    return (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == row.tenant_id,
            WorkflowTask.task_type == "QUALITY_REVIEW",
            WorkflowTask.source_entity_type == SOURCE_TYPE,
            WorkflowTask.source_entity_id == row.id,
            WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        )
        .order_by(WorkflowTask.created_at)
        .with_for_update()
        .all()
    )


def _claim_review_task(db: Session, ctx, person: Person, row: DecisionBriefVersion, role: str | None, now) -> None:
    """The reviewer takes the version's QUALITY_REVIEW task: their own stays theirs, else they claim the one waiting
    in the queue. Refused when every open review task is someone else's (409 REVIEW_TAKEN)."""
    tasks = _review_tasks(db, row)
    if not tasks or person.user_uuid is None:
        return
    for task in tasks:
        if task.assigned_user_id == person.user_uuid:
            if task.status == "ASSIGNED":
                task.status = "ACCEPTED"
                task.accepted_at = now
                task.updated_at = now
                task_service.record_event(
                    db,
                    task,
                    "ACCEPTED",
                    actor_ref=person.user_id,
                    actor_role=role,
                    from_status="ASSIGNED",
                    to_status="ACCEPTED",
                    correlation_id=ctx.correlation_id,
                    now=now,
                )
            return
    for task in tasks:
        if task.assigned_user_id is None and task.status in task_service.QUEUE_STATUSES:
            previous = task.status
            task.assigned_user_id = person.user_uuid
            task.status = "ACCEPTED"
            task.accepted_at = now
            task.updated_at = now
            task_service.record_event(
                db,
                task,
                "CLAIMED",
                actor_ref=person.user_id,
                actor_role=role,
                from_status=previous,
                to_status="ACCEPTED",
                details={"how": "quality review started"},
                correlation_id=ctx.correlation_id,
                now=now,
            )
            return
    raise error(409, "REVIEW_TAKEN", "Another reviewer has taken this review")


def _record_action(
    db: Session, ctx, row: DecisionBriefVersion, action: str, comment: str | None, role: str | None, now, **details
) -> None:
    db.add(
        BriefReviewAction(
            id=uuid.uuid4(),
            tenant_id=row.tenant_id,
            brief_version_id=row.id,
            investigation_id=row.investigation_id,
            action=action,
            comment=comment,
            actor_ref=str(ctx.user_id),
            actor_role=role,
            created_at=now,
        )
    )
    _audit(db, ctx, row, f"BRIEF_{action}", now, role=role, reason=comment, details=details)


def _start_review(db: Session, ctx, person: Person, row: DecisionBriefVersion, comment: str | None, role, now) -> None:
    _claim_review_task(db, ctx, person, row, role, now)
    before = row.status
    row.status = rules.status_after(row.status, rules.START_REVIEW)
    row.updated_at = now
    _record_action(db, ctx, row, rules.START_REVIEW, comment, role, now, from_status=before)


@router.post(CASE_BASE + "/versions/{version}/start-review", dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def start_decision_brief_review(
    investigation_id: uuid.UUID,
    version: int = Path(ge=1, le=100000),
    payload: rules.StartReviewPayload | None = None,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Start the quality review of a submitted version (UNDER_REVIEW); the reviewer takes its review task."""
    payload = payload or rules.StartReviewPayload()
    person = current_person(control_db, ctx)
    case, row = _reviewable(db, person, ctx, investigation_id, version)
    if rules.status_after(row.status, rules.START_REVIEW) is None:
        raise error(
            409,
            "BRIEF_STATE_CONFLICT",
            f"Version {row.version} is {rules.status_label(row.status).lower()}; only a version ready for review starts",
        )
    now = states.now_utc()
    _start_review(db, ctx, person, row, payload.comment, person.role_for(QUALITY_REVIEW), now)
    db.commit()
    return version_view(db, control_db, row)


def _author_user_id(control_db: Session, row: DecisionBriefVersion):
    from backend.app.workflow.people import find_user

    try:
        user = find_user(control_db, row.tenant_id, row.submitted_by or row.created_by)
    except Exception:
        logger.warning("The author of brief %s could not be read", row.id, exc_info=True)
        return None
    return user.id if user is not None else None


def _request_review(
    db: Session, ctx, person: Person, investigation_id: uuid.UUID, row: DecisionBriefVersion, review_type: str, reason
) -> dict:
    """Ask for a new risk or regulatory review of the case through the case reviews (backend/app/case_reviews: the
    review is requested for this brief version and queued for its reviewers). Runs after the return is saved, on the
    case locked again; a refusal (a review of the type is already open) or a failure is reported, never undoing the
    return."""
    try:
        from backend.app.case_reviews.router import request_review_and_task
    except ImportError:
        logger.warning("Case reviews are not available; no %s review was requested", review_type)
        return {"review_type": review_type, "requested": False, "reason": "Case reviews are not available"}
    brief_version_id = row.id

    def link_to_brief(review) -> None:
        review.brief_version_id = brief_version_id

    try:
        case = load_case(db, _tenant(ctx), investigation_id, lock=True)
        review = request_review_and_task(
            db, ctx, person, case, review_type=review_type, reason=reason, before_commit=link_to_brief
        )
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        message = detail.get("message") if isinstance(detail, dict) else None
        if message is None:
            logger.exception("Requesting a %s review failed; the return itself is saved", review_type)
        try:
            db.rollback()
        except Exception:
            logger.exception("The session could not be rolled back after a failed review request")
        return {
            "review_type": review_type,
            "requested": False,
            "reason": message or "The review could not be requested",
        }
    return {"review_type": review_type, "requested": True, "business_id": review.business_id}


@router.post(CASE_BASE + "/versions/{version}/review", dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def review_decision_brief(
    investigation_id: uuid.UUID,
    payload: rules.ReviewPayload,
    version: int = Path(ge=1, le=100000),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The reviewer's decision on a version under review (a version ready for review starts its review first):
    accept for decision (the case becomes ready for decision and the approvers' queue gets a DECISION_APPROVAL task),
    return it or reject its proposed conclusion (back to the author with a FOLLOW_UP task; a return for a risk or
    regulatory review also asks for that review), or escalate it to the leaders (it stays under review)."""
    person = current_person(control_db, ctx)
    case, row = _reviewable(db, person, ctx, investigation_id, version)
    action = payload.action
    if rules.status_after(row.status, action) is None:
        raise error(
            409,
            "BRIEF_STATE_CONFLICT",
            f"Version {row.version} is {rules.status_label(row.status).lower()}; it is not waiting for a review",
        )
    now = states.now_utc()
    role = person.role_for(QUALITY_REVIEW)
    actor = person.user_id
    if row.status == rules.READY_FOR_REVIEW:
        # Reviewing a version nobody started starts it first; stamped a moment earlier, so the history always lists
        # the start before the outcome (it is ordered by time).
        _start_review(db, ctx, person, row, None, role, now - timedelta(microseconds=1))
    before = row.status
    row.status = rules.status_after(row.status, action)
    row.updated_at = now
    if action != rules.ESCALATE:
        row.reviewed_by = actor
        row.reviewed_at = now
    _record_action(db, ctx, row, action, payload.comment, role, now, from_status=before, to_status=row.status)
    target = rules.case_state_after(action)
    if target is not None:
        _move_case(
            db,
            ctx,
            case,
            target,
            f"Brief version {row.version}: {rules.action_label(action).lower()}",
            now,
            {"brief_version_id": str(row.id), "brief_version": row.version, "quality_action": action},
        )
    if action == rules.ESCALATE:
        task_service.create_task(
            db,
            case.tenant_id,
            task_type="QUALITY_REVIEW",
            title=f"Escalated: quality review of {case.business_id} brief v{row.version}",
            source_type=SOURCE_TYPE,
            source_id=row.id,
            investigation_id=case.id,
            assigned_role=rules.ESCALATION_ROLE,
            priority=states.normalize_priority(case.priority),
            created_by=actor,
            actor_role=role,
            details={
                "brief_version": row.version,
                "comment": payload.comment,
                "escalated_by": actor,
                "brief_author_refs": _all_author_refs(row),
            },
            correlation_id=ctx.correlation_id,
        )
    else:
        task_service.complete_tasks(
            db,
            case.tenant_id,
            source_type=SOURCE_TYPE,
            source_id=row.id,
            task_types=["QUALITY_REVIEW"],
            outcome=action,
            actor_ref=actor,
            actor_role=role,
            reason=payload.comment,
            correlation_id=ctx.correlation_id,
        )
    if action == rules.ACCEPT_FOR_DECISION:
        task_service.create_task(
            db,
            case.tenant_id,
            task_type="DECISION_APPROVAL",
            title=f"Decide on {case.business_id} (brief v{row.version})",
            source_type=SOURCE_TYPE,
            source_id=row.id,
            investigation_id=case.id,
            priority=states.normalize_priority(case.priority),
            created_by=actor,
            actor_role=role,
            details={
                "brief_version": row.version,
                "brief_author_ref": row.submitted_by or row.created_by,
                "brief_author_refs": _all_author_refs(row),
            },
            correlation_id=ctx.correlation_id,
        )
    elif action in rules.RETURN_ACTIONS:
        author = _author_user_id(control_db, row)
        task_service.create_task(
            db,
            case.tenant_id,
            task_type="FOLLOW_UP",
            title=f"{case.business_id} brief v{row.version}: {rules.action_label(action).lower()}",
            source_type=SOURCE_TYPE,
            source_id=row.id,
            investigation_id=case.id,
            assigned_user_id=author,
            priority=states.normalize_priority(case.priority),
            created_by=actor,
            is_return=True,
            actor_role=role,
            details={"brief_version": row.version, "quality_action": action, "comment": payload.comment},
            correlation_id=ctx.correlation_id,
        )
    db.commit()
    review_request = None
    if action in rules.REVIEW_REQUESTS:
        reason = f"Quality review of {case.business_id} brief v{row.version}: {payload.comment}"
        review_request = _request_review(
            db, ctx, person, investigation_id, row, rules.REVIEW_REQUESTS[action], rules.shorten(reason)
        )
    return {**version_view(db, control_db, row), "review_request": review_request}


# ------------------------------------------------------------------------------------------- quality dashboard


def _submitted_rows(db: Session, tenant_id, statuses) -> list[tuple[DecisionBriefVersion, Investigation]]:
    return (
        db.query(DecisionBriefVersion, Investigation)
        .join(
            Investigation,
            (Investigation.id == DecisionBriefVersion.investigation_id)
            & (Investigation.tenant_id == DecisionBriefVersion.tenant_id),
        )
        .filter(DecisionBriefVersion.tenant_id == tenant_id, DecisionBriefVersion.status.in_(list(statuses)))
        .order_by(DecisionBriefVersion.submitted_at.asc().nulls_last(), DecisionBriefVersion.version)
        .all()
    )


def _investigation_ref(case: Investigation) -> dict:
    return {
        "id": str(case.id),
        "business_id": case.business_id,
        "question": case.investigation_question,
        "product_id": str(case.product_id) if case.product_id else None,
    }


def _list_item(row: DecisionBriefVersion, case: Investigation, names: dict[str, str], person: Person) -> dict:
    """A brief version in the quality lists: the version (``business_id`` is the brief's), its case nested under
    ``investigation`` (with flat ``investigation_*`` aliases)."""
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "investigation": _investigation_ref(case),
        "investigation_id": str(case.id),
        "investigation_business_id": case.business_id,
        "question": case.investigation_question,
        "priority": case.priority,
        "workflow_state": states.case_state(case),
        "brief_id": str(row.id),
        "brief_business_id": row.business_id,
        "version": row.version,
        "status": row.status,
        "status_label": rules.status_label(row.status),
        "submitted_by_name": names.get(str(row.submitted_by)) if row.submitted_by else None,
        "submitted_at": _iso(row.submitted_at),
        "reviewed_by_name": names.get(str(row.reviewed_by)) if row.reviewed_by else None,
        "reviewed_at": _iso(row.reviewed_at),
        "can_review": row.status in rules.REVIEWABLE_STATUSES and not _is_author(person, row),
    }


@router.get(LIST_BASE + "/summary", dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def decision_brief_summary(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The quality dashboard: briefs waiting for review (most urgent case first), those under review by the person,
    returned briefs not yet followed by a new version, resubmissions, and open cases whose readiness is blocked."""
    person = current_person(control_db, ctx)
    tenant_id = _tenant(ctx)
    now = states.now_utc()
    reviewing = _submitted_rows(db, tenant_id, rules.REVIEWABLE_STATUSES)
    versions_by_case: dict = {}
    for case_id, number, status in db.query(
        DecisionBriefVersion.investigation_id, DecisionBriefVersion.version, DecisionBriefVersion.status
    ).filter(DecisionBriefVersion.tenant_id == tenant_id):
        versions_by_case.setdefault(case_id, []).append((number, status))
    returned_open = sum(
        1 for items in versions_by_case.values() if max(items, key=lambda item: item[0])[1] == rules.RETURNED
    )
    resubmitted = sum(
        1
        for row, _ in reviewing
        if any(
            number < row.version and status == rules.RETURNED
            for number, status in versions_by_case.get(row.investigation_id, ())
        )
    )
    mine = set()
    under_review = [row.id for row, _ in reviewing if row.status == rules.UNDER_REVIEW]
    if under_review:
        mine = {
            item[0]
            for item in db.query(BriefReviewAction.brief_version_id).filter(
                BriefReviewAction.tenant_id == tenant_id,
                BriefReviewAction.brief_version_id.in_(under_review),
                BriefReviewAction.action == rules.START_REVIEW,
                BriefReviewAction.actor_ref == person.user_id,
            )
        }
    open_cases = (
        db.query(Investigation)
        .filter(
            Investigation.tenant_id == tenant_id,
            func.lower(func.coalesce(Investigation.status, "")) != "closed",
            Investigation.workflow_state.in_([item for item in OPEN_INVESTIGATION_STATES if item != "DECIDED"]),
        )
        .order_by(_PRIORITY_ORDER, Investigation.due_at.asc().nulls_last(), Investigation.business_id)
    )
    overdue = open_cases.filter(Investigation.due_at < now).count()
    blocked = []
    scanned = open_cases.limit(BLOCKED_SCAN_LIMIT).all()
    for case in scanned:
        checks = composer.case_readiness(db, case).get("checks") or []
        blocking = rules.blocked_checks(checks)
        if blocking:
            blocked.append(
                {
                    "investigation": _investigation_ref(case),
                    "investigation_id": str(case.id),
                    "investigation_business_id": case.business_id,
                    "question": case.investigation_question,
                    "priority": case.priority,
                    "workflow_state": states.case_state(case),
                    "blocking": blocking,
                }
            )
    names = _names(control_db, tenant_id, [ref for row, _ in reviewing for ref in (row.submitted_by, row.reviewed_by)])
    awaiting = sorted(
        reviewing,
        key=lambda pair: (
            states.PRIORITY_RANK.get(str(pair[1].priority or "").upper(), len(states.PRIORITY_RANK)),
            pair[0].submitted_at or now,
        ),
    )
    return {
        "counts": {
            "awaiting_review": sum(1 for row, _ in reviewing if row.status == rules.READY_FOR_REVIEW),
            "under_review_by_me": len(mine),
            "returned_open": returned_open,
            "resubmitted": resubmitted,
            "blocked_cases": len(blocked),
            "overdue_cases": overdue,
        },
        "awaiting": [_list_item(row, case, names, person) for row, case in awaiting[:DASHBOARD_LIST_LIMIT]],
        "blocked": blocked,
        "blocked_scan": {"scanned": len(scanned), "limit": BLOCKED_SCAN_LIMIT},
    }


@router.get(LIST_BASE, dependencies=[Depends(require_permission(QUALITY_REVIEW))])
def list_decision_briefs(
    status: str | None = Query(default=None, pattern="^(" + "|".join(BRIEF_STATUSES) + ")$"),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of the organization's brief versions (optionally of one status), most recently changed first."""
    person = current_person(control_db, ctx)
    tenant_id = _tenant(ctx)
    query = (
        db.query(DecisionBriefVersion, Investigation)
        .join(
            Investigation,
            (Investigation.id == DecisionBriefVersion.investigation_id)
            & (Investigation.tenant_id == DecisionBriefVersion.tenant_id),
        )
        .filter(DecisionBriefVersion.tenant_id == tenant_id)
    )
    if status:
        query = query.filter(DecisionBriefVersion.status == status)
    total = query.count()
    rows = (
        query.order_by(DecisionBriefVersion.updated_at.desc(), DecisionBriefVersion.version.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    names = _names(control_db, tenant_id, [ref for row, _ in rows for ref in (row.submitted_by, row.reviewed_by)])
    return {
        "items": [_list_item(row, case, names, person) for row, case in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "status": status,
    }
