"""Reading for the human decision: the approved brief of a case, its decisions on briefs, the people who wrote the
brief, whether the case reports serious harm, the decision queue, the views of the screen and of a signed decision,
and the verification of a signed decision. Nothing here changes data.

The decision, its context snapshot and its follow-ups live in the tenant data plane with the case; the signature
(``signed_approval_records``) lives in the control database, as legacy signatures do.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from sqlalchemy.orm import Session

from backend.app.complaint_disposition.rules import ATTRIBUTION_LABELS
from backend.app.case_workflow import states
from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import Decision, Investigation, Product, SignedApprovalRecord
from backend.app.db.models.reviews import BriefReviewAction, DecisionBriefVersion
from backend.app.db.models.stage3 import ContextSnapshot
from backend.app.db.models.workflow import WorkflowTask
from backend.app.decision_brief import rules as brief_rules
from backend.app.human_decision import rules
from backend.app.workflow.labels import role_label

logger = logging.getLogger("mdarix.human_decision")

BRIEF_SOURCE = "DecisionBriefVersion"
FOLLOW_UP_SOURCE = "DecisionFollowUp"


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def names(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    if control_db is None:
        return {}
    from backend.app.workflow.people import names_by_id

    try:
        return names_by_id(control_db, tenant_id, refs)
    except Exception:
        logger.warning("Names for the decision could not be read", exc_info=True)
        return {}


# ------------------------------------------------------------------------------------------------------- briefs


def brief_version(db: Session, case: Investigation, brief_version_id, *, lock: bool = False):
    """The case's brief version ``brief_version_id``; None when it is not one of this case's versions."""
    query = db.query(DecisionBriefVersion).filter(
        DecisionBriefVersion.tenant_id == case.tenant_id,
        DecisionBriefVersion.investigation_id == case.id,
        DecisionBriefVersion.id == brief_version_id,
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def approved_brief(db: Session, case: Investigation) -> DecisionBriefVersion | None:
    """The case's latest version approved for decision (a case has at most one: submitting a new version supersedes
    the approved one)."""
    return (
        db.query(DecisionBriefVersion)
        .filter(
            DecisionBriefVersion.tenant_id == case.tenant_id,
            DecisionBriefVersion.investigation_id == case.id,
            DecisionBriefVersion.status == brief_rules.APPROVED_FOR_DECISION,
        )
        .order_by(DecisionBriefVersion.version.desc())
        .first()
    )


def latest_brief(db: Session, case: Investigation) -> DecisionBriefVersion | None:
    return (
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .order_by(DecisionBriefVersion.version.desc())
        .first()
    )


def hash_verified(row: DecisionBriefVersion | None) -> bool:
    return (
        row is not None
        and bool(row.content_hash)
        and brief_rules.content_hash(row.content, row.narrative) == row.content_hash
    )


def brief_author_refs(db: Session, row: DecisionBriefVersion) -> set[str]:
    """Everyone who wrote this version: its creator, submitter and contributors, and the authors its decision tasks
    name (``brief_author_refs``/``brief_author_ref``)."""
    narrative = brief_rules.normalize_narrative(row.narrative)
    refs = {row.created_by, row.submitted_by, *narrative["contributors"]}
    # A failure to read the tasks fails the request: segregation of duties is never skipped.
    for (details,) in db.query(WorkflowTask.details).filter(
        WorkflowTask.tenant_id == row.tenant_id,
        WorkflowTask.source_entity_type == BRIEF_SOURCE,
        WorkflowTask.source_entity_id == row.id,
        WorkflowTask.task_type == "DECISION_APPROVAL",
    ):
        details = details if isinstance(details, dict) else {}
        refs.update(details.get("brief_author_refs") or ())
        refs.add(details.get("brief_author_ref"))
    return {str(ref).strip() for ref in refs if ref and str(ref).strip()}


# ---------------------------------------------------------------------------------------------------- decisions


def case_decisions(db: Session, case: Investigation) -> list[Decision]:
    """The case's decisions on briefs, newest first (superseded ones included)."""
    return (
        db.query(Decision)
        .filter(
            Decision.tenant_id == case.tenant_id,
            Decision.investigation_id == case.id,
            Decision.decision_kind == rules.DECISION_KIND,
        )
        .order_by(Decision.decided_at.desc().nulls_last(), Decision.created_at.desc())
        .all()
    )


