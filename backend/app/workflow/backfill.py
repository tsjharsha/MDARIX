"""Tasks for work that existed before workflow tasks did, for one organization (scripts/backfill_workflow_tasks.py;
the demo workspace calls it after seeding its story).

- an open investigation with an owner: an INVESTIGATION task ACCEPTED by that person (their sign-in name is resolved
  in the control database; an owner who is unknown or no longer active leaves the task in the investigators' queue);
- an open investigation without an owner: an INVESTIGATION task in the investigators' queue;
- a decision awaiting review (REQUIRES_REVIEW): a DECISION_APPROVAL task in the approvers' queue;
- a supplier evidence request still waiting for its reply: an EVIDENCE_REQUEST task WAITING for the person who sent it.

Idempotent: a source that already has an open task of that type is skipped. Does not commit.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.workflow import tasks as service
from backend.app.workflow.hooks import DECISION, INVESTIGATION, SUPPLIER_REQUEST
from backend.app.workflow.labels import TASK_TYPES
from backend.app.workflow.people import find_user

BACKFILL_ACTOR = "system:workflow-backfill"
# Supplier evidence requests in these states need nothing more from the supplier.
ANSWERED_REQUEST_STATUSES = ("REPLIED", "CLOSED", "CANCELLED", "WITHDRAWN")


def backfill_tenant(data_db: Session, control_db: Session, tenant_id, *, apply: bool = False) -> dict:
    """Create (``apply``) or count (dry run) the missing tasks of one organization. ``data_db`` holds its business
    records and tasks, ``control_db`` its accounts (the same session on the shared plane). Returns the counts per
    task type and how many sources already had an open task. Does not commit."""
    from backend.app.db.models.foundation import Decision, Investigation
    from backend.app.db.models.stage3 import SupplierEvidenceRequest

    tenant = as_uuid(tenant_id)
    if tenant is None:
        raise ValueError("backfill_tenant needs the organization's id")
    result = {"INVESTIGATION": 0, "DECISION_APPROVAL": 0, "EVIDENCE_REQUEST": 0, "skipped": 0, "applied": apply}
    owners: dict[str, object] = {}

    def owner_id(ref):
        key = str(ref or "").strip().lower()
        if not key:
            return None
        if key not in owners:
            user = find_user(control_db, tenant, ref)
            owners[key] = user.id if user is not None else None
        return owners[key]

    def missing(task_type: str, source_type: str, source_id) -> bool:
        if service.has_open_task(data_db, tenant, task_type=task_type, source_type=source_type, source_id=source_id):
            result["skipped"] += 1
            return False
        return True

    cases = (
        data_db.query(Investigation)
        .filter(Investigation.tenant_id == tenant, func.lower(func.coalesce(Investigation.status, "")) != "closed")
        .order_by(Investigation.opened_at, Investigation.id)
        .all()
    )
    for case in cases:
        if not missing("INVESTIGATION", INVESTIGATION, case.id):
            continue
        result["INVESTIGATION"] += 1
        if apply:
            owner = owner_id(case.owner_ref)
            service.create_task(
                data_db,
                tenant,
                task_type="INVESTIGATION",
                title=f"Investigate {case.business_id}: {service.shorten(case.investigation_question, 200)}",
                source_type=INVESTIGATION,
                source_id=case.id,
                investigation_id=case.id,
                assigned_user_id=owner,
                assigned_role=TASK_TYPES["INVESTIGATION"].queue_role,
                status="ACCEPTED" if owner is not None else None,
                created_by=BACKFILL_ACTOR,
                details={"backfilled": True},
            )

    case_ids = {}
    decisions = (
        data_db.query(Decision)
        .filter(Decision.tenant_id == tenant, Decision.decision_status == "REQUIRES_REVIEW")
        .order_by(Decision.created_at, Decision.id)
        .all()
    )
    if decisions:
        wanted = list({row.investigation_id for row in decisions if row.investigation_id})
        if wanted:
            case_ids = {
                str(row_id): business_id
                for row_id, business_id in data_db.query(Investigation.id, Investigation.business_id).filter(
                    Investigation.tenant_id == tenant, Investigation.id.in_(wanted)
                )
            }
    for decision in decisions:
        if not missing("DECISION_APPROVAL", DECISION, decision.id):
            continue
        result["DECISION_APPROVAL"] += 1
        if apply:
            reference = case_ids.get(str(decision.investigation_id))
            service.create_task(
                data_db,
                tenant,
                task_type="DECISION_APPROVAL",
                title=f"Approve or reject {decision.business_id}" + (f" on {reference}" if reference else ""),
                source_type=DECISION,
                source_id=decision.id,
                investigation_id=decision.investigation_id,
                created_by=BACKFILL_ACTOR,
                details={"backfilled": True, "decision_author_ref": str(decision.authorized_by_ref or "") or None},
            )

    requests = (
        data_db.query(SupplierEvidenceRequest)
        .filter(
            SupplierEvidenceRequest.tenant_id == tenant,
            SupplierEvidenceRequest.status.notin_(ANSWERED_REQUEST_STATUSES),
        )
        .order_by(SupplierEvidenceRequest.created_at, SupplierEvidenceRequest.id)
        .all()
    )
    for row in requests:
        if not missing("EVIDENCE_REQUEST", SUPPLIER_REQUEST, row.id):
            continue
        result["EVIDENCE_REQUEST"] += 1
        if apply:
            requester = owner_id(row.requested_by)
            service.create_task(
                data_db,
                tenant,
                task_type="EVIDENCE_REQUEST",
                title=f"Waiting for supplier reply {row.business_id}: {service.shorten(row.title, 160)}",
                source_type=SUPPLIER_REQUEST,
                source_id=row.id,
                investigation_id=row.investigation_id,
                assigned_user_id=requester,
                status="WAITING" if requester is not None else None,
                created_by=BACKFILL_ACTOR,
                details={"backfilled": True},
            )
    return result
