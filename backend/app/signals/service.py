"""Reading and changing signals in the tenant's data plane (where complaints, cases and tasks live).

Every change goes through ``record``: a history row (signal_events, never updated) and an audit event
(``SIGNAL_<EVENT>``) in the same session. Each signal has one open SIGNAL_TRIAGE task while it waits for triage
(backend/app/workflow/tasks.py). Nothing here commits; the router, the detection run and the hooks do.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.db.models.foundation import Complaint, Investigation, Product, ProductVersion
from backend.app.db.models.signals import InvestigationSignal, Signal, SignalComplaint, SignalEvent, SignalRule
from backend.app.enterprise_audit import make_audit_event
from backend.app.role_codes import role_code
from backend.app.signals import logic
from backend.app.signals.labels import (
    AWAITING_TRIAGE,
    DETECTION_ACTOR,
    ORIGIN_LABELS,
    SIGNAL_SOURCE,
    STATUS_LABELS,
    THRESHOLD_DEFAULTS,
    THRESHOLD_RULE,
    TRIAGE_TASK,
)
from backend.app.workflow import tasks as task_service

SEVERITY_LENGTH = 40
RECENT_DAYS = 7
# Complaint ids per IN (...) list when linking, well within PostgreSQL's limit of bind parameters.
LINK_BATCH = 1000
# At most this many complaint sources are listed for the inbox's Data filter.
SOURCES_MAX = 50
# Audit actions of the history events whose action is not simply SIGNAL_<EVENT>.
AUDIT_ACTIONS = {
    "MERGED_INTO": "SIGNAL_MERGED",
    "MERGED_FROM": "SIGNAL_MERGED",
    "INVESTIGATION_CREATED": "SIGNAL_INVESTIGATION_CREATED",
}
# When a complaint happened (its event time, else when it was received, else when it was recorded).
COMPLAINT_EVENT_AT = func.coalesce(Complaint.event_timestamp, Complaint.complaint_timestamp, Complaint.created_at)
# A link's complaint, joined on the complaint's id alone (0.10.42). The link's foreign key (tenant_id, complaint_id)
# holds the complaint to the link's organization, every query here filters the links by organization, and row-level
# security applies as ever. A condition on the complaint's organization as well let PostgreSQL, while its statistics
# do not know a new organization's rows yet (until autovacuum analyzes the tables, a minute or so after a large
# import), scan all the organization's complaints for every link: seconds to minutes for one import's signal, where
# the primary key finds each complaint at once.
LINKED_COMPLAINT = Complaint.id == SignalComplaint.complaint_id


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def not_found() -> logic.SignalRuleError:
    return logic.SignalRuleError(404, "SIGNAL_NOT_FOUND", "Signal not found")


# --------------------------------------------------------------------------------------------------- history


def record(
    db: Session,
    signal: Signal,
    event_type: str,
    *,
    actor_ref,
    actor_role: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    details: dict | None = None,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> SignalEvent:
    """The signal's history row and its audit event (``SIGNAL_<EVENT>``, merges ``SIGNAL_MERGED``). Does not
    commit."""
    now = now or now_utc()
    actor = str(actor_ref) if actor_ref else DETECTION_ACTOR
    role = (role_code(actor_role) or None) if actor_role else None
    event = SignalEvent(
        id=uuid.uuid4(),
        tenant_id=signal.tenant_id,
        signal_id=signal.id,
        event_type=event_type,
        actor_ref=actor,
        actor_role=role,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        details=dict(details or {}),
        created_at=now,
    )
    db.add(event)
    db.add(
        make_audit_event(
            tenant_id=signal.tenant_id,
            actor_ref=actor,
            action=AUDIT_ACTIONS.get(event_type, f"SIGNAL_{event_type}"),
            entity_type="Signal",
            entity_id=signal.id,
            correlation_id=correlation_id,
            reason=reason,
            details={
                "signal_business_id": signal.business_id,
                "event": event_type,
                "from_status": from_status,
                "to_status": to_status,
                "actor_role": role,
                **dict(details or {}),
            },
            created_at=now,
        )
    )
    return event


def set_status(db: Session, signal: Signal, to_status: str, event_type: str, **kwargs) -> SignalEvent:
    """Move the signal to ``to_status`` and record why (``record``'s arguments). Does not commit."""
    now = kwargs.pop("now", None) or now_utc()
    previous = signal.status
    signal.status = to_status
    signal.updated_at = now
    return record(db, signal, event_type, from_status=previous, to_status=to_status, now=now, **kwargs)


# ---------------------------------------------------------------------------------------------------- reading


def load(db: Session, tenant_id, signal_id, *, lock: bool = False) -> Signal:
    """The organization's signal; SIGNAL_NOT_FOUND for an unknown id or another organization's."""
    key = as_uuid(signal_id)
    if key is None:
        raise not_found()
    query = db.query(Signal).filter(Signal.tenant_id == as_uuid(tenant_id), Signal.id == key)
    if lock:
        query = query.with_for_update()
    signal = query.first()
    if signal is None:
        raise not_found()
    return signal


def load_many(db: Session, tenant_id, signal_ids, *, lock: bool = False) -> list[Signal]:
    """Several of the organization's signals, locked in id order (no deadlock between two requests); any unknown id
    is SIGNAL_NOT_FOUND."""
    given = list(signal_ids)
    ids = sorted(wanted_ids(given), key=str)
    if len(ids) != len(set(str(item) for item in given)):
        raise not_found()
    if not ids:
        return []
    query = db.query(Signal).filter(Signal.tenant_id == as_uuid(tenant_id), Signal.id.in_(ids)).order_by(Signal.id)
    if lock:
        query = query.with_for_update()
    rows = query.all()
    if len(rows) != len(ids):
        raise not_found()
    return rows


def _facts(row) -> logic.ComplaintFacts:
    return logic.ComplaintFacts(
        id=row.id,
        product_id=row.product_id,
        product_version_id=row.product_version_id,
        problem_key=logic.problem_key(row.problem_code, row.complaint_type),
        event_at=row.event_at,
        severity=row.severity,
        serious_injury=bool(row.serious_injury),
        death=bool(row.death),
    )


def complaint_facts_query(db: Session, tenant_id, *, linked: bool = False):
    """The facts of the organization's complaints; with ``linked``, of the complaints the signal links filtered by the
    caller (the organization is then the links', LINKED_COMPLAINT)."""
    query = db.query(
        Complaint.id,
        Complaint.product_id,
        Complaint.product_version_id,
        Complaint.problem_code,
        Complaint.complaint_type,
        COMPLAINT_EVENT_AT.label("event_at"),
        Complaint.severity,
        Complaint.serious_injury,
        Complaint.death,
    )
    if linked:
        return query.select_from(SignalComplaint).join(Complaint, LINKED_COMPLAINT)
    return query.filter(Complaint.tenant_id == as_uuid(tenant_id))


def complaint_facts(query) -> list[logic.ComplaintFacts]:
    return [_facts(row) for row in query.all()]


def linked_events(db: Session, tenant_id) -> dict[uuid.UUID, uuid.UUID]:
    """S2: complaints a person linked as one event (``record_links`` LINKED, complaint to complaint; linked through
    each other, so connected components), each mapped to the complaint that stands for the event: the one with the
    earliest event date (then the lowest id). The count rule and the trend check count an event once, at that date;
    every record stays listed as evidence. Complaints in no such link are not in the map."""
    from backend.app.db.models.intake import RecordLink
    from backend.app.intake.service import groups

    links = (
        db.query(RecordLink)
        .filter(
            RecordLink.tenant_id == as_uuid(tenant_id),
            RecordLink.state == "LINKED",
            RecordLink.left_kind == "COMPLAINT",
            RecordLink.right_kind == "COMPLAINT",
        )
        .all()
    )
    if not links:
        return {}
    group = {rid: key for (_kind, rid), key in groups(links).items()}
    when = dict(
        db.query(Complaint.id, COMPLAINT_EVENT_AT)
        .filter(Complaint.tenant_id == as_uuid(tenant_id), Complaint.id.in_(list(group)))
        .all()
    )
    first: dict = {}
    for rid, key in group.items():
        if rid not in when:
            continue
        moment = when[rid]
        rank = (moment is None, moment or datetime.max.replace(tzinfo=timezone.utc), str(rid))
        if key not in first or rank < first[key][0]:
            first[key] = (rank, rid)
    return {rid: first[key][1] for rid, key in group.items() if rid in when and key in first}


def signal_complaint_facts(db: Session, signal: Signal) -> list[logic.ComplaintFacts]:
    """The facts of the signal's complaints, read through its links (LINKED_COMPLAINT)."""
    return complaint_facts(
        complaint_facts_query(db, signal.tenant_id, linked=True).filter(
            SignalComplaint.tenant_id == signal.tenant_id, SignalComplaint.signal_id == signal.id
        )
    )


def from_source(source: str):
    """The signals whose data comes from ``source`` (the Signal inbox's Data filter, like the complaint list's;
    signals have no source of their own, so it is read from the complaints linked to them):

    - the sample's source (MDARIX_SAMPLE, "Only the sample data"): at least one complaint is linked and every linked
      complaint is from the sample;
    - any other source (TRIAL_UPLOAD, "Only your imported data"): at least one linked complaint is from it, so a
      signal that mixes imported and sample complaints counts as the organization's own data;
    - a signal with no linked complaint (one created by hand without complaints) matches no source: it is listed
      under All data only.

    A condition on Signal (correlated EXISTS), so the list, its count and the counts per status stay one query each."""
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    def linked(*conditions):
        return (
            select(SignalComplaint.id)
            .join(Complaint, LINKED_COMPLAINT)
            .where(SignalComplaint.tenant_id == Signal.tenant_id, SignalComplaint.signal_id == Signal.id, *conditions)
            .exists()
        )

    if source == SAMPLE_SOURCE:
        return and_(
            linked(Complaint.source_system == SAMPLE_SOURCE),
            ~linked(Complaint.source_system.is_distinct_from(SAMPLE_SOURCE)),
        )
    return linked(Complaint.source_system == source)


def complaint_sources(db: Session, tenant_id) -> list[str]:
    """The sources the organization's complaints come from (the complaint list's ``sources``): the inbox offers its
    Data filter only while the sample data is there."""
    return [
        row[0]
        for row in db.query(Complaint.source_system)
        .filter(
            Complaint.tenant_id == as_uuid(tenant_id),
            Complaint.source_system.is_not(None),
            Complaint.source_system != "",
        )
        .distinct()
        .order_by(Complaint.source_system)
        .limit(SOURCES_MAX)
    ]


def linked_complaint_ids(db: Session, signal: Signal) -> list[uuid.UUID]:
    return [
        row[0]
        for row in db.query(SignalComplaint.complaint_id)
        .filter(SignalComplaint.tenant_id == signal.tenant_id, SignalComplaint.signal_id == signal.id)
        .order_by(SignalComplaint.added_at, SignalComplaint.complaint_id)
    ]


def rule_settings(db: Session, tenant_id, *, lock: bool = False) -> dict:
    """The organization's threshold rule (its signal_rules row, else the defaults at version 1)."""
    query = db.query(SignalRule).filter(
        SignalRule.tenant_id == as_uuid(tenant_id), SignalRule.rule_code == THRESHOLD_RULE
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        return {"row": None, "enabled": True, "version": 1, **THRESHOLD_DEFAULTS}
    return {
        "row": row,
        "enabled": bool(row.enabled),
        "version": int(row.version or 1),
        "min_complaints": int(row.min_complaints),
        "window_days": int(row.window_days),
    }


def rule_row(db: Session, tenant_id, *, lock: bool = True) -> SignalRule:
    """The organization's rule row, created with the defaults when it has none yet. Does not commit."""
    settings = rule_settings(db, tenant_id, lock=lock)
    if settings["row"] is not None:
        return settings["row"]
    now = now_utc()
    row = SignalRule(
        id=uuid.uuid4(),
        tenant_id=as_uuid(tenant_id),
        rule_code=THRESHOLD_RULE,
        enabled=True,
        min_complaints=THRESHOLD_DEFAULTS["min_complaints"],
        window_days=THRESHOLD_DEFAULTS["window_days"],
        version=1,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def min_complaints_of(db: Session, signal: Signal) -> int:
    """The threshold a signal's suggested priority is measured against: the rule version that raised it, else the
    organization's current rule."""
    value = (signal.rule_parameters or {}).get("min_complaints")
    if value:
        return int(value)
    return int(rule_settings(db, signal.tenant_id)["min_complaints"])


# --------------------------------------------------------------------------------------------------- changing


def recompute(db: Session, signal: Signal, *, min_complaints: int | None = None, now: datetime | None = None) -> None:
    """Count, time range, highest severity, serious harm and suggested priority from the linked complaints."""
    facts = logic.summarize(signal_complaint_facts(db, signal))
    signal.complaint_count = facts.count
    signal.first_event_at = facts.first_event_at
    signal.last_event_at = facts.last_event_at
    signal.highest_severity = (facts.highest_severity or "")[:SEVERITY_LENGTH] or None
    signal.serious_harm = facts.serious_harm
    signal.suggested_priority = logic.suggested_priority(facts, min_complaints or min_complaints_of(db, signal))
    signal.updated_at = now or now_utc()


def link_complaints(db: Session, signal: Signal, complaint_ids, *, how: str, actor_ref) -> list[uuid.UUID]:
    """Link complaints to the signal (``how``: RULE, MANUAL, MERGE); those already linked are skipped. Returns the
    newly linked ids. Does not commit.

    The links are inserted in a few statements (db/bulk.py), not one per complaint: an import's signal can link
    thousands of complaints, and one INSERT each was most of detection's time (0.10.42). The rows are not loaded into
    the session."""
    from backend.app.db.bulk import insert_rows

    wanted = list(dict.fromkeys(as_uuid(item) for item in complaint_ids if as_uuid(item) is not None))
    if not wanted:
        return []
    present: set[uuid.UUID] = set()
    for start in range(0, len(wanted), LINK_BATCH):
        present.update(
            row[0]
            for row in db.query(SignalComplaint.complaint_id).filter(
                SignalComplaint.tenant_id == signal.tenant_id,
                SignalComplaint.signal_id == signal.id,
                SignalComplaint.complaint_id.in_(wanted[start : start + LINK_BATCH]),
            )
        )
    now = now_utc()
    added = [complaint_id for complaint_id in wanted if complaint_id not in present]
    if added:
        db.flush()  # the signal itself first: the links reference it
        insert_rows(
            db,
            SignalComplaint,
            [
                {
                    "id": uuid.uuid4(),
                    "tenant_id": signal.tenant_id,
                    "signal_id": signal.id,
                    "complaint_id": complaint_id,
                    "added_how": how,
                    "added_by": str(actor_ref or DETECTION_ACTOR),
                    "added_at": now,
                }
                for complaint_id in added
            ],
        )
    return added


def complaints_of_product(db: Session, tenant_id, product_id, complaint_ids) -> list[uuid.UUID]:
    """The ids, in the order given, when every complaint belongs to the product in this organization; else
    COMPLAINT_NOT_FOR_PRODUCT."""
    wanted = list(dict.fromkeys(as_uuid(item) for item in complaint_ids))
    if not wanted:
        return []
    if any(item is None for item in wanted) or product_id is None:
        raise logic.SignalRuleError(
            422, "COMPLAINT_NOT_FOR_PRODUCT", "Every complaint must belong to this product in your organization"
        )
    found = {
        row[0]
        for row in db.query(Complaint.id).filter(
            Complaint.tenant_id == as_uuid(tenant_id), Complaint.product_id == product_id, Complaint.id.in_(wanted)
        )
    }
    if len(found) != len(wanted):
        raise logic.SignalRuleError(
            422, "COMPLAINT_NOT_FOR_PRODUCT", "Every complaint must belong to this product in your organization"
        )
    return wanted


def triage_task_title(signal: Signal) -> str:
    return f"Triage {signal.business_id}: {task_service.shorten(signal.title, 200)}"


def queue_triage_task(db: Session, signal: Signal, *, actor_ref, actor_role: str | None = None, details=None):
    """The signal's SIGNAL_TRIAGE task in the triage leads' queue, at its priority and due date (idempotent: an open
    one is returned). Does not commit."""
    return task_service.create_task(
        db,
        signal.tenant_id,
        task_type=TRIAGE_TASK,
        title=triage_task_title(signal),
        source_type=SIGNAL_SOURCE,
        source_id=signal.id,
        priority=logic.effective_priority(signal.confirmed_priority, signal.suggested_priority) or "MEDIUM",
        due_at=signal.due_at,
        created_by=str(actor_ref or DETECTION_ACTOR),
        actor_role=actor_role,
        details=dict(details or {}),
    )


def finish_triage_tasks(db: Session, signal: Signal, *, outcome: str, actor_ref, actor_role=None, supersede=False):
    """Complete (or supersede) the signal's open SIGNAL_TRIAGE tasks with ``outcome``. Does not commit."""
    finish = task_service.supersede_tasks if supersede else task_service.complete_tasks
    return finish(
        db,
        signal.tenant_id,
        source_type=SIGNAL_SOURCE,
        source_id=signal.id,
        task_types=[TRIAGE_TASK],
        outcome=outcome,
        actor_ref=str(actor_ref or DETECTION_ACTOR),
        actor_role=actor_role,
    )


def take_triage_task(db: Session, signal: Signal, *, user_id: uuid.UUID, actor_role: str | None, correlation_id=None):
    """Give the signal's open SIGNAL_TRIAGE task to the person starting triage (ACCEPTED): claimed from the queue,
    moved from someone else, or created when none is open. Does not commit."""
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask

    rows = (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == signal.tenant_id,
            WorkflowTask.source_entity_type == SIGNAL_SOURCE,
            WorkflowTask.source_entity_id == signal.id,
            WorkflowTask.task_type == TRIAGE_TASK,
            WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        )
        .order_by(WorkflowTask.created_at)
        .with_for_update()
        .all()
    )
    if not rows:
        task = queue_triage_task(db, signal, actor_ref=str(user_id), actor_role=actor_role)
        rows = [task]
    now = now_utc()
    for task in rows:
        if task.assigned_user_id == user_id and task.status in ("ACCEPTED", "IN_PROGRESS"):
            continue
        previous = task.status
        event = "CLAIMED" if task.assigned_user_id is None else "REASSIGNED"
        if task.assigned_user_id == user_id:
            event = "ACCEPTED"
        task.assigned_user_id = user_id
        task.status = "ACCEPTED"
        task.accepted_at = now
        task.updated_at = now
        task_service.record_event(
            db,
            task,
            event,
            actor_ref=str(user_id),
            actor_role=actor_role,
            from_status=previous,
            to_status="ACCEPTED",
            reason="Triage started on the signal",
            correlation_id=correlation_id,
            now=now,
        )
    return rows[0]


def update_open_task_schedule(db: Session, signal: Signal) -> None:
    """Keep the open triage task's priority and due date in step with the signal's. Does not commit."""
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask

    priority = logic.effective_priority(signal.confirmed_priority, signal.suggested_priority) or "MEDIUM"
    for task in (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == signal.tenant_id,
            WorkflowTask.source_entity_type == SIGNAL_SOURCE,
            WorkflowTask.source_entity_id == signal.id,
            WorkflowTask.task_type == TRIAGE_TASK,
            WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        )
        .with_for_update()
    ):
        task.priority = priority
        task.due_at = signal.due_at
        task.updated_at = now_utc()


def create_signal(
    db: Session,
    tenant_id,
    *,
    title: str,
    origin: str,
    product_id,
    product_version_id=None,
    problem_key: str | None = None,
    complaint_ids=(),
    added_how: str = "RULE",
    description: str | None = None,
    actor_ref,
    actor_role: str | None = None,
    rule: dict | None = None,
    confirmed_priority: str | None = None,
    priority_reason: str | None = None,
    min_complaints: int | None = None,
    correlation_id: str | None = None,
) -> Signal:
    """A new signal (status NEW) with its complaints, facts, suggested priority and due date, its CREATED history and
    a SIGNAL_TRIAGE task in the triage leads' queue. ``rule``: the rule version and parameters that raised it. The
    number (SIG000001) is assigned by the database. Does not commit."""
    now = now_utc()
    actor = str(actor_ref or DETECTION_ACTOR)
    signal = Signal(
        id=uuid.uuid4(),
        tenant_id=as_uuid(tenant_id),
        title=str(title).strip()[: logic.TITLE_LENGTH],
        description=(description or "").strip() or None,
        origin=origin,
        rule_code=(rule or {}).get("code"),
        rule_version=(rule or {}).get("version"),
        rule_parameters=dict((rule or {}).get("parameters") or {}),
        product_id=as_uuid(product_id),
        product_version_id=as_uuid(product_version_id),
        problem_key=problem_key,
        complaint_count=0,
        serious_harm=False,
        confirmed_priority=confirmed_priority,
        priority_reason=priority_reason,
        status="NEW",
        created_by=actor,
        created_at=now,
        updated_at=now,
        details={},
    )
    db.add(signal)
    db.flush()
    linked = link_complaints(db, signal, complaint_ids, how=added_how, actor_ref=actor)
    threshold = min_complaints or (rule or {}).get("parameters", {}).get("min_complaints")
    recompute(db, signal, min_complaints=threshold or min_complaints_of(db, signal), now=now)
    signal.due_at = logic.due_at(logic.effective_priority(signal.confirmed_priority, signal.suggested_priority), now)
    record(
        db,
        signal,
        "CREATED",
        actor_ref=actor,
        actor_role=actor_role,
        to_status="NEW",
        reason=priority_reason,
        details={
            "origin": origin,
            "rule_code": signal.rule_code,
            "rule_version": signal.rule_version,
            "complaints": len(linked),
            "suggested_priority": signal.suggested_priority,
            "confirmed_priority": signal.confirmed_priority,
        },
        correlation_id=correlation_id,
        now=now,
    )
    queue_triage_task(db, signal, actor_ref=actor, actor_role=actor_role)
    return signal


# ------------------------------------------------------------------------------------------------ serializing


def people_names(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    if control_db is None:
        return {}
    from backend.app.workflow.people import names_by_id

    try:
        return names_by_id(control_db, tenant_id, refs)
    except Exception:
        return {}


def actor_name(names: dict[str, str], ref) -> str | None:
    """A person's name for a history row; MDARIX for the system's own changes; never a raw reference."""
    if as_uuid(ref) is not None:
        return names.get(str(as_uuid(ref)))
    return "MDARIX" if str(ref or "").startswith("system") else None


def _by_id(db: Session, model, tenant_id, ids, *columns) -> dict[str, tuple]:
    wanted = wanted_ids(ids)
    if not wanted:
        return {}
    rows = db.query(model.id, *columns).filter(model.tenant_id == as_uuid(tenant_id), model.id.in_(list(wanted)))
    return {str(row[0]): tuple(row[1:]) for row in rows}


def summaries(db: Session, control_db: Session | None, tenant_id, rows: list[Signal]) -> list[dict]:
    """The SignalSummary of each signal, with products, versions, owners, canonical signals and cases read in bulk."""
    if not rows:
        return []
    tenant = as_uuid(tenant_id)
    now = now_utc()
    products = _by_id(db, Product, tenant, (row.product_id for row in rows), Product.business_id, Product.name)
    versions = _by_id(
        db,
        ProductVersion,
        tenant,
        (row.product_version_id for row in rows),
        ProductVersion.business_id,
        ProductVersion.version_identifier,
    )
    canonical = _by_id(db, Signal, tenant, (row.canonical_signal_id for row in rows), Signal.business_id)
    names = people_names(control_db, tenant, (row.owner_user_id for row in rows))
    ids = [row.id for row in rows]
    cases: dict[str, list[dict]] = {}
    for signal_id, case_id, business_id, status in (
        db.query(InvestigationSignal.signal_id, Investigation.id, Investigation.business_id, Investigation.status)
        .join(
            Investigation,
            and_(
                Investigation.tenant_id == InvestigationSignal.tenant_id,
                Investigation.id == InvestigationSignal.investigation_id,
            ),
        )
        .filter(InvestigationSignal.tenant_id == tenant, InvestigationSignal.signal_id.in_(ids))
        .order_by(InvestigationSignal.created_at)
    ):
        cases.setdefault(str(signal_id), []).append({"id": str(case_id), "business_id": business_id, "status": status})
    recent = {
        str(signal_id): int(count)
        for signal_id, count in db.query(SignalComplaint.signal_id, func.count(SignalComplaint.id))
        .join(Complaint, LINKED_COMPLAINT)
        .filter(
            SignalComplaint.tenant_id == tenant,
            SignalComplaint.signal_id.in_(ids),
            COMPLAINT_EVENT_AT >= now - timedelta(days=RECENT_DAYS),
        )
        .group_by(SignalComplaint.signal_id)
    }
    items = []
    for row in rows:
        product = products.get(str(row.product_id)) if row.product_id else None
        version = versions.get(str(row.product_version_id)) if row.product_version_id else None
        canonical_row = canonical.get(str(row.canonical_signal_id)) if row.canonical_signal_id else None
        created = row.created_at
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "title": logic.display_title(row.title, row.origin),
                "origin": row.origin,
                "origin_label": ORIGIN_LABELS.get(row.origin, row.origin),
                "rule_code": row.rule_code,
                "product": (
                    {"id": str(row.product_id), "business_id": product[0], "name": product[1]} if product else None
                ),
                "product_version": (
                    {"id": str(row.product_version_id), "business_id": version[0], "version_identifier": version[1]}
                    if version
                    else None
                ),
                "problem_key": row.problem_key,
                "complaint_count": int(row.complaint_count or 0),
                "recent_complaints_7d": recent.get(str(row.id), 0),
                "first_event_at": iso(row.first_event_at),
                "last_event_at": iso(row.last_event_at),
                "highest_severity": row.highest_severity,
                "serious_harm": bool(row.serious_harm),
                "suggested_priority": row.suggested_priority,
                "confirmed_priority": row.confirmed_priority,
                "priority": logic.effective_priority(row.confirmed_priority, row.suggested_priority),
                "status": row.status,
                "status_label": STATUS_LABELS.get(row.status, row.status),
                "owner": (
                    {"id": str(row.owner_user_id), "name": names.get(str(row.owner_user_id))}
                    if row.owner_user_id
                    else None
                ),
                "due_at": iso(row.due_at),
                "overdue": bool(row.status in AWAITING_TRIAGE and row.due_at is not None and row.due_at < now),
                "age_days": max((now - created).days, 0) if created is not None else 0,
                "canonical": (
                    {"id": str(row.canonical_signal_id), "business_id": canonical_row[0]} if canonical_row else None
                ),
                "investigations": cases.get(str(row.id), []),
                "created_at": iso(row.created_at),
                "updated_at": iso(row.updated_at),
            }
        )
    return items