def legacy_decision_count(db: Session, case: Investigation) -> int:
    return (
        db.query(Decision.id)
        .filter(
            Decision.tenant_id == case.tenant_id,
            Decision.investigation_id == case.id,
            Decision.decision_kind != rules.DECISION_KIND,
        )
        .count()
    )


def current_decision(db: Session, case: Investigation, *, lock: bool = False) -> Decision | None:
    """The case's current signed decision on a brief (signed and not superseded), else None."""
    query = db.query(Decision).filter(
        Decision.tenant_id == case.tenant_id,
        Decision.investigation_id == case.id,
        Decision.decision_kind == rules.DECISION_KIND,
        Decision.decision_status == rules.SIGNED,
        Decision.superseded_by_decision_id.is_(None),
    )
    if lock:
        query = query.with_for_update()
    return query.order_by(Decision.decided_at.desc().nulls_last(), Decision.created_at.desc()).first()


def next_identifier(db: Session, case: Investigation) -> str:
    """``<case identifier>-D<n>``: n counts the case's decisions, skipping any identifier already used."""
    count = (
        db.query(Decision.id).filter(Decision.tenant_id == case.tenant_id, Decision.investigation_id == case.id).count()
    )
    number = count + 1
    while True:
        identifier = rules.decision_identifier(case.investigation_identifier, number)
        taken = (
            db.query(Decision.id)
            .filter(Decision.tenant_id == case.tenant_id, Decision.decision_identifier == identifier)
            .first()
        )
        if taken is None:
            return identifier
        number += 1


def authority_id(control_db: Session, tenant_id, role: str | None):
    """The active approval authority the signer decided under (the one granting their role), else None."""
    from backend.app.access.permissions import normalize_role
    from backend.app.db.models.foundation import ApprovalAuthority

    if not role:
        return None
    wanted = normalize_role(role)
    for row in control_db.query(ApprovalAuthority).filter_by(
        tenant_id=tenant_id,
        object_type="Decision",
        decision_type="INVESTIGATION_REVIEW",
        authority="AUTHORIZED",
        status="ACTIVE",
    ):
        if normalize_role(row.role_name) == wanted:
            return row.id
    return None


def approval_subject(row: DecisionBriefVersion) -> SimpleNamespace:
    """What ``governance_router.approval_check`` reads for segregation of duties: the brief's author stands as the
    creator of the decision."""
    return SimpleNamespace(authorized_by_ref=row.submitted_by or row.created_by)


def serious_harm(db: Session, case: Investigation) -> bool:
    """True when a complaint in the case's current scope reports a serious injury or a death, or a signal the case was
    opened for reports serious harm. False when it cannot be read."""
    from backend.app.case_workflow.readiness import safely

    def read(session: Session) -> bool:
        from backend.app.case_reviews.service import linked_signals, scope_complaints

        if any(item.get("serious_harm") for item in linked_signals(session, case)):
            return True
        return any(bool(row.serious_injury) or bool(row.death) for row in scope_complaints(session, case))

    return bool(safely(db, "serious harm", read, default=False))


# ------------------------------------------------------------------------------------------------------- views


def investigation_view(db: Session, case: Investigation) -> dict:
    from backend.app.decision_brief.compose import investigation_section

    product = (
        db.query(Product.business_id, Product.name)
        .filter(Product.tenant_id == case.tenant_id, Product.id == case.product_id)
        .first()
    )
    return {
        **investigation_section(case),
        "investigation_identifier": case.investigation_identifier,
        "owner_ref": case.owner_ref,
        "product": {
            "id": str(case.product_id) if case.product_id else None,
            "business_id": product.business_id if product is not None else None,
            "name": product.name if product is not None else None,
        },
    }


def brief_summary(row: DecisionBriefVersion | None, people: dict[str, str]) -> dict | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "version": row.version,
        "status": row.status,
        "status_label": brief_rules.status_label(row.status),
        "content_hash": row.content_hash,
        "approved_at": _iso(row.reviewed_at) if row.status == brief_rules.APPROVED_FOR_DECISION else None,
        "quality_reviewer_name": people.get(str(row.reviewed_by)) if row.reviewed_by else None,
    }


