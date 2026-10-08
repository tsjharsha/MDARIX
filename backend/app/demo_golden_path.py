"""The golden path of the AcmeCare demo workspace: case ACD-INV-401 (FlowSure 300 flow interruptions) taken from a
signal all the way to a signed decision, so every Phase 1-6 screen has a worked example. Synthetic data only.

The story, dated in days before the day the workspace is loaded:

- day 63: the complaint threshold rule raises a signal (SIG...) for flow interruption on FlowSure 300 Rev 2;
- day 62: Tara Triage (PMS / Signal Triage Lead) takes it into triage, sets priority HIGH and dispositions it
  INVESTIGATION_REQUIRED; day 61: she opens the case for Ines Investigator, who accepts its task;
- scope version 1 (the signal's complaints), later complaints added by the rule, scope version 2 (one complaint
  excluded with its reason);
- evidence reviewed (accepted, accepted with a limitation, one rejected with its reason; supporting and
  contradicting), an AI-origin and a human hypothesis judged by Ines (PARTIALLY_SUPPORTED with supporting and
  contradicting links, and RETIRED), unknowns (one resolved, one accepted as a limitation), a failure chain built by
  hand with mixed link states, and observations;
- risk review (Rita Risk: RISK_CONTROL_REVIEW_REQUIRED) and regulatory review (Rory Regulatory:
  REPORTABILITY_ASSESSMENT_COMPLETE);
- Decision Brief v1 returned by Ravi Reviewer for evidence, an internal evidence request answered and reviewed into
  evidence (resolving an unknown), Decision Brief v2 accepted for decision;
- day 6: Ana Approver signs ACCEPT_WITH_CONDITIONS with a CAPA_REQUIRED follow-up and its CAPA record;
- after signing: a late complaint, and late evidence with an OPEN impact assessment.

Records are written the way the domain services write them (their helpers are called where they need no request;
otherwise rows, history and audit events are written as the endpoint writes them), each at its moment of the story.
Helpers that stamp the wall clock (workflow tasks, signals) are re-dated to the story moment afterwards; the audit
events they wrote keep the real time.

The signature is made with the signing code's own functions (``human_decision.rules``: signature material,
fingerprint, signature hash, snapshot hash; ``service.reviewers``), so verification reports VALID. Seeding is a system
action: no password is checked, and it is audited as DEMO_SEEDED (never as CASE_DECISION_SIGNED).

``seed_golden_path`` runs in a session of its own bound to the demo tenant, writes everything in one transaction
(nothing is half-seeded), is idempotent (a case already opened from a signal is left alone) and never fails the setup
or the reset: a failure is logged and reported.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.app import demo_story as story

logger = logging.getLogger("mdarix.demo_workspace")

SEED_ACTOR = "system:demo-workspace"
SEEDED_ACTION = "DEMO_SEEDED"
# The team members the golden path needs, by role code (backend/app/demo_workspace.py DEMO_TEAM).
NEEDED_ROLES = ("TRIAGE_LEAD", "INVESTIGATOR", "RISK_REVIEWER", "REGULATORY_REVIEWER", "REVIEWER", "APPROVER")


class GoldenPathSkipped(RuntimeError):
    """The workspace cannot hold the golden path (its story predates it, or a team member is missing)."""


# ----------------------------------------------------------------------------------------------- pure helpers


def story_moment(now: datetime, days: int, minutes: int = 0) -> datetime:
    """``days`` before ``now``, ``minutes`` later in that day (keeps the order of steps taken on the same day)."""
    return now - timedelta(days=days) + timedelta(minutes=minutes)


def retimed(value: datetime | None, wall: datetime, moment: datetime) -> datetime | None:
    """A timestamp written by a helper that reads the wall clock during this run (``value >= wall``) moves to the
    story ``moment``; anything else is kept."""
    if value is None or value < wall:
        return value
    return moment


def scope_split(complaint_ids: list, excluded_index: int, late_index: int) -> tuple[list, list]:
    """Scope version 2 of the golden case: every complaint before the late one is included except the excluded one.
    Returns ``(included, excluded)`` as lists of ids, in story order."""
    included = [item for index, item in enumerate(complaint_ids[:late_index]) if index != excluded_index]
    return included, [complaint_ids[excluded_index]]


# ---------------------------------------------------------------------------------------------- the context


@dataclass
class Story:
    """What every step of the golden path shares: the bound session, the tenant, the story's today, the wall-clock
    start of this run, the case and its records, the team (``Person`` per role code) and what was made."""

    db: Session
    tenant_id: uuid.UUID
    now: datetime
    wall: datetime
    case: object
    product: object
    version: object
    complaints: list
    evidence: dict
    users: dict
    team: dict
    made: dict = field(default_factory=dict)

    def at(self, days: int, minutes: int = 0) -> datetime:
        return story_moment(self.now, days, minutes)

    def user(self, role: str):
        return self.users[role]

    def person(self, role: str):
        return self.team[role]

    def settle(self, moment: datetime) -> None:
        """Re-date to ``moment`` what the helpers stamped with the wall clock since the run started (workflow tasks
        and their history, signals with their history and complaint links). Audit events are never changed."""
        from backend.app.db.models.decision_outcomes import ImpactAssessment
        from backend.app.db.models.signals import Signal, SignalComplaint, SignalEvent
        from backend.app.db.models.workflow import WorkflowTask, WorkflowTaskEvent

        self.db.flush()
        for model, names in (
            (ImpactAssessment, ("created_at", "updated_at")),
            (WorkflowTask, ("created_at", "updated_at", "accepted_at", "completed_at")),
            (WorkflowTaskEvent, ("created_at",)),
            (Signal, ("created_at", "updated_at")),
            (SignalEvent, ("created_at",)),
            (SignalComplaint, ("added_at",)),
        ):
            columns = [getattr(model, name) for name in names]
            rows = (
                self.db.query(model)
                .filter(model.tenant_id == self.tenant_id, or_(*(column >= self.wall for column in columns)))
                .all()
            )
            for row in rows:
                for name in names:
                    setattr(row, name, retimed(getattr(row, name), self.wall, moment))
        self.db.flush()


def _person(db: Session, user):
    """The team member as the evidence and intelligence services see a signed-in person (roles, permissions)."""
    from backend.app.evidence_workflow.people import Person
    from backend.app.workflow.people import permissions_of, roles_of

    return Person(
        user_id=str(user.id),
        user_uuid=user.id,
        tenant_id=user.tenant_id,
        permissions=permissions_of(db, user),
        roles=roles_of(db, user),
        account_role=user.role,
    )


def story_today(opened_at: datetime, opened_days: int) -> datetime:
    """The day the story was loaded, read back from the golden case (stamped ``opened_days`` before it)."""
    return opened_at + timedelta(days=opened_days)


def _opened_days() -> int:
    return next(item[4] for item in story.INVESTIGATIONS if item[0] == story.GOLDEN_CASE)


def _context(db: Session, tenant_id: uuid.UUID, now: datetime | None) -> Story:
    from backend.app.db.models.foundation import AuthUser, Complaint, Evidence, Investigation, Product, ProductVersion
    from backend.app.demo_workspace import DEMO_TEAM
    from backend.app.role_codes import role_code

    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == story.GOLDEN_CASE)
        .with_for_update()
        .first()
    )
    if case is None:
        raise GoldenPathSkipped(f"{story.GOLDEN_CASE} is not in this workspace; reset the demo to load the story")
    # Without a given today (a workspace loaded earlier), the story is dated from the day it was loaded.
    now = now or story_today(case.created_at, _opened_days())
    product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == case.product_id).one()
    identifiers = [
        f"ACD-CMP-{index:04d}" for index, record in enumerate(story.COMPLAINTS, 1) if record[0] == story.GOLDEN_PRODUCT
    ]
    found = {
        row.complaint_identifier: row
        for row in db.query(Complaint).filter(
            Complaint.tenant_id == tenant_id, Complaint.complaint_identifier.in_(identifiers)
        )
    }
    codes = [code for code, *_ in story.EVIDENCE[story.GOLDEN_CASE]]
    evidence = {
        row.evidence_identifier: row
        for row in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.evidence_identifier.in_(codes))
    }
    if len(found) != len(identifiers) or len(evidence) != len(codes):
        raise GoldenPathSkipped("The golden case's complaints or evidence are missing; reset the demo")
    # The version the complaints (and so the signal) are about.
    version = (
        db.query(ProductVersion)
        .filter(
            ProductVersion.tenant_id == tenant_id,
            ProductVersion.id == found[identifiers[0]].product_version_id,
        )
        .one()
    )
    emails = [email for _, email, _ in DEMO_TEAM]
    users = {}
    for user in db.query(AuthUser).filter(
        AuthUser.tenant_id == tenant_id, AuthUser.username.in_(emails), AuthUser.status == "ACTIVE"
    ):
        users.setdefault(role_code(user.role), user)
    missing = [role for role in NEEDED_ROLES if role not in users]
    if missing:
        raise GoldenPathSkipped(f"The demo team has nobody for {', '.join(missing)}; run setup first")
    return Story(
        db=db,
        tenant_id=tenant_id,
        now=now,
        wall=datetime.now(timezone.utc),
        case=case,
        product=product,
        version=version,
        complaints=[found[identifier] for identifier in identifiers],
        evidence=evidence,
        users=users,
        team={role: _person(db, users[role]) for role in NEEDED_ROLES},
    )


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


# --------------------------------------------------------------------------------------- the case and its scope

EXCLUSION_REASON = (
    "The extension-set clamp was found closed at handover: a use issue, not the cassette valve; kept on record but "
    "outside this investigation."
)
SCOPE_CHANGE_REASON = (
    "Complaints added by the threshold rule since the case was opened; the closed-clamp report is excluded."
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


# --------------------------------------------------------------------------------------------- evidence review

# (evidence, review status, relationship, days ago, reason, limitation)
EVIDENCE_REVIEWS = (
    ("ACD-EV-4011", "ACCEPTED", "SUPPORTING", 58, None, None),
    ("ACD-EV-4014", "ACCEPTED", "CONTRADICTING", 56, None, None),
    (
        "ACD-EV-4015",
        "REJECTED",
        "UNRELATED",
        38,
        "Hearsay without dates, lots or temperatures; it cannot be traced to any complaint or cassette lot.",
        None,
    ),
    ("ACD-EV-4012", "ACCEPTED", "SUPPORTING", 32, None, None),
    (
        "ACD-EV-4013",
        "ACCEPTED_WITH_LIMITATION",
        "SUPPORTING",
        29,
        None,
        "Only two returned cassettes were tested; one reproduced the alarm.",
    ),
)


def _ctx(person=None):
    """What the endpoint helpers read from a request: the signed-in person's id and the correlation id (none for
    the seeding)."""
    from types import SimpleNamespace

    return SimpleNamespace(correlation_id=None, user_id=person.user_id if person is not None else None)


def review_evidence(
    s: Story, code: str, status: str, relationship: str, moment: datetime, *, reason=None, limitation=None
):
    """Ines's review of one piece of the case's evidence (link, history row, EVIDENCE_REVIEWED), as
    ``POST /api/v1/investigations/{id}/evidence/{evidence_id}/review`` writes it."""
    from backend.app.access.permissions import EVIDENCE_REVIEW
    from backend.app.db.models.foundation import InvestigationEvidence
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow.inventory import review_event
    from backend.app.evidence_workflow.rules import review_problem

    problem = review_problem(status, relationship, reason, limitation)
    if problem:
        raise ValueError(f"{code}: {problem}")
    ines = s.person("INVESTIGATOR")
    ev = s.evidence[code]
    link = (
        s.db.query(InvestigationEvidence)
        .filter(
            InvestigationEvidence.tenant_id == s.tenant_id,
            InvestigationEvidence.investigation_id == s.case.id,
            InvestigationEvidence.evidence_id == ev.id,
        )
        .one()
    )
    link.created_at = min(s.case.opened_at, moment)
    before = {
        "review_status": link.review_status,
        "relationship": link.relationship,
        "review_reason": link.review_reason,
        "limitation": link.limitation,
    }
    link.review_status = status
    link.relationship = relationship
    link.review_reason = reason
    link.limitation = limitation
    link.reviewed_by = ines.user_id
    link.reviewed_at = moment
    review_event(
        s.db,
        tenant_id=s.tenant_id,
        case_id=s.case.id,
        evidence_id=ev.id,
        event_type="REVIEWED",
        actor=ines,
        permission=EVIDENCE_REVIEW,
        from_status=before["review_status"],
        to_status=status,
        from_relationship=before["relationship"],
        to_relationship=relationship,
        reason=reason,
        details={"limitation": limitation} if limitation else None,
        now=moment,
    )
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=ines.user_id,
            action="EVIDENCE_REVIEWED",
            entity_type="InvestigationEvidence",
            entity_id=link.id,
            reason=reason,
            old_values=before,
            new_values={
                "review_status": status,
                "relationship": relationship,
                "review_reason": reason,
                "limitation": limitation,
            },
            details={
                "investigation_id": str(s.case.id),
                "evidence_id": str(ev.id),
                "actor_role": ines.role_for(EVIDENCE_REVIEW),
            },
            created_at=moment,
        )
    )
    s.db.flush()
    return link


def review_case_evidence(s: Story) -> None:
    for code, status, relationship, days, reason, limitation in EVIDENCE_REVIEWS:
        review_evidence(s, code, status, relationship, s.at(days), reason=reason, limitation=limitation)


# ------------------------------------------------------------------------------------------------ intelligence

AI_HYPOTHESIS = (
    "Cassette valves moulded on the new tool T-4 have a thicker membrane at the gate that can stay closed after the "
    "cassette is loaded, so the pump detects no flow and stops the infusion."
)
HUMAN_HYPOTHESIS = (
    "The interruptions are use errors (cassette not fully seated or the extension-set clamp left closed), not a "
    "device fault."
)
HUMAN_HYPOTHESIS_RATIONALE = "One report describes a closed clamp; loading errors are a known cause of no-flow alarms."
UNKNOWN_LOTS = "Were the valve membranes of cassette lots C-301 to C-303 within the drawing tolerance at incoming?"
UNKNOWN_REV1 = "Do cassettes from the previous tool (Rev 1 pumps) show the same sticking under the same test?"
CHAIN_NAME = "Thick membrane to interrupted therapy"
CHAIN_NODES = (
    "Valve moulding moved to tool T-4",
    "Membrane thicker than drawing at the gate",
    "Membrane stays closed after cassette loading",
    "Pump detects no flow and stops the infusion",
    "Therapy delayed",
)
# (from, to, state, evidence or None, rationale)
CHAIN_LINKS = (
    (0, 1, "PARTIALLY_SUPPORTED", "ACD-EV-4011", "The change notice gives no membrane data; RMA-9127 measured thick."),
    (1, 2, "HYPOTHESIZED", None, "Plausible mechanism; not yet shown on more than one cassette."),
    (2, 3, "SUPPORTED", "ACD-EV-4013", "RMA-9127 reproduced the no-flow alarm when its membrane stayed closed."),
    (3, 4, "SUPPORTED", "ACD-EV-4012", "Complaints report delayed doses after the interruptions."),
)
# (evidence, epistemic type, statement, rationale)
OBSERVATIONS = (
    (
        "ACD-EV-4013",
        "FACT",
        "One of two returned cassettes gave a no-flow alarm on three of twenty loads at 23 C.",
        "Read from the bench test report.",
    ),
    (
        "ACD-EV-4014",
        "SOURCE_ASSERTION",
        "DV-305 tested flow continuity with cassettes from the previous tool only.",
        "The verification report says so; tool T-4 parts were never verified.",
    ),
    (
        "ACD-EV-4012",
        "DERIVED_OBSERVATION",
        "Every flow interruption complaint since Rev 2 comes from pump lots built with tool T-4 cassettes.",
        "Lot comparison of the complaint trend.",
    ),
)


def seed_ai_hypothesis(s: Story):
    """Day 31: an AI-origin hypothesis with the AI's own evidence links, as the hypothesis engine materializes them.
    The AI run behind it is a synthetic demo record (no model was called), labelled so in its provider and kind."""
    from backend.app.db.models.foundation import AIExecution, Hypothesis, HypothesisEvidence

    moment = s.at(31)
    execution = AIExecution(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        requestor_ref=s.person("INVESTIGATOR").user_id,
        provider="demo-seed",
        model_name="synthetic-demo",
        model_version="none",
        prompt_template_version="Hypotheses (synthetic demo run, no model called)",
        orchestration_version="demo-seed",
        evidence_refs={"evidence_identifiers": ["ACD-EV-4011", "ACD-EV-4012", "ACD-EV-4014"]},
        structured_output={"synthetic": True, "hypotheses": [AI_HYPOTHESIS]},
        rationale_summary=f"{story.SYNTHETIC}: stands in for an AI hypothesis run in the demo story.",
        validation_status="DEMO_SEEDED",
        execution_timestamp=moment,
        latency_ms=0,
    )
    s.db.add(execution)
    s.db.flush()
    row = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        statement=AI_HYPOTHESIS,
        status="mixed_evidence",
        origin="ai",
        reviewer_disposition=None,
        source_system="demo-seed",
        created_at=moment,
        updated_at=moment,
    )
    s.db.add(row)
    s.db.flush()
    for code, relation, rationale in (
        ("ACD-EV-4011", "support", "The change notice dates the new tool before the complaints began."),
        ("ACD-EV-4012", "support", "All complaints come from lots with tool T-4 cassettes."),
        ("ACD-EV-4014", "contradict", "Design verification found no flow interruption."),
    ):
        s.db.add(
            HypothesisEvidence(
                id=uuid.uuid4(),
                tenant_id=s.tenant_id,
                hypothesis_id=row.id,
                evidence_id=s.evidence[code].id,
                relation_type=relation,
                rationale=rationale,
                created_by_type="system",
                created_at=moment,
            )
        )
    s.db.flush()
    s.made["ai_execution"] = execution
    s.made["ai_hypothesis"] = row
    return row


def seed_human_intelligence(s: Story):
    """Days 44-28: Ines adds a hypothesis, two unknowns, an evidence link, a failure chain and observations, each
    with its history row and audit event, as the case intelligence endpoints write them."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_intelligence import rules
    from backend.app.case_intelligence.router import _record, _store_chain
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import Hypothesis, HypothesisEvidence, Unknown

    ines = s.person("INVESTIGATOR")
    ctx = _ctx()

    def record(moment, **kwargs):
        _record(s.db, ctx=ctx, person=ines, permission=INVESTIGATION_WORK, case=s.case, now=moment, **kwargs)

    moment = s.at(44)
    human = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        statement=HUMAN_HYPOTHESIS,
        status=rules.PROPOSED.lower(),
        origin=rules.ORIGIN_HUMAN,
        human_status=rules.PROPOSED,
        status_reason=HUMAN_HYPOTHESIS_RATIONALE,
        status_changed_by=ines.user_id,
        status_changed_at=moment,
        created_by=ines.user_id,
        created_at=moment,
        updated_at=moment,
    )
    s.db.add(human)
    s.db.flush()
    record(
        moment,
        object_type=rules.OBJECT_HYPOTHESIS,
        object_id=human.id,
        entity_type="Hypothesis",
        event_type=rules.EVENT_CREATED,
        to_value=rules.PROPOSED,
        reason=HUMAN_HYPOTHESIS_RATIONALE,
        details={"business_id": human.business_id, "statement": HUMAN_HYPOTHESIS, "origin": "HUMAN"},
        new_values={"statement": HUMAN_HYPOTHESIS, "human_status": rules.PROPOSED},
    )

    unknowns = {}
    for key, description, needed, hypothesis in (
        ("lots", UNKNOWN_LOTS, "Incoming inspection records of the cassette lots.", s.made["ai_hypothesis"]),
        ("rev1", UNKNOWN_REV1, "Rev 1 cassettes from the old tool loaded under the same bench test.", None),
    ):
        moment = s.at(30, 10 if key == "lots" else 20)
        row = Unknown(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            investigation_id=s.case.id,
            hypothesis_id=hypothesis.id if hypothesis is not None else None,
            category="evidence_gap",
            description=description,
            evidence_needed=needed,
            status=rules.UNKNOWN_OPEN,
            origin=rules.ORIGIN_HUMAN,
            created_by=ines.user_id,
            created_at=moment,
            updated_at=moment,
        )
        s.db.add(row)
        s.db.flush()
        record(
            moment,
            object_type=rules.OBJECT_UNKNOWN,
            object_id=row.id,
            entity_type="Unknown",
            event_type=rules.EVENT_CREATED,
            to_value=rules.UNKNOWN_OPEN,
            details={
                "business_id": row.business_id,
                "description": description,
                "hypothesis_business_id": hypothesis.business_id if hypothesis is not None else None,
            },
            new_values={"description": description, "category": "evidence_gap", "evidence_needed": needed},
        )
        unknowns[key] = row

    moment = s.at(29, 30)
    ai = s.made["ai_hypothesis"]
    link = HypothesisEvidence(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        hypothesis_id=ai.id,
        evidence_id=s.evidence["ACD-EV-4013"].id,
        relation_type=rules.relation_type("SUPPORTING"),
        rationale="RMA-9127 reproduced the alarm and its membrane measured above the drawing tolerance.",
        created_by_type=rules.CREATED_BY_HUMAN,
        created_by=ines.user_id,
        created_at=moment,
    )
    s.db.add(link)
    s.db.flush()
    ai.updated_at = moment
    record(
        moment,
        object_type=rules.OBJECT_HYPOTHESIS_EVIDENCE,
        object_id=link.id,
        entity_type="HypothesisEvidence",
        event_type=rules.EVENT_EVIDENCE_LINKED,
        to_value="SUPPORTING",
        reason=link.rationale,
        details={
            "business_id": ai.business_id,
            "hypothesis_id": str(ai.id),
            "evidence_id": str(link.evidence_id),
            "evidence_business_id": s.evidence["ACD-EV-4013"].business_id,
            "relation": "SUPPORTING",
        },
        new_values={"relation_type": link.relation_type, "rationale": link.rationale},
    )

    moment = s.at(28)
    links = [
        {
            "from_index": start,
            "to_index": end,
            "state": state,
            "evidence_id": s.evidence[code].id if code else None,
            "rationale": rationale,
        }
        for start, end, state, code, rationale in CHAIN_LINKS
    ]
    chain = _store_chain(
        s.db,
        tenant_id=s.tenant_id,
        case=s.case,
        person=ines,
        name=CHAIN_NAME,
        origin=rules.CHAIN_ORIGIN_HUMAN,
        labels=list(CHAIN_NODES),
        links=links,
        now=moment,
    )
    record(
        moment,
        object_type=rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=rules.EVENT_CREATED,
        to_value=rules.CHAIN_STATUS_DRAFT,
        details={
            "business_id": chain.business_id,
            "name": chain.name,
            "origin": "HUMAN",
            "nodes": len(CHAIN_NODES),
            "links": len(links),
        },
        new_values={
            "name": chain.name,
            "nodes": list(CHAIN_NODES),
            "links": [{"from_index": a, "to_index": b, "state": state} for a, b, state, *_ in CHAIN_LINKS],
        },
    )

    for index, (code, kind, statement, rationale) in enumerate(OBSERVATIONS):
        moment = s.at(27, index * 10)
        ev = s.evidence[code]
        row = EvidenceObservation(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            evidence_id=ev.id,
            statement=statement,
            observation_type=rules.HUMAN_OBSERVATION_TYPE,
            extraction_method=rules.HUMAN_EXTRACTION_METHOD,
            quality_status=rules.HUMAN_QUALITY_STATUS,
            effective_context={"rationale": rationale},
            epistemic_type=kind,
            origin=rules.OBSERVATION_ORIGIN_HUMAN,
            created_by=ines.user_id,
            investigation_id=s.case.id,
            created_at=moment,
        )
        s.db.add(row)
        s.db.flush()
        record(
            moment,
            object_type=rules.OBJECT_OBSERVATION,
            object_id=row.id,
            entity_type="EvidenceObservation",
            event_type=rules.EVENT_CREATED,
            to_value=kind,
            reason=rationale,
            details={
                "evidence_id": str(ev.id),
                "evidence_business_id": ev.business_id,
                "statement": statement,
                "epistemic_type": kind,
            },
            new_values={"statement": statement, "epistemic_type": kind},
        )
    s.db.flush()
    s.made.update(human_hypothesis=human, unknowns=unknowns, failure_chain=chain)