def _window(signal: Signal, now: datetime) -> tuple[datetime, datetime]:
    """The signal's time window: its first to last complaint, else the rule's window up to now."""
    days = int((signal.rule_parameters or {}).get("window_days") or THRESHOLD_DEFAULTS["window_days"])
    start = signal.first_event_at or (now - timedelta(days=days))
    end = signal.last_event_at or now
    return (start, end) if start <= end else (end, start)


def _complaints(db: Session, signal: Signal) -> list[dict]:
    rows = (
        db.query(Complaint, SignalComplaint.added_how, ProductVersion.business_id, ProductVersion.version_identifier)
        .join(SignalComplaint, LINKED_COMPLAINT)
        .outerjoin(
            ProductVersion,
            and_(ProductVersion.tenant_id == Complaint.tenant_id, ProductVersion.id == Complaint.product_version_id),
        )
        .filter(SignalComplaint.tenant_id == signal.tenant_id, SignalComplaint.signal_id == signal.id)
        .order_by(COMPLAINT_EVENT_AT.desc().nulls_last(), Complaint.business_id)
        .all()
    )
    return [
        {
            "id": str(complaint.id),
            "business_id": complaint.business_id,
            "complaint_identifier": complaint.complaint_identifier,
            "description": complaint.description,
            "severity": complaint.severity,
            "serious_injury": complaint.serious_injury,
            "death": complaint.death,
            "malfunction": complaint.malfunction,
            "country": complaint.country,
            "status": complaint.status,
            "event_timestamp": iso(logic.event_time(complaint.event_timestamp, complaint.complaint_timestamp)),
            "product_version": (
                {"business_id": version_business_id, "version_identifier": version_identifier}
                if version_business_id
                else None
            ),
            "added_how": added_how,
        }
        for complaint, added_how, version_business_id, version_identifier in rows
    ]


