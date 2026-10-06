"""Readers of the case trust and audit views. Each reader turns one history source of a case into timeline items
(``rules.item``); ``timeline`` merges them with the audit events about the case. ``replay``, ``ai_runs`` and
``integrity`` read the case as it was known at a moment, its AI runs and the verification of what was signed.

``db`` is the tenant data plane (the case and its records), ``control_db`` the control database (people, signatures
and the control-plane audit trail); on the shared plane both are the same session. Nothing here writes.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import ExitStack
from datetime import datetime
from typing import Any

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from backend.app.case_audit import rules
from backend.app.db.models.case_scope import EvidenceReviewEvent, InvestigationScopeVersion
from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
from backend.app.db.models.foundation import (
    AIExecution,
    AuditEvent,
    Complaint,
    Decision,
    Evidence,
    HumanReview,
    Hypothesis,
    Investigation,
    InvestigationBrief,
    InvestigationComplaint,
    InvestigationEvidence,
    SignedApprovalRecord,
    Unknown,
)
from backend.app.db.models.intelligence import IntelligenceEvent
from backend.app.db.models.reviews import BriefReviewAction, CaseReview, DecisionBriefVersion
from backend.app.db.models.signals import InvestigationSignal, Signal, SignalEvent
from backend.app.db.models.stage3 import AIInteraction, SupplierEvidenceRequest
from backend.app.db.models.workflow import WorkflowTask, WorkflowTaskEvent

logger = logging.getLogger("mdarix.case_audit")

# Rows read from each history source of one case, and audit events read from each plane.
SOURCE_LIMIT = 2000
AUDIT_LIMIT = 2000
RELATED_IDS_MAX = 5000
# The audit chain is recomputed only for organizations with at most this many audit events per plane.
CHAIN_CHECK_MAX_EVENTS = 50000
BRIEF_KIND = "BRIEF"
SIGNED = "SIGNED"


def _role_label(code: str | None) -> str | None:
    from backend.app.workflow.labels import role_label

    return role_label(code)


class Gathered:
    """What the readers of one case found: the timeline items, the records' business ids by id (to name the
    record of an audit event), and every id related to the case (to find its audit events)."""

    def __init__(self, db: Session, control_db: Session | None, case: Investigation):
        self.db = db
        self.control_db = control_db
        self.case = case
        self.tenant_id = case.tenant_id
        self.items: list[dict] = []
        self.known: dict[str, tuple[str, str | None]] = {}
        self.truncated: set[str] = set()
        self.remember("Investigation", case.id, case.business_id)

    def remember(self, kind: str, row_id: Any, business_id: str | None) -> dict:
        key = rules.as_uuid_text(row_id)
        if key is not None:
            self.known[key] = (kind, business_id)
        return rules.object_ref(kind, row_id, business_id)

    def add(self, *, actor_ref: Any = None, actor_role: str | None = None, **values) -> dict:
        entry = rules.item(**values)
        entry["_actor"] = (actor_ref, actor_role)
        self.items.append(entry)
        return entry

    def rows(self, name: str, query) -> list:
        found = query.limit(SOURCE_LIMIT + 1).all()
        if len(found) > SOURCE_LIMIT:
            self.truncated.add(name)
            found = found[:SOURCE_LIMIT]
        return found


def _business_ids(db: Session, model, tenant_id, ids) -> dict[str, str | None]:
    wanted = [key for key in {rules.as_uuid_text(value) for value in ids} if key]
    if not wanted:
        return {}
    return {
        str(row_id): business_id
        for row_id, business_id in db.query(model.id, model.business_id).filter(
            model.tenant_id == tenant_id, model.id.in_([uuid.UUID(key) for key in wanted])
        )
    }


# ---------------------------------------------------------------------------------------------- the readers


def read_signals(found: Gathered) -> None:
    from backend.app.signals.labels import EVENT_LABELS, STATUS_LABELS
    from backend.app.signals.service import AUDIT_ACTIONS

    db, case = found.db, found.case
    links = found.rows(
        "signals",
        db.query(InvestigationSignal).filter(
            InvestigationSignal.tenant_id == case.tenant_id, InvestigationSignal.investigation_id == case.id
        ),
    )
    if not links:
        return
    signals = {
        row.id: row
        for row in db.query(Signal).filter(
            Signal.tenant_id == case.tenant_id, Signal.id.in_([link.signal_id for link in links])
        )
    }
    for link in links:
        signal = signals.get(link.signal_id)
        ref = found.remember("Signal", link.signal_id, signal.business_id if signal else None)
        found.add(
            at=link.created_at,
            category="SIGNAL",
            event="SIGNAL_LINKED_TO_CASE",
            title=rules.title("Signal linked to the case", signal.title if signal else None),
            obj=ref,
            origin=rules.origin_of(link.created_by),
            actor_ref=link.created_by,
            match=(link.signal_id,),
        )
    events = found.rows(
        "signal events",
        db.query(SignalEvent)
        .filter(SignalEvent.tenant_id == case.tenant_id, SignalEvent.signal_id.in_(list(signals)))
        .order_by(SignalEvent.created_at),
    )
    for event in events:
        signal = signals.get(event.signal_id)
        label = EVENT_LABELS.get(event.event_type) or rules.readable(event.event_type)
        status = STATUS_LABELS.get(event.to_status or "", event.to_status) if event.to_status else None
        found.add(
            at=event.created_at,
            category="SIGNAL",
            event=AUDIT_ACTIONS.get(event.event_type, f"SIGNAL_{event.event_type}"),
            title=rules.title(f"Signal {signal.business_id if signal else ''}: {label}".replace("  ", " "), status),
            obj=rules.object_ref("Signal", event.signal_id, signal.business_id if signal else None),
            reason=event.reason,
            details={
                "from_status": event.from_status,
                "to_status": event.to_status,
                **rules.safe_details(event.details),
            },
            origin=rules.origin_of(event.actor_ref),
            actor_ref=event.actor_ref,
            actor_role=event.actor_role,
            match=(event.signal_id,),
        )


def read_scope(found: Gathered) -> None:
    db, case = found.db, found.case
    rows = found.rows(
        "scope",
        db.query(InvestigationScopeVersion)
        .filter(
            InvestigationScopeVersion.tenant_id == case.tenant_id,
            InvestigationScopeVersion.investigation_id == case.id,
        )
        .order_by(InvestigationScopeVersion.version),
    )
    for row in rows:
        first = row.version == 1
        found.add(
            at=row.created_at,
            category="SCOPE",
            event="INVESTIGATION_SCOPE_DEFINED" if first else "INVESTIGATION_SCOPE_CHANGED",
            title=f"Scope defined (version {row.version})" if first else f"Scope changed to version {row.version}",
            obj=rules.object_ref("InvestigationScope", case.id, f"{case.business_id} scope v{row.version}"),
            reason=row.change_reason,
            details={
                "version": row.version,
                "included_complaints": len(row.included_complaint_ids or []),
                "excluded_complaints": len(row.excluded_complaints or []),
                "reviews_must_restart": bool(row.reviews_must_restart),
                "conclusions_invalidated": bool(row.conclusions_invalidated),
            },
            origin=rules.origin_of(row.created_by),
            actor_ref=row.created_by,
            actor_role=row.created_role,
            match=(case.id, row.id),
        )


def read_tasks(found: Gathered) -> None:
    from backend.app.workflow.labels import task_type_label

    db, case = found.db, found.case
    tasks = {
        row.id: row
        for row in found.rows(
            "tasks",
            db.query(WorkflowTask).filter(
                WorkflowTask.tenant_id == case.tenant_id, WorkflowTask.investigation_id == case.id
            ),
        )
    }
    for task in tasks.values():
        found.remember("WorkflowTask", task.id, task.business_id)
    if not tasks:
        return
    events = found.rows(
        "task events",
        db.query(WorkflowTaskEvent)
        .filter(WorkflowTaskEvent.tenant_id == case.tenant_id, WorkflowTaskEvent.task_id.in_(list(tasks)))
        .order_by(WorkflowTaskEvent.created_at),
    )
    for event in events:
        task = tasks.get(event.task_id)
        kind = task_type_label(task.task_type) if task else None
        found.add(
            at=event.created_at,
            category="TASK",
            event=f"TASK_{event.event_type}",
            title=rules.title(f"{kind or 'Task'} task {rules.readable(event.event_type).lower()}", task.title)
            if task
            else f"Task {rules.readable(event.event_type).lower()}",
            obj=rules.object_ref("WorkflowTask", event.task_id, task.business_id if task else None),
            reason=event.reason,
            details={
                "task_type": task.task_type if task else None,
                "from_status": event.from_status,
                "to_status": event.to_status,
                **rules.safe_details(event.details, ("outcome", "follow_up_business_id", "decision_business_id")),
            },
            origin=rules.origin_of(event.actor_ref),
            actor_ref=event.actor_ref,
            actor_role=event.actor_role,
            match=(event.task_id,),
        )


def _case_evidence(db: Session, case: Investigation) -> tuple[dict, dict]:
    """``(links by evidence id, evidence rows by id)`` of the case: its links and evidence recorded on it."""
    links = {
        link.evidence_id: link
        for link in db.query(InvestigationEvidence)
        .filter(InvestigationEvidence.tenant_id == case.tenant_id, InvestigationEvidence.investigation_id == case.id)
        .limit(SOURCE_LIMIT)
    }
    direct = [
        row_id
        for (row_id,) in db.query(Evidence.id)
        .filter(Evidence.tenant_id == case.tenant_id, Evidence.investigation_id == case.id)
        .limit(SOURCE_LIMIT)
    ]
    ids = set(links) | set(direct)
    rows = (
        {
            row.id: row
            for row in db.query(Evidence).filter(Evidence.tenant_id == case.tenant_id, Evidence.id.in_(list(ids)))
        }
        if ids
        else {}
    )
    return links, rows


def read_evidence(found: Gathered) -> None:
    from backend.app.evidence_workflow.rules import relationship_label, review_status_label

    db, case = found.db, found.case
    links, evidence = _case_evidence(db, case)
    for row in evidence.values():
        found.remember("Evidence", row.id, row.business_id)
    for link in links.values():
        row = evidence.get(link.evidence_id)
        found.remember("InvestigationEvidence", link.id, row.business_id if row else None)
    events = found.rows(
        "evidence reviews",
        db.query(EvidenceReviewEvent)
        .filter(EvidenceReviewEvent.tenant_id == case.tenant_id, EvidenceReviewEvent.investigation_id == case.id)
        .order_by(EvidenceReviewEvent.created_at),
    )
    linked = set()
    for event in events:
        row = evidence.get(event.evidence_id)
        link = links.get(event.evidence_id)
        name = row.title if row else None
        if event.event_type == "LINKED":
            linked.add(event.evidence_id)
            label = rules.title("Evidence linked", name)
        else:
            judged = ", ".join(
                part
                for part in (review_status_label(event.to_review_status), relationship_label(event.to_relationship))
                if part
            )
            label = rules.title(f"Evidence reviewed ({judged})" if judged else "Evidence reviewed", name)
        found.add(
            at=event.created_at,
            category="EVIDENCE",
            event=f"EVIDENCE_{event.event_type}",
            title=label,
            obj=rules.object_ref("Evidence", event.evidence_id, row.business_id if row else None),
            reason=event.reason,
            details={
                "from_review_status": event.from_review_status,
                "to_review_status": event.to_review_status,
                "from_relationship": event.from_relationship,
                "to_relationship": event.to_relationship,
            },
            origin=rules.origin_of(event.actor_ref),
            actor_ref=event.actor_ref,
            actor_role=event.actor_role,
            match=(event.evidence_id, link.id if link else None),
        )
    # Evidence that reached the case without a recorded link (recorded on the case by an import or a request).
    for row in evidence.values():
        if row.id in linked:
            continue
        link = links.get(row.id)
        found.add(
            at=rules.known_at(
                (row.ingestion_timestamp, row.recorded_timestamp, row.created_at), link.created_at if link else None
            ),
            category="EVIDENCE",
            event="EVIDENCE_RECORDED" if link is None else "EVIDENCE_LINKED",
            title=rules.title("Evidence received" if link is None else "Evidence linked", row.title),
            obj=rules.object_ref("Evidence", row.id, row.business_id),
            details={"evidence_type": row.evidence_type, "source_system": row.source_system},
            origin=rules.origin_of(link.linked_by if link else None),
            actor_ref=link.linked_by if link else None,
            match=(row.id, link.id if link else None),
        )


def read_requests(found: Gathered) -> None:
    db, case = found.db, found.case
    rows = found.rows(
        "requests",
        db.query(SupplierEvidenceRequest)
        .filter(
            SupplierEvidenceRequest.tenant_id == case.tenant_id, SupplierEvidenceRequest.investigation_id == case.id
        )
        .order_by(SupplierEvidenceRequest.created_at),
    )
    for row in rows:
        ref = found.remember("EvidenceRequest", row.id, row.business_id)
        supplier = str(row.request_kind or "").upper() == "SUPPLIER"
        found.add(
            at=row.created_at,
            category="REQUEST",
            event="EVIDENCE_REQUESTED",
            title=rules.title("Evidence requested from a supplier" if supplier else "Evidence requested", row.title),
            obj=ref,
            details={"request_kind": row.request_kind, "priority": row.priority, "status_now": row.status},
            origin=rules.origin_of(row.requested_by),
            actor_ref=row.requested_by,
            match=(row.id,),
        )


def read_intelligence(found: Gathered) -> None:
    from backend.app.case_intelligence.rules import OBJECT_LABELS, event_label

    db, case = found.db, found.case
    events = found.rows(
        "intelligence",
        db.query(IntelligenceEvent)
        .filter(IntelligenceEvent.tenant_id == case.tenant_id, IntelligenceEvent.investigation_id == case.id)
        .order_by(IntelligenceEvent.created_at),
    )
    for event in events:
        details = event.details if isinstance(event.details, dict) else {}
        business_id = details.get("business_id")
        kind = OBJECT_LABELS.get(event.object_type, rules.readable(event.object_type))
        found.remember(str(event.object_type or "Intelligence").title().replace("_", ""), event.object_id, business_id)
        change = f"{event.from_value or '—'} → {event.to_value}" if event.to_value else None
        found.add(
            at=event.created_at,
            category="INTELLIGENCE",
            event=f"INTELLIGENCE_{event.event_type}",
            title=rules.title(f"{kind}: {(event_label(event.event_type) or '').lower()}", change),
            obj=rules.object_ref(event.object_type, event.object_id, business_id),
            reason=event.reason,
            details={"from_value": event.from_value, "to_value": event.to_value},
            origin=rules.origin_of(event.actor_ref),
            actor_ref=event.actor_ref,
            actor_role=event.actor_role,
            match=(event.object_id,),
        )


def read_ai(found: Gathered) -> None:
    db, case = found.db, found.case
    runs = found.rows(
        "ai runs",
        db.query(AIExecution)
        .filter(AIExecution.tenant_id == case.tenant_id, AIExecution.investigation_id == case.id)
        .order_by(AIExecution.execution_timestamp),
    )
    for run in runs:
        ref = found.remember("AIExecution", run.id, run.business_id)
        kind = rules.ai_kind(run.provider, run.model_name, run.prompt_template_version)
        person = rules.as_uuid_text(run.requestor_ref)
        found.add(
            at=run.execution_timestamp,
            category="AI",
            event="AI_RUN_RECORDED",
            aliases=("DECISION_ADVISORY_CREATED",),
            title=rules.title(
                f"AI run ({rules.readable(kind).lower()})", f"{run.model_name} {run.model_version or ''}".strip()
            ),
            obj=ref,
            details={
                "kind": kind,
                "provider": run.provider,
                "model": run.model_name,
                "model_version": run.model_version,
                "prompt_template_version": run.prompt_template_version,
                "orchestration_version": run.orchestration_version,
                "status": rules.run_status(run.validation_status, run.error_state),
            },
            origin=rules.AI,
            actor_ref=run.requestor_ref if person else None,
            match=(run.id, case.id),
        )
    reviews = found.rows(
        "human reviews",
        db.query(HumanReview)
        .filter(HumanReview.tenant_id == case.tenant_id, HumanReview.investigation_id == case.id)
        .order_by(HumanReview.review_timestamp),
    )
    for review in reviews:
        on_ai = review.ai_execution_id is not None
        found.add(
            at=review.review_timestamp,
            category="AI" if on_ai else "DECISION",
            event="AI_OUTPUT_REVIEWED" if on_ai else "DECISION_REVIEWED",
            aliases=("DECISION_REVIEWED",),
            title=rules.title(
                "AI output reviewed" if on_ai else "Decision reviewed", rules.readable(review.disposition)
            ),
            obj=rules.object_ref(
                "AIExecution" if on_ai else "Decision",
                review.ai_execution_id or review.decision_id,
                found.known.get(str(review.ai_execution_id or review.decision_id), (None, None))[1],
            ),
            reason=review.comments,
            details={"disposition": review.disposition},
            origin=rules.HUMAN,
            actor_ref=review.reviewer_ref,
            match=(review.decision_id, review.ai_execution_id),
        )
    asks = found.rows(
        "ask",
        db.query(AIInteraction)
        .filter(AIInteraction.tenant_id == case.tenant_id, AIInteraction.investigation_id == case.id)
        .order_by(AIInteraction.created_at),
    )
    for ask in asks:
        provenance = ask.provenance if isinstance(ask.provenance, dict) else {}
        found.add(
            at=ask.created_at,
            category="AI",
            event="ASK_ANSWERED",
            aliases=("GENAI_EXECUTION_RECORDED",),
            title=rules.title("Ask MDARIX answered a question", provenance.get("model")),
            obj=rules.object_ref("AIInteraction", ask.id),
            details={
                "intent": ask.normalized_intent,
                "provider": provenance.get("provider"),
                "model": provenance.get("model"),
                "temporal_mode": ask.temporal_mode,
            },
            origin=rules.AI,
            actor_ref=ask.user_id,
            match=(ask.id,),
        )
    briefs = found.rows(
        "ai briefs",
        db.query(InvestigationBrief)
        .filter(InvestigationBrief.tenant_id == case.tenant_id, InvestigationBrief.investigation_id == case.id)
        .order_by(InvestigationBrief.brief_version),
    )
    for brief in briefs:
        ref = found.remember("InvestigationBrief", brief.id, brief.business_id)
        found.add(
            at=brief.created_at,
            category="AI",
            event="BRIEF_GENERATED" if brief.brief_version == 1 else "BRIEF_REGENERATED",
            title=f"AI investigation brief version {brief.brief_version} generated",
            obj=ref,
            details={"version": brief.brief_version, "human_review_state": brief.human_review_state},
            origin=rules.AI,
            actor_ref=brief.generated_by if rules.as_uuid_text(brief.generated_by) else None,
            match=(brief.id,),
        )


def read_reviews(found: Gathered) -> None:
    from backend.app.case_reviews import rules as review_rules

    db, case = found.db, found.case
    rows = found.rows(
        "reviews",
        db.query(CaseReview)
        .filter(CaseReview.tenant_id == case.tenant_id, CaseReview.investigation_id == case.id)
        .order_by(CaseReview.created_at),
    )
    for row in rows:
        ref = found.remember("CaseReview", row.id, row.business_id)
        kind = review_rules.type_label(row.review_type) or "Review"
        found.add(
            at=row.created_at,
            category="REVIEW",
            event="CASE_REVIEW_REQUESTED",
            title=f"{kind} requested" + (" (required by policy)" if row.required_by_policy else ""),
            obj=ref,
            reason=row.request_reason,
            details={"review_type": row.review_type, "scope_version": row.scope_version},
            origin=rules.origin_of(row.requested_by),
            actor_ref=row.requested_by,
            actor_role=row.requested_role,
            match=(row.id,),
        )
        if row.completed_at is not None:
            found.add(
                at=row.completed_at,
                category="REVIEW",
                event="CASE_REVIEW_COMPLETED",
                title=rules.title(f"{kind} completed", review_rules.outcome_label(row.outcome)),
                obj=ref,
                reason=row.rationale,
                details={"review_type": row.review_type, "outcome": row.outcome, "scope_version": row.scope_version},
                origin=rules.HUMAN,
                actor_ref=row.reviewer_user_id,
                actor_role=row.reviewer_role,
                match=(row.id,),
            )
        if row.status in ("CANCELLED", "SUPERSEDED"):
            found.add(
                at=row.updated_at,
                category="REVIEW",
                event=f"CASE_REVIEW_{row.status}",
                title=f"{kind} {row.status.lower()}",
                obj=ref,
                reason=row.superseded_reason,
                details={"review_type": row.review_type},
                origin=rules.SYSTEM if row.status == "SUPERSEDED" else rules.HUMAN,
                match=(row.id,),
            )


def read_briefs(found: Gathered) -> None:
    from backend.app.decision_brief import rules as brief_rules

    db, case = found.db, found.case
    rows = found.rows(
        "briefs",
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version),
    )
    versions = {}
    for row in rows:
        versions[row.id] = row
        ref = found.remember("DecisionBriefVersion", row.id, row.business_id)
        found.add(
            at=row.created_at,
            category="BRIEF",
            event="BRIEF_CREATED",
            title=f"Decision brief version {row.version} started",
            obj=ref,
            details={"version": row.version, "status_now": row.status},
            origin=rules.origin_of(row.created_by),
            actor_ref=row.created_by,
            actor_role=row.created_role,
            match=(row.id,),
        )
        if row.submitted_at is not None:
            found.add(
                at=row.submitted_at,
                category="BRIEF",
                event="BRIEF_SUBMITTED",
                aliases=("BRIEF_RESUBMITTED",),
                title=f"Decision brief version {row.version} submitted for quality review",
                obj=ref,
                details={"version": row.version},
                origin=rules.origin_of(row.submitted_by),
                actor_ref=row.submitted_by,
                match=(row.id,),
            )
    if not versions:
        return
    actions = found.rows(
        "brief reviews",
        db.query(BriefReviewAction)
        .filter(BriefReviewAction.tenant_id == case.tenant_id, BriefReviewAction.brief_version_id.in_(list(versions)))
        .order_by(BriefReviewAction.created_at),
    )
    for action in actions:
        row = versions.get(action.brief_version_id)
        found.add(
            at=action.created_at,
            category="BRIEF",
            event=f"BRIEF_{action.action}",
            title=f"Decision brief version {row.version if row else '?'}: "
            f"{(brief_rules.action_label(action.action) or '').lower()}",
            obj=rules.object_ref("DecisionBriefVersion", action.brief_version_id, row.business_id if row else None),
            reason=action.comment,
            details={"action": action.action, "version": row.version if row else None},
            origin=rules.HUMAN,
            actor_ref=action.actor_ref,
            actor_role=action.actor_role,
            match=(action.brief_version_id,),
        )


def case_decisions(db: Session, case: Investigation) -> list[Decision]:
    return (
        db.query(Decision)
        .filter(Decision.tenant_id == case.tenant_id, Decision.investigation_id == case.id)
        .order_by(Decision.created_at)
        .limit(SOURCE_LIMIT)
        .all()
    )


def signature_records(control_db: Session | None, tenant_id, decision_ids) -> list[SignedApprovalRecord]:
    ids = [value for value in decision_ids if value is not None]
    if control_db is None or not ids:
        return []
    return (
        control_db.query(SignedApprovalRecord)
        .filter(
            SignedApprovalRecord.tenant_id == tenant_id,
            SignedApprovalRecord.object_type == "Decision",
            SignedApprovalRecord.object_id.in_(ids),
        )
        .order_by(SignedApprovalRecord.signed_at)
        .limit(SOURCE_LIMIT)
        .all()
    )


def read_decisions(found: Gathered) -> None:
    from backend.app.human_decision import rules as decision_rules

    db, case = found.db, found.case
    decisions = case_decisions(db, case)
    by_id = {}
    for decision in decisions:
        by_id[decision.id] = decision
        ref = found.remember("Decision", decision.id, decision.business_id)
        if decision.decision_kind == BRIEF_KIND:
            found.add(
                at=decision.decided_at or decision.created_at,
                category="DECISION",
                event="CASE_DECISION_SIGNED",
                title=rules.title("Decision signed", decision_rules.outcome_label(decision.outcome)),
                obj=ref,
                reason=decision.rationale,
                details={
                    "outcome": decision.outcome,
                    "follow_ups": len(decision.follow_up_actions or []),
                    "conditions": bool(decision.conditions),
                    "ai_runs_disclosed": len(decision.ai_execution_refs or []),
                },
                origin=rules.HUMAN,
                actor_ref=decision.decided_by_user_id or decision.authorized_by_ref,
                actor_role=decision.decided_under_role,
                match=(decision.id,),
            )
        else:
            found.add(
                at=decision.created_at,
                category="DECISION",
                event="DECISION_CREATED",
                title=rules.title("Decision recorded", rules.readable(decision.disposition)),
                obj=ref,
                reason=decision.rationale,
                details={"disposition": decision.disposition, "status_now": decision.decision_status},
                origin=rules.origin_of(decision.authorized_by_ref),
                actor_ref=decision.authorized_by_ref,
                match=(decision.id,),
            )
        if decision.superseded_at is not None:
            found.add(
                at=decision.superseded_at,
                category="DECISION",
                event="CASE_DECISION_SUPERSEDED",
                title="Decision superseded by a new decision",
                obj=ref,
                reason=decision.supersede_reason,
                details={},
                origin=rules.HUMAN,
                match=(decision.id,),
            )
    for record in signature_records(found.control_db, case.tenant_id, list(by_id)):
        decision = by_id.get(record.object_id)
        ref = found.remember("SignedApprovalRecord", record.id, record.business_id)
        found.add(
            at=record.signed_at,
            category="SIGNATURE",
            event="SIGNATURE_RECORDED",
            title=rules.title("Electronic signature applied", record.signature_meaning),
            obj=ref,
            details={
                "decision": record.decision,
                "decision_business_id": decision.business_id if decision else None,
                "status": record.status,
            },
            origin=rules.HUMAN,
            actor_ref=record.signer_user_id,
            actor_role=record.signer_role,
            match=(record.id, record.object_id),
        )
        if record.invalidated_at is not None:
            found.add(
                at=record.invalidated_at,
                category="SIGNATURE",
                event="SIGNATURE_INVALIDATED",
                title="Electronic signature invalidated",
                obj=ref,
                reason=record.invalidation_reason,
                details={"decision_business_id": decision.business_id if decision else None},
                origin=rules.SYSTEM,
                match=(record.id,),
            )


def read_follow_ups(found: Gathered) -> None:
    from backend.app.decision_followups import rules as follow_rules

    db, case = found.db, found.case
    rows = found.rows(
        "follow-ups",
        db.query(DecisionFollowUp)
        .filter(DecisionFollowUp.tenant_id == case.tenant_id, DecisionFollowUp.investigation_id == case.id)
        .order_by(DecisionFollowUp.created_at),
    )
    for row in rows:
        ref = found.remember("DecisionFollowUp", row.id, row.business_id)
        label = follow_rules.action_label(row.action_type)
        found.add(
            at=row.created_at,
            category="FOLLOW_UP",
            event="FOLLOW_UP_CREATED",
            title=rules.title(f"Follow-up created ({label})" if label else "Follow-up created", row.title),
            obj=ref,
            details={"action_type": row.action_type, "status_now": row.status, "due_at": rules.iso(row.due_at)},
            origin=rules.origin_of(row.created_by),
            actor_ref=row.created_by,
            match=(row.id,),
        )
        if row.status == "DONE" and row.completed_at is not None:
            found.add(
                at=row.completed_at,
                category="FOLLOW_UP",
                event="FOLLOW_UP_COMPLETED",
                title=rules.title("Follow-up completed", row.title),
                obj=ref,
                reason=row.completion_note,
                details={"action_type": row.action_type},
                origin=rules.origin_of(row.completed_by),
                actor_ref=row.completed_by,
                match=(row.id,),
            )
        elif row.status == "CANCELLED":
            found.add(
                at=row.completed_at or row.updated_at,
                category="FOLLOW_UP",
                event="FOLLOW_UP_CANCELLED",
                title=rules.title("Follow-up cancelled", row.title),
                obj=ref,
                reason=row.completion_note,
                details={"action_type": row.action_type},
                origin=rules.origin_of(row.completed_by),
                actor_ref=row.completed_by,
                match=(row.id,),
            )


def read_impacts(found: Gathered) -> None:
    from backend.app.decision_followups import rules as follow_rules

    db, case = found.db, found.case
    rows = found.rows(
        "impact assessments",
        db.query(ImpactAssessment)
        .filter(ImpactAssessment.tenant_id == case.tenant_id, ImpactAssessment.investigation_id == case.id)
        .order_by(ImpactAssessment.created_at),
    )
    for row in rows:
        ref = found.remember("ImpactAssessment", row.id, row.business_id)
        found.add(
            at=row.created_at,
            category="IMPACT",
            event="IMPACT_ASSESSMENT_OPENED",
            title=rules.title("Impact assessment opened", follow_rules.trigger_label(row.trigger)),
            obj=ref,
            details={
                "trigger": row.trigger,
                "evidence_business_id": found.known.get(str(row.evidence_id), (None, None))[1],
                "decision_business_id": found.known.get(str(row.decision_id), (None, None))[1],
            },
            origin=rules.SYSTEM,
            match=(row.id,),
        )
        if row.assessed_at is not None:
            found.add(
                at=row.assessed_at,
                category="IMPACT",
                event="IMPACT_ASSESSMENT_COMPLETED",
                title=rules.title("Impact assessment completed", follow_rules.conclusion_label(row.conclusion)),
                obj=ref,
                reason=row.rationale,
                details={"conclusion": row.conclusion},
                origin=rules.HUMAN,
                actor_ref=row.assessed_by,
                actor_role=row.assessed_role,
                match=(row.id,),
            )


# ---------------------------------------------------------------------------------------------- audit events


def _audit_rows(session: Session, tenant_id, case: Investigation, related: list[uuid.UUID]) -> list[AuditEvent]:
    clause = AuditEvent.details["investigation_id"].astext == str(case.id)
    if related:
        clause = or_(AuditEvent.entity_id.in_(related), clause)
    return (
        session.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == tenant_id,
            clause,
            AuditEvent.action.notin_(list(rules.IGNORED_AUDIT_ACTIONS)),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(AUDIT_LIMIT)
        .all()
    )


def _audit_extra(row: AuditEvent) -> str | None:
    from backend.app.case_workflow.states import state_label

    new = row.new_values if isinstance(row.new_values, dict) else {}
    details = row.details if isinstance(row.details, dict) else {}
    if row.action == "INVESTIGATION_STATE_CHANGED" and new.get("workflow_state"):
        return f"now {(state_label(new['workflow_state']) or new['workflow_state']).lower()}"
    for key in ("outcome", "conclusion", "to_status", "status", "format"):
        value = details.get(key) or new.get(key)
        if isinstance(value, str) and value:
            return rules.readable(value)
    return None


def read_audit(found: Gathered) -> None:
    case = found.case
    related = [uuid.UUID(key) for key in list(found.known)[:RELATED_IDS_MAX]]
    sessions = [("data", found.db)]
    if found.control_db is not None and found.control_db is not found.db:
        sessions.append(("control", found.control_db))
    for plane, session in sessions:
        try:
            with session.begin_nested():
                rows = _audit_rows(session, case.tenant_id, case, related)
        except Exception:
            logger.warning("Audit events of the case could not be read from the %s plane", plane, exc_info=True)
            found.truncated.add(f"audit ({plane})")
            continue
        if len(rows) >= AUDIT_LIMIT:
            found.truncated.add(f"audit ({plane})")
        for row in rows:
            details = row.details if isinstance(row.details, dict) else {}
            new = row.new_values if isinstance(row.new_values, dict) else {}
            kind, business_id = found.known.get(str(row.entity_id), (row.entity_type, None))
            shown = rules.safe_details({**details, **new}, rules.AUDIT_DETAIL_KEYS)
            found.add(
                at=row.created_at,
                category=rules.audit_category(row.action),
                event=row.action,
                title=rules.audit_title(row.action, _audit_extra(row)),
                obj=rules.object_ref(row.entity_type or kind, row.entity_id, business_id) if row.entity_id else None,
                reason=row.reason,
                details={**shown, "audit_seq": row.chain_seq, "plane": plane},
                origin=rules.audit_origin(row.actor_ref, row.action),
                actor_ref=row.actor_ref,
                actor_role=details.get("actor_role") or details.get("signer_role"),
                match=(row.entity_id,),
                source="audit",
                key=f"audit:{row.id}",
            )


# ------------------------------------------------------------------------------------------------- timeline

READERS = (
    read_signals,
    read_scope,
    read_tasks,
    read_evidence,
    read_requests,
    read_intelligence,
    read_reviews,
    read_briefs,
    read_decisions,
    read_ai,
    read_follow_ups,
    read_impacts,
)


def people(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    from backend.app.decision_followups.common import names

    return names(control_db, tenant_id, refs)


def resolve_actors(items: list[dict], control_db: Session | None, tenant_id) -> list[dict]:
    names = people(control_db, tenant_id, [entry.get("_actor", (None, None))[0] for entry in items])
    for entry in items:
        ref, role = entry.pop("_actor", (None, None))
        entry["actor"] = rules.actor_view(ref, role, names, _role_label)
    return items


def gather(db: Session, control_db: Session | None, case: Investigation) -> Gathered:
    """Every reader of the case, each guarded: a source that cannot be read is reported, never fatal."""
    found = Gathered(db, control_db, case)
    separate = control_db is not None and control_db is not db
    for reader in (*READERS, read_audit):
        try:
            with ExitStack() as stack:
                # A savepoint on each session: a source that fails leaves both transactions usable.
                stack.enter_context(db.begin_nested())
                if separate:
                    stack.enter_context(control_db.begin_nested())
                reader(found)
        except Exception:
            logger.warning("Case audit source %s could not be read", reader.__name__, exc_info=True)
            found.truncated.add(reader.__name__.removeprefix("read_"))
    return found


def timeline(db: Session, control_db: Session | None, case: Investigation) -> tuple[list[dict], list[str]]:
    """``(items, sources not read in full)``: the whole merged timeline of the case, oldest first, with actors."""
    found = gather(db, control_db, case)
    items = resolve_actors(rules.merge([found.items]), control_db, case.tenant_id)
    return items, sorted(found.truncated)


# --------------------------------------------------------------------------------------------------- decisions


def current_decision(db: Session, case: Investigation) -> Decision | None:
    from backend.app.human_decision.service import current_decision as current

    return current(db, case)


def decision_in_force(decisions: list[Decision], moment: datetime) -> Decision | None:
    """The signed BRIEF decision in force at ``moment``: signed by then and not yet superseded."""
    chosen = None
    for decision in decisions:
        if decision.decision_kind != BRIEF_KIND:
            continue
        decided = rules.as_utc(decision.decided_at)
        superseded = rules.as_utc(decision.superseded_at)
        if decided is None or decided > moment or (superseded is not None and superseded <= moment):
            continue
        if chosen is None or decided > rules.as_utc(chosen.decided_at):
            chosen = decision
    return chosen


def evidence_hash_now(db: Session, case: Investigation) -> str:
    links, evidence = _case_evidence(db, case)
    return rules.evidence_set_hash(
        (
            str(row_id),
            links[row_id].review_status if row_id in links else "UNREVIEWED",
            links[row_id].relationship if row_id in links else "UNREVIEWED",
        )
        for row_id in evidence
    )


# ------------------------------------------------------------------------------------------------------ replay


def _status_events(db: Session, case: Investigation, object_type: str) -> dict[str, list[tuple]]:
    events: dict[str, list[tuple]] = {}
    for row in (
        db.query(IntelligenceEvent)
        .filter(
            IntelligenceEvent.tenant_id == case.tenant_id,
            IntelligenceEvent.investigation_id == case.id,
            IntelligenceEvent.object_type == object_type,
            IntelligenceEvent.event_type == "STATUS_CHANGED",
        )
        .order_by(IntelligenceEvent.created_at)
        .limit(SOURCE_LIMIT)
    ):
        events.setdefault(str(row.object_id), []).append((row.created_at, row.from_value, row.to_value))
    return events


def _complaints(db: Session, case: Investigation, moment: datetime) -> dict:
    links = {
        row.complaint_id: row.created_at
        for row in db.query(InvestigationComplaint)
        .filter(InvestigationComplaint.tenant_id == case.tenant_id, InvestigationComplaint.investigation_id == case.id)
        .limit(SOURCE_LIMIT)
    }
    for version in (
        db.query(InvestigationScopeVersion)
        .filter(
            InvestigationScopeVersion.tenant_id == case.tenant_id,
            InvestigationScopeVersion.investigation_id == case.id,
        )
        .order_by(InvestigationScopeVersion.version)
    ):
        for value in version.included_complaint_ids or ():
            key = rules.as_uuid_text(value)
            if key is not None and uuid.UUID(key) not in links:
                links[uuid.UUID(key)] = version.created_at
    rows = (
        db.query(Complaint).filter(Complaint.tenant_id == case.tenant_id, Complaint.id.in_(list(links))).all()
        if links
        else []
    )
    items = [
        {
            "business_id": row.business_id,
            "complaint_identifier": row.complaint_identifier,
            "event_at": rules.iso(row.event_timestamp or row.complaint_timestamp),
            "known_at": rules.known_at(
                (row.ingestion_timestamp, row.recorded_timestamp, row.created_at), links.get(row.id)
            ),
            "severity": row.severity,
            "status_now": row.status,
        }
        for row in rows
    ]
    known, later = rules.partition_known(items, moment)
    return {"known_then": _dated(known), "arrived_later": _dated(later)}


def _strip(rows: list[dict]) -> list[dict]:
    return [{key: value for key, value in row.items() if key != "_id"} for row in _dated(rows)]


def _dated(items: list[dict]) -> list[dict]:
    ordered = sorted(
        items, key=lambda entry: (rules.as_utc(entry.get("known_at")) or rules._EPOCH, entry.get("business_id") or "")
    )
    return [{**entry, "known_at": rules.iso(entry.get("known_at"))} for entry in ordered]


def _evidence_then(db: Session, case: Investigation, moment: datetime) -> tuple[dict, list[tuple]]:
    from backend.app.evidence_workflow.rules import relationship_label, review_status_label

    links, evidence = _case_evidence(db, case)
    history: dict[Any, list] = {}
    for event in (
        db.query(EvidenceReviewEvent)
        .filter(EvidenceReviewEvent.tenant_id == case.tenant_id, EvidenceReviewEvent.investigation_id == case.id)
        .order_by(EvidenceReviewEvent.created_at)
        .limit(SOURCE_LIMIT)
    ):
        history.setdefault(event.evidence_id, []).append(event)
    items = []
    for row in evidence.values():
        link = links.get(row.id)
        events = history.get(row.id, [])
        status_now = link.review_status if link else "UNREVIEWED"
        relationship_now = link.relationship if link else "UNREVIEWED"
        status = rules.value_as_of(
            [
                (event.created_at, event.from_review_status, event.to_review_status)
                for event in events
                if event.to_review_status
            ],
            moment,
            current=status_now,
            current_changed_at=link.reviewed_at if link else None,
            default="UNREVIEWED",
        )
        relationship = rules.value_as_of(
            [
                (event.created_at, event.from_relationship, event.to_relationship)
                for event in events
                if event.to_relationship
            ],
            moment,
            current=relationship_now,
            current_changed_at=link.reviewed_at if link else None,
            default="UNREVIEWED",
        )
        items.append(
            {
                "_id": str(row.id),
                "business_id": row.business_id,
                "evidence_identifier": row.evidence_identifier,
                "title": row.title,
                "evidence_type": row.evidence_type,
                "known_at": rules.known_at(
                    (row.ingestion_timestamp, row.recorded_timestamp, row.created_at),
                    link.created_at if link else None,
                ),
                "review_status": status or "UNREVIEWED",
                "review_status_label": review_status_label(status or "UNREVIEWED"),
                "relationship": relationship or "UNREVIEWED",
                "relationship_label": relationship_label(relationship or "UNREVIEWED"),
                "review_status_now": status_now,
                "relationship_now": relationship_now,
            }
        )
    known, later = rules.partition_known(items, moment)
    hash_items = [(entry["_id"], entry["review_status"], entry["relationship"]) for entry in known]
    later_view = [
        {key: entry[key] for key in ("business_id", "evidence_identifier", "title", "evidence_type", "known_at")}
        for entry in _strip(later)
    ]
    return {"known_then": _strip(known), "arrived_later": later_view}, hash_items


def _hypotheses_then(db: Session, case: Investigation, moment: datetime) -> list[dict]:
    from backend.app.case_intelligence.rules import human_status_label

    events = _status_events(db, case, "HYPOTHESIS")
    result = []
    for row in (
        db.query(Hypothesis)
        .filter(Hypothesis.tenant_id == case.tenant_id, Hypothesis.investigation_id == case.id)
        .order_by(Hypothesis.created_at)
        .limit(SOURCE_LIMIT)
    ):
        created = rules.as_utc(row.recorded_timestamp or row.created_at)
        if created is None or created > moment:
            continue
        status = rules.value_as_of(
            events.get(str(row.id), []), moment, current=row.human_status, current_changed_at=row.status_changed_at
        )
        result.append(
            {
                "business_id": row.business_id,
                "statement": rules.shorten(row.statement, 300),
                "origin": str(row.origin or "").upper(),
                "human_status": status,
                "human_status_label": human_status_label(status) if status else "Not judged yet",
                "human_status_now": row.human_status,
                "ai_status_now": row.status,
            }
        )
    return result


def _unknowns_then(db: Session, case: Investigation, moment: datetime) -> list[dict]:
    from backend.app.case_intelligence.rules import unknown_status_label

    events = _status_events(db, case, "UNKNOWN")
    result = []
    for row in (
        db.query(Unknown)
        .filter(Unknown.tenant_id == case.tenant_id, Unknown.investigation_id == case.id)
        .order_by(Unknown.created_at)
        .limit(SOURCE_LIMIT)
    ):
        created = rules.as_utc(row.created_at)
        if created is None or created > moment:
            continue
        status = rules.value_as_of(
            events.get(str(row.id), []),
            moment,
            current=row.status,
            current_changed_at=row.status_changed_at,
            default="open",
        )
        result.append(
            {
                "business_id": row.business_id,
                "description": rules.shorten(row.description, 300),
                "status": status,
                "status_label": unknown_status_label(status),
                "status_now": row.status,
            }
        )
    return result


def _reviews_then(db: Session, case: Investigation, moment: datetime) -> list[dict]:
    from backend.app.case_reviews import rules as review_rules

    result = []
    for row in (
        db.query(CaseReview)
        .filter(CaseReview.tenant_id == case.tenant_id, CaseReview.investigation_id == case.id)
        .order_by(CaseReview.completed_at)
    ):
        completed = rules.as_utc(row.completed_at)
        if completed is None or completed > moment:
            continue
        result.append(
            {
                "business_id": row.business_id,
                "review_type": row.review_type,
                "review_type_label": review_rules.type_label(row.review_type),
                "outcome": row.outcome,
                "outcome_label": review_rules.outcome_label(row.outcome),
                "completed_at": rules.iso(completed),
                "scope_version": row.scope_version,
                "status_now": row.status,
            }
        )
    return result


def _brief_then(db: Session, case: Investigation, moment: datetime) -> dict | None:
    from backend.app.human_decision.service import hash_verified

    approvals = (
        db.query(BriefReviewAction)
        .filter(
            BriefReviewAction.tenant_id == case.tenant_id,
            BriefReviewAction.investigation_id == case.id,
            BriefReviewAction.action == "ACCEPT_FOR_DECISION",
            BriefReviewAction.created_at <= moment,
        )
        .order_by(BriefReviewAction.created_at.desc())
        .first()
    )
    row, approved_at = None, None
    if approvals is not None:
        row = (
            db.query(DecisionBriefVersion)
            .filter(
                DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.id == approvals.brief_version_id
            )
            .first()
        )
        approved_at = approvals.created_at
    if row is None:
        row = (
            db.query(DecisionBriefVersion)
            .filter(
                DecisionBriefVersion.tenant_id == case.tenant_id,
                DecisionBriefVersion.investigation_id == case.id,
                DecisionBriefVersion.status.in_(("APPROVED_FOR_DECISION", "SUPERSEDED")),
                DecisionBriefVersion.reviewed_at <= moment,
            )
            .order_by(DecisionBriefVersion.version.desc())
            .first()
        )
        approved_at = row.reviewed_at if row is not None else None
    if row is None:
        return None
    return {
        "business_id": row.business_id,
        "version": row.version,
        "content_hash": row.content_hash,
        "hash_verified": hash_verified(row),
        "approved_at": rules.iso(approved_at),
        "status_now": row.status,
    }


def _snapshot(db: Session, decision: Decision | None, at_signing: bool) -> dict:
    from backend.app.human_decision import rules as decision_rules
    from backend.app.human_decision.service import context_snapshot, stored_snapshot_hash

    if decision is None:
        return {"available": False, "reason": "No signed decision is in force at this moment"}
    if not at_signing:
        return {"available": False, "reason": "The context snapshot describes the moment of signing only"}
    row = context_snapshot(db, decision)
    if row is None or not isinstance(row.snapshot, dict):
        return {"available": False, "reason": "The decision has no stored context snapshot"}
    data = row.snapshot
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    return {
        "available": True,
        "reason": None,
        "brief_business_id": brief.get("business_id"),
        "brief_version": brief.get("version"),
        "brief_hash": brief.get("content_hash"),
        "evidence_set_hash": data.get("evidence_set_hash"),
        "scope_version": data.get("scope_version"),
        "snapshot_hash_verified": decision_rules.snapshot_hash(data) == stored_snapshot_hash(decision),
        "created_at": rules.iso(row.created_at),
    }


def replay(
    db: Session,
    control_db: Session | None,
    case: Investigation,
    *,
    as_known_at: datetime | None = None,
    decision: Decision | None = None,
    now: datetime,
) -> dict:
    """The case as known at ``as_known_at`` (default: when ``decision``, else the current signed decision, was
    signed; else now)."""
    decisions = case_decisions(db, case)
    if decision is None and as_known_at is None:
        decision = current_decision(db, case)
    moment = rules.as_utc(as_known_at) or rules.as_utc(decision.decided_at if decision else None) or now
    if decision is None:
        decision = decision_in_force(decisions, moment)
    decided = rules.as_utc(decision.decided_at) if decision is not None else None
    at_signing = decided is not None and abs((decided - moment).total_seconds()) < 1
    signer = None
    if decision is not None:
        ref = decision.decided_by_user_id or decision.authorized_by_ref
        signer = rules.actor_view(
            ref, decision.decided_under_role, people(control_db, case.tenant_id, [ref]), _role_label
        )
    evidence, hash_items = _evidence_then(db, case, moment)
    signed_hash = decision.evidence_set_hash if (decision is not None and at_signing) else None
    hash_then = signed_hash or rules.evidence_set_hash(hash_items)
    hash_now = evidence_hash_now(db, case)
    return {
        "investigation": {"business_id": case.business_id, "identifier": case.investigation_identifier},
        "as_known_at": moment.isoformat(),
        "decision": (
            {
                "decision_id": str(decision.id),
                "business_id": decision.business_id,
                "outcome": decision.outcome or decision.disposition,
                "decided_at": rules.iso(decision.decided_at or decision.created_at),
                "signer": signer,
                "status_now": decision.decision_status,
            }
            if decision is not None
            else None
        ),
        "snapshot": _snapshot(db, decision, at_signing),
        "complaints": _complaints(db, case, moment),
        "evidence": evidence,
        "hypotheses": _hypotheses_then(db, case, moment),
        "unknowns": _unknowns_then(db, case, moment),
        "reviews": _reviews_then(db, case, moment),
        "brief": _brief_then(db, case, moment),
        "integrity": {
            "evidence_set_hash_then": hash_then,
            "evidence_set_hash_then_source": "SIGNED_DECISION" if signed_hash else "RECONSTRUCTED",
            "evidence_set_hash_now": hash_now,
            "changed_since": hash_then != hash_now,
        },
        "limitations": list(rules.REPLAY_LIMITATIONS),
    }


# ----------------------------------------------------------------------------------------------------- AI runs


def ai_runs(db: Session, control_db: Session | None, case: Investigation) -> dict:
    current = current_decision(db, case)
    used = {str(ref) for ref in (current.ai_execution_refs or [])} if current is not None else set()
    runs = (
        db.query(AIExecution)
        .filter(AIExecution.tenant_id == case.tenant_id, AIExecution.investigation_id == case.id)
        .order_by(AIExecution.execution_timestamp, AIExecution.business_id)
        .limit(SOURCE_LIMIT)
        .all()
    )
    reviews: dict[str, HumanReview] = {}
    for review in (
        db.query(HumanReview)
        .filter(
            HumanReview.tenant_id == case.tenant_id,
            HumanReview.investigation_id == case.id,
            HumanReview.ai_execution_id.isnot(None),
        )
        .order_by(HumanReview.review_timestamp)
    ):
        reviews[str(review.ai_execution_id)] = review  # the latest review of each run
    names = people(control_db, case.tenant_id, [review.reviewer_ref for review in reviews.values()])
    items = []
    for run in runs:
        review = reviews.get(str(run.id))
        reviewer = rules.actor_view(review.reviewer_ref, None, names) if review is not None else None
        items.append(
            {
                "id": str(run.id),
                "business_id": run.business_id,
                "kind": rules.ai_kind(run.provider, run.model_name, run.prompt_template_version),
                "provider": run.provider,
                "model": run.model_name,
                "model_version": run.model_version,
                "prompt_template_version": run.prompt_template_version,
                "orchestration_version": run.orchestration_version,
                "context_hash": rules.context_hash(run.context_refs, run.evidence_refs),
                "status": rules.run_status(run.validation_status, run.error_state),
                "guardrails": rules.guardrail_summary(run.structured_output, run.validation_status, run.error_state),
                "execution_timestamp": rules.iso(run.execution_timestamp),
                **rules.run_times(run.execution_timestamp, run.latency_ms),
                **rules.usage(run.structured_output),
                "human_review": (
                    {
                        "status": review.disposition,
                        "by": (reviewer or {}).get("name"),
                        "at": rules.iso(review.review_timestamp),
                    }
                    if review is not None
                    else None
                ),
                "used_in_signed_decision": bool(run.business_id) and run.business_id in used,
            }
        )
    for ask in (
        db.query(AIInteraction)
        .filter(AIInteraction.tenant_id == case.tenant_id, AIInteraction.investigation_id == case.id)
        .order_by(AIInteraction.created_at)
        .limit(SOURCE_LIMIT)
    ):
        provenance = ask.provenance if isinstance(ask.provenance, dict) else {}
        refused = str(provenance.get("provider") or "").lower() == "unavailable"
        items.append(
            {
                "id": str(ask.id),
                "business_id": None,
                "kind": "ask",
                "provider": provenance.get("provider"),
                "model": provenance.get("model"),
                "model_version": provenance.get("model_version"),
                "prompt_template_version": provenance.get("prompt_template_version"),
                "orchestration_version": None,
                "context_hash": rules.context_hash(
                    {
                        "investigation_id": str(ask.investigation_id),
                        "temporal_mode": ask.temporal_mode,
                        "temporal_cutoff": rules.iso(ask.temporal_cutoff),
                    },
                    None,
                ),
                "status": "REFUSED" if refused else "COMPLETED",
                "guardrails": {
                    "validation_status": None,
                    "checks": 0,
                    "passed": 0,
                    "failed": [],
                    "rejected_items": 0,
                    "dropped_statements": 0,
                    "error": rules.shorten(provenance.get("refusal_code") or provenance.get("error_state"), 160),
                },
                "execution_timestamp": rules.iso(ask.created_at),
                **rules.run_times(ask.created_at, provenance.get("latency_ms")),
                **rules.usage(provenance),
                "human_review": None,
                "used_in_signed_decision": False,
            }
        )
    items.sort(key=lambda run: (run.get("finished_at") or "", run.get("business_id") or run["id"]))
    return {"items": items, "counts": rules.ai_counts(items)}


# --------------------------------------------------------------------------------------------------- integrity


def chain_check(session: Session, tenant_id, plane: str) -> dict:
    """The audit hash chain of the organization on one plane, recomputed by the database
    (backend/app/audit_chain.py) when it holds at most ``CHAIN_CHECK_MAX_EVENTS`` events; NOT_CHECKED otherwise
    or when it cannot be checked."""
    from backend.app.audit_chain import verify_tenant_chain

    try:
        with session.begin_nested():
            count = session.execute(
                text("SELECT count(*) FROM public.audit_events WHERE tenant_id = :tenant"),
                {"tenant": uuid.UUID(str(tenant_id))},
            ).scalar()
            if int(count or 0) > CHAIN_CHECK_MAX_EVENTS:
                return {
                    "plane": plane,
                    "status": "NOT_CHECKED",
                    "checked_events": 0,
                    "first_broken_seq": None,
                    "reason": f"More than {CHAIN_CHECK_MAX_EVENTS} audit events; the daily verification covers them",
                }
            result = verify_tenant_chain(session, tenant_id)
    except Exception:
        logger.warning("The audit chain could not be verified on the %s plane", plane, exc_info=True)
        return {
            "plane": plane,
            "status": "NOT_CHECKED",
            "checked_events": 0,
            "first_broken_seq": None,
            "reason": "The audit chain could not be verified now",
        }
    return {
        "plane": plane,
        "status": "VALID" if result["valid"] else "BROKEN",
        "checked_events": result["checked"],
        "first_broken_seq": result["first_broken_seq"],
        "reason": None,
    }


def integrity(db: Session, control_db: Session | None, case: Investigation) -> dict:
    from backend.app.human_decision import rules as decision_rules
    from backend.app.human_decision.service import hash_verified, verify_signature

    decisions = {decision.id: decision for decision in case_decisions(db, case)}
    records = signature_records(control_db, case.tenant_id, list(decisions))
    names = people(control_db, case.tenant_id, [record.signer_user_id for record in records])
    signatures = []
    for record in records:
        decision = decisions.get(record.object_id)
        if decision is None:
            continue
        if record.decision_type == decision_rules.DECISION_TYPE:
            verification = verify_signature(db, record, decision)
            status, checks = verification["status"], verification["checks"]
        else:
            checks = rules.legacy_signature_checks(
                {
                    "object_version": record.object_version,
                    "decision_type": record.decision_type,
                    "decision": record.decision,
                    "remarks": record.remarks,
                    "signer_user_id": record.signer_user_id,
                    "content_fingerprint": record.content_fingerprint,
                    "signature_hash": record.signature_hash,
                    "status": record.status,
                },
                decision.id,
            )
            status = rules.checks_status(checks)
        signatures.append(
            {
                "business_id": record.business_id,
                "decision_id": str(decision.id),
                "decision_business_id": decision.business_id,
                "decision_kind": decision.decision_kind,
                "kind": record.decision_type,
                "status": status,
                "checks": checks,
                "signed_at": rules.iso(record.signed_at),
                "signer": rules.actor_view(record.signer_user_id, record.signer_role, names, _role_label),
                "record_status": record.status,
            }
        )
    briefs = [
        {
            "business_id": row.business_id,
            "version": row.version,
            "status": row.status,
            "content_hash": row.content_hash,
            "hash_verified": hash_verified(row) if row.content_hash else None,
        }
        for row in db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version)
    ]
    planes = [chain_check(db, case.tenant_id, "data")]
    if control_db is not None and control_db is not db:
        planes.append(chain_check(control_db, case.tenant_id, "control"))
    return {
        "signatures": signatures,
        "audit_chain": rules.combine_chains(planes),
        "brief_hashes": briefs,
        "summary": {
            "signatures": len(signatures),
            "signatures_invalid": sum(1 for item in signatures if item["status"] != "VALID"),
            "briefs_unverified": sum(1 for item in briefs if item["hash_verified"] is False),
        },
    }