def judge_hypothesis(s: Story, row, status: str, reason: str, moment: datetime) -> None:
    """Ines's judgement of a hypothesis, as ``POST .../hypotheses/{id}/status`` records it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_intelligence import rules
    from backend.app.case_intelligence.router import _record

    ines = s.person("INVESTIGATOR")
    before = {
        "human_status": row.human_status,
        "status_reason": row.status_reason,
        "reviewer_disposition": row.reviewer_disposition,
    }
    row.human_status = status
    row.status_reason = reason
    row.status_changed_by = ines.user_id
    row.status_changed_at = moment
    if row.reviewer_disposition is None:
        row.reviewer_disposition = rules.HUMAN_JUDGED
    row.updated_at = moment
    _record(
        s.db,
        ctx=_ctx(),
        person=ines,
        permission=INVESTIGATION_WORK,
        case=s.case,
        object_type=rules.OBJECT_HYPOTHESIS,
        object_id=row.id,
        entity_type="Hypothesis",
        event_type=rules.EVENT_STATUS_CHANGED,
        from_value=before["human_status"],
        to_value=status,
        reason=reason,
        details={"business_id": row.business_id, "origin": rules.origin_code(row.origin), "ai_status": row.status},
        old_values=before,
        new_values={"human_status": status, "status_reason": reason, "reviewer_disposition": row.reviewer_disposition},
        now=moment,
    )
    s.db.flush()


def settle_unknown(s: Story, row, status: str, reason: str, moment: datetime) -> None:
    """Ines resolves an unknown or accepts it as a limitation, as ``POST .../unknowns/{id}/status`` records it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_intelligence import rules
    from backend.app.case_intelligence.router import _record

    if not rules.unknown_transition_allowed(row.status, status):
        raise ValueError(f"{row.business_id}: {row.status} cannot become {status}")
    ines = s.person("INVESTIGATOR")
    before = {"status": row.status, "resolution": row.resolution}
    row.status = status
    row.resolution = reason if status in rules.RESOLUTION_STATUSES else None
    row.status_changed_by = ines.user_id
    row.status_changed_at = moment
    row.updated_at = moment
    _record(
        s.db,
        ctx=_ctx(),
        person=ines,
        permission=INVESTIGATION_WORK,
        case=s.case,
        object_type=rules.OBJECT_UNKNOWN,
        object_id=row.id,
        entity_type="Unknown",
        event_type=rules.EVENT_STATUS_CHANGED,
        from_value=before["status"],
        to_value=status,
        reason=reason,
        details={"business_id": row.business_id, "previous_resolution": before["resolution"]},
        old_values=before,
        new_values={"status": row.status, "resolution": row.resolution},
        now=moment,
    )
    s.db.flush()


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
    "author_notes": "Incoming inspection data of the suspect lots is not yet in the case.",
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