def _version_split(db: Session, signal: Signal, now: datetime) -> list[dict]:
    """The signal's own complaints (those its complaint count counts), by version (``unknown`` when none recorded), so
    the chart and the signal never disagree. ``now`` is unused and kept for the callers."""
    rows = (
        db.query(
            ProductVersion.id,
            ProductVersion.business_id,
            ProductVersion.version_identifier,
            func.count(Complaint.id),
        )
        .select_from(Complaint)
        .join(SignalComplaint, LINKED_COMPLAINT)
        .outerjoin(
            ProductVersion,
            and_(ProductVersion.tenant_id == Complaint.tenant_id, ProductVersion.id == Complaint.product_version_id),
        )
        .filter(SignalComplaint.tenant_id == signal.tenant_id, SignalComplaint.signal_id == signal.id)
        .group_by(ProductVersion.id, ProductVersion.business_id, ProductVersion.version_identifier)
        .all()
    )
    items = [
        {
            "product_version_id": str(version_id) if version_id else None,
            "product_version_business_id": business_id,
            "version_identifier": version_identifier if version_id else "unknown",
            "count": int(count),
        }
        for version_id, business_id, version_identifier, count in rows
    ]
    return sorted(items, key=lambda item: (-item["count"], str(item["version_identifier"])))


