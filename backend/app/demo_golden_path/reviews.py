"""The risk and regulatory reviews. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
from datetime import timedelta

from backend.app.demo_golden_path.context import Story


# ------------------------------------------------------------------------------------- risk and regulatory reviews

# (type, reviewer role, permission, requested, started, completed (days ago), outcome, rationale, markets, notes)
CASE_REVIEWS = (
    (
        "RISK",
        "RISK_REVIEWER",
        "risk.review",
        30,
        29,
        28,
        "RISK_CONTROL_REVIEW_REQUIRED",
        "Occurrence of interrupted infusion is above the estimate in the risk file for ACD-RSK-F3-04; the incoming "
        "inspection control for cassette membranes must be reviewed and strengthened.",
        [],
        "Severity unchanged (delay of therapy, no injury reported); occurrence to be re-estimated after containment.",
    ),
    (
        "REGULATORY",
        "REGULATORY_REVIEWER",
        "regulatory.review",
        30,
        28,
        27,
        "REPORTABILITY_ASSESSMENT_COMPLETE",
        "Each complaint was assessed for reportability: malfunctions without injury, no event met the reporting "
        "criteria; trend monitoring continues under the post-market surveillance plan.",
        ["EU", "US"],
        "Synthetic demo assessment; reportability and deadlines are determined by the reviewer.",
    ),
)


def complete_case_review(s: Story, spec) -> object:
    """A review requested by Ines, taken and completed by its reviewer, with its task moving from the reviewers'
    queue to completed, as the case review endpoints and their hooks write it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_reviews import hooks as review_hooks
    from backend.app.case_reviews import service as reviews
    from backend.app.db.models.foundation import Risk
    from backend.app.workflow import tasks as task_service

    review_type, reviewer_role, permission, asked, started, done, outcome, rationale, markets, notes = spec
    ines = s.person("INVESTIGATOR")
    requester_role = ines.role_for(INVESTIGATION_WORK)
    requested = s.at(asked, 30 if review_type == "REGULATORY" else 0)
    row = reviews.create_review(
        s.db,
        s.case,
        review_type=review_type,
        actor_ref=ines.user_id,
        actor_role=requester_role,
        reason="The case reports repeated interruptions of therapy on a HIGH priority signal.",
        due_at=requested + timedelta(days=10),
        now=requested,
    )
    review_hooks._queue_task(
        s.db,
        row,
        case_reference=s.case.business_id,
        priority=s.case.priority,
        actor=ines.user_id,
        actor_role=requester_role,
    )
    s.settle(requested)

    reviewer = s.person(reviewer_role)
    role = reviewer.role_for(permission)
    moment = s.at(started)
    row.status = "IN_PROGRESS"
    row.reviewer_user_id = reviewer.user_uuid
    row.reviewer_role = role
    row.updated_at = moment
    reviews.audit(
        s.db,
        row,
        "CASE_REVIEW_STARTED",
        actor_ref=reviewer.user_id,
        actor_role=role,
        now=moment,
        old_values={"status": "REQUESTED"},
        new_values={"status": "IN_PROGRESS", "reviewer_user_id": reviewer.user_id},
    )
    for task in review_hooks._open_review_tasks(s.db, row):
        previous = task.status
        task.assigned_user_id = reviewer.user_uuid
        task.status = "IN_PROGRESS"
        task.accepted_at = moment
        task.updated_at = moment
        task_service.record_event(
            s.db,
            task,
            "CLAIMED",
            actor_ref=reviewer.user_id,
            actor_role=role,
            from_status=previous,
            to_status="IN_PROGRESS",
            details={"review_business_id": row.business_id},
            now=moment,
        )
        break
    s.settle(moment)

    moment = s.at(done)
    risk_ids = [
        str(item)
        for (item,) in s.db.query(Risk.id).filter(Risk.tenant_id == s.tenant_id, Risk.product_id == s.product.id)
    ]
    row.status = "COMPLETED"
    row.outcome = outcome
    row.rationale = rationale
    row.assessed = {"risk_ids": risk_ids if review_type == "RISK" else [], "markets": markets, "notes": notes}
    row.completed_at = moment
    row.updated_at = moment
    reviews.audit(
        s.db,
        row,
        "CASE_REVIEW_COMPLETED",
        actor_ref=reviewer.user_id,
        actor_role=role,
        now=moment,
        reason=rationale,
        old_values={"status": "IN_PROGRESS"},
        new_values={"status": "COMPLETED", "outcome": outcome},
        details={
            "outcome": outcome,
            "assessed_risks": len(row.assessed["risk_ids"]),
            "assessed_markets": len(markets),
            "scope_version": row.scope_version,
        },
    )
    task_service.complete_tasks(
        s.db,
        s.tenant_id,
        source_type="CaseReview",
        source_id=row.id,
        task_types=[review_hooks.rules.TYPE_TASKS[review_type]],
        outcome=outcome,
        actor_ref=reviewer.user_id,
        actor_role=role,
    )
    s.settle(moment)
    s.made.setdefault("reviews", []).append(row)
    return row
