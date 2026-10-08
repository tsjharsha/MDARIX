"""The signal and its triage. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
from backend.app import demo_story as story

from backend.app.demo_golden_path.context import Story


# ------------------------------------------------------------------------------------- signal and its triage

TRIAGE_PRIORITY_REASON = (
    "Each interruption stops the therapy; the complaints cluster on the new cassette lots and keep coming."
)
DISPOSITION_REASON = (
    "Three flow interruptions in two weeks on Rev 2 only, all with cassettes from the new moulding tool: "
    "the cause needs an investigation."
)


def seed_signal(s: Story):
    """Day 63: the threshold rule raises the signal from the first three complaints (with its triage task in the
    triage leads' queue), as detection does."""
    from backend.app.signals import logic
    from backend.app.signals import service as signals
    from backend.app.signals.labels import DETECTION_ACTOR, THRESHOLD_RULE

    settings = signals.rule_settings(s.db, s.tenant_id)
    first = s.complaints[:3]
    signal = signals.create_signal(
        s.db,
        s.tenant_id,
        title=logic.rule_title(
            len(first), story.GOLDEN_PROBLEM, s.product.name, s.version.version_identifier, settings["window_days"]
        ),
        origin="THRESHOLD_RULE",
        product_id=s.product.id,
        product_version_id=s.version.id,
        problem_key=logic.problem_key(story.GOLDEN_PROBLEM, None),
        complaint_ids=[row.id for row in first],
        added_how="RULE",
        actor_ref=DETECTION_ACTOR,
        rule={
            "code": THRESHOLD_RULE,
            "version": settings["version"],
            "parameters": {"min_complaints": settings["min_complaints"], "window_days": settings["window_days"]},
        },
        min_complaints=settings["min_complaints"],
    )
    moment = s.at(63)
    s.settle(moment)
    signal.due_at = logic.due_at(logic.effective_priority(signal.confirmed_priority, signal.suggested_priority), moment)
    signals.update_open_task_schedule(s.db, signal)
    s.settle(moment)
    s.made["signal"] = signal
    return signal


def triage_signal(s: Story, signal) -> None:
    """Day 62: Tara takes the signal into triage, confirms priority HIGH and dispositions it INVESTIGATION_REQUIRED
    (the triage task completes with that outcome), as the triage endpoints do."""
    from backend.app.access.permissions import SIGNAL_TRIAGE
    from backend.app.signals import logic
    from backend.app.signals import service as signals

    tara = s.person("TRIAGE_LEAD")
    role = tara.role_for(SIGNAL_TRIAGE)
    started = s.at(62)
    signal.owner_user_id = tara.user_uuid
    signals.set_status(s.db, signal, "TRIAGE", "TRIAGE_STARTED", actor_ref=tara.user_id, actor_role=role, now=started)
    signals.take_triage_task(s.db, signal, user_id=tara.user_uuid, actor_role=role)
    s.settle(started)

    prioritised = s.at(62, 20)
    previous = logic.effective_priority(signal.confirmed_priority, signal.suggested_priority)
    reason = TRIAGE_PRIORITY_REASON if logic.needs_priority_reason("HIGH", signal.suggested_priority) else None
    signal.confirmed_priority = "HIGH"
    signal.priority_reason = reason
    signal.due_at = logic.due_at("HIGH", signal.created_at or prioritised)
    signal.updated_at = prioritised
    signals.update_open_task_schedule(s.db, signal)
    signals.record(
        s.db,
        signal,
        "PRIORITY_SET",
        actor_ref=tara.user_id,
        actor_role=role,
        reason=reason,
        details={"from": previous, "to": "HIGH", "suggested": signal.suggested_priority},
        now=prioritised,
    )
    s.settle(prioritised)

    decided = s.at(62, 45)
    logic.check_disposition("INVESTIGATION_REQUIRED", signal.status, signal_id=signal.id, today=decided.date())
    signal.disposition_reason = DISPOSITION_REASON
    signal.dispositioned_by = tara.user_id
    signal.dispositioned_at = decided
    signals.set_status(
        s.db,
        signal,
        "INVESTIGATION_REQUIRED",
        "DISPOSITIONED",
        actor_ref=tara.user_id,
        actor_role=role,
        reason=DISPOSITION_REASON,
        details={"disposition": "INVESTIGATION_REQUIRED"},
        now=decided,
    )
    signals.finish_triage_tasks(s.db, signal, outcome="INVESTIGATION_REQUIRED", actor_ref=tara.user_id, actor_role=role)
    s.settle(decided)
