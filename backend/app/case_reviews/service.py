"""Case reviews in the database: the facts the review policy reads, requesting a review, restarting reviews when the
scope changes, the readiness facts, the Review JSON and what a reviewer needs to see (the review context).

Nothing here commits; the routers do (and the scope save, for ``restart_reviews``). Reads that may fail on an older
organization database (signals, intelligence) are read inside a SAVEPOINT and fall back to nothing.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.case_reviews import rules
from backend.app.case_workflow import readiness, scope, states
from backend.app.db.models.foundation import Complaint, Investigation, Product, Risk
from backend.app.db.models.reviews import CaseReview
from backend.app.enterprise_audit import make_audit_event

logger = logging.getLogger("mdarix.case_reviews")

ENTITY = "CaseReview"
TEXT_SHORT = 300


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _short(value, limit: int = TEXT_SHORT) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def case_is_open(case: Investigation) -> bool:
    return states.case_state(case) not in states.CLOSED_STATES


# ------------------------------------------------------------------------------------------------------ policy


def scope_complaint_ids(db: Session, case: Investigation) -> list[str]:
    """The complaints included in the case's current scope (its linked complaints before any scope was saved)."""
    return list(scope.current_scope(db, case).get("included_complaint_ids") or ())


def scope_complaints(db: Session, case: Investigation) -> list[Complaint]:
    ids = wanted_ids(scope_complaint_ids(db, case))
    if not ids:
        return []
    return (
        db.query(Complaint)
        .filter(Complaint.tenant_id == case.tenant_id, Complaint.id.in_(list(ids)))
        .order_by(Complaint.business_id)
        .all()
    )


def linked_signals(db: Session, case: Investigation) -> list[dict]:
    """The signals the case was opened for, as ``{"id", "business_id", "serious_harm"}``; none when they cannot be
    read (an organization database without signals)."""

    def read(session: Session) -> list[dict]:
        from backend.app.db.models.signals import InvestigationSignal, Signal

        rows = (
            session.query(Signal.id, Signal.business_id, Signal.serious_harm)
            .join(
                InvestigationSignal,
                (InvestigationSignal.signal_id == Signal.id) & (InvestigationSignal.tenant_id == Signal.tenant_id),
            )
            .filter(InvestigationSignal.tenant_id == case.tenant_id, InvestigationSignal.investigation_id == case.id)
            .order_by(Signal.business_id)
            .all()
        )
        return [
            {"id": str(row_id), "business_id": business_id, "serious_harm": bool(harm)}
            for row_id, business_id, harm in rows
        ]

    return readiness.safely(db, "linked signals", read, default=[]) or []


def policy_for_case(db: Session, case: Investigation) -> dict:
    """``{"risk": {"required", "reasons"}, "regulatory": {...}}`` of the case now (backend/app/case_reviews/rules.py)."""
    complaints = [
        {"serious_injury": row.serious_injury, "death": row.death, "malfunction": row.malfunction}
        for row in scope_complaints(db, case)
    ]
    return rules.review_policy(case.priority, complaints, linked_signals(db, case))


# ------------------------------------------------------------------------------------------------------ reading


def current_reviews(db: Session, case: Investigation) -> list[CaseReview]:
    """The case's requested, in-progress and completed reviews, newest first."""
    return (
        db.query(CaseReview)
        .filter(
            CaseReview.tenant_id == case.tenant_id,
            CaseReview.investigation_id == case.id,
            CaseReview.status.in_(rules.CURRENT_STATUSES),
        )
        .order_by(CaseReview.created_at.desc(), CaseReview.business_id.desc())
        .all()
    )


def open_review(db: Session, case: Investigation, review_type: str) -> CaseReview | None:
    return (
        db.query(CaseReview)
        .filter(
            CaseReview.tenant_id == case.tenant_id,
            CaseReview.investigation_id == case.id,
            CaseReview.review_type == review_type,
            CaseReview.status.in_(rules.OPEN_STATUSES),
        )
        .order_by(CaseReview.created_at.desc())
        .first()
    )


def open_review_types(db: Session, case: Investigation) -> set[str]:
    return {
        row[0]
        for row in db.query(CaseReview.review_type).filter(
            CaseReview.tenant_id == case.tenant_id,
            CaseReview.investigation_id == case.id,
            CaseReview.status.in_(rules.OPEN_STATUSES),
        )
    }


