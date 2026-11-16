"""Pareto of confirmed causes (RCA spec 3.4, RCA-D5). Counts only, never a rate.

Each complaint counts once, under its current confirmed cause: the latest signed, not superseded decision of an
investigation whose scope holds it; else its current signed service-level disposition's attribution. Complaints with
neither are one bar, "No confirmed cause yet", always shown and always last. Decisions signed before RCA carry no
category and count as "Not categorised" (never rewritten, RCA-D2). Bars largest first with the cumulative share.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.rca import rules

GROUPS = ("category", "attribution", "product", "version", "problem_code")
DECISION, DISPOSITION, NONE = "DECISION", "DISPOSITION", "NONE"
NOT_RECORDED = "Not recorded"
NOT_ATTRIBUTED = "Not attributed"
EXAMPLES_MAX = 50
CUMULATIVE_MARK = 80.0


def current_cause(decisions: list[dict], disposition: dict | None) -> dict:
    """The cause a complaint counts under. ``decisions``: the signed, not superseded decisions of the investigations
    whose scope holds it (``decided_at`` comparable); ``disposition``: its current service-level disposition."""
    if decisions:
        latest = max(decisions, key=lambda item: (item["decided_at"] is not None, item["decided_at"] or 0))
        return {"source": DECISION, **latest}
    if disposition is not None and disposition.get("attribution"):
        return {"source": DISPOSITION, **disposition}
    return {"source": NONE}


def _attribution_label(code: str | None) -> str:
    from backend.app.complaint_disposition.rules import ATTRIBUTION_LABELS

    return ATTRIBUTION_LABELS.get(code or "", NOT_ATTRIBUTED)


def group_label(row: dict, group_by: str) -> str:
    cause = row["cause"]
    if cause["source"] == NONE:
        return rules.NO_CONFIRMED_CAUSE
    if group_by == "category":
        if cause["source"] == DISPOSITION:
            return f"Service level: {_attribution_label(cause.get('attribution'))}"
        return rules.category_label(cause.get("category"))
    if group_by == "attribution":
        return _attribution_label(cause.get("attribution"))
    return row.get(group_by) or NOT_RECORDED


def build(rows: list[dict], group_by: str = "category") -> dict:
    """The bars of ``rows`` (each ``{"complaint": {...}, "cause": current_cause(...), product, version,
    problem_code}``) grouped by ``group_by``."""
    if group_by not in GROUPS:
        raise ValueError(f"Group by one of {', '.join(GROUPS)}")
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[group_label(row, group_by)].append(row)
    groups.setdefault(rules.NO_CONFIRMED_CAUSE, [])
    total = len(rows)
    ordered = sorted(
        (label for label in groups if label != rules.NO_CONFIRMED_CAUSE), key=lambda label: (-len(groups[label]), label)
    ) + [rules.NO_CONFIRMED_CAUSE]
    bars, running = [], 0
    for label in ordered:
        members = groups[label]
        running += len(members)
        decisions = {}
        for row in members:
            cause = row["cause"]
            if cause["source"] == DECISION:
                decisions[cause["decision_id"]] = {
                    "id": cause["decision_id"],
                    "business_id": cause.get("decision_business_id"),
                    "investigation_id": cause.get("investigation_id"),
                }
        bars.append(
            {
                "label": label,
                "count": len(members),
                "share": round(100 * len(members) / total, 1) if total else 0.0,
                "cumulative_share": round(100 * running / total, 1) if total else 0.0,
                "confirmed": label != rules.NO_CONFIRMED_CAUSE,
                "complaints": [row["complaint"] for row in members[:EXAMPLES_MAX]],
                "decisions": list(decisions.values()),
                "investigations": len({d["investigation_id"] for d in decisions.values()}),
            }
        )
    return {
        "group_by": group_by,
        "unit": "complaints",
        "total": total,
        "bars": bars,
        "mark": CUMULATIVE_MARK,
        "note": "Counts of complaints, each once under its current confirmed cause. Not a rate.",
    }


def read(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    group_by: str = "category",
    product_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """The Pareto of one organization's complaints (filters: product, event period)."""
    from backend.app.complaint_disposition.service import current_by_complaint
    from backend.app.db.models.foundation import (
        Complaint,
        Decision,
        InvestigationComplaint,
        Product,
        ProductVersion,
    )
    from backend.app.human_decision.rules import DECISION_KIND, SIGNED

    when = func.coalesce(Complaint.event_timestamp, Complaint.awareness_timestamp, Complaint.complaint_timestamp)
    query = db.query(Complaint).filter(Complaint.tenant_id == tenant_id)
    if product_id is not None:
        query = query.filter(Complaint.product_id == product_id)
    if date_from is not None:
        query = query.filter(when >= date_from)
    if date_to is not None:
        query = query.filter(when <= date_to)
    complaints = query.order_by(Complaint.business_id).all()
    ids = [row.id for row in complaints]
    products = {row.id: row.name for row in db.query(Product).filter(Product.tenant_id == tenant_id)}
    versions = {
        row.id: row.version_identifier for row in db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id)
    }
    scope: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if ids:
        for complaint_id, investigation_id in db.query(
            InvestigationComplaint.complaint_id, InvestigationComplaint.investigation_id
        ).filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id.in_(ids)):
            scope[complaint_id].add(investigation_id)
    cases = {case for linked in scope.values() for case in linked}
    signed: dict[uuid.UUID, list[dict]] = defaultdict(list)
    if cases:
        for decision in db.query(Decision).filter(
            Decision.tenant_id == tenant_id,
            Decision.investigation_id.in_(list(cases)),
            Decision.decision_kind == DECISION_KIND,
            Decision.decision_status == SIGNED,
            Decision.superseded_by_decision_id.is_(None),
        ):
            signed[decision.investigation_id].append(
                {
                    "decision_id": str(decision.id),
                    "decision_business_id": decision.business_id,
                    "investigation_id": str(decision.investigation_id),
                    "decided_at": decision.decided_at or decision.decision_timestamp,
                    "category": decision.root_cause_category,
                    "attribution": decision.root_cause_attribution,
                }
            )
    dispositions = current_by_complaint(db, tenant_id, ids) if ids else {}
    rows = []
    for complaint in complaints:
        decisions = [item for case in scope.get(complaint.id, ()) for item in signed.get(case, ())]
        disposition = dispositions.get(complaint.id)
        rows.append(
            {
                "complaint": {"id": str(complaint.id), "business_id": complaint.business_id},
                "cause": current_cause(
                    decisions,
                    {"attribution": disposition.attribution}
                    if disposition is not None and disposition.branch == "SERVICE_LEVEL"
                    else None,
                ),
                "product": products.get(complaint.product_id),
                "version": versions.get(complaint.product_version_id),
                "problem_code": complaint.problem_code,
            }
        )
    return build(rows, group_by)
