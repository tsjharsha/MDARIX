"""What existing actions do to workflow tasks. Each ``on_*`` function is called by a router after its action is saved;
it runs inside a SAVEPOINT on the same data-plane session and commits its own changes (``tasks.run_hook``). A failure
is logged and swallowed: a task can never block or undo the action that caused it.

- opening a case: an INVESTIGATION task for its owner (accepted) or for the investigators' queue;
- managing a case: assignment moves that task, closing cancels every open task of the case, reopening adds one;
- a decision: a DECISION_APPROVAL task in the approvers' queue; a review that asks for more evidence returns the
  decision to its author (FOLLOW_UP, ``is_return``); a signature completes the approval; a material change replaces it;
- a risk review request: a RISK_REVIEW task in the risk reviewers' queue;
- a supplier evidence request: an EVIDENCE_REQUEST task waiting for the reply; the reply completes it and asks the
  requester to review it (EVIDENCE_REVIEW).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.workflow import tasks as service
from backend.app.workflow.labels import TASK_TYPES
from backend.app.workflow.people import acting_role, find_user

logger = logging.getLogger("mdarix.workflow")

INVESTIGATION = "Investigation"
DECISION = "Decision"
RISK = "Risk"
SUPPLIER_REQUEST = "SupplierEvidenceRequest"


def _permission(task_type: str) -> str:
    return TASK_TYPES[task_type].permission


def case_business_id(db: Session | None, tenant_id, investigation_id) -> str | None:
    """The business identifier of a case (INV000147) for e-mail deep links; None when unknown. Never raises."""
    if db is None or as_uuid(investigation_id) is None:
        return None
    from backend.app.db.models.foundation import Investigation

    try:
        row = (
            db.query(Investigation.business_id)
            .filter(Investigation.tenant_id == as_uuid(tenant_id), Investigation.id == as_uuid(investigation_id))
            .first()
        )
        return row[0] if row else None
    except Exception:
        logger.warning("The business id of investigation %s could not be read", investigation_id, exc_info=True)
        return None


def _investigation_title(case) -> str:
    return f"Investigate {case.business_id}: {service.shorten(case.investigation_question, 200)}"


def _investigation_task(db: Session, control_db, case, *, owner_user_id, actor_user_id: str):
    """An INVESTIGATION task for the case's owner (accepted when they gave it to themselves) or the queue."""
    actor = str(actor_user_id)
    owner = as_uuid(owner_user_id)
    status = None if owner is None else ("ACCEPTED" if str(owner) == actor else "ASSIGNED")
    return service.create_task(
        db,
        case.tenant_id,
        task_type="INVESTIGATION",
        title=_investigation_title(case),
        source_type=INVESTIGATION,
        source_id=case.id,
        investigation_id=case.id,
        assigned_user_id=owner,
        # A person's case task keeps its queue, so declining or releasing it hands it back to the investigators.
        assigned_role=TASK_TYPES["INVESTIGATION"].queue_role,
        created_by=actor,
        status=status,
        actor_role=acting_role(control_db, case.tenant_id, actor, _permission("INVESTIGATION")),
    )


# ------------------------------------------------------------------------------------------------- investigations


def on_investigation_opened(db: Session, control_db, case, *, actor_user_id, owner_user_id=None) -> None:
    def step(session):
        _investigation_task(session, control_db, case, owner_user_id=owner_user_id, actor_user_id=actor_user_id)

    service.run_hook(db, "investigation opened", step)