def review_facts(db: Session, case: Investigation) -> dict:
    """What readiness needs of each review type: ``{"RISK": {"required", "reasons", "latest"}, "REGULATORY": ...}``
    where ``latest`` is the newest requested, in-progress or completed review (``{"business_id", "status",
    "outcome"}``) or None. Cancelled and superseded reviews do not count."""
    policy = policy_for_case(db, case)
    latest: dict[str, dict] = {}
    for row in current_reviews(db, case):
        if row.review_type not in latest:
            latest[row.review_type] = {"business_id": row.business_id, "status": row.status, "outcome": row.outcome}
    return {
        code: {
            "required": bool(policy[key]["required"]),
            "reasons": list(policy[key]["reasons"]),
            "latest": latest.get(code),
        }
        for code, key in rules.TYPE_KEYS.items()
    }


# ------------------------------------------------------------------------------------------------------ writing


def audit(
    db: Session,
    row: CaseReview,
    action: str,
    *,
    actor_ref: str | None,
    actor_role: str | None,
    now: datetime,
    correlation_id: str | None = None,
    reason: str | None = None,
    details: dict | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> None:
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=str(actor_ref) if actor_ref else "system",
            action=action,
            entity_type=ENTITY,
            entity_id=row.id,
            correlation_id=correlation_id,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
            details={
                "investigation_id": str(row.investigation_id),
                "review_type": row.review_type,
                "status": row.status,
                "actor_role": actor_role,
                **dict(details or {}),
            },
            created_at=now,
        )
    )


