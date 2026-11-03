"""Composing a Decision Brief version from the case's records: the case and its product, the signals it was opened
for, its scope, established facts, the evidence inventory, supporting and contradicting evidence, the hypotheses
(leading and alternatives), open questions and accepted limitations, failure chains, the risk and regulatory reviews,
the AI assistance used, and the readiness checks at composition time.

Nothing here changes data. Each section is read on its own (``readiness.safely``): a section that cannot be read is
recorded as unavailable (``content["unavailable"]``) and blocks submission instead of failing the page.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.case_intelligence import rules as intelligence
from backend.app.case_workflow import readiness, states
from backend.app.decision_brief import rules
from backend.app.signals.logic import display_title

logger = logging.getLogger("mdarix.decision_brief")

# How many rows of a long list a brief keeps (the counts always cover everything).
EVIDENCE_MAX = 500
FACTS_MAX = 150
OBSERVATIONS_SCANNED = 5000
UNKNOWNS_MAX = 200
CHAINS_MAX = 20
COMPLAINTS_MAX = 1000
EXECUTIONS_MAX = 100
ACCEPTED_REVIEW_STATUSES = frozenset({"ACCEPTED", "ACCEPTED_WITH_LIMITATION"})
SET_ASIDE_REVIEW_STATUSES = frozenset({"REJECTED", "QUARANTINED", "SUPERSEDED"})
FACT_TYPES = frozenset({"FACT", "SOURCE_ASSERTION"})
REVIEW_TYPES = {"risk_review": "RISK", "regulatory_review": "REGULATORY"}
CLOSED_REVIEW_STATUSES = ("SUPERSEDED", "CANCELLED")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


# ------------------------------------------------------------------------------------------------- sections


def investigation_section(case) -> dict:
    state = states.case_state(case)
    return {
        "id": str(case.id),
        "business_id": case.business_id,
        "question": case.investigation_question,
        "workflow_state": state,
        "workflow_state_label": states.state_label(state),
        "priority": case.priority,
        "due_at": _iso(case.due_at),
        "opened_at": _iso(case.opened_at),
    }


def product_section(db: Session, case, scope_data: dict | None) -> dict:
    from backend.app.db.models.foundation import Product, ProductVersion

    product = db.query(Product).filter(Product.tenant_id == case.tenant_id, Product.id == case.product_id).first()
    version_ids = [as_uuid(item) for item in (scope_data or {}).get("product_version_ids") or ()]
    version_ids = [item for item in version_ids if item is not None]
    versions = []
    if version_ids:
        versions = [
            {"id": str(row.id), "business_id": row.business_id, "version_identifier": row.version_identifier}
            for row in db.query(ProductVersion)
            .filter(ProductVersion.tenant_id == case.tenant_id, ProductVersion.id.in_(version_ids))
            .order_by(ProductVersion.version_identifier)
        ]
    return {
        "id": str(case.product_id) if case.product_id else None,
        "business_id": product.business_id if product is not None else None,
        "name": product.name if product is not None else None,
        "versions": versions,
    }


def signals_section(db: Session, case) -> list[dict]:
    from backend.app.db.models.signals import InvestigationSignal, Signal

    rows = (
        db.query(Signal)
        .join(
            InvestigationSignal,
            (InvestigationSignal.signal_id == Signal.id) & (InvestigationSignal.tenant_id == Signal.tenant_id),
        )
        .filter(InvestigationSignal.tenant_id == case.tenant_id, InvestigationSignal.investigation_id == case.id)
        .order_by(Signal.business_id)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "title": display_title(row.title, row.origin),
            "priority": row.confirmed_priority or row.suggested_priority,
            "status": row.status,
            "complaint_count": int(row.complaint_count or 0),
        }
        for row in rows
    ]


def scope_section(db: Session, case, data: dict) -> dict:
    from backend.app.case_workflow import scope

    refs = scope.references(db, case.tenant_id, [data])
    complaints = refs["complaints"]

    def complaint(item) -> dict:
        row = complaints.get(str(item))
        return {
            "id": str(item),
            "business_id": row.business_id if row is not None else None,
            "complaint_identifier": row.complaint_identifier if row is not None else None,
        }

    included = list(data.get("included_complaint_ids") or ())
    excluded = list(data.get("excluded_complaints") or ())
    versions = refs["versions"]
    return {
        "version": data.get("version") or 0,
        "question": data.get("question"),
        "included_count": len(included),
        "included": [complaint(item) for item in included[:COMPLAINTS_MAX]],
        "excluded_count": len(excluded),
        "excluded": [
            {**complaint(item.get("complaint_id")), "reason": item.get("reason")} for item in excluded[:COMPLAINTS_MAX]
        ],
        "product_versions": [
            {
                "id": str(item),
                "business_id": versions[str(item)].business_id if str(item) in versions else None,
                "version_identifier": versions[str(item)].version_identifier if str(item) in versions else None,
            }
            for item in data.get("product_version_ids") or ()
        ],
        "markets": list(data.get("markets") or ()),
        "date_from": _iso(data.get("date_from")),
        "date_to": _iso(data.get("date_to")),
        "objectives": data.get("objectives"),
    }


def evidence_rows(db: Session, case) -> list[dict]:
    """The case's evidence (inventory rules of the evidence workflow) as flat rows, newest first."""
    from backend.app.evidence_workflow.inventory import inventory_items

    rows = []
    for item in inventory_items(db, None, case.tenant_id, case):
        evidence, link = item["evidence"], item["link"]
        rows.append(
            {
                "id": evidence["id"],
                "business_id": evidence["business_id"],
                "evidence_identifier": evidence["evidence_identifier"],
                "title": evidence["title"],
                "evidence_type": evidence["evidence_type"],
                "review_status": link["review_status"],
                "review_status_label": link["review_status_label"],
                "relationship": link["relationship"],
                "relationship_label": link["relationship_label"],
                "limitation": link.get("limitation"),
                "origin": item["origin"],
            }
        )
    return rows