def brief_view(row: DecisionBriefVersion | None, people: dict[str, str]) -> dict | None:
    """The brief as the decision maker reads it: narrative, facts, contradictions, unknowns, reviews, AI assistance
    and the readiness recorded when it was submitted, with whether its stored content still matches its fingerprint."""
    if row is None:
        return None
    content = row.content or {}
    narrative = brief_rules.normalize_narrative(row.narrative)
    unknowns = content.get("unknowns") if isinstance(content.get("unknowns"), dict) else {}
    readiness = row.readiness if isinstance(row.readiness, dict) else {}
    return {
        **brief_summary(row, people),
        "title": row.title,
        "hash_verified": hash_verified(row),
        "submitted_by_name": people.get(str(row.submitted_by)) if row.submitted_by else None,
        "submitted_at": _iso(row.submitted_at),
        "created_by_name": people.get(str(row.created_by)) if row.created_by else None,
        "scope_version": row.scope_version,
        "narrative": {
            "problem_statement": narrative["problem_statement"],
            "proposed_conclusion": narrative["proposed_conclusion"],
            "recommended_actions": narrative["recommended_actions"],
            "author_notes": narrative["author_notes"],
            "ai_draft_used": narrative["ai_draft_used"],
            "ai_draft_label": narrative["ai_draft_label"],
        },
        "established_facts": content.get("established_facts") or [],
        "supporting_evidence": content.get("supporting_evidence") or [],
        "contradictions": content.get("contradicting_evidence") or [],
        "leading_hypothesis": content.get("leading_hypothesis"),
        "alternative_hypotheses": content.get("alternative_hypotheses") or [],
        "unknowns": {
            "open": unknowns.get("open") or [],
            "accepted_limitations": unknowns.get("accepted_limitations") or [],
            "open_count": int(unknowns.get("open_count") or 0),
            "accepted_limitation_count": int(unknowns.get("accepted_limitation_count") or 0),
        },
        "residual_unknowns": rules.residual_unknowns(content),
        "risk_review": content.get("risk_review"),
        "regulatory_review": content.get("regulatory_review"),
        "required_reviews": rules.required_reviews(content),
        "ai_assistance": content.get("ai_assistance"),
        "evidence_inventory": {
            key: (content.get("evidence_inventory") or {}).get(key)
            for key in ("total", "by_review_status", "by_relationship")
        },
        "readiness": readiness.get("checks") or content.get("readiness") or [],
        "context": content.get("context") or {},
    }


def reviewers(db: Session, control_db: Session | None, row: DecisionBriefVersion | None) -> list[dict]:
    """The quality review actions on the brief version and the case reviews it carries, with names, roles and
    times, oldest first."""
    if row is None:
        return []
    actions = (
        db.query(BriefReviewAction)
        .filter(BriefReviewAction.tenant_id == row.tenant_id, BriefReviewAction.brief_version_id == row.id)
        .order_by(BriefReviewAction.created_at, BriefReviewAction.id)
        .all()
    )
    people = names(control_db, row.tenant_id, (item.actor_ref for item in actions))
    result = [
        {
            "kind": "QUALITY",
            "action": item.action,
            "label": brief_rules.action_label(item.action),
            "comment": item.comment,
            "name": people.get(str(item.actor_ref)),
            "role": item.actor_role,
            "role_label": role_label(item.actor_role),
            "at": _iso(item.created_at),
        }
        for item in actions
    ]
    content = row.content or {}
    for key, kind in (("risk_review", "RISK"), ("regulatory_review", "REGULATORY")):
        section = content.get(key) if isinstance(content.get(key), dict) else {}
        review = section.get("review") if isinstance(section.get("review"), dict) else None
        if review is None:
            continue
        result.append(
            {
                "kind": kind,
                "action": review.get("status"),
                "label": "Risk review" if kind == "RISK" else "Regulatory review",
                "outcome": review.get("outcome"),
                "business_id": review.get("business_id"),
                "comment": review.get("rationale"),
                "name": review.get("reviewer_name"),
                "role": review.get("reviewer_role"),
                "role_label": role_label(review.get("reviewer_role")),
                "at": review.get("completed_at"),
            }
        )
    return result