CLOSED_RECORD_STATUSES = ("closed", "cancelled", "canceled", "completed", "done")


def _related(db: Session, signal: Signal, now: datetime) -> dict:
    """Context for triage: the changes to the product, or to a component of one of its versions, from 90 days before
    the first complaint to the last (a supplier change is usually recorded against the component it affects), its open
    CAPAs and its open investigations."""
    from sqlalchemy import or_

    from backend.app.db.models.foundation import Capa, Change, ProductComponent, RealityRelationship

    if signal.product_id is None:
        return {"changes": [], "open_capas": [], "open_investigations": []}
    start, end = _window(signal, now)
    start = start - timedelta(days=90)
    tenant = signal.tenant_id
    components = (
        db.query(ProductComponent.component_id)
        .join(
            ProductVersion,
            and_(
                ProductVersion.tenant_id == ProductComponent.tenant_id,
                ProductVersion.id == ProductComponent.product_version_id,
            ),
        )
        .filter(ProductComponent.tenant_id == tenant, ProductVersion.product_id == signal.product_id)
    )
    linked_changes = db.query(RealityRelationship.source_entity_id).filter(
        RealityRelationship.tenant_id == tenant,
        RealityRelationship.source_entity_type == "Change",
        or_(
            and_(
                RealityRelationship.target_entity_type == "Product",
                RealityRelationship.target_entity_id == signal.product_id,
            ),
            and_(
                RealityRelationship.target_entity_type == "Component",
                RealityRelationship.target_entity_id.in_(components),
            ),
        ),
    )
    changed_at = func.coalesce(Change.event_timestamp, Change.effective_timestamp)
    changes = [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "identifier": row.change_identifier,
            "title": task_service.shorten(row.description, 200),
            "change_type": row.change_type,
            "event_at": iso(row.event_timestamp),
            "effective_at": iso(row.effective_timestamp),
        }
        for row in db.query(Change)
        .filter(Change.tenant_id == tenant, Change.id.in_(linked_changes), changed_at >= start, changed_at <= end)
        .order_by(changed_at.desc())
        .limit(50)
    ]
    capas = [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "identifier": row.capa_identifier,
            "title": row.title,
            "status": row.status,
            "due_at": iso(row.due_at),
        }
        for row in db.query(Capa)
        .filter(
            Capa.tenant_id == tenant,
            Capa.product_id == signal.product_id,
            func.lower(func.coalesce(Capa.status, "")).notin_(CLOSED_RECORD_STATUSES),
        )
        .order_by(Capa.opened_at.desc().nulls_last())
        .limit(50)
    ]
    investigations = [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "identifier": row.investigation_identifier,
            "status": row.status,
            "question": row.investigation_question,
        }
        for row in db.query(Investigation)
        .filter(
            Investigation.tenant_id == tenant,
            Investigation.product_id == signal.product_id,
            func.lower(func.coalesce(Investigation.status, "")) != "closed",
        )
        .order_by(Investigation.opened_at.desc().nulls_last())
        .limit(50)
    ]
    return {"changes": changes, "open_capas": capas, "open_investigations": investigations}