def inventory_section(rows: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    by_relationship: dict[str, int] = {}
    for row in rows:
        by_status[row["review_status"]] = by_status.get(row["review_status"], 0) + 1
        by_relationship[row["relationship"]] = by_relationship.get(row["relationship"], 0) + 1
    return {
        "total": len(rows),
        "by_review_status": by_status,
        "by_relationship": by_relationship,
        "items": rows[:EVIDENCE_MAX],
        "truncated": len(rows) > EVIDENCE_MAX,
    }


def facts_section(db: Session, case, rows: list[dict]) -> list[dict]:
    """Facts and source assertions observed in the case's evidence (not set aside), and summaries of the evidence the
    case accepted. Never an AI interpretation."""
    from sqlalchemy import or_

    from backend.app.db.models.evidence_intelligence import EvidenceObservation

    by_id = {row["id"]: row for row in rows}
    usable = [as_uuid(key) for key, row in by_id.items() if row["review_status"] not in SET_ASIDE_REVIEW_STATUSES]
    clauses = [EvidenceObservation.investigation_id == case.id]
    if usable:
        clauses.append(EvidenceObservation.evidence_id.in_(usable))
    facts: list[dict] = []
    for observation in (
        db.query(EvidenceObservation)
        .filter(EvidenceObservation.tenant_id == case.tenant_id, or_(*clauses))
        .order_by(EvidenceObservation.created_at, EvidenceObservation.id)
        .limit(OBSERVATIONS_SCANNED)
    ):
        evidence = by_id.get(str(observation.evidence_id))
        if evidence is not None and evidence["review_status"] in SET_ASIDE_REVIEW_STATUSES:
            continue
        kind = intelligence.observation_kind(
            observation.epistemic_type, observation.observation_type, observation.extraction_method
        )
        if kind not in FACT_TYPES:
            continue
        facts.append(
            {
                "kind": "OBSERVATION",
                "statement": observation.statement,
                "epistemic_type": kind,
                "epistemic_label": intelligence.epistemic_label(kind),
                "origin": intelligence.observation_origin(observation.origin, observation.extraction_method),
                "evidence_business_id": evidence["business_id"] if evidence is not None else None,
            }
        )
        if len(facts) >= FACTS_MAX:
            break
    for row in rows:
        if row["review_status"] not in ACCEPTED_REVIEW_STATUSES:
            continue
        facts.append(
            {
                "kind": "EVIDENCE",
                "statement": row["title"],
                "epistemic_type": "ACCEPTED_EVIDENCE",
                "epistemic_label": row["review_status_label"],
                "origin": "HUMAN",
                "evidence_business_id": row["business_id"],
                "limitation": row.get("limitation"),
            }
        )
    return facts


def hypotheses_rows(db: Session, case) -> tuple[list[dict], list[dict]]:
    """Every hypothesis of the case with its supporting and contradicting evidence counts (links not withdrawn), and
    the evidence links of those still considered."""
    from backend.app.db.models.foundation import Evidence, Hypothesis, HypothesisEvidence

    hypotheses = (
        db.query(Hypothesis)
        .filter(Hypothesis.tenant_id == case.tenant_id, Hypothesis.investigation_id == case.id)
        .order_by(Hypothesis.business_id)
        .all()
    )
    ids = [row.id for row in hypotheses]
    links = []
    if ids:
        links = (
            db.query(HypothesisEvidence, Evidence.business_id, Evidence.title)
            .join(
                Evidence,
                (Evidence.id == HypothesisEvidence.evidence_id) & (Evidence.tenant_id == HypothesisEvidence.tenant_id),
            )
            .filter(
                HypothesisEvidence.tenant_id == case.tenant_id,
                HypothesisEvidence.hypothesis_id.in_(ids),
                HypothesisEvidence.retracted_at.is_(None),
            )
            .order_by(HypothesisEvidence.created_at, HypothesisEvidence.id)
            .all()
        )
    counts: dict = {row.id: {"support": 0, "contradict": 0} for row in hypotheses}
    for link, _, _ in links:
        relation = str(link.relation_type or "").lower()
        if relation in ("support", "contradict"):
            counts[link.hypothesis_id][relation] += 1
    items = []
    by_id = {}
    for row in hypotheses:
        human_status = str(row.human_status or "").upper() or None
        item = {
            "id": str(row.id),
            "business_id": row.business_id,
            "statement": row.statement,
            "origin": intelligence.origin_code(row.origin),
            "ai_status": str(row.status or "").lower() or None,
            "ai_status_label": intelligence.ai_status_label(row.status),
            "human_status": human_status,
            "human_status_label": intelligence.human_status_label(human_status),
            "status_reason": row.status_reason,
            "kind_label": intelligence.kind_label(row.origin, human_status),
            "supporting_count": counts[row.id]["support"],
            "contradicting_count": counts[row.id]["contradict"],
        }
        items.append(item)
        by_id[row.id] = item
    considered_links = []
    for link, business_id, title in links:
        hypothesis = by_id.get(link.hypothesis_id)
        if hypothesis is None or not rules.considered(hypothesis):
            continue
        considered_links.append(
            {
                "relation": str(link.relation_type or "").lower(),
                "evidence_business_id": business_id,
                "title": title,
                "hypothesis_business_id": hypothesis["business_id"],
                "rationale": link.rationale,
                "linked_by": "HUMAN" if intelligence.link_is_human(link.created_by_type) else "AI",
            }
        )
    return items, considered_links


def evidence_for_and_against(
    rows: list[dict], links: list[dict], leading: str | None = None
) -> tuple[list[dict], list[dict]]:
    """Supporting and contradicting evidence, for and against the leading explanation, each piece of evidence once.

    The case's own judgement of its evidence, then the links to the leading hypothesis (``leading``, its business ID),
    which replace the case's judgement of the same evidence (they say why). A link to another hypothesis stays on that
    hypothesis (0.10.72: listed here, the same evidence read twice, and as both supporting and contradicting, when it
    supports the leading explanation and contradicts an alternative). Without a leading hypothesis every link counts,
    the first one per evidence."""
    found: dict[str, tuple[str, dict]] = {}
    for row in rows:
        side = {"SUPPORTING": "for", "CONTRADICTING": "against"}.get(row["relationship"])
        if side is not None:
            found[row["business_id"]] = (
                side,
                {
                    "source": "CASE",
                    "evidence_business_id": row["business_id"],
                    "title": row["title"],
                    "review_status": row["review_status"],
                    "hypothesis_business_id": None,
                    "rationale": None,
                    "linked_by": "HUMAN",
                },
            )
    for link in links:
        side = {"support": "for", "contradict": "against"}.get(link["relation"])
        key = link["evidence_business_id"]
        if side is None or (leading and link["hypothesis_business_id"] != leading):
            continue
        if key in found and found[key][1]["source"] == "HYPOTHESIS":
            continue
        found[key] = (
            side,
            {
                "source": "HYPOTHESIS",
                "evidence_business_id": key,
                "title": link["title"],
                "review_status": None,
                "hypothesis_business_id": link["hypothesis_business_id"],
                "rationale": link["rationale"],
                "linked_by": link["linked_by"],
            },
        )
    supporting = [item for side, item in found.values() if side == "for"]
    contradicting = [item for side, item in found.values() if side == "against"]
    return supporting[:EVIDENCE_MAX], contradicting[:EVIDENCE_MAX]


def unknowns_section(db: Session, case) -> dict:
    from backend.app.db.models.foundation import Unknown

    open_items: list[dict] = []
    accepted: list[dict] = []
    resolved = 0
    for row in (
        db.query(Unknown)
        .filter(Unknown.tenant_id == case.tenant_id, Unknown.investigation_id == case.id)
        .order_by(Unknown.business_id)
    ):
        status = str(row.status or "open").lower()
        item = {
            "business_id": row.business_id,
            "description": row.description,
            "category": row.category,
            "evidence_needed": row.evidence_needed,
            "status": status,
            "status_label": intelligence.unknown_status_label(status),
            "origin": intelligence.plain_origin(row.origin),
        }
        if status == intelligence.UNKNOWN_ACCEPTED_LIMITATION:
            accepted.append({**item, "resolution": row.resolution})
        elif readiness.unknown_is_open(status):
            open_items.append(item)
        else:
            resolved += 1
    return {
        "open": open_items[:UNKNOWNS_MAX],
        "accepted_limitations": accepted[:UNKNOWNS_MAX],
        "open_count": len(open_items),
        "accepted_limitation_count": len(accepted),
        "closed_count": resolved,
    }


def chains_section(db: Session, case) -> list[dict]:
    from backend.app.db.models.foundation import Evidence, FailureChain, FailureChainEdge, FailureChainNode

    chains = (
        db.query(FailureChain)
        .filter(
            FailureChain.tenant_id == case.tenant_id,
            FailureChain.investigation_id == case.id,
            FailureChain.status != "superseded",
        )
        .order_by(FailureChain.business_id)
        .limit(CHAINS_MAX)
        .all()
    )
    ids = [chain.id for chain in chains]
    if not ids:
        return []
    nodes = {
        node.id: node
        for node in db.query(FailureChainNode).filter(
            FailureChainNode.tenant_id == case.tenant_id, FailureChainNode.failure_chain_id.in_(ids)
        )
    }
    edges = (
        db.query(FailureChainEdge)
        .filter(FailureChainEdge.tenant_id == case.tenant_id, FailureChainEdge.failure_chain_id.in_(ids))
        .order_by(FailureChainEdge.created_at, FailureChainEdge.id)
        .all()
    )
    evidence_ids = [edge.evidence_id for edge in edges if edge.evidence_id]
    evidence = (
        dict(
            db.query(Evidence.id, Evidence.business_id).filter(
                Evidence.tenant_id == case.tenant_id, Evidence.id.in_(evidence_ids)
            )
        )
        if evidence_ids
        else {}
    )
    result = []
    for chain in chains:
        chain_nodes = sorted(
            (node for node in nodes.values() if node.failure_chain_id == chain.id),
            key=lambda node: node.sequence_number,
        )
        links = []
        for edge in edges:
            if edge.failure_chain_id != chain.id:
                continue
            state = intelligence.link_state(edge.edge_status)
            source, target = nodes.get(edge.from_node_id), nodes.get(edge.to_node_id)
            links.append(
                {
                    "from": source.label if source is not None else None,
                    "to": target.label if target is not None else None,
                    "state": state,
                    "state_label": intelligence.link_state_label(state),
                    "evidence_business_id": evidence.get(edge.evidence_id) if edge.evidence_id else None,
                    "rationale": edge.rationale,
                }
            )
        states_count: dict[str, int] = {}
        for link in links:
            states_count[link["state"]] = states_count.get(link["state"], 0) + 1
        result.append(
            {
                "business_id": chain.business_id,
                "name": chain.name,
                "status": chain.status,
                "origin": intelligence.chain_origin(chain.origin),
                "origin_label": intelligence.chain_origin_label(chain.origin),
                "nodes": [node.label for node in chain_nodes],
                "links": links,
                "link_states": states_count,
            }
        )
    return result


def latest_reviews(db: Session, control_db, case) -> dict[str, dict | None]:
    """``{"RISK": review, "REGULATORY": review}``: the latest review of each type that is not superseded or
    cancelled, with the reviewer's name."""
    from backend.app.db.models.reviews import CaseReview

    rows = (
        db.query(CaseReview)
        .filter(
            CaseReview.tenant_id == case.tenant_id,
            CaseReview.investigation_id == case.id,
            CaseReview.status.notin_(CLOSED_REVIEW_STATUSES),
        )
        .order_by(CaseReview.created_at.desc(), CaseReview.business_id.desc())
        .all()
    )
    latest: dict[str, object] = {}
    for row in rows:
        latest.setdefault(str(row.review_type or "").upper(), row)
    names = _names(control_db, case.tenant_id, [row.reviewer_user_id for row in latest.values()])
    result: dict[str, dict | None] = {}
    for review_type in ("RISK", "REGULATORY"):
        row = latest.get(review_type)
        result[review_type] = (
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "status": row.status,
                "outcome": row.outcome,
                "rationale": row.rationale,
                "required_by_policy": bool(row.required_by_policy),
                "reviewer_name": names.get(str(row.reviewer_user_id)) if row.reviewer_user_id else None,
                "reviewer_role": row.reviewer_role,
                "completed_at": _iso(row.completed_at),
                "scope_version": row.scope_version,
            }
            if row is not None
            else None
        )
    return result