def _follow_up_action_view(item) -> dict:
    data = item if isinstance(item, dict) else {"action_type": item}
    return {**data, "label": rules.follow_up_label(data.get("action_type"))}


def decision_view(
    decision: Decision,
    people: dict[str, str],
    briefs: dict[str, DecisionBriefVersion] | None = None,
    business_ids: dict[str, str] | None = None,
) -> dict:
    """A decision on a brief with its labels, the signer's name and role, its brief's business id and the decisions it
    supersedes or is superseded by (``business_ids``: their business ids by id, when known)."""
    brief = (briefs or {}).get(str(decision.brief_version_id)) if decision.brief_version_id else None
    signer_name = people.get(str(decision.decided_by_user_id)) if decision.decided_by_user_id else None

    def link(value) -> dict | None:
        return {"id": str(value), "business_id": (business_ids or {}).get(str(value))} if value else None

    return {
        "status": decision.decision_status,
        "signer_name": signer_name,
        "signer_role": decision.decided_under_role,
        "supersedes": link(decision.supersedes_decision_id),
        "superseded_by": link(decision.superseded_by_decision_id),
        "id": str(decision.id),
        "business_id": decision.business_id,
        "decision_identifier": decision.decision_identifier,
        "decision_kind": decision.decision_kind,
        "decision_type": decision.decision_type,
        "investigation_id": str(decision.investigation_id),
        "outcome": decision.outcome,
        "outcome_label": rules.outcome_label(decision.outcome),
        "decision_status": decision.decision_status,
        "decision_status_label": rules.decision_status_label(decision.decision_status),
        "rationale": decision.rationale,
        "root_cause_attribution": decision.root_cause_attribution,
        "root_cause_attribution_label": ATTRIBUTION_LABELS.get(decision.root_cause_attribution or ""),
        "attribution_reason": decision.attribution_reason,
        # Decisions signed before 0.10.53 carry none.
        "attribution_note": None if decision.root_cause_attribution else "Recorded before root-cause attribution",
        "conditions": decision.conditions,
        "follow_up_actions": [_follow_up_action_view(item) for item in decision.follow_up_actions or ()],
        "residual_unknowns": list(decision.residual_unknowns or ()),
        "decided_by_user_id": str(decision.decided_by_user_id) if decision.decided_by_user_id else None,
        "decided_by_name": signer_name,
        "decided_under_role": decision.decided_under_role,
        "decided_under_role_label": role_label(decision.decided_under_role),
        "approval_authority_id": str(decision.approval_authority_id) if decision.approval_authority_id else None,
        "decided_at": _iso(decision.decided_at),
        "brief_version_id": str(decision.brief_version_id) if decision.brief_version_id else None,
        "brief_business_id": brief.business_id if brief is not None else None,
        "brief_version": brief.version if brief is not None else None,
        "brief_content_hash": decision.brief_content_hash,
        "evidence_set_hash": decision.evidence_set_hash,
        "context_snapshot_id": str(decision.context_snapshot_id) if decision.context_snapshot_id else None,
        "ai_execution_refs": list(decision.ai_execution_refs or ()),
        "supersedes_decision_id": str(decision.supersedes_decision_id) if decision.supersedes_decision_id else None,
        "superseded_by_decision_id": (
            str(decision.superseded_by_decision_id) if decision.superseded_by_decision_id else None
        ),
        "superseded_at": _iso(decision.superseded_at),
        "supersede_reason": decision.supersede_reason,
        "product_id": str(decision.product_id) if decision.product_id else None,
    }


def briefs_by_id(db: Session, tenant_id, ids) -> dict[str, DecisionBriefVersion]:
    from backend.app.business_ids import wanted_ids

    wanted = wanted_ids(ids)
    if not wanted:
        return {}
    return {
        str(row.id): row
        for row in db.query(DecisionBriefVersion).filter(
            DecisionBriefVersion.tenant_id == tenant_id, DecisionBriefVersion.id.in_(list(wanted))
        )
    }