def create_review(
    db: Session,
    case: Investigation,
    *,
    review_type: str,
    actor_ref: str,
    actor_role: str | None,
    reason: str | None = None,
    due_at: datetime | None = None,
    brief_version_id=None,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> CaseReview:
    """A REQUESTED review of the case, with what the policy says and the current scope version, audited
    (CASE_REVIEW_REQUESTED). The caller holds the case row lock (one open review per type) and commits, then calls
    ``hooks.on_review_requested`` for the reviewers' queue task. 409 when the case is closed or a review of the type
    is already open."""
    code = rules.review_type_code(review_type)
    if code is None:
        raise error(422, "UNKNOWN_REVIEW_TYPE", f"Choose one of: {', '.join(rules.TYPE_LABELS)}")
    if not case_is_open(case):
        raise error(409, "INVESTIGATION_CLOSED", "This investigation is closed; reopen it first")
    existing = open_review(db, case, code)
    if existing is not None:
        raise error(
            409,
            "REVIEW_ALREADY_OPEN",
            f"{rules.TYPE_LABELS[code]} {existing.business_id} is already open on this case",
            review_id=str(existing.id),
        )
    now = now or now_utc()
    policy = policy_for_case(db, case)[rules.TYPE_KEYS[code]]
    version = scope.current_scope(db, case).get("version")
    row = CaseReview(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        review_type=code,
        status="REQUESTED",
        required_by_policy=bool(policy["required"]),
        policy_reasons=list(policy["reasons"]),
        requested_by=str(actor_ref),
        requested_role=actor_role,
        request_reason=reason,
        scope_version=int(version) if version is not None else None,
        brief_version_id=as_uuid(brief_version_id),
        due_at=rules.as_utc(due_at),
        assessed={},
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        row,
        "CASE_REVIEW_REQUESTED",
        actor_ref=actor_ref,
        actor_role=actor_role,
        now=now,
        correlation_id=correlation_id,
        reason=reason,
        details={
            "required_by_policy": row.required_by_policy,
            "policy_reasons": row.policy_reasons,
            "scope_version": row.scope_version,
            "due_at": _iso(row.due_at),
            "brief_version_id": str(row.brief_version_id) if row.brief_version_id else None,
        },
    )
    return row


def restart_reviews(
    db: Session,
    case: Investigation,
    *,
    version: int,
    actor_ref: str | None,
    actor_role: str | None = None,
    now: datetime | None = None,
    correlation_id: str | None = None,
) -> int:
    """A scope version saved with "reviews must restart": the case's requested, in-progress and completed reviews are
    SUPERSEDED ("Scope changed in version N"), audited (CASE_REVIEW_SUPERSEDED), and their open tasks superseded.
    Runs inside a SAVEPOINT of the caller's transaction (the scope save commits it) and never fails it: an error is
    logged and nothing of this step is kept. Returns how many reviews were superseded."""
    from backend.app.workflow import tasks

    try:
        with db.begin_nested():
            rows = (
                db.query(CaseReview)
                .filter(
                    CaseReview.tenant_id == case.tenant_id,
                    CaseReview.investigation_id == case.id,
                    CaseReview.status.in_(rules.CURRENT_STATUSES),
                )
                .order_by(CaseReview.created_at)
                .with_for_update()
                .all()
            )
            moment = now or now_utc()
            reason = f"Scope changed in version {version}"
            for row in rows:
                before = row.status
                row.status = "SUPERSEDED"
                row.superseded_reason = reason
                row.updated_at = moment
                audit(
                    db,
                    row,
                    "CASE_REVIEW_SUPERSEDED",
                    actor_ref=actor_ref,
                    actor_role=actor_role,
                    now=moment,
                    correlation_id=correlation_id,
                    reason=reason,
                    old_values={"status": before},
                    new_values={"status": "SUPERSEDED"},
                    details={"scope_version": version, "reviewed_scope_version": row.scope_version},
                )
            if rows:
                db.flush()
            for row in rows:
                tasks.supersede_tasks(
                    db,
                    case.tenant_id,
                    source_type=rules.SOURCE_TYPE,
                    source_id=row.id,
                    task_types=None,
                    outcome="SCOPE_CHANGED",
                    actor_ref=actor_ref or tasks.SYSTEM_ACTOR,
                    actor_role=actor_role,
                    reason=reason,
                    correlation_id=correlation_id,
                )
            return len(rows)
    except Exception:
        logger.exception("Reviews of case %s could not be restarted after scope version %s", case.id, version)
        return 0


# ------------------------------------------------------------------------------------------------ serialization


def _names(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    if control_db is None:
        return {}
    from backend.app.workflow.people import names_by_id

    try:
        return names_by_id(control_db, tenant_id, refs)
    except Exception:
        logger.warning("Names of reviewers could not be read", exc_info=True)
        return {}


def _name(names: dict[str, str], ref) -> str | None:
    key = as_uuid(ref)
    return names.get(str(key)) if key is not None else None


def open_tasks_by_review(db: Session, tenant_id, review_ids) -> dict[str, list]:
    """``{review id: [open task]}`` of the reviews (the queue task, a follow-up ...)."""
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask

    ids = wanted_ids(review_ids)
    if not ids:
        return {}
    found: dict[str, list] = defaultdict(list)
    for task in db.query(WorkflowTask).filter(
        WorkflowTask.tenant_id == as_uuid(tenant_id),
        WorkflowTask.source_entity_type == rules.SOURCE_TYPE,
        WorkflowTask.source_entity_id.in_(list(ids)),
        WorkflowTask.status.in_(OPEN_TASK_STATUSES),
    ):
        found[str(task.source_entity_id)].append(task)
    return found


def review_task(tasks_of_review: list, review: CaseReview):
    """The open queue task of the review (its type's task), else None."""
    wanted = rules.TYPE_TASKS.get(review.review_type)
    return next((task for task in tasks_of_review if task.task_type == wanted), None)


def task_taken_by_other(task, person) -> bool:
    return task is not None and task.assigned_user_id is not None and not person.is_user(task.assigned_user_id)


def _assessed_view(assessed: dict | None, risks: dict[str, Risk]) -> dict:
    data = dict(assessed or {}) if isinstance(assessed, dict) else {}
    risk_ids = [str(item) for item in data.get("risk_ids") or ()]
    return {
        "risk_ids": risk_ids,
        "risks": [
            {
                "id": item,
                "business_id": risks[item].business_id if item in risks else None,
                "risk_identifier": risks[item].risk_identifier if item in risks else None,
                "title": _short(risks[item].description, 160) if item in risks else None,
            }
            for item in risk_ids
        ],
        "markets": list(data.get("markets") or ()),
        "notes": data.get("notes"),
    }


def serialize_reviews(db: Session, control_db: Session | None, person, rows: list[CaseReview]) -> list[dict]:
    """The Review JSON of each row, with cases, products, names, assessed risks and tasks read in bulk. ``person`` is
    the signed-in person (backend/app/evidence_workflow/people.py) whose actions are given."""
    from backend.app.access.permissions import INVESTIGATION_ASSIGN
    from backend.app.workflow.labels import role_label

    if not rows:
        return []
    now = now_utc()
    tenant_id = rows[0].tenant_id
    cases = {
        str(row.id): row
        for row in db.query(Investigation).filter(
            Investigation.tenant_id == tenant_id,
            Investigation.id.in_(list({row.investigation_id for row in rows})),
        )
    }
    product_ids = {case.product_id for case in cases.values() if case.product_id}
    products = (
        {
            str(row.id): row
            for row in db.query(Product).filter(Product.tenant_id == tenant_id, Product.id.in_(list(product_ids)))
        }
        if product_ids
        else {}
    )
    risk_ids = wanted_ids(
        item
        for row in rows
        for item in ((row.assessed or {}).get("risk_ids") or () if isinstance(row.assessed, dict) else ())
    )
    risks = (
        {str(row.id): row for row in db.query(Risk).filter(Risk.tenant_id == tenant_id, Risk.id.in_(list(risk_ids)))}
        if risk_ids
        else {}
    )
    names = _names(control_db, tenant_id, [ref for row in rows for ref in (row.requested_by, row.reviewer_user_id)])
    tasks = open_tasks_by_review(db, tenant_id, [row.id for row in rows])
    items = []
    for row in rows:
        case = cases.get(str(row.investigation_id))
        product = products.get(str(case.product_id)) if case is not None and case.product_id else None
        permission = rules.TYPE_PERMISSIONS.get(row.review_type)
        is_reviewer = row.reviewer_user_id is not None and person.is_user(row.reviewer_user_id)
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "review_type": row.review_type,
                "review_type_label": rules.type_label(row.review_type),
                "status": row.status,
                "status_label": rules.status_label(row.status),
                "required_by_policy": bool(row.required_by_policy),
                "policy_reasons": list(row.policy_reasons or ()),
                "requested_by_name": _name(names, row.requested_by),
                "requested_role": row.requested_role,
                "request_reason": row.request_reason,
                "reviewer": (
                    {"id": str(row.reviewer_user_id), "name": names.get(str(row.reviewer_user_id))}
                    if row.reviewer_user_id
                    else None
                ),
                "reviewer_role": row.reviewer_role,
                "reviewer_role_label": role_label(row.reviewer_role),
                "outcome": row.outcome,
                "outcome_label": rules.outcome_label(row.outcome),
                "rationale": row.rationale,
                "assessed": _assessed_view(row.assessed, risks),
                "scope_version": row.scope_version,
                "brief_version_id": str(row.brief_version_id) if row.brief_version_id else None,
                "due_at": _iso(row.due_at),
                "overdue": rules.is_overdue(row.status, row.due_at, now),
                "completed_at": _iso(row.completed_at),
                "superseded_reason": row.superseded_reason,
                "investigation": (
                    {
                        "id": str(case.id),
                        "business_id": case.business_id,
                        "question": case.investigation_question,
                        "workflow_state": states.case_state(case),
                        "product": (
                            {"id": str(product.id), "business_id": product.business_id, "name": product.name}
                            if product is not None
                            else None
                        ),
                    }
                    if case is not None
                    else None
                ),
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
                "actions": rules.review_actions(
                    status=row.status,
                    holds_type_permission=person.holds(permission),
                    is_reviewer=is_reviewer,
                    is_requester=person.is_user(row.requested_by),
                    can_assign=person.holds(INVESTIGATION_ASSIGN),
                    case_open=case is not None and case_is_open(case),
                    task_taken_by_other=task_taken_by_other(review_task(tasks.get(str(row.id), []), row), person),
                ),
            }
        )
    return items