# --------------------------------------------------------------------------------------------- the decision

DECISION_RATIONALE = (
    "The evidence supports a membrane above the drawing tolerance on cassettes from tool T-4 as the cause of the flow "
    "interruptions; use error is retired. Risk and regulatory reviews are complete. The Rev 1 limitation is accepted."
)
DECISION_CONDITIONS = (
    "Cassette lots C-301 to C-303 stay on hold until the corrected incoming inspection releases them, and tool T-4 "
    "cassettes are verified for flow continuity before release."
)
CAPA_TITLE = "Correct incoming inspection of cassette membranes and rework moulding tool T-4"


def sign_decision(s: Story, brief, moment: datetime):
    """Day 6: Ana signs ACCEPT_WITH_CONDITIONS on the approved brief with a CAPA_REQUIRED follow-up. The decision,
    its context snapshot, the follow-up with its task, the case and task changes and the signature are written as
    ``POST .../decision/sign`` writes them, with the signing code's own material, fingerprint, signature hash and
    snapshot hash, so verification reports VALID. No password is checked (seeding is a system action): the signature
    is audited as DEMO_SEEDED, never as CASE_DECISION_SIGNED."""
    from backend.app import governance_router as governance
    from backend.app.case_workflow import states
    from backend.app.db.models.decision_outcomes import DecisionFollowUp
    from backend.app.db.models.foundation import Decision, SignedApprovalRecord, Tenant
    from backend.app.db.models.stage3 import ContextSnapshot
    from backend.app.decision_brief import router as brief_api
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.human_decision import rules, service
    from backend.app.role_codes import role_code
    from backend.app.workflow import tasks as task_service

    case = s.case
    ana = s.person("APPROVER")
    problem = rules.brief_problem(
        status=brief.status,
        stored_hash=brief.content_hash,
        sent_hash=brief.content_hash,
        recomputed_hash=brief_rules.content_hash(brief.content, brief.narrative),
    )
    if problem:
        raise ValueError(f"The golden brief cannot be signed: {problem[1]}")
    if service.current_decision(s.db, case) is not None or not rules.state_allows(states.case_state(case), False):
        raise ValueError("The golden case is not waiting for its first decision")
    tenant = s.db.query(Tenant).filter(Tenant.id == s.tenant_id).one()
    if not governance.entitled(s.db, tenant):
        raise ValueError("The demo plan does not include controlled signatures")
    denial, signer_role = governance.approval_check(
        s.db, s.tenant_id, ana.roles or [s.user("APPROVER").role], service.approval_subject(brief), ana.user_id
    )
    if denial:
        raise ValueError(f"The demo approver may not sign: {denial[1]}")
    if rules.is_author(ana.user_id, service.brief_author_refs(s.db, brief)):
        raise ValueError("The demo approver wrote the brief")

    ines = s.user("INVESTIGATOR")
    planned = [
        {
            "action_type": "CAPA_REQUIRED",
            "title": CAPA_TITLE,
            "assignee_user_id": ines.id,
            "assigned_role": None,
            "due_at": moment + timedelta(days=rules.FOLLOW_UP_DUE_DAYS),
        }
    ]
    user_id = ana.user_id
    role = role_code(signer_role)[:60] or None
    decision_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    content = brief.content or {}
    residual = rules.residual_unknowns(content)
    evidence_hash = rules.evidence_set_hash(content)
    follow_up_actions = brief_rules.jsonable(planned)
    reviews = service.reviewers(s.db, s.db, brief)
    snapshot = brief_rules.jsonable(
        {
            "decision_id": decision_id,
            "brief": {
                "id": brief.id,
                "business_id": brief.business_id,
                "version": brief.version,
                "content_hash": brief.content_hash,
            },
            "content": content,
            "narrative": brief.narrative or {},
            "readiness": brief.readiness or {},
            "evidence_set_hash": evidence_hash,
            "scope_version": brief.scope_version,
            "reviews": reviews,
            "as_of": (content.get("context") or {}).get("as_of"),
            "decided_at": moment,
            "signer": {"id": user_id, "role": role},
            "outcome": rules.ACCEPT_WITH_CONDITIONS,
        }
    )
    snapshot_digest = rules.snapshot_hash(snapshot)
    decision = Decision(
        id=decision_id,
        tenant_id=s.tenant_id,
        investigation_id=case.id,
        decision_identifier=service.next_identifier(s.db, case),
        decision_type=rules.DECISION_TYPE,
        disposition=rules.ACCEPT_WITH_CONDITIONS,
        rationale=DECISION_RATIONALE,
        product_id=case.product_id,
        decision_status=rules.SIGNED,
        human_decision=rules.outcome_label(rules.ACCEPT_WITH_CONDITIONS),
        context_snapshot={"snapshot_id": str(snapshot_id), "snapshot_hash": snapshot_digest},
        updated_at=moment,
        decision_timestamp=moment,
        authorized_by_ref=user_id,
        created_at=moment,
        decision_kind=rules.DECISION_KIND,
        brief_version_id=brief.id,
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        conditions=DECISION_CONDITIONS,
        follow_up_actions=follow_up_actions,
        residual_unknowns=brief_rules.jsonable(residual),
        decided_by_user_id=ana.user_uuid,
        decided_under_role=role,
        approval_authority_id=service.authority_id(s.db, s.tenant_id, signer_role),
        decided_at=moment,
        brief_content_hash=brief.content_hash,
        evidence_set_hash=evidence_hash,
        context_snapshot_id=snapshot_id,
        ai_execution_refs=rules.ai_execution_refs(content),
        supersedes_decision_id=None,
    )
    s.db.add(decision)
    s.db.flush()
    s.db.add(
        ContextSnapshot(
            id=snapshot_id,
            tenant_id=s.tenant_id,
            decision_id=decision_id,
            decision_version=brief.content_hash,
            snapshot=snapshot,
            created_by=user_id,
            created_at=moment,
        )
    )
    s.db.flush()
    follow_ups = []
    for item in planned:
        follow_up = DecisionFollowUp(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            decision_id=decision_id,
            investigation_id=case.id,
            action_type=item["action_type"],
            title=item["title"],
            assignee_user_id=item["assignee_user_id"],
            assigned_role=item["assigned_role"],
            due_at=item["due_at"],
            status="OPEN",
            created_by=user_id,
            created_at=moment,
            updated_at=moment,
        )
        s.db.add(follow_up)
        s.db.flush()
        task = task_service.create_task(
            s.db,
            s.tenant_id,
            task_type="FOLLOW_UP",
            title=item["title"],
            source_type=service.FOLLOW_UP_SOURCE,
            source_id=follow_up.id,
            investigation_id=case.id,
            assigned_user_id=item["assignee_user_id"],
            assigned_role=item["assigned_role"],
            priority=states.normalize_priority(case.priority),
            due_at=item["due_at"],
            created_by=user_id,
            actor_role=role,
            details={
                "follow_up_id": str(follow_up.id),
                "follow_up_business_id": follow_up.business_id,
                "action_type": item["action_type"],
                "decision_id": str(decision_id),
                "decision_business_id": decision.business_id,
            },
        )
        follow_up.task_id = task.id
        follow_ups.append(follow_up)
    brief_api._move_case(
        s.db,
        _ctx(ana),
        case,
        rules.case_state_after(rules.ACCEPT_WITH_CONDITIONS),
        f"Decision on brief version {brief.version}: {rules.outcome_label(rules.ACCEPT_WITH_CONDITIONS).lower()}",
        moment,
        {
            "brief_version_id": str(brief.id),
            "brief_version": brief.version,
            "decision_id": str(decision_id),
            "outcome": rules.ACCEPT_WITH_CONDITIONS,
        },
    )
    task_service.complete_tasks(
        s.db,
        s.tenant_id,
        source_type=service.BRIEF_SOURCE,
        source_id=brief.id,
        task_types=["DECISION_APPROVAL"],
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        actor_ref=user_id,
        actor_role=role,
    )
    s.db.flush()

    version = brief.content_hash
    material = rules.signature_material(
        decision_id=decision_id,
        version=version,
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        remarks=DECISION_RATIONALE,
        brief_version_id=brief.id,
        evidence_set_hash=evidence_hash,
        snapshot_hash=snapshot_digest,
        conditions=DECISION_CONDITIONS,
        follow_up_actions=follow_up_actions,
    )
    content_fingerprint = rules.fingerprint(material)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        object_type="Decision",
        object_id=decision_id,
        object_version=version,
        decision_type=rules.DECISION_TYPE,
        decision=rules.SIGNATURE_CODES[rules.ACCEPT_WITH_CONDITIONS],
        remarks=DECISION_RATIONALE,
        signer_user_id=user_id,
        signer_role=signer_role,
        signature_meaning=rules.signature_meaning(brief.business_id, brief.version, rules.ACCEPT_WITH_CONDITIONS),
        content_fingerprint=content_fingerprint,
        signature_hash=rules.signature_hash(content_fingerprint, user_id, version),
        status="SIGNED",
        signed_at=moment,
        created_at=moment,
    )
    s.db.add(record)
    s.db.flush()
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=SEED_ACTOR,
            action=SEEDED_ACTION,
            entity_type="Decision",
            entity_id=decision_id,
            reason="Demo workspace golden path: a signed decision written by the seeding, no credentials checked",
            details={
                "seeded": "CASE_DECISION_SIGNED",
                # Not "credentials_…": the audit trail drops keys that look secret (enterprise_audit.SECRET_TERMS).
                "signer_reauthenticated": False,
                "signature_id": str(record.id),
                "signature_business_id": record.business_id,
                "fingerprint": content_fingerprint,
                "investigation_id": str(case.id),
                "brief_version_id": str(brief.id),
                "brief_version": brief.version,
                "brief_content_hash": version,
                "outcome": rules.ACCEPT_WITH_CONDITIONS,
                "follow_ups": rules.follow_up_types(follow_up_actions),
                "signer_user_id": user_id,
                "signer_role": role,
                "story_signed_at": moment.isoformat(),
            },
        )
    )
    s.settle(moment)
    s.made.update(decision=decision, signature=record, follow_ups=follow_ups)
    return decision