def on_investigation_managed(
    db: Session,
    control_db,
    case,
    *,
    actor_user_id,
    before_owner: str | None,
    before_status: str | None,
    assignee_user_id=None,
) -> None:
    """Closing cancels every open task of the case (CASE_CLOSED); reopening adds a task for the owner (or the
    queue); a new owner, or none, replaces the open INVESTIGATION task."""

    def step(session):
        actor = str(actor_user_id)
        role = acting_role(control_db, case.tenant_id, actor, _permission("INVESTIGATION"))
        was_closed = str(before_status or "").lower() == "closed"
        closed = str(case.status or "").lower() == "closed"
        if closed and not was_closed:
            service.cancel_tasks(
                session,
                case.tenant_id,
                investigation_id=case.id,
                outcome="CASE_CLOSED",
                actor_ref=actor,
                actor_role=role,
            )
            return
        if not closed and was_closed:
            _investigation_task(
                session, control_db, case, owner_user_id=_owner_id(control_db, case), actor_user_id=actor
            )
            return
        if (case.owner_ref or None) == (before_owner or None):
            return
        owner = as_uuid(assignee_user_id) if assignee_user_id is not None else _owner_id(control_db, case)
        service.supersede_tasks(
            session,
            case.tenant_id,
            source_type=INVESTIGATION,
            source_id=case.id,
            task_types=["INVESTIGATION"],
            outcome="REASSIGNED" if case.owner_ref else "UNASSIGNED",
            actor_ref=actor,
            actor_role=role,
        )
        _investigation_task(session, control_db, case, owner_user_id=owner, actor_user_id=actor)

    service.run_hook(db, "investigation managed", step)


def _owner_id(control_db, case):
    """The case owner's account id (``owner_ref`` holds a sign-in name); None when unowned or not an active
    colleague any more, so the task goes to the queue."""
    if not case.owner_ref or control_db is None:
        return None
    user = find_user(control_db, case.tenant_id, case.owner_ref)
    return user.id if user is not None else None


# ------------------------------------------------------------------------------------------------------ decisions


def _approval_task(session, decision, *, actor_ref: str, actor_role: str | None, case_reference: str | None):
    title = f"Approve or reject {decision.business_id}"
    if case_reference:
        title += f" on {case_reference}"
    return service.create_task(
        session,
        decision.tenant_id,
        task_type="DECISION_APPROVAL",
        title=title,
        source_type=DECISION,
        source_id=decision.id,
        investigation_id=decision.investigation_id,
        created_by=actor_ref,
        actor_role=actor_role,
        details={"decision_author_ref": str(decision.authorized_by_ref or "") or None},
    )