# ------------------------------------------------------------------------------------------------- verification


def signature_record(control_db: Session, decision: Decision) -> SignedApprovalRecord | None:
    return (
        control_db.query(SignedApprovalRecord)
        .filter(
            SignedApprovalRecord.tenant_id == decision.tenant_id,
            SignedApprovalRecord.object_type == "Decision",
            SignedApprovalRecord.object_id == decision.id,
            SignedApprovalRecord.decision_type == rules.DECISION_TYPE,
        )
        .order_by(SignedApprovalRecord.signed_at.desc())
        .first()
    )


def context_snapshot(db: Session, decision: Decision) -> ContextSnapshot | None:
    query = db.query(ContextSnapshot).filter(
        ContextSnapshot.tenant_id == decision.tenant_id, ContextSnapshot.decision_id == decision.id
    )
    if decision.context_snapshot_id:
        query = query.filter(ContextSnapshot.id == decision.context_snapshot_id)
    return query.order_by(ContextSnapshot.created_at.desc()).first()


def stored_snapshot_hash(decision: Decision) -> str | None:
    """The snapshot hash recorded with the decision when it was signed (``decisions.context_snapshot``)."""
    data = decision.context_snapshot if isinstance(decision.context_snapshot, dict) else {}
    value = data.get("snapshot_hash")
    return str(value) if value else None


def verify_signature(db: Session, record: SignedApprovalRecord | None, decision: Decision) -> dict:
    """``{"status": VALID|INVALID|NOT_SIGNED, "checks": [...]}`` for a decision on a brief: the signed material is
    recomputed from the signature record, the decision, the stored context snapshot and the stored brief version
    (``rules.verification_checks``). ``db`` is the data plane (decision, snapshot and brief)."""
    if record is None:
        return {"status": rules.verification_status(None, signed=False), "checks": []}
    snapshot = context_snapshot(db, decision)
    brief = (
        db.query(DecisionBriefVersion)
        .filter(
            DecisionBriefVersion.tenant_id == decision.tenant_id,
            DecisionBriefVersion.id == decision.brief_version_id,
        )
        .first()
        if decision.brief_version_id
        else None
    )
    checks = rules.verification_checks(
        record={
            "decision": record.decision,
            "remarks": record.remarks,
            "object_version": record.object_version,
            "content_fingerprint": record.content_fingerprint,
            "signature_hash": record.signature_hash,
            "signer_user_id": record.signer_user_id,
            "status": record.status,
        },
        decision={
            "id": decision.id,
            "outcome": decision.outcome,
            "rationale": decision.rationale,
            "conditions": decision.conditions,
            "follow_up_actions": decision.follow_up_actions or [],
            "brief_version_id": decision.brief_version_id,
            "evidence_set_hash": decision.evidence_set_hash,
            "brief_content_hash": decision.brief_content_hash,
        },
        snapshot=snapshot.snapshot if snapshot is not None else None,
        snapshot_found=snapshot is not None and str(snapshot.decision_id) == str(decision.id),
        stored_snapshot_hash=stored_snapshot_hash(decision),
        brief_stored_hash=brief.content_hash if brief is not None else None,
        brief_recomputed_hash=brief_rules.content_hash(brief.content, brief.narrative) if brief is not None else None,
    )
    checks += rules.signer_checks(
        signer_user_id=record.signer_user_id,
        signer_role_label=role_label(record.signer_role),
        authority_id=decision.approval_authority_id,
        author_refs=brief_author_refs(db, brief) if brief is not None else (),
    )
    return {"status": rules.verification_status(checks), "checks": checks}


def signature_valid(db: Session, record: SignedApprovalRecord, decision: Decision) -> bool:
    """True when a CASE_DECISION signature still verifies (used by the governance signature verification)."""
    return verify_signature(db, record, decision)["status"] == "VALID"


# ---------------------------------------------------------------------------------------------------- follow-ups


def follow_ups(db: Session, decision: Decision) -> list[DecisionFollowUp]:
    return (
        db.query(DecisionFollowUp)
        .filter(DecisionFollowUp.tenant_id == decision.tenant_id, DecisionFollowUp.decision_id == decision.id)
        .order_by(DecisionFollowUp.created_at, DecisionFollowUp.business_id)
        .all()
    )


