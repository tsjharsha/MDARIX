"""Stage 3 connected-product experience APIs.

These endpoints deliberately return governed summaries and catalogs. They do
not invent conclusions or move business data into the browser; all results
are scoped by the authenticated request context.
"""

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from backend.app.access.trends import daily, window
from backend.app.db.models.foundation import AIExecution
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1", tags=["Stage 3 Experience"])

_COUNT_TABLES = {
    "products": "products",
    "product_versions": "product_versions",
    "complaints": "complaints",
    "investigations": "investigations",
    "evidence": "evidence",
    "decisions": "decisions",
    "audit_events": "audit_events",
}


def _tenant_count(db: Session, table: str, tenant_id: str) -> int:
    """Count only known, fixed table names; tenant_id is always a parameter."""
    try:
        return int(
            db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id}
            ).scalar()
            or 0
        )
    except Exception:
        # Optional domain tables must not make the command center unavailable.
        db.rollback()
        return 0


def _tenant_count_where(db: Session, table: str, clause: str, params: dict) -> int:
    try:
        return int(
            db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id AND {clause}"), params).scalar()
            or 0
        )
    except Exception:
        db.rollback()
        return 0


def _rows(db: Session, query: str, params: dict) -> list[dict]:
    """Return bounded analytics rows; missing optional tables become limitations."""
    try:
        result = db.execute(text(query), params)
        return [dict(row._mapping) for row in result]
    except Exception:
        db.rollback()
        return []