def record_decision_on_signal(s: Story, signal, decision, moment: datetime) -> None:
    """The case's signal records the signed decision (DECISION_RECORDED), as the signing hook does."""
    from backend.app.signals import service as signals

    signals.set_status(
        s.db,
        signal,
        "DECISION_RECORDED",
        "DECISION_RECORDED",
        actor_ref=s.person("APPROVER").user_id,
        actor_role=decision.decided_under_role,
        details={
            "decision_business_id": decision.business_id,
            "investigation_business_id": s.case.business_id,
            "decision_status": decision.decision_status,
        },
        now=moment,
    )
    s.settle(moment)


def open_capa(s: Story, follow_up, decision, moment: datetime):
    """Day 5: Ines opens the CAPA the follow-up asks for, as ``POST /api/v1/follow-ups/{id}/capa`` writes it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.db.models.foundation import Capa
    from backend.app.decision_followups import common
    from backend.app.decision_followups import rules as followup_rules

    ines = s.person("INVESTIGATOR")
    taken = {
        value
        for (value,) in s.db.query(Capa.capa_identifier).filter(
            Capa.tenant_id == s.tenant_id, Capa.capa_identifier.like(f"CAPA-{s.case.business_id}-%")
        )
    }
    identifier = followup_rules.capa_identifier(s.case.business_id, taken)
    due = moment + timedelta(days=60)
    capa = Capa(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        capa_identifier=identifier,
        title=CAPA_TITLE,
        action_type=followup_rules.CAPA_ACTION_TYPE,
        source_type=followup_rules.CAPA_SOURCE_TYPE,
        source_reference=decision.business_id,
        source_system=followup_rules.CAPA_SOURCE_SYSTEM,
        source_identifier=identifier,
        product_id=s.case.product_id,
        investigation_id=s.case.id,
        status=followup_rules.CAPA_STATUS,
        opened_at=moment,
        due_at=due,
        source_timestamp=moment,
        effective_timestamp=moment,
        recorded_timestamp=moment,
        ingestion_timestamp=moment,
        created_at=moment,
        updated_at=moment,
    )
    s.db.add(capa)
    s.db.flush()
    follow_up.capa_id = capa.id
    follow_up.updated_at = moment
    role = ines.role_for(INVESTIGATION_WORK)
    common.audit(
        s.db,
        tenant_id=s.tenant_id,
        actor_ref=ines.user_id,
        action="FOLLOW_UP_CAPA_CREATED",
        entity_type=followup_rules.FOLLOW_UP_ENTITY,
        entity_id=follow_up.id,
        new_values={"capa_id": str(capa.id), "capa_identifier": identifier},
        details={
            "investigation_id": str(follow_up.investigation_id),
            "decision_id": str(follow_up.decision_id),
            "action_type": follow_up.action_type,
            "actor_role": role,
            "capa_id": str(capa.id),
            "capa_identifier": identifier,
            "title": CAPA_TITLE,
            "due_at": common.iso(due),
        },
        now=moment,
    )
    s.db.flush()
    s.made["capa"] = capa
    return capa


LATE_LINK_REASON = "Field service report on the flow interruption reported after the decision was signed."


def link_late_evidence(s: Story, moment: datetime):
    """Day 1: Ines links the field service report on the late complaint to the decided case; it asks for an impact
    assessment (OPEN, with its task), as linking evidence to a decided case does. The signed decision never
    changes."""
    from backend.app.access.permissions import EVIDENCE_REVIEW
    from backend.app.db.models.foundation import InvestigationEvidence
    from backend.app.decision_followups.impact import on_late_evidence
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.evidence_workflow.inventory import review_event
    from backend.app.evidence_workflow.rules import UNREVIEWED

    ines = s.person("INVESTIGATOR")
    ev = s.evidence["ACD-EV-4017"]
    link = InvestigationEvidence(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        evidence_id=ev.id,
        relevance=LATE_LINK_REASON,
        created_at=moment,
        review_status=UNREVIEWED,
        relationship="UNRESOLVED",
        linked_by=ines.user_id,
    )
    s.db.add(link)
    s.db.flush()
    review_event(
        s.db,
        tenant_id=s.tenant_id,
        case_id=s.case.id,
        evidence_id=ev.id,
        event_type="LINKED",
        actor=ines,
        permission=EVIDENCE_REVIEW,
        to_status=UNREVIEWED,
        to_relationship="UNRESOLVED",
        reason=LATE_LINK_REASON,
        now=moment,
    )
    s.db.add(
        make_audit_event(
            tenant_id=s.tenant_id,
            actor_ref=ines.user_id,
            action="EVIDENCE_LINKED",
            entity_type="InvestigationEvidence",
            entity_id=link.id,
            reason=LATE_LINK_REASON,
            details={
                "investigation_id": str(s.case.id),
                "evidence_id": str(ev.id),
                "relationship": "UNRESOLVED",
                "actor_role": ines.role_for(EVIDENCE_REVIEW),
            },
            created_at=moment,
        )
    )
    s.db.flush()
    assessment = on_late_evidence(s.db, s.db, s.case, ev.id, trigger="EVIDENCE_LINKED", actor_ref=ines.user_id)
    if assessment is None:
        raise ValueError("The late evidence did not ask for an impact assessment")
    s.settle(moment)
    s.made["impact_assessment"] = assessment
    return assessment


# ------------------------------------------------------------------------------------------------ the whole path


def run_story(s: Story) -> dict:
    """Every step, in the order of the story (each brief is composed from what the case holds at its moment)."""
    signal = seed_signal(s)
    triage_signal(s, signal)
    open_case(s, signal)
    add_later_complaints(s, signal)
    review_case_evidence(s)
    seed_ai_hypothesis(s)
    seed_human_intelligence(s)
    rescope_case(s)
    for spec in CASE_REVIEWS:
        complete_case_review(s, spec)

    first = create_brief_version(s, 1, BRIEF_V1, s.at(24), s.at(24, 60))
    quality_review(s, first, "RETURN_FOR_EVIDENCE", RETURN_COMMENT, s.at(23))
    unknowns = s.made["unknowns"]
    answer_evidence_request(s, unknowns["lots"])
    settle_unknown(
        s,
        unknowns["lots"],
        "resolved",
        "Answered by the incoming inspection records (ACD-EV-4016): membranes above tolerance were accepted.",
        s.at(18),
    )
    judge_hypothesis(
        s,
        s.made["human_hypothesis"],
        "RETIRED",
        "Bench tests reproduce the alarm with correct loading; only the excluded report shows a closed clamp.",
        s.at(17),
    )
    judge_hypothesis(
        s,
        s.made["ai_hypothesis"],
        "PARTIALLY_SUPPORTED",
        "Supported by the change notice, the lot trend, RMA-9127 and the inspection records; DV-305 did not test "
        "T-4 cassettes and only one returned cassette reproduced the alarm.",
        s.at(17, 20),
    )
    settle_unknown(
        s,
        unknowns["rev1"],
        "accepted_limitation",
        "No Rev 1 cassettes from the old tool are left to test; the decision accepts this limitation.",
        s.at(17, 40),
    )
    second = create_brief_version(s, 2, BRIEF_V2, s.at(14), s.at(14, 60))
    quality_review(s, second, "ACCEPT_FOR_DECISION", ACCEPT_COMMENT, s.at(12))

    decision = sign_decision(s, second, s.at(6))
    record_decision_on_signal(s, signal, decision, s.at(6, 5))
    open_capa(s, s.made["follow_ups"][0], decision, s.at(5))
    link_late_evidence(s, s.at(1))
    return summary(s)


def summary(s: Story) -> dict:
    """The business ids of what the golden path made."""
    made = s.made
    return {
        "investigation": s.case.business_id,
        "investigation_identifier": s.case.investigation_identifier,
        "signal": made["signal"].business_id,
        "scope_version": made.get("scope_version"),
        "evidence_request": made["evidence_request"].business_id,
        "hypotheses": [made["ai_hypothesis"].business_id, made["human_hypothesis"].business_id],
        "unknowns": [row.business_id for row in made["unknowns"].values()],
        "failure_chain": made["failure_chain"].business_id,
        "reviews": [row.business_id for row in made.get("reviews", [])],
        "decision_briefs": [row.business_id for row in made.get("briefs", [])],
        "decision": made["decision"].business_id,
        "signature": made["signature"].business_id,
        "follow_ups": [row.business_id for row in made["follow_ups"]],
        "capa": made["capa"].capa_identifier,
        "impact_assessment": made["impact_assessment"].business_id,
    }


def _already_seeded(db: Session, tenant_id) -> bool:
    """True when the golden case was already opened from a signal (the path is written in one transaction)."""
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.models.signals import InvestigationSignal

    return (
        db.query(InvestigationSignal.id)
        .join(
            Investigation,
            (Investigation.tenant_id == InvestigationSignal.tenant_id)
            & (Investigation.id == InvestigationSignal.investigation_id),
        )
        .filter(
            InvestigationSignal.tenant_id == tenant_id,
            Investigation.investigation_identifier == story.GOLDEN_CASE,
        )
        .first()
        is not None
    )


def seed_golden_path(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Write the golden path into the demo workspace (``now``: the story's today, the day the story was loaded; read
    back from the golden case when not given), in a session of its own bound to the demo tenant (same database), in one transaction. Idempotent. Never raises:
    ``{"seeded": False, "reason": ...}`` when it was already there, cannot be written here, or failed (logged)."""
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.enterprise_audit import make_audit_event

    try:
        with Session(bind=db.get_bind()) as session:
            bind_tenant(session, tenant_id)
            if _already_seeded(session, tenant_id):
                return {"seeded": False, "reason": "The golden path is already in the workspace"}
            story_state = _context(session, tenant_id, now)
            made = run_story(story_state)
            session.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref=SEED_ACTOR,
                    action=SEEDED_ACTION,
                    entity_type="Investigation",
                    entity_id=story_state.case.id,
                    reason="Demo workspace golden path written (synthetic records, dated relative to today)",
                    details={"golden_path": made},
                )
            )
            session.commit()
            return {"seeded": True, **made}
    except GoldenPathSkipped as exc:
        logger.warning("The demo workspace's golden path was not written: %s", exc)
        return {"seeded": False, "reason": str(exc)}
    except Exception:
        logger.exception("The demo workspace's golden path was not written")
        return {"seeded": False, "reason": "Writing the golden path failed; see the log"}