# ------------------------------------------------------------------------------------------------------ context


def _product_view(db: Session, case: Investigation) -> dict | None:
    product = (
        db.query(Product).filter(Product.tenant_id == case.tenant_id, Product.id == case.product_id).first()
        if case.product_id
        else None
    )
    if product is None:
        return None
    return {
        "id": str(product.id),
        "business_id": product.business_id,
        "product_identifier": product.product_identifier,
        "name": product.name,
    }


def _risk_register(db: Session, case: Investigation) -> dict:
    from backend.app.risk.service import register

    if not case.product_id:
        return {"items": [], "fields_not_captured": [], "data_notice": None}
    return register(db, case.tenant_id, product_id=case.product_id)


def _failure_modes(db: Session, case: Investigation, register_items: list[dict]) -> list[dict]:
    """The failure modes in the case's scope and those linked to the product's risks, each once."""
    from backend.app.db.models.foundation import FailureMode

    in_scope = {str(item) for item in scope.current_scope(db, case).get("failure_mode_ids") or ()}
    linked = {mode["id"] for item in register_items for mode in item.get("failure_modes") or ()}
    ids = wanted_ids(in_scope | linked)
    if not ids:
        return []
    rows = (
        db.query(FailureMode)
        .filter(FailureMode.tenant_id == case.tenant_id, FailureMode.id.in_(list(ids)))
        .order_by(FailureMode.failure_mode_identifier)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "identifier": row.failure_mode_identifier,
            "name": row.name,
            "title": row.name,
            "description": row.description,
            "in_scope": str(row.id) in in_scope,
            "linked_to_risk": str(row.id) in linked,
        }
        for row in rows
    ]