def on_decision_created(db: Session, control_db, decision, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        _approval_task(
            session,
            decision,
            actor_ref=actor,
            actor_role=acting_role(control_db, decision.tenant_id, actor, _permission("INVESTIGATION")),
            case_reference=case_business_id(session, decision.tenant_id, decision.investigation_id),
        )

    service.run_hook(db, "decision created", step)


def on_decision_reviewed(db: Session, control_db, decision, *, actor_user_id, disposition: str | None = None) -> None:
    """A review that sends the decision back (REJECTED, REQUIRES_ADDITIONAL_EVIDENCE: the decision then needs more
    evidence) completes the approval task (RETURNED) and gives the author a FOLLOW_UP task. An approving review
    leaves the approval task open: the signature is still pending."""

    def step(session):
        if str(decision.decision_status or "").upper() != "REQUIRES_ADDITIONAL_EVIDENCE":
            return
        actor = str(actor_user_id)
        role = acting_role(control_db, decision.tenant_id, actor, _permission("DECISION_APPROVAL"))
        service.complete_tasks(
            session,
            decision.tenant_id,
            source_type=DECISION,
            source_id=decision.id,
            task_types=["DECISION_APPROVAL"],
            outcome="RETURNED",
            actor_ref=actor,
            actor_role=role,
        )
        author = find_user(control_db, decision.tenant_id, decision.authorized_by_ref) if control_db else None
        service.create_task(
            session,
            decision.tenant_id,
            task_type="FOLLOW_UP",
            title=f"{decision.business_id} returned: needs additional evidence",
            source_type=DECISION,
            source_id=decision.id,
            investigation_id=decision.investigation_id,
            assigned_user_id=author.id if author is not None else None,
            created_by=actor,
            is_return=True,
            actor_role=role,
            details={"review_disposition": str(disposition or "").upper() or None},
        )

    service.run_hook(db, "decision reviewed", step)


def on_decision_signed(db: Session, decision, *, decision_value: str, actor_user_id, actor_role=None) -> None:
    def step(session):
        outcome = "SIGNED_APPROVE" if str(decision_value or "").upper() == "APPROVE" else "SIGNED_REJECT"
        service.complete_tasks(
            session,
            decision.tenant_id,
            source_type=DECISION,
            source_id=decision.id,
            task_types=["DECISION_APPROVAL"],
            outcome=outcome,
            actor_ref=str(actor_user_id),
            actor_role=actor_role,
        )

    service.run_hook(db, "decision signed", step)


def on_decision_material_change(db: Session, decision, *, actor_user_id, actor_role=None) -> None:
    """The changed decision needs a new approval: open approval tasks are superseded and a new one is queued. A
    returned decision's FOLLOW_UP task is completed (RESUBMITTED): the author has acted on it."""

    def step(session):
        actor = str(actor_user_id)
        service.supersede_tasks(
            session,
            decision.tenant_id,
            source_type=DECISION,
            source_id=decision.id,
            task_types=["DECISION_APPROVAL"],
            outcome="MATERIAL_CHANGE",
            actor_ref=actor,
            actor_role=actor_role,
        )
        service.complete_tasks(
            session,
            decision.tenant_id,
            source_type=DECISION,
            source_id=decision.id,
            task_types=["FOLLOW_UP"],
            outcome="RESUBMITTED",
            actor_ref=actor,
            actor_role=actor_role,
        )
        _approval_task(
            session,
            decision,
            actor_ref=actor,
            actor_role=actor_role,
            case_reference=case_business_id(session, decision.tenant_id, decision.investigation_id),
        )

    service.run_hook(db, "decision material change", step)


# ---------------------------------------------------------------------------------------------- risks, suppliers


def on_risk_review_requested(db: Session, control_db, risk, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        service.create_task(
            session,
            risk.tenant_id,
            task_type="RISK_REVIEW",
            title=f"Review risk {risk.business_id}: {service.shorten(risk.description, 160)}",
            source_type=RISK,
            source_id=risk.id,
            created_by=actor,
            actor_role=acting_role(control_db, risk.tenant_id, actor, _permission("INVESTIGATION")),
        )

    service.run_hook(db, "risk review requested", step)


def _requester(control_db, row):
    if control_db is None:
        return None
    user = find_user(control_db, row.tenant_id, row.requested_by)
    return user.id if user is not None else None


def on_supplier_request_created(db: Session, control_db, row, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        requester = _requester(control_db, row)
        service.create_task(
            session,
            row.tenant_id,
            task_type="EVIDENCE_REQUEST",
            title=f"Waiting for supplier reply {row.business_id}: {service.shorten(row.title, 160)}",
            source_type=SUPPLIER_REQUEST,
            source_id=row.id,
            investigation_id=row.investigation_id,
            assigned_user_id=requester,
            status="WAITING" if requester is not None else None,
            created_by=actor,
            actor_role=acting_role(control_db, row.tenant_id, actor, _permission("EVIDENCE_REQUEST")),
        )

    service.run_hook(db, "supplier evidence request created", step)


def on_supplier_reply_recorded(db: Session, control_db, row, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        role = acting_role(control_db, row.tenant_id, actor, _permission("EVIDENCE_REQUEST"))
        service.complete_tasks(
            session,
            row.tenant_id,
            source_type=SUPPLIER_REQUEST,
            source_id=row.id,
            task_types=["EVIDENCE_REQUEST"],
            outcome="REPLY_RECEIVED",
            actor_ref=actor,
            actor_role=role,
        )
        service.create_task(
            session,
            row.tenant_id,
            task_type="EVIDENCE_REVIEW",
            title=f"Review supplier reply {row.business_id}",
            source_type=SUPPLIER_REQUEST,
            source_id=row.id,
            investigation_id=row.investigation_id,
            assigned_user_id=_requester(control_db, row),
            created_by=actor,
            actor_role=role,
        )

    service.run_hook(db, "supplier reply recorded", step)
