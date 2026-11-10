"""The Decision Brief versions and their quality review. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
import uuid
from datetime import datetime

from backend.app.demo_golden_path.context import Story, logger
from backend.app.demo_golden_path.evidence import _ctx


# ------------------------------------------------------------------------------------------- the Decision Brief

BRIEF_V1 = {
    "problem_statement": (
        "FlowSure 300 Rev 2 pumps interrupt infusions after cassette loading: seven complaints in six weeks, all with "
        "cassettes moulded on the new tool T-4."
    ),
    "proposed_conclusion": (
        "The new cassette moulding tool is the most likely cause; contain lots from tool T-4 pending confirmation."
    ),
    "recommended_actions": ["Contain cassette lots moulded on tool T-4", "Bench-test more returned cassettes"],
    "author_notes": "Incoming inspection data of the suspect lots is not yet in the investigation.",
}
BRIEF_V2 = {
    "problem_statement": BRIEF_V1["problem_statement"],
    "proposed_conclusion": (
        "Cassettes moulded on tool T-4 can carry a valve membrane above the drawing tolerance that stays closed "
        "after loading; incoming inspection did not check the tolerance. The cause is partially supported; use "
        "error is retired. Correct the inspection plan and the tool, and contain the affected lots."
    ),
    "recommended_actions": [
        "Contain cassette lots C-301 to C-303",
        "Correct incoming inspection plan IP-77 to check the membrane tolerance",
        "Rework tool T-4 gate and re-verify flow continuity (DV-305) with T-4 cassettes",
    ],
    "author_notes": "Rev 1 cassettes from the old tool could not be tested; accepted as a limitation.",
}
RETURN_COMMENT = (
    "The membrane dimension of lots C-301 to C-303 is still an open question: add the incoming inspection records "
    "before this goes to a decision."
)
ACCEPT_COMMENT = "Evidence, reviews and limitations are documented; ready for the decision maker."


def create_brief_version(s: Story, number: int, narrative: dict, created: datetime, submitted: datetime):
    """Ines composes version ``number`` of the brief from the case's records and submits it to quality review, as
    ``POST .../decision-brief`` and ``.../submit`` write it (an earlier returned version's follow-up completes)."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.db.models.reviews import DecisionBriefVersion
    from backend.app.decision_brief import compose as composer
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.workflow import tasks as task_service

    ines = s.person("INVESTIGATOR")
    ctx = _ctx(ines)
    role = ines.role_for(INVESTIGATION_WORK)
    text = brief_rules.with_contributor(dict(narrative), ines.user_id)
    content, state = composer.compose(s.db, s.db, s.case, now=created)
    row = DecisionBriefVersion(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        version=number,
        status=brief_rules.DRAFT,
        title=f"Decision brief {s.case.business_id} v{number}",
        content=content,
        narrative=text,
        readiness=state,
        content_hash=brief_rules.content_hash(content, text),
        scope_version=content["context"]["scope_version"] or None,
        created_by=ines.user_id,
        created_role=role,
        created_at=created,
        updated_at=created,
    )
    s.db.add(row)
    s.db.flush()
    brief_api._audit(s.db, ctx, row, "BRIEF_CREATED", created, role=role, details={"ai_draft_used": False})

    content, state = composer.compose(s.db, s.db, s.case, now=submitted)
    gate = brief_rules.evaluate_gate(state.get("checks") or [], text, content_complete=not content.get("unavailable"))
    if not gate["can_submit"]:
        logger.warning(
            "Golden path brief v%s would not pass the submission gate: %s",
            number,
            [item.get("key") for item in gate["blocking"]],
        )
    row.content = content
    row.readiness = state
    row.scope_version = content["context"]["scope_version"] or None
    row.content_hash = brief_rules.content_hash(content, text)
    row.status = brief_rules.READY_FOR_REVIEW
    row.submitted_by = ines.user_id
    row.submitted_at = submitted
    row.updated_at = submitted
    for old in s.db.query(DecisionBriefVersion).filter(
        DecisionBriefVersion.tenant_id == s.tenant_id,
        DecisionBriefVersion.investigation_id == s.case.id,
        DecisionBriefVersion.id != row.id,
        DecisionBriefVersion.status == brief_rules.RETURNED,
    ):
        task_service.complete_tasks(
            s.db,
            s.tenant_id,
            source_type=brief_api.SOURCE_TYPE,
            source_id=old.id,
            task_types=["FOLLOW_UP"],
            outcome="RESUBMITTED",
            actor_ref=ines.user_id,
            actor_role=role,
        )
    brief_api._move_case(
        s.db,
        ctx,
        s.case,
        "BRIEF_IN_REVIEW",
        f"Brief version {row.version} submitted for quality review",
        submitted,
        {"brief_version_id": str(row.id), "brief_version": row.version},
    )
    task_service.create_task(
        s.db,
        s.tenant_id,
        task_type="QUALITY_REVIEW",
        title=brief_api._quality_task_title(s.case, row),
        source_type=brief_api.SOURCE_TYPE,
        source_id=row.id,
        investigation_id=s.case.id,
        priority=s.case.priority,
        created_by=ines.user_id,
        actor_role=role,
        details={
            "brief_version": row.version,
            "brief_author_ref": ines.user_id,
            "brief_author_refs": brief_api._all_author_refs(row, ines.user_id),
        },
    )
    brief_api._audit(
        s.db,
        ctx,
        row,
        "BRIEF_SUBMITTED",
        submitted,
        role=role,
        old_values={"status": brief_rules.DRAFT},
        new_values={"status": brief_rules.READY_FOR_REVIEW},
        details={
            "evidence_set_hash": content["context"]["evidence_set_hash"],
            "scope_version": row.scope_version,
            "superseded_versions": [],
            "warnings": [item["key"] for item in gate["warnings"]],
        },
    )
    s.settle(submitted)
    s.made.setdefault("briefs", []).append(row)
    return row


def quality_review(s: Story, row, action: str, comment: str | None, moment: datetime) -> None:
    """Ravi's quality review of a submitted version (he takes the review task, then accepts it for decision or
    returns it), as ``POST .../decision-brief/versions/{n}/review`` writes it."""
    from backend.app.access.permissions import QUALITY_REVIEW
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.workflow import tasks as task_service

    ravi = s.person("REVIEWER")
    ctx = _ctx(ravi)
    role = ravi.role_for(QUALITY_REVIEW)
    if brief_api._is_author(ravi, row):
        raise ValueError("The quality reviewer wrote this brief")
    brief_api._start_review(s.db, ctx, ravi, row, None, role, moment)
    before = row.status
    row.status = brief_rules.status_after(row.status, action)
    row.updated_at = moment
    row.reviewed_by = ravi.user_id
    row.reviewed_at = moment
    brief_api._record_action(s.db, ctx, row, action, comment, role, moment, from_status=before, to_status=row.status)
    target = brief_rules.case_state_after(action)
    if target is not None:
        brief_api._move_case(
            s.db,
            ctx,
            s.case,
            target,
            f"Brief version {row.version}: {brief_rules.action_label(action).lower()}",
            moment,
            {"brief_version_id": str(row.id), "brief_version": row.version, "quality_action": action},
        )
    task_service.complete_tasks(
        s.db,
        s.tenant_id,
        source_type=brief_api.SOURCE_TYPE,
        source_id=row.id,
        task_types=["QUALITY_REVIEW"],
        outcome=action,
        actor_ref=ravi.user_id,
        actor_role=role,
        reason=comment,
    )
    if action == brief_rules.ACCEPT_FOR_DECISION:
        task_service.create_task(
            s.db,
            s.tenant_id,
            task_type="DECISION_APPROVAL",
            title=f"Decide on {s.case.business_id} (brief v{row.version})",
            source_type=brief_api.SOURCE_TYPE,
            source_id=row.id,
            investigation_id=s.case.id,
            priority=s.case.priority,
            created_by=ravi.user_id,
            actor_role=role,
            details={
                "brief_version": row.version,
                "brief_author_ref": row.submitted_by or row.created_by,
                "brief_author_refs": brief_api._all_author_refs(row),
            },
        )
    elif action in brief_rules.RETURN_ACTIONS:
        task_service.create_task(
            s.db,
            s.tenant_id,
            task_type="FOLLOW_UP",
            title=f"{s.case.business_id} brief v{row.version}: {brief_rules.action_label(action).lower()}",
            source_type=brief_api.SOURCE_TYPE,
            source_id=row.id,
            investigation_id=s.case.id,
            assigned_user_id=brief_api._author_user_id(s.db, row),
            priority=s.case.priority,
            created_by=ravi.user_id,
            is_return=True,
            actor_role=role,
            details={"brief_version": row.version, "quality_action": action, "comment": comment},
        )
    s.settle(moment)