# ---------------------------------------------------------------------------------------------------- status

LIVE_CASE = "ACD-INV-101"


def _status_of(db: Session, tenant_id) -> dict:
    from backend.app.case_workflow import states
    from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
    from backend.app.db.models.foundation import Capa, Investigation
    from backend.app.db.models.reviews import CaseReview, DecisionBriefVersion
    from backend.app.db.models.signals import InvestigationSignal, Signal
    from backend.app.human_decision import service

    cases = {
        row.investigation_identifier: row
        for row in db.query(Investigation).filter(
            Investigation.tenant_id == tenant_id,
            Investigation.investigation_identifier.in_([story.GOLDEN_CASE, LIVE_CASE]),
        )
    }
    waiting = [
        row.business_id
        for row in db.query(Signal)
        .filter(Signal.tenant_id == tenant_id, Signal.status == "NEW")
        .order_by(Signal.business_id)
    ]
    live = cases.get(LIVE_CASE)
    result = {
        "seeded": False,
        "live_case": (
            {"business_id": live.business_id, "identifier": LIVE_CASE, "workflow_state": states.case_state(live)}
            if live is not None
            else None
        ),
        "signals_awaiting_triage": waiting,
    }
    case = cases.get(story.GOLDEN_CASE)
    if case is None:
        return result

    def of_case(model, *order):
        return db.query(model).filter(model.tenant_id == tenant_id, model.investigation_id == case.id).order_by(*order)

    signals = [
        {"business_id": row.business_id, "status": row.status}
        for row in db.query(Signal)
        .join(
            InvestigationSignal,
            (InvestigationSignal.tenant_id == Signal.tenant_id) & (InvestigationSignal.signal_id == Signal.id),
        )
        .filter(InvestigationSignal.tenant_id == tenant_id, InvestigationSignal.investigation_id == case.id)
        .order_by(Signal.business_id)
    ]
    decision = service.current_decision(db, case)
    record = service.signature_record(db, decision) if decision is not None else None
    result.update(
        seeded=bool(signals) and decision is not None,
        investigation={
            "business_id": case.business_id,
            "identifier": case.investigation_identifier,
            "workflow_state": states.case_state(case),
        },
        signals=signals,
        decision_briefs=[
            {"business_id": row.business_id, "version": row.version, "status": row.status}
            for row in of_case(DecisionBriefVersion, DecisionBriefVersion.version)
        ],
        reviews=[
            {"business_id": row.business_id, "type": row.review_type, "outcome": row.outcome}
            for row in of_case(CaseReview, CaseReview.created_at)
        ],
        decision=(
            {
                "business_id": decision.business_id,
                "identifier": decision.decision_identifier,
                "outcome": decision.outcome,
                "signature": record.business_id if record is not None else None,
                "verification": service.verify_signature(db, record, decision)["status"],
            }
            if decision is not None
            else None
        ),
        follow_ups=[
            {"business_id": row.business_id, "action_type": row.action_type, "status": row.status}
            for row in of_case(DecisionFollowUp, DecisionFollowUp.business_id)
        ],
        capas=[row.capa_identifier for row in of_case(Capa, Capa.capa_identifier)],
        impact_assessments=[
            {"business_id": row.business_id, "status": row.status}
            for row in of_case(ImpactAssessment, ImpactAssessment.business_id)
        ],
    )
    return result


def golden_path_status(db: Session, tenant_id) -> dict:
    """What the demo shows on the golden path, by business id (case, signal, briefs, reviews, the signed decision
    with its verification, follow-ups, CAPA, impact assessments), the case left mid-investigation for live demos and
    the signals awaiting triage. Read in a session bound to the demo tenant; never raises."""
    from backend.app.db.tenant_scope import bind_tenant

    try:
        with Session(bind=db.get_bind()) as session:
            bind_tenant(session, tenant_id)
            return _status_of(session, tenant_id)
    except Exception:
        logger.exception("The demo workspace's golden path could not be read")
        return {"seeded": False, "error": "The golden path could not be read; see the log"}