def ai_executions(db: Session, case) -> list[dict]:
    from backend.app.db.models.foundation import AIExecution

    rows = (
        db.query(AIExecution)
        .filter(AIExecution.tenant_id == case.tenant_id, AIExecution.investigation_id == case.id)
        .order_by(AIExecution.execution_timestamp, AIExecution.business_id)
        .limit(EXECUTIONS_MAX)
        .all()
    )
    return [
        {
            "business_id": row.business_id,
            "kind": rules.ai_kind(row.provider, row.prompt_template_version),
            "provider": row.provider,
            "model": row.model_name,
            "model_version": row.model_version,
            "created_at": _iso(row.execution_timestamp),
        }
        for row in rows
    ]


def latest_ai_brief(db: Session, case):
    """The case's latest brief from investigation_briefs (GET .../briefs/latest), else None."""
    from backend.app.db.models.foundation import InvestigationBrief

    return (
        db.query(InvestigationBrief)
        .filter(InvestigationBrief.tenant_id == case.tenant_id, InvestigationBrief.investigation_id == case.id)
        .order_by(InvestigationBrief.brief_version.desc())
        .first()
    )


def _names(control_db, tenant_id, refs) -> dict[str, str]:
    if control_db is None:
        return {}
    from backend.app.workflow.people import names_by_id

    try:
        return names_by_id(control_db, tenant_id, refs)
    except Exception:
        logger.warning("Names for the decision brief could not be read", exc_info=True)
        return {}


