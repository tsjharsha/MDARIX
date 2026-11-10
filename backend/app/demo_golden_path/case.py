"""The case, its scope and the complaints added and excluded later. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
import uuid
from datetime import timedelta

from backend.app.demo_golden_path.context import Story, scope_split


# --------------------------------------------------------------------------------------- the case and its scope

EXCLUSION_REASON = (
    "The extension-set clamp was found closed at handover: a use issue, not the cassette valve; kept on record but "
    "outside this investigation."
)
SCOPE_CHANGE_REASON = (
    "Complaints added by the threshold rule since the investigation was opened; the closed-clamp report is excluded."
)
SCOPE_OBJECTIVES = (
    "Establish whether cassettes from moulding tool T-4 cause flow interruption on FlowSure 300 Rev 2, and decide "
    "on containment and correction."
)


def open_case(s: Story, signal):
    """Day 61: Tara opens the case from the signal for Ines (complaint links, scope version 1, INVESTIGATION_OPENED,
    the signal INVESTIGATION_OPEN and linked to the case, Ines's INVESTIGATION task); Ines accepts it and the case
    is in progress. As ``POST /api/v1/signals/{id}/create-investigation`` and accepting the task do."""
    from backend.app.access.permissions import INVESTIGATION_CREATE, INVESTIGATION_WORK
    from backend.app.case_workflow import scope, states
    from backend.app.db.models.foundation import AuditEvent, InvestigationComplaint
    from backend.app.db.models.signals import InvestigationSignal
    from backend.app.signals import logic
    from backend.app.signals import service as signals
    from backend.app.workflow import tasks as task_service
    from backend.app.workflow.hooks import _investigation_task

    tara = s.person("TRIAGE_LEAD")
    ines = s.user("INVESTIGATOR")
    role = tara.role_for(INVESTIGATION_CREATE)
    opened = s.at(61)
    case = s.case
    complaint_ids = signals.linked_complaint_ids(s.db, signal)
    case.priority = states.normalize_priority(
        logic.effective_priority(signal.confirmed_priority, signal.suggested_priority)
    )
    case.owner_ref = ines.username
    case.opened_at = opened
    case.due_at = states.due_at_for(case.priority, opened)
    states.set_state(case, "OPEN", opened)
    scope.sync_complaint_links(s.db, case, complaint_ids, opened)
    for link in s.db.query(InvestigationComplaint).filter(
        InvestigationComplaint.tenant_id == s.tenant_id, InvestigationComplaint.investigation_id == case.id
    ):
        link.created_at = opened
    scope.first_version(s.db, case, complaint_ids=complaint_ids, actor_ref=tara.user_id, actor_role=role, now=opened)
    s.db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            actor_ref=tara.user_id,
            action="INVESTIGATION_OPENED",
            entity_type="Investigation",
            entity_id=case.id,
            details={
                "identifier": case.investigation_identifier,
                "product": s.product.product_identifier,
                "complaints": len(complaint_ids),
                "workflow_state": case.workflow_state,
                "priority": case.priority,
            },
            created_at=opened,
        )
    )
    s.db.add(
        InvestigationSignal(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            investigation_id=case.id,
            signal_id=signal.id,
            created_by=tara.user_id,
            created_at=opened,
        )
    )
    s.db.flush()
    signals.set_status(
        s.db,
        signal,
        "INVESTIGATION_OPEN",
        "INVESTIGATION_CREATED",
        actor_ref=tara.user_id,
        actor_role=role,
        details={"investigation_business_id": case.business_id, "primary": True},
        now=opened,
    )
    signals.finish_triage_tasks(s.db, signal, outcome="INVESTIGATION_OPENED", actor_ref=tara.user_id, actor_role=role)
    task = _investigation_task(s.db, s.db, case, owner_user_id=ines.id, actor_user_id=tara.user_id)
    s.settle(opened)

    accepted = s.at(61, 90)
    investigator = s.person("INVESTIGATOR")
    previous = task.status
    task.status = "ACCEPTED"
    task.accepted_at = accepted
    task.updated_at = accepted
    task_service.record_event(
        s.db,
        task,
        "ACCEPTED",
        actor_ref=investigator.user_id,
        actor_role=investigator.role_for(INVESTIGATION_WORK),
        from_status=previous,
        to_status="ACCEPTED",
        now=accepted,
    )
    before = {"workflow_state": case.workflow_state, "status": case.status}
    states.set_state(case, "IN_PROGRESS", accepted)
    states.audit_state_change(
        s.db,
        case,
        actor_ref=investigator.user_id,
        before=before,
        reason=f"Investigation task {task.business_id or task.id} accepted",
        details={"task_id": str(task.id)},
        now=accepted,
    )
    s.settle(accepted)
    s.made["investigation_task"] = task


def add_later_complaints(s: Story, signal) -> None:
    """The next complaints (before the late one) reach the open signal through the threshold rule, the day after
    each happened."""
    from backend.app.signals import service as signals
    from backend.app.signals.labels import DETECTION_ACTOR, THRESHOLD_RULE

    for complaint in s.complaints[3:7]:
        moment = complaint.event_timestamp + timedelta(days=1)
        added = signals.link_complaints(s.db, signal, [complaint.id], how="RULE", actor_ref=DETECTION_ACTOR)
        if not added:
            continue
        signals.recompute(s.db, signal, now=moment)
        signals.record(
            s.db,
            signal,
            "COMPLAINTS_ADDED",
            actor_ref=DETECTION_ACTOR,
            details={"how": "RULE", "complaints": len(added), "rule_code": THRESHOLD_RULE},
            now=moment,
        )
        signals.update_open_task_schedule(s.db, signal)
        s.settle(moment)


def rescope_case(s: Story):
    """Day 34: Ines records scope version 2 (the rule's later complaints included, the closed-clamp report excluded
    with its reason), as ``PUT /api/v1/investigations/{id}/scope`` does."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_workflow import scope
    from backend.app.enterprise_audit import make_audit_event

    ines = s.person("INVESTIGATOR")
    role = ines.role_for(INVESTIGATION_WORK)
    moment = s.at(34)
    case = s.case
    ids = [str(row.id) for row in s.complaints]
    included, excluded = scope_split(ids, excluded_index=5, late_index=7)
    previous = scope.current_scope(s.db, case)
    data = {
        **previous,
        "question": case.investigation_question,
        "product_version_ids": [str(s.version.id)],
        "included_complaint_ids": included,
        "excluded_complaints": [{"complaint_id": excluded[0], "reason": EXCLUSION_REASON}],
        "lot_ids": scope.id_list(row.lot_batch_id for row in s.complaints[:7]),
        "date_from": s.complaints[0].event_timestamp.date(),
        "date_to": moment.date(),
        "objectives": SCOPE_OBJECTIVES,
        "change_reason": SCOPE_CHANGE_REASON,
        "reviews_must_restart": False,
        "conclusions_invalidated": False,
    }
    diff = scope.scope_diff(previous, data)
    row = scope.write_version(s.db, case, data, actor_ref=ines.user_id, actor_role=role, now=moment)
    linked, unlinked = scope.sync_complaint_links(s.db, case, row.included_complaint_ids, moment)
    case.updated_at = moment
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=ines.user_id,
            action="INVESTIGATION_SCOPE_CHANGED",
            entity_type="Investigation",
            entity_id=case.id,
            reason=row.change_reason,
            details={
                "version": row.version,
                **scope.diff_counts(diff),
                "complaint_links_added": len(linked),
                "complaint_links_removed": len(unlinked),
                "reviews_must_restart": False,
                "conclusions_invalidated": False,
                "warnings": 0,
                "actor_role": role,
            },
            created_at=moment,
        )
    )
    s.db.flush()
    s.made["scope_version"] = row.version
    return row