def _hypotheses(db: Session, case: Investigation) -> dict:
    """The case's current hypotheses with a person's judgement and how much evidence supports and contradicts each
    (withdrawn links left out)."""
    from backend.app.case_intelligence import rules as intelligence
    from backend.app.db.models.foundation import Hypothesis, HypothesisEvidence

    rows = [
        row
        for row in db.query(Hypothesis)
        .filter(Hypothesis.tenant_id == case.tenant_id, Hypothesis.investigation_id == case.id)
        .order_by(Hypothesis.created_at.desc(), Hypothesis.business_id)
        .all()
        if intelligence.counts_toward_case(row.status, row.human_status)
    ]
    counts: dict[uuid.UUID, dict[str, int]] = {row.id: defaultdict(int) for row in rows}
    if rows:
        for hypothesis_id, relation in db.query(
            HypothesisEvidence.hypothesis_id, HypothesisEvidence.relation_type
        ).filter(
            HypothesisEvidence.tenant_id == case.tenant_id,
            HypothesisEvidence.hypothesis_id.in_([row.id for row in rows]),
            HypothesisEvidence.retracted_at.is_(None),
        ):
            counts[hypothesis_id][intelligence.relation_bucket(relation)] += 1
    items = [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "statement": row.statement,
            "origin": intelligence.origin_code(row.origin),
            "human_status": row.human_status,
            "human_status_label": intelligence.human_status_label(row.human_status),
            "status_reason": row.status_reason,
            "supporting": counts[row.id]["supporting"],
            "contradicting": counts[row.id]["contradicting"],
            # The same facts grouped as the review screen reads them.
            "human_judgement": (
                {"status": row.human_status, "label": intelligence.human_status_label(row.human_status)}
                if row.human_status
                else None
            ),
            "evidence_counts": {
                "supporting": counts[row.id]["supporting"],
                "contradicting": counts[row.id]["contradicting"],
            },
        }
        for row in rows
    ]
    return {
        "items": items,
        "contradictions": sum(1 for item in items if item["contradicting"]),
        "contradicting_links": sum(item["contradicting"] for item in items),
    }


def _open_unknowns(db: Session, case: Investigation) -> list[dict]:
    from backend.app.case_intelligence import rules as intelligence
    from backend.app.db.models.foundation import Unknown

    rows = (
        db.query(Unknown)
        .filter(Unknown.tenant_id == case.tenant_id, Unknown.investigation_id == case.id)
        .order_by(Unknown.created_at, Unknown.business_id)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "description": row.description,
            "evidence_needed": row.evidence_needed,
            "status": row.status,
            "status_label": intelligence.unknown_status_label(row.status),
        }
        for row in rows
        if readiness.unknown_is_open(row.status)
    ]


