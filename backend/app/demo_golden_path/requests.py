"""The evidence request sent after the first brief was returned, and its answer. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
import uuid
from datetime import timedelta
from backend.app import demo_story as story

from backend.app.demo_golden_path.context import Story
from backend.app.demo_golden_path.evidence import _ctx


# ------------------------------------------------------------------------------------------- evidence request

REQUEST_TITLE = "Incoming inspection records of cassette lots C-301 to C-303"
REQUEST_ITEMS = ["Membrane thickness measurements at the gate", "Inspection plan revision in force"]
REQUEST_RATIONALE = "Brief version 1 was returned for evidence: the membrane dimension of the suspect lots is open."
RESPONSE_NOTE = (
    "Attached summary of incoming inspection for lots C-301 to C-303: membrane thickness was measured but not "
    "checked against the drawing tolerance (inspection plan error IP-77)."
)


def answer_evidence_request(s: Story, unknown):
    """Days 22-19: Ines asks Ravi for the incoming inspection records (resolving an unknown), Ravi acknowledges and
    answers, and Ines accepts the answer as evidence of the case (ACD-EV-4016), as the evidence request endpoints
    and their task hooks write it. The evidence keeps its story identifier."""
    from backend.app.access.permissions import EVIDENCE_REQUEST, EVIDENCE_REVIEW
    from backend.app.db.models.foundation import InvestigationEvidence
    from backend.app.db.models.stage3 import SupplierEvidenceRequest
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow import hooks as request_hooks
    from backend.app.evidence_workflow import requests as request_api
    from backend.app.evidence_workflow.inventory import review_event
    from backend.app.evidence_workflow.rules import EVIDENCE_SOURCE_SYSTEM, KIND_INTERNAL, UNREVIEWED, task_source_type
    from backend.app.workflow import tasks as task_service

    ines = s.person("INVESTIGATOR")
    ravi = s.person("REVIEWER")
    asked = s.at(22)
    row = SupplierEvidenceRequest(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        supplier_id=None,
        requested_by=ines.user_id,
        recipient=None,
        title=REQUEST_TITLE,
        requested_items={"items": list(REQUEST_ITEMS), "rationale": REQUEST_RATIONALE},
        status="OPEN",
        request_kind=KIND_INTERNAL,
        recipient_user_id=ravi.user_uuid,
        recipient_role=None,
        unknown_id=unknown.id,
        priority="HIGH",
        due_at=asked + timedelta(days=5),
        created_at=asked,
        updated_at=asked,
    )
    s.db.add(row)
    s.db.flush()
    request_api._audit(
        s.db,
        _ctx(ines),
        ines,
        row,
        "EVIDENCE_REQUESTED",
        asked,
        details={
            "recipient_user_id": ravi.user_id,
            "recipient_role": None,
            "unknown_id": str(unknown.id),
            "priority": row.priority,
            "due_at": request_api._iso(row.due_at),
            "item_count": len(REQUEST_ITEMS),
            "actor_role": ines.role_for(EVIDENCE_REQUEST),
        },
    )
    requester_role = ines.role_for(EVIDENCE_REQUEST)
    response_task = task_service.create_task(
        s.db,
        s.tenant_id,
        task_type=request_hooks.RESPONSE_TASK,
        title=f"Provide evidence {row.business_id}: {task_service.shorten(row.title, 160)}",
        source_type=task_source_type(row.request_kind),
        source_id=row.id,
        investigation_id=row.investigation_id,
        assigned_user_id=row.recipient_user_id,
        priority=row.priority,
        due_at=row.due_at,
        created_by=ines.user_id,
        actor_role=requester_role,
        details={"request_kind": KIND_INTERNAL},
    )
    request_hooks._waiting_task(s.db, s.db, row, actor=ines.user_id, role=requester_role)
    s.settle(asked)

    moment = s.at(21)
    recipient_role = ravi.role_for(EVIDENCE_REQUEST)
    row.status = "ACKNOWLEDGED"
    row.acknowledged_at = moment
    row.updated_at = moment
    request_api._audit(
        s.db, _ctx(ravi), ravi, row, "EVIDENCE_REQUEST_ACKNOWLEDGED", moment, details={"previous_status": "OPEN"}
    )
    previous = response_task.status
    response_task.status = "ACCEPTED"
    response_task.accepted_at = moment
    response_task.updated_at = moment
    task_service.record_event(
        s.db,
        response_task,
        "ACCEPTED",
        actor_ref=ravi.user_id,
        actor_role=recipient_role,
        from_status=previous,
        to_status="ACCEPTED",
        details={"evidence_request_acknowledged": True},
        now=moment,
    )
    s.settle(moment)

    moment = s.at(20)
    row.status = "RECEIVED"
    row.response_note = RESPONSE_NOTE
    row.responded_at = moment
    row.updated_at = moment
    request_api._audit(
        s.db,
        _ctx(ravi),
        ravi,
        row,
        "EVIDENCE_REQUEST_RESPONDED",
        moment,
        details={"previous_status": "ACKNOWLEDGED", "note_length": len(RESPONSE_NOTE)},
    )
    request_hooks._finish_answer_tasks(s.db, s.db, row, actor=ravi.user_id, outcome="REPLY_RECEIVED")
    task_service.create_task(
        s.db,
        s.tenant_id,
        task_type=request_hooks.REVIEW_TASK,
        title=f"Review evidence response {row.business_id}",
        source_type=task_source_type(row.request_kind),
        source_id=row.id,
        investigation_id=row.investigation_id,
        assigned_user_id=ines.user_uuid,
        priority=row.priority,
        created_by=ravi.user_id,
        actor_role=recipient_role,
    )
    s.settle(moment)

    moment = s.at(19)
    reviewer_role = ines.role_for(EVIDENCE_REVIEW)
    ev = s.evidence["ACD-EV-4016"]
    ev.investigation_id = s.case.id
    ev.source_system = EVIDENCE_SOURCE_SYSTEM
    ev.source_identifier = row.business_id
    ev.source_reference = f"Evidence request {row.business_id} ({story.SYNTHETIC})"
    ev.source_timestamp = ev.effective_timestamp = row.responded_at
    link = InvestigationEvidence(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        evidence_id=ev.id,
        created_at=moment,
        review_status="ACCEPTED",
        relationship="SUPPORTING",
        reviewed_by=ines.user_id,
        reviewed_at=moment,
        linked_by=ines.user_id,
    )
    s.db.add(link)
    s.db.flush()
    source = {"request_id": str(row.id), "request_business_id": row.business_id}
    review_event(
        s.db,
        tenant_id=s.tenant_id,
        case_id=s.case.id,
        evidence_id=ev.id,
        event_type="LINKED",
        actor=ines,
        permission=EVIDENCE_REVIEW,
        to_status=UNREVIEWED,
        to_relationship=UNREVIEWED,
        details=source,
        now=moment,
    )
    review_event(
        s.db,
        tenant_id=s.tenant_id,
        case_id=s.case.id,
        evidence_id=ev.id,
        event_type="REVIEWED",
        actor=ines,
        permission=EVIDENCE_REVIEW,
        from_status=UNREVIEWED,
        to_status="ACCEPTED",
        from_relationship=UNREVIEWED,
        to_relationship="SUPPORTING",
        details=source,
        now=moment,
    )
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=ines.user_id,
            action="EVIDENCE_REVIEWED",
            entity_type="InvestigationEvidence",
            entity_id=link.id,
            new_values={"review_status": "ACCEPTED", "relationship": "SUPPORTING"},
            details={
                "investigation_id": str(s.case.id),
                "evidence_id": str(ev.id),
                "actor_role": reviewer_role,
                **source,
            },
            created_at=moment,
        )
    )
    row.resolved_evidence_id = ev.id
    document = request_api._document(row)
    document["review"] = {
        "accepted": True,
        "reason": None,
        "reviewed_by": ines.user_id,
        "reviewed_at": request_api._iso(moment),
    }
    row.requested_items = document
    row.status = "REVIEWED"
    row.reviewed_by = ines.user_id
    row.reviewed_at = moment
    row.updated_at = moment
    request_api._audit(
        s.db,
        _ctx(ines),
        ines,
        row,
        "EVIDENCE_REQUEST_REVIEWED",
        moment,
        details={
            "previous_status": "RECEIVED",
            "accepted": True,
            "evidence_id": str(ev.id),
            "review_status": "ACCEPTED",
            "relationship": "SUPPORTING",
            "actor_role": reviewer_role,
        },
    )
    request_hooks._complete_reviews(s.db, s.db, row, actor=ines.user_id, outcome="EVIDENCE_ACCEPTED")
    s.settle(moment)
    s.made["evidence_request"] = row
    return row