@router.get("/analytics/command-center")
def command_center(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    counts = {name: _tenant_count(db, table, ctx.tenant_id) for name, table in _COUNT_TABLES.items()}
    return {
        "tenant_id": ctx.tenant_id,
        "scope": "TENANT",
        "counts": counts,
        "attention": [
            {"code": "OPEN_INVESTIGATIONS", "count": counts["investigations"], "action": "Review investigations"},
            {"code": "EVIDENCE_AVAILABLE", "count": counts["evidence"], "action": "Review evidence"},
        ],
        "limitations": ["Analytics are bounded to the authenticated tenant and available canonical tables."],
    }


# Daily series for the workspace dashboard: (table, date expression, key expression or None). Fixed SQL only; the
# tenant and the window start are always parameters. Missing optional tables yield an empty series.
_DAILY = {
    "signals": ("complaints", "COALESCE(complaint_timestamp, event_timestamp)", None),
    "investigations_opened": ("investigations", "COALESCE(opened_at, created_at)", None),
    "investigations_closed": ("investigations", "closed_at", None),
    "evidence": ("evidence", "created_at", None),
    "decisions": ("decisions", "COALESCE(decision_timestamp, created_at)", None),
    "ai_runs": ("ai_executions", "execution_timestamp", "(error_state IS NULL)"),
}
_BREAKDOWNS = {
    "signals_by_status": ("complaints", "status"),
    "investigations_by_status": ("investigations", "status"),
    "evidence_by_reliability": ("evidence", "reliability_status"),
    "evidence_by_type": ("evidence", "evidence_type"),
    "decisions_by_status": ("decisions", "decision_status"),
}


@router.get("/analytics/trends")
def workspace_trends(
    days: int = 30,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The tenant's quality work day by day (signals, investigations opened and closed, evidence, decisions, AI
    runs) and how it breaks down by status. Counts only, never record content."""
    days, today, since = window(days)
    params = {"tenant_id": ctx.tenant_id, "since": since}
    series = {}
    for name, (table, column, key) in _DAILY.items():
        group = f", {key} AS k" if key else ""
        rows = _rows(
            db,
            f"SELECT date({column}) AS day{group}, COUNT(*) AS n FROM {table} "
            f"WHERE tenant_id = :tenant_id AND {column} >= :since GROUP BY 1{', 2' if key else ''}",
            params,
        )
        if key:
            points = [(row["day"], "completed" if row["k"] else "failed", row["n"]) for row in rows]
        else:
            points = [(row["day"], "count", row["n"]) for row in rows]
        series[name] = daily(points, days, today)
    breakdowns = {
        name: [
            {"label": row["label"] or "UNKNOWN", "count": int(row["n"])}
            for row in _rows(
                db,
                f"SELECT {column} AS label, COUNT(*) AS n FROM {table} WHERE tenant_id = :tenant_id "
                f"GROUP BY 1 ORDER BY 2 DESC",
                {"tenant_id": ctx.tenant_id},
            )
        ]
        for name, (table, column) in _BREAKDOWNS.items()
    }
    return {"tenant_id": ctx.tenant_id, "days": days, **series, **breakdowns, "scope": "TENANT"}


@router.get("/analytics/signals")
def signals_summary(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    rows = _rows(
        db,
        """
        SELECT complaint_identifier AS signal_id, business_id, description, severity, status, event_timestamp
        FROM complaints WHERE tenant_id = :tenant_id
        ORDER BY event_timestamp DESC NULLS LAST LIMIT 100
    """,
        {"tenant_id": ctx.tenant_id},
    )
    return {
        "tenant_id": ctx.tenant_id,
        "scope": "TENANT",
        "signals": rows,
        "limitations": [
            "Signal clusters are not inferred from complaint rows in this read-only foundation.",
            "Severity and status are returned only when recorded by the source system.",
        ],
    }


@router.get("/signals/{signal_id}")
def signal_detail(
    signal_id: str,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Return one tenant-scoped complaint signal with product/version story context."""
    complaint = _rows(
        db,
        """
        SELECT c.id, c.business_id, c.complaint_identifier AS signal_id, c.description, c.severity, c.status,
               c.event_timestamp, c.complaint_timestamp, c.product_id, c.product_version_id,
               p.business_id AS product_business_id, p.product_identifier, p.name AS product_name,
               pv.business_id AS product_version_business_id, pv.version_identifier
        FROM complaints c
        LEFT JOIN products p ON p.tenant_id = c.tenant_id AND p.id = c.product_id
        LEFT JOIN product_versions pv ON pv.tenant_id = c.tenant_id AND pv.id = c.product_version_id
        WHERE c.tenant_id = :tenant_id
          AND (c.id::text = :signal_id OR c.complaint_identifier = :signal_id OR c.business_id = upper(:signal_id))
        LIMIT 1
    """,
        {"tenant_id": ctx.tenant_id, "signal_id": signal_id},
    )
    if not complaint:
        return {
            "status": "NOT_FOUND",
            "signal_id": signal_id,
            "tenant_id": ctx.tenant_id,
            "message": "Signal is not available for this tenant.",
        }
    row = complaint[0]
    related = _rows(
        db,
        """
        SELECT business_id, investigation_identifier, status, investigation_question
        FROM investigations WHERE tenant_id = :tenant_id
          AND (product_id = :product_id OR (:product_id IS NULL AND false))
        ORDER BY created_at DESC NULLS LAST LIMIT 20
    """,
        {"tenant_id": ctx.tenant_id, "product_id": row.get("product_id")},
    )
    return {
        "status": "READY_FOR_REVIEW",
        "tenant_id": ctx.tenant_id,
        "signal": row,
        "related_investigations": related,
        "interpretation": {
            "observed": "Signal data is source-recorded.",
            "correlation": "Not inferred by this endpoint.",
            "unknown": "Causality is not established.",
            "missing_evidence": "Review source evidence and temporal context before opening an investigation.",
        },
        "human_review_required": True,
    }


# Investigations and evidence carry no product version of their own. A version's investigations are those linked
# (investigation_complaints) to complaints on that version, and (PV-1, the rule Product 360's Overview applies) the
# product's investigations with no version recorded at all, which apply to the whole product; its evidence is what those
# investigations hold, directly (evidence.investigation_id) or linked (investigation_evidence), as the case story counts
# it (_story_counts). Fixed SQL: the tenant, product and version are always parameters, and every subquery is scoped to
# the same tenant.
_ON_VERSION = (
    "EXISTS (SELECT 1 FROM investigation_complaints ic JOIN complaints c ON c.tenant_id = ic.tenant_id "
    "AND c.id = ic.complaint_id WHERE ic.tenant_id = :tenant_id AND ic.investigation_id = i.id "
    "AND c.product_version_id {})"
)
_VERSION_INVESTIGATIONS = (
    "SELECT i.id FROM investigations i WHERE i.tenant_id = :tenant_id AND i.product_id = :product_id AND ("
    + _ON_VERSION.format("= :version_id")
    + " OR NOT "
    + _ON_VERSION.format("IS NOT NULL")
    + ")"
)
_VERSION_INVESTIGATION_CLAUSE = f"id IN ({_VERSION_INVESTIGATIONS})"
_VERSION_EVIDENCE_CLAUSE = (
    f"(investigation_id IN ({_VERSION_INVESTIGATIONS}) OR id IN ("
    "SELECT ie.evidence_id FROM investigation_evidence ie "
    f"WHERE ie.tenant_id = :tenant_id AND ie.investigation_id IN ({_VERSION_INVESTIGATIONS})))"
)


@router.get("/products/{product_id}/versions/{version_id}/story")
def product_version_story(
    product_id: str,
    version_id: str,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Return a dedicated ProductVersion story, bounded to the authenticated tenant."""
    version = _rows(
        db,
        """
        SELECT pv.id, pv.business_id, pv.product_id, pv.version_identifier, pv.description, pv.lifecycle_status,
               pv.release_timestamp, p.business_id AS product_business_id, p.product_identifier, p.name AS product_name
        FROM product_versions pv JOIN products p ON p.tenant_id = pv.tenant_id AND p.id = pv.product_id
        WHERE pv.tenant_id = :tenant_id AND pv.id = :version_id AND pv.product_id = :product_id LIMIT 1
    """,
        {"tenant_id": ctx.tenant_id, "version_id": version_id, "product_id": product_id},
    )
    if not version:
        return {"status": "NOT_FOUND", "product_id": product_id, "version_id": version_id, "tenant_id": ctx.tenant_id}
    params = {"tenant_id": ctx.tenant_id, "version_id": version_id, "product_id": product_id}
    return {
        "status": "READY_FOR_REVIEW",
        "tenant_id": ctx.tenant_id,
        "version": version[0],
        "counts": {
            "complaints": _tenant_count_where(db, "complaints", "product_version_id = :version_id", params),
            "investigations": _tenant_count_where(db, "investigations", _VERSION_INVESTIGATION_CLAUSE, params),
            "evidence": _tenant_count_where(db, "evidence", _VERSION_EVIDENCE_CLAUSE, params),
        },
        "complaints": _rows(
            db,
            "SELECT business_id, complaint_identifier, description, status, event_timestamp FROM complaints WHERE tenant_id=:tenant_id AND product_version_id=:version_id ORDER BY event_timestamp DESC NULLS LAST LIMIT 50",
            params,
        ),
        "investigations": _rows(
            db,
            "SELECT business_id, investigation_identifier, status, investigation_question, "
            f"CASE WHEN {_ON_VERSION.format('IS NOT NULL')} THEN 'VERSION' ELSE 'PRODUCT' END AS applies_to "
            f"FROM investigations i WHERE tenant_id=:tenant_id AND {_VERSION_INVESTIGATION_CLAUSE} "
            "ORDER BY created_at DESC NULLS LAST LIMIT 50",
            params,
        ),
        "evidence": _rows(
            db,
            "SELECT business_id, evidence_identifier, title, evidence_type, reliability_status FROM evidence "
            f"WHERE tenant_id=:tenant_id AND {_VERSION_EVIDENCE_CLAUSE} ORDER BY created_at DESC NULLS LAST LIMIT 50",
            params,
        ),
        "limitations": [
            "Changes and causality are not inferred from this read-only story endpoint.",
            "All records are limited to the authenticated tenant and selected ProductVersion.",
        ],
    }


@router.get("/analytics/investigations")
def investigations_summary(
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    control_db: Session = Depends(get_db),
):
    from backend.app.case_workflow.states import effective_state, state_label, with_owner_names

    rows = _rows(
        db,
        """
        SELECT id, business_id, investigation_identifier, status, investigation_question,
               workflow_state, priority, due_at, owner_ref
        FROM investigations WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC NULLS LAST LIMIT 100
    """,
        {"tenant_id": ctx.tenant_id},
    )
    if not rows:
        # An organization database without the case workflow columns yet still lists its cases.
        rows = _rows(
            db,
            """
            SELECT id, business_id, investigation_identifier, status, investigation_question
            FROM investigations WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC NULLS LAST LIMIT 100
        """,
            {"tenant_id": ctx.tenant_id},
        )
    for row in rows:
        if "workflow_state" in row:
            row["workflow_state"] = effective_state(row["workflow_state"], row.get("status"))
            row["workflow_state_label"] = state_label(row["workflow_state"])
    if rows and "owner_ref" in rows[0]:
        with_owner_names(control_db, ctx.tenant_id, rows)
    return {
        "tenant_id": ctx.tenant_id,
        "investigations": rows,
        "limitations": ["Investigation status is source-recorded; no readiness conclusion is inferred."],
    }


@router.get("/analytics/evidence")
def evidence_summary(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    rows = _rows(
        db,
        """
        SELECT id, business_id, evidence_identifier, evidence_type, title, reliability_status, source_system
        FROM evidence WHERE tenant_id = :tenant_id ORDER BY created_at DESC NULLS LAST LIMIT 100
    """,
        {"tenant_id": ctx.tenant_id},
    )
    return {
        "tenant_id": ctx.tenant_id,
        "evidence": rows,
        "classification": ["Supporting", "Contradicting", "Contextual", "Unresolved", "Missing"],
        "limitations": ["Evidence classification is displayed only when persisted by an authorized workflow."],
    }


@router.get("/analytics/persona/{persona}")
def persona_dashboard(
    persona: str,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    allowed = {"investigator", "quality-manager", "regulatory", "risk-manager", "approver", "executive"}
    normalized = persona.lower()
    if normalized not in allowed:
        return {"status": "NOT_AVAILABLE", "tenant_id": ctx.tenant_id, "persona": normalized}
    counts = {name: _tenant_count(db, table, ctx.tenant_id) for name, table in _COUNT_TABLES.items()}
    emphasis = {
        "investigator": "evidence_gaps",
        "quality-manager": "investigation_progress",
        "regulatory": "vigilance_scope",
        "risk-manager": "risk_challenges",
        "approver": "decision_supportability",
        "executive": "material_attention",
    }
    return {
        "status": "READY_FOR_REVIEW",
        "tenant_id": ctx.tenant_id,
        "persona": normalized,
        "emphasis": emphasis[normalized],
        "counts": counts,
        "human_review_required": True,
        "limitations": ["Persona changes emphasis, not authorization or tenant scope."],
    }


STORY_STAGES = (
    ("product", "Product"),
    ("product_version", "ProductVersion"),
    ("signal", "Signal"),
    ("investigation", "Investigation"),
    ("evidence", "Evidence"),
    ("analysis", "Analysis"),
    ("hypotheses", "Hypotheses"),
    ("unknowns", "Unknowns"),
    ("failure_chain", "Failure Chain"),
    ("scenario", "Scenario"),
    ("decision", "Decision"),
    ("assurance", "AI Assurance"),
    ("audit", "Audit"),
)


def _story_counts(db: Session, control_db: Session, tenant_id: uuid.UUID, case) -> dict[str, int]:
    """How many records of each story stage the case has, read from the tenant's own data (signed decisions and the
    audit trail from the control plane)."""
    from backend.app.db.models.foundation import (
        AssuranceResult,
        AuditEvent,
        Complaint,
        Decision,
        Evidence,
        FailureChain,
        Hypothesis,
        InvestigationComplaint,
        InvestigationEvidence,
        Product,
        Scenario,
        SignedApprovalRecord,
        Unknown,
    )

    complaint_ids = db.query(InvestigationComplaint.complaint_id).filter(
        InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.investigation_id == case.id
    )
    linked_evidence = db.query(InvestigationEvidence.evidence_id).filter(
        InvestigationEvidence.tenant_id == tenant_id, InvestigationEvidence.investigation_id == case.id
    )
    executions = db.query(AIExecution.id).filter(
        AIExecution.tenant_id == tenant_id, AIExecution.investigation_id == case.id, AIExecution.error_state.is_(None)
    )
    decision_ids = [
        row.id
        for row in db.query(Decision.id).filter(Decision.tenant_id == tenant_id, Decision.investigation_id == case.id)
    ]
    signed = (
        control_db.query(func.count(func.distinct(SignedApprovalRecord.object_id)))
        .filter(
            SignedApprovalRecord.tenant_id == tenant_id,
            SignedApprovalRecord.object_id.in_(decision_ids),
            SignedApprovalRecord.status == "SIGNED",
        )
        .scalar()
        if decision_ids
        else 0
    )
    product = (
        db.query(Product.id).filter(Product.tenant_id == tenant_id, Product.id == case.product_id).count()
        if case.product_id
        else 0
    )
    return {
        "product": product,
        "product_version": db.query(func.count(func.distinct(Complaint.product_version_id)))
        .filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(complaint_ids))
        .scalar()
        or 0,
        "signal": complaint_ids.count(),
        "investigation": 1,
        "evidence": db.query(Evidence.id)
        .filter(
            Evidence.tenant_id == tenant_id, or_(Evidence.investigation_id == case.id, Evidence.id.in_(linked_evidence))
        )
        .count(),
        "analysis": executions.count(),
        "hypotheses": db.query(Hypothesis.id)
        .filter(Hypothesis.tenant_id == tenant_id, Hypothesis.investigation_id == case.id)
        .count(),
        "unknowns": db.query(Unknown.id)
        .filter(Unknown.tenant_id == tenant_id, Unknown.investigation_id == case.id)
        .count(),
        "failure_chain": db.query(FailureChain.id)
        .filter(FailureChain.tenant_id == tenant_id, FailureChain.investigation_id == case.id)
        .count(),
        "scenario": db.query(Scenario.id)
        .filter(Scenario.tenant_id == tenant_id, Scenario.investigation_id == case.id)
        .count(),
        "decision": len(decision_ids),
        "decision_signed": int(signed or 0),
        "assurance": db.query(AssuranceResult.id)
        .filter(AssuranceResult.tenant_id == tenant_id, AssuranceResult.ai_execution_id.in_(executions))
        .count(),
        "audit": control_db.query(AuditEvent.id)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id.in_([case.id, *decision_ids]))
        .count(),
    }


def _stage_status(key: str, counts: dict[str, int]) -> str:
    """COMPLETE only for a decision with a valid signature; AVAILABLE when the stage has records; PENDING otherwise."""
    if key == "decision" and counts.get("decision_signed"):
        return "COMPLETE"
    return "AVAILABLE" if counts.get(key) else "PENDING"


@router.get("/story/{investigation_id}")
def story_view(
    investigation_id: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's story, stage by stage, with each stage's status computed from the case's records: AVAILABLE when
    it has records (evidence, an analysis, hypotheses, ...), COMPLETE for a signed decision, PENDING otherwise."""
    from backend.app.db.models.foundation import Investigation

    try:
        case_id = uuid.UUID(str(investigation_id))
    except ValueError:
        case_id = None  # not an id at all: the same answer as an unknown or foreign case
    tenant_id = uuid.UUID(str(ctx.tenant_id)) if case_id else None
    case = (
        db.query(Investigation).filter(Investigation.id == case_id, Investigation.tenant_id == tenant_id).first()
        if case_id
        else None
    )
    if case is None:  # unknown, malformed or another organization's case: 404, like every by-id route
        raise HTTPException(
            404,
            detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Investigation is not available for this tenant."},
        )
    counts = _story_counts(db, control_db, tenant_id, case)
    return {
        "status": "READY_FOR_REVIEW",
        "investigation_id": investigation_id,
        "investigation_business_id": case.business_id,
        "tenant_id": ctx.tenant_id,
        "stages": [
            {"key": key, "label": label, "status": _stage_status(key, counts), "count": counts.get(key, 0)}
            for key, label in STORY_STAGES
        ],
        "human_review_required": True,
        "causality_state": "NOT_ESTABLISHED",
        "limitations": [
            "The story view is a traceability view; relationships are not causal conclusions.",
            "A stage is AVAILABLE when the investigation has records for it; only a signed decision is COMPLETE.",
        ],
    }


@router.get("/reports/catalog")
def reports_catalog(ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """The twelve governed reports (reports/service.py:REPORTS), each with the organization's own records."""
    from reports.service import REPORTS

    return {
        "tenant_id": ctx.tenant_id,
        "reports": [
            {"code": code, "label": label, "formats": ["JSON", "CSV", "PDF"]} for code, label in REPORTS.items()
        ],
        "human_review_required": True,
    }


@router.get("/ai/agents/catalog")
def agent_catalog(ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    return {
        "tenant_id": ctx.tenant_id,
        "agents": [
            {
                "code": code,
                "label": label,
                "allowed": ["READ", "ANALYZE", "SUMMARIZE", "SUGGEST"],
                "forbidden": ["APPROVE", "REJECT", "DECLARE_ROOT_CAUSE", "WRITE_APPROVED_RECORD"],
            }
            for code, label in [
                ("PRODUCT_INTELLIGENCE", "Product Intelligence Agent"),
                ("COMPLAINT_SIGNAL", "Complaint Signal Agent"),
                ("INVESTIGATION", "Investigation Agent"),
                ("EVIDENCE", "Evidence Agent"),
                ("HYPOTHESIS", "Hypothesis Agent"),
                ("CHALLENGER", "Challenger Agent"),
                ("TRACEABILITY", "Traceability Agent"),
                ("DECISION_BRIEF", "Decision Brief Agent"),
            ]
        ],
        "human_authority_required": True,
    }


@router.get("/ai/assurance/summary")
def assurance_summary(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    """The organization's AI executions and how MDARIX's assurance checks judged them (AssuranceResult records)."""
    from backend.app.db.models.foundation import AssuranceResult

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    by_status = dict(
        db.query(AssuranceResult.status, func.count())
        .filter(AssuranceResult.tenant_id == tenant_id)
        .group_by(AssuranceResult.status)
        .all()
    )
    return {
        "tenant_id": ctx.tenant_id,
        "metrics": {
            "total_executions": db.query(AIExecution.id).filter(AIExecution.tenant_id == tenant_id).count(),
            "assessed": sum(int(count) for count in by_status.values()),
            "pass": int(by_status.get("PASS", 0)),
            "pass_with_limitations": int(by_status.get("PASS_WITH_LIMITATIONS", 0)),
            "blocked": int(by_status.get("BLOCKED", 0)),
        },
        "guardrails": {"tenant_scope": "ENFORCED", "causality_restraint": "ENFORCED", "human_review": "REQUIRED"},
        "limitations": [
            "Metrics count the organization's persisted AI executions and their assurance results; an execution "
            "without an assurance result is not counted as passed."
        ],
    }


def _execution_cost(row: AIExecution) -> Decimal:
    payload = row.structured_output or {}
    audit = payload.get("audit", {}) if isinstance(payload, dict) else {}
    if isinstance(payload, dict) and isinstance(payload.get("provenance"), dict):
        audit = payload["provenance"].get("audit", audit)
    try:
        return Decimal(str(audit.get("estimated_cost", 0)))
    except (InvalidOperation, TypeError):
        return Decimal(0)


@router.get("/analytics/ai/provider-monitoring")
def ai_provider_monitoring(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    """Tenant-scoped operational view for provider health and persisted executions."""
    rows = (
        db.query(AIExecution)
        .filter(AIExecution.tenant_id == ctx.tenant_id)
        .order_by(AIExecution.execution_timestamp.desc())
        .limit(1000)
        .all()
    )
    failures = [
        row for row in rows if row.error_state or str(row.validation_status or "").upper() in {"FAILED", "BLOCKED"}
    ]
    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    by_provider = {}
    for row in rows:
        item = by_provider.setdefault(row.provider, {"executions": 0, "failures": 0, "estimated_cost": Decimal(0)})
        item["executions"] += 1
        item["failures"] += int(row in failures)
        item["estimated_cost"] += _execution_cost(row)
    return {
        "tenant_id": ctx.tenant_id,
        "status": "DEGRADED" if failures else "HEALTHY",
        "metrics": {
            "executions": len(rows),
            "failures": len(failures),
            "failure_rate": round(len(failures) / len(rows), 4) if rows else 0,
            "p95_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None,
        },
        "providers": [
            {**item, "estimated_cost": str(item["estimated_cost"])}
            for item in ({"provider": key, **value} for key, value in by_provider.items())
        ],
        "alert": bool(failures),
        "limitations": [
            "Metrics are tenant-scoped persisted execution telemetry; external provider monitoring remains deployment-specific."
        ],
    }


@router.get("/analytics/ai/cost-reconciliation")
def ai_cost_reconciliation(
    provider_invoice_total: str | None = Query(default=None),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Reconcile persisted estimated provider cost with an supplied invoice total."""
    # Every execution counts: a reconciliation against an invoice must never stop at an arbitrary number of rows.
    rows = db.query(AIExecution).filter(AIExecution.tenant_id == ctx.tenant_id).yield_per(1000)
    estimated, count = Decimal(0), 0
    for row in rows:
        estimated += _execution_cost(row)
        count += 1
    invoice = None
    variance = None
    if provider_invoice_total is not None:
        try:
            invoice = Decimal(provider_invoice_total)
            variance = invoice - estimated
        except InvalidOperation:
            return {"code": "INVALID_INVOICE_TOTAL", "message": "provider_invoice_total must be a decimal amount"}
    return {
        "tenant_id": ctx.tenant_id,
        "currency": "USD",
        "execution_count": count,
        "estimated_total": str(estimated),
        "provider_invoice_total": str(invoice) if invoice is not None else None,
        "variance": str(variance) if variance is not None else None,
        "within_tolerance": abs(variance) <= Decimal("0.01") if variance is not None else None,
        "status": "REQUIRES_PROVIDER_INVOICE"
        if invoice is None
        else ("RECONCILED" if abs(variance) <= Decimal("0.01") else "VARIANCE_REQUIRES_REVIEW"),
        "human_review_required": True,
    }