def follow_up_view(row: DecisionFollowUp, people: dict[str, str], now) -> dict:
    open_ = row.status in ("OPEN", "IN_PROGRESS")
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "action_type": row.action_type,
        "action_label": rules.follow_up_label(row.action_type),
        "title": row.title,
        "status": row.status,
        "assignee_user_id": str(row.assignee_user_id) if row.assignee_user_id else None,
        "assignee_name": people.get(str(row.assignee_user_id)) if row.assignee_user_id else None,
        "assigned_role": row.assigned_role,
        "assigned_role_label": role_label(row.assigned_role),
        "due_at": _iso(row.due_at),
        "overdue": bool(open_ and row.due_at is not None and row.due_at < now),
        "task_id": str(row.task_id) if row.task_id else None,
        "capa_id": str(row.capa_id) if row.capa_id else None,
        "completion_note": row.completion_note,
        "completed_at": _iso(row.completed_at),
        "created_at": _iso(row.created_at),
    }


def record_view(control_db: Session, db: Session, decision: Decision) -> dict:
    """The signed decision record: the decision, its brief, its signature and verification, its snapshot, its
    follow-ups and the decisions it supersedes or is superseded by."""
    tenant_id = decision.tenant_id
    record = signature_record(control_db, decision)
    rows = follow_ups(db, decision)
    people = names(
        control_db,
        tenant_id,
        [decision.decided_by_user_id, *(row.assignee_user_id for row in rows)]
        + ([record.signer_user_id] if record is not None else []),
    )
    briefs = briefs_by_id(db, tenant_id, [decision.brief_version_id])
    brief = briefs.get(str(decision.brief_version_id)) if decision.brief_version_id else None
    case = (
        db.query(Investigation.business_id)
        .filter(Investigation.tenant_id == tenant_id, Investigation.id == decision.investigation_id)
        .first()
    )
    snapshot = context_snapshot(db, decision)
    verification = verify_signature(db, record, decision)
    linked = {}
    for key in ("supersedes_decision_id", "superseded_by_decision_id"):
        value = getattr(decision, key)
        if value:
            other = (
                db.query(Decision.id, Decision.business_id)
                .filter(Decision.tenant_id == tenant_id, Decision.id == value)
                .first()
            )
            linked[key] = {"id": str(value), "business_id": other.business_id if other is not None else None}
    snapshot_data = snapshot.snapshot if snapshot is not None and isinstance(snapshot.snapshot, dict) else {}
    linked_ids = {item["id"]: item["business_id"] for item in linked.values()}
    return {
        "decision": {
            **decision_view(decision, people, briefs, linked_ids),
            "investigation_business_id": case.business_id if case is not None else None,
        },
        "brief": (
            {
                "id": str(brief.id),
                "business_id": brief.business_id,
                "version": brief.version,
                "status": brief.status,
                "content_hash": brief.content_hash,
                "hash_verified": hash_verified(brief),
            }
            if brief is not None
            else None
        ),
        "signature": (
            {
                "id": str(record.id),
                "business_id": record.business_id,
                "signer_user_id": record.signer_user_id,
                "signer_name": people.get(str(record.signer_user_id)),
                "signer_role": record.signer_role,
                "signer_role_label": role_label(record.signer_role),
                "signature_meaning": record.signature_meaning,
                "signed_at": _iso(record.signed_at),
                "fingerprint": rules.short_fingerprint(record.content_fingerprint),
                "fingerprint_full": record.content_fingerprint,
                "status": record.status,
            }
            if record is not None
            else None
        ),
        "verification": verification,
        "snapshot": (
            {
                "id": str(snapshot.id),
                "created_at": _iso(snapshot.created_at),
                "evidence_set_hash": snapshot_data.get("evidence_set_hash"),
                "scope_version": snapshot_data.get("scope_version"),
            }
            if snapshot is not None
            else None
        ),
        "follow_ups": [follow_up_view(row, people, states.now_utc()) for row in rows],
        "supersedes": linked.get("supersedes_decision_id"),
        "superseded_by": linked.get("superseded_by_decision_id"),
    }