# ---------------------------------------------------------------------------------------------------- compose


def case_readiness(db: Session, case) -> dict:
    """The case's steps and checks right now (backend/app/case_workflow/readiness.py)."""
    return readiness.evaluate(readiness.case_facts(db, case))


def compose(db: Session, control_db, case, *, now: datetime, ai_draft_used: bool = False) -> tuple[dict, dict]:
    """``(content, readiness)`` of the case as its records stand at ``now``. Content is plain JSON data."""
    from backend.app.case_workflow import scope

    unavailable: list[str] = []

    def read(name: str, step, default):
        value = readiness.safely(db, f"decision brief {name}", step, default=None)
        if value is None:
            unavailable.append(name)
            return default
        return value

    state = case_readiness(db, case)
    checks = {check["key"]: check for check in state.get("checks") or ()}
    scope_data = read("scope", lambda session: scope.current_scope(session, case), {})
    rows = read("evidence", lambda session: evidence_rows(session, case), [])
    hypotheses, links = read("hypotheses", lambda session: hypotheses_rows(session, case), ([], []))
    leading = rules.leading_hypothesis(hypotheses)
    supporting, contradicting = evidence_for_and_against(rows, links, (leading or {}).get("business_id"))
    reviews = read("reviews", lambda session: latest_reviews(session, control_db, case), {})
    executions = read("ai executions", lambda session: ai_executions(session, case), [])
    content = {
        "investigation": investigation_section(case),
        "product": read("product", lambda session: product_section(session, case, scope_data), {}),
        "signals": read("signals", lambda session: signals_section(session, case), []),
        "scope": read("scope details", lambda session: scope_section(session, case, scope_data), {})
        if scope_data
        else {},
        "established_facts": read("facts", lambda session: facts_section(session, case, rows), []),
        "evidence_inventory": inventory_section(rows),
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "leading_hypothesis": leading,
        "leading_hypothesis_rule": (
            "The hypothesis a person judged strongly (else partially) supported with the most supporting evidence; "
            "never chosen from the AI's own status"
        ),
        "alternative_hypotheses": rules.alternative_hypotheses(hypotheses, leading),
        "unknowns": read("unknowns", lambda session: unknowns_section(session, case), {}),
        "failure_chains": read("failure chains", lambda session: chains_section(session, case), []),
        "risk_review": rules.review_section((reviews or {}).get("RISK"), checks.get("risk_review")),
        "regulatory_review": rules.review_section((reviews or {}).get("REGULATORY"), checks.get("regulatory_review")),
        "ai_assistance": {
            "executions": executions,
            "ai_draft_used": bool(ai_draft_used),
            "statement": rules.ai_statement(executions, ai_draft_used=ai_draft_used),
        },
        "readiness": list(state.get("checks") or ()),
        "context": {
            "as_of": now.isoformat(),
            "composed_at": now.isoformat(),
            "scope_version": (scope_data or {}).get("version") or 0,
            "evidence_set_hash": rules.evidence_set_hash(
                (row["id"], row["review_status"], row["relationship"]) for row in rows
            ),
        },
        "unavailable": sorted(set(unavailable)),
    }
    return rules.jsonable(content), rules.jsonable(state)