def detail(db: Session, control_db: Session | None, signal: Signal, *, actions: dict | None = None) -> dict:
    """SignalSummary plus everything the triage screen shows: complaints, version split, related records, lineage,
    history and what the person may do."""
    now = now_utc()
    events = (
        db.query(SignalEvent)
        .filter(SignalEvent.tenant_id == signal.tenant_id, SignalEvent.signal_id == signal.id)
        .order_by(SignalEvent.created_at, SignalEvent.id)
        .all()
    )
    names = people_names(
        control_db,
        signal.tenant_id,
        [row.actor_ref for row in events] + [signal.dispositioned_by, signal.owner_user_id],
    )
    merged_from = [
        {"id": str(row.id), "business_id": row.business_id, "status": row.status}
        for row in db.query(Signal)
        .filter(Signal.tenant_id == signal.tenant_id, Signal.canonical_signal_id == signal.id)
        .order_by(Signal.created_at)
    ]
    disposition = None
    if signal.dispositioned_at is not None:
        disposition = {
            "status": signal.status,
            "reason": signal.disposition_reason,
            "by_name": actor_name(names, signal.dispositioned_by),
            "at": iso(signal.dispositioned_at),
            "monitor_review_date": iso(signal.monitor_review_date),
            "monitor_trigger": signal.monitor_trigger,
        }
    rule = None
    if signal.rule_code:
        rule = {"code": signal.rule_code, "version": signal.rule_version, "parameters": signal.rule_parameters or {}}
    return {
        **summaries(db, control_db, signal.tenant_id, [signal])[0],
        "description": signal.description,
        "rule": rule,
        "priority_reason": signal.priority_reason,
        "disposition": disposition,
        "complaints": _complaints(db, signal),
        "version_split": _version_split(db, signal, now),
        "related": _related(db, signal, now),
        "merged_from": merged_from,
        "events": [
            {
                "event_type": row.event_type,
                "actor_name": actor_name(names, row.actor_ref),
                "actor_role": row.actor_role,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "reason": row.reason,
                "details": row.details or {},
                "created_at": iso(row.created_at),
            }
            for row in events
        ],
        "actions": actions or {},
    }