def _failure_chains(db: Session, case: Investigation) -> list[dict]:
    from backend.app.db.models.foundation import FailureChain, FailureChainEdge, FailureChainNode

    chains = (
        db.query(FailureChain)
        .filter(FailureChain.tenant_id == case.tenant_id, FailureChain.investigation_id == case.id)
        .order_by(FailureChain.created_at, FailureChain.business_id)
        .all()
    )
    if not chains:
        return []
    ids = [row.id for row in chains]
    nodes: dict[uuid.UUID, list] = defaultdict(list)
    for node in (
        db.query(FailureChainNode)
        .filter(FailureChainNode.tenant_id == case.tenant_id, FailureChainNode.failure_chain_id.in_(ids))
        .order_by(FailureChainNode.failure_chain_id, FailureChainNode.sequence_number)
    ):
        nodes[node.failure_chain_id].append(node)
    edges: dict[uuid.UUID, list] = defaultdict(list)
    for edge in db.query(FailureChainEdge).filter(
        FailureChainEdge.tenant_id == case.tenant_id, FailureChainEdge.failure_chain_id.in_(ids)
    ):
        edges[edge.failure_chain_id].append(edge)
    return [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "name": row.name,
            "status": row.status,
            "origin": row.origin,
            "steps": [{"sequence": node.sequence_number, "label": node.label} for node in nodes[row.id]],
            "links": len(edges[row.id]),
            "link_states": dict(sorted(_count(edge.edge_status for edge in edges[row.id]).items())),
        }
        for row in chains
    ]


def _count(values) -> dict[str, int]:
    found: dict[str, int] = defaultdict(int)
    for value in values:
        found[str(value or "UNKNOWN").upper()] += 1
    return dict(found)


def _risk_items(items: list[dict]) -> list[dict]:
    """The register's risks, each with a ``title`` (its description, shortened)."""
    return [{**item, "title": _short(item.get("description"), 160)} for item in items]


def _recorded(items: list[dict], field: str) -> list[dict]:
    """Hazards or harms as the risks record them (``field``), with the risk's id (what ``assessed.risk_ids`` names).
    The imported risk records carry none today (``fields_not_captured``): nothing is estimated."""
    return [
        {
            "id": item["id"],
            "business_id": item.get("business_id"),
            "risk_identifier": item.get("risk_identifier"),
            "title": item.get(field),
            field: item.get(field),
        }
        for item in items
        if item.get(field)
    ]


def _controls(items: list[dict]) -> list[dict]:
    """Every control linked to the risks, once, with the risks it controls."""
    found: dict[str, dict] = {}
    for item in items:
        for control in item.get("controls") or ():
            entry = found.setdefault(
                control["id"],
                {
                    **control,
                    "title": _short(control.get("description"), 160),
                    "name": control.get("control_identifier"),
                    "risk_ids": [],
                },
            )
            entry["risk_ids"].append(item["id"])
    return sorted(found.values(), key=lambda control: str(control.get("control_identifier") or ""))


def risk_context(db: Session, case: Investigation) -> dict:
    """What a risk reviewer needs, read only: the product's risk register (risks, hazards and harms as recorded,
    controls), failure modes, hypotheses with people's judgement and their evidence, contradictions, open questions
    and stored failure chains. Each part that cannot be read is empty."""
    register = readiness.safely(db, "risk register", lambda session: _risk_register(session, case), default=None)
    items = _risk_items(list((register or {}).get("items") or ()))
    hypotheses = readiness.safely(db, "hypotheses", lambda session: _hypotheses(session, case), default=None) or {
        "items": [],
        "contradictions": 0,
        "contradicting_links": 0,
    }
    return {
        "type": rules.RISK,
        "product": _product_view(db, case),
        "risks": items,
        "hazards": _recorded(items, "hazard"),
        "harms": _recorded(items, "harm"),
        "controls": _controls(items),
        "fields_not_captured": list((register or {}).get("fields_not_captured") or ()),
        "data_notice": (register or {}).get("data_notice"),
        "failure_modes": readiness.safely(
            db, "failure modes", lambda session: _failure_modes(session, case, items), default=[]
        )
        or [],
        "hypotheses": hypotheses["items"],
        "contradictions": hypotheses["contradictions"],
        "contradictions_count": hypotheses["contradictions"],
        "contradicting_links": hypotheses["contradicting_links"],
        "open_unknowns": readiness.safely(db, "unknowns", lambda session: _open_unknowns(session, case), default=[])
        or [],
        "failure_chains": readiness.safely(
            db, "failure chains", lambda session: _failure_chains(session, case), default=[]
        )
        or [],
    }


def _awareness(row: Complaint):
    """When the organization first knew of a complaint: the earliest of its awareness, received and recorded times."""
    found = [
        rules.as_utc(value) for value in (row.awareness_timestamp, row.complaint_timestamp, row.recorded_timestamp)
    ]
    found = [value for value in found if value is not None]
    return min(found) if found else None


NOT_RECORDED = "Not recorded"


def regulatory_context(db: Session, case: Investigation) -> dict:
    """What a regulatory reviewer needs, read only: the complaints in scope with their country (market), event and
    received dates and serious injury, death and malfunction flags, counts per market and the earliest awareness date.
    MDARIX computes no reporting deadline and never decides reportability."""
    complaints = scope_complaints(db, case)
    per_market: dict[str, dict[str, int]] = {}
    earliest = None
    items = []
    for row in complaints:
        market = " ".join(str(row.country or "").split()) or None
        bucket = per_market.setdefault(
            market or NOT_RECORDED, {"complaints": 0, "serious_injury": 0, "death": 0, "malfunction": 0}
        )
        bucket["complaints"] += 1
        for flag in ("serious_injury", "death", "malfunction"):
            if getattr(row, flag):
                bucket[flag] += 1
        aware = _awareness(row)
        if aware is not None and (earliest is None or aware < earliest[0]):
            earliest = (aware, row)
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "complaint_identifier": row.complaint_identifier,
                "description": _short(row.description),
                "country": row.country,
                "market": market,
                "event_at": _iso(row.event_timestamp),
                "received_at": _iso(row.complaint_timestamp),
                "event_date": _iso(row.event_timestamp),
                "received_date": _iso(row.complaint_timestamp),
                "awareness_at": _iso(row.awareness_timestamp),
                "recorded_at": _iso(row.recorded_timestamp),
                "serious_injury": bool(row.serious_injury),
                "death": bool(row.death),
                "malfunction": bool(row.malfunction),
                "severity": row.severity,
                "complaint_type": row.complaint_type,
                "problem_code": row.problem_code,
                "reporter_type": row.reporter_type,
            }
        )
    return {
        "type": rules.REGULATORY,
        "product": _product_view(db, case),
        "complaints": items,
        "counts": {
            "complaints": len(items),
            "serious_injury": sum(1 for item in items if item["serious_injury"]),
            "death": sum(1 for item in items if item["death"]),
            "malfunction": sum(1 for item in items if item["malfunction"]),
        },
        "markets": [
            {"market": market, **counts}
            for market, counts in sorted(per_market.items(), key=lambda pair: (-pair[1]["complaints"], pair[0]))
        ],
        "counts_by_market": {market: counts["complaints"] for market, counts in per_market.items()},
        "scope_markets": list(scope.current_scope(db, case).get("markets") or ()),
        "earliest_awareness": (
            {
                "at": _iso(earliest[0]),
                "complaint": {"id": str(earliest[1].id), "business_id": earliest[1].business_id},
            }
            if earliest is not None
            else None
        ),
        "earliest_awareness_date": _iso(earliest[0]) if earliest is not None else None,
        # Each complaint's reporting clock against the organization's own windows (the reportability watch, md41):
        # the reviewer sees what is due when; MDARIX still computes no obligation and decides nothing.
        "reporting_clocks": readiness.safely(
            db, "reporting clocks", lambda session: _reporting_clocks(session, case.tenant_id, complaints), default=[]
        )
        or [],
        "note": rules.REGULATORY_NOTE,
    }


def _reporting_clocks(db: Session, tenant_id, complaints: list[Complaint]) -> list[dict]:
    from backend.app.reportability.service import clocks_for

    return clocks_for(db, tenant_id, complaints)


def review_context(db: Session, review: CaseReview) -> dict | None:
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == review.tenant_id, Investigation.id == review.investigation_id)
        .first()
    )
    if case is None:
        return None
    if review.review_type == rules.RISK:
        return risk_context(db, case)
    return regulatory_context(db, case)
