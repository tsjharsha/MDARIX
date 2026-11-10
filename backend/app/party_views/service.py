"""The submitter status and the authorised representative's panels, written once (T-G37P now; G14 and G37 in 1.0.1).

- ``submitter_status``: each complaint's status as its submitter sees it (received, under assessment, closed) and the
  date of its last change.
- ``portfolio``, ``high_risk`` and ``recurring_issues``: what an EU authorised representative sees for a product set:
  every complaint with its EU/NI market assessment, the complaints with a safety or injury trigger, a harm level at or
  above the EU threshold or a reportable conclusion, and the open signals and recurring service-level matters.

The trial preview (preview.py) passes the fixed sample party and product set; G37 passes a mandate's product set.
Reading only. No row carries patient or reporter data: ids, product, country, states, dates and trigger facts only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.complaint_disposition import rules as disposition_rules
from backend.app.complaint_disposition import service as dispositions
from backend.app.complaint_disposition import triggers
from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.foundation import Complaint, InvestigationComplaint, Product
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES, Signal
from backend.app.reportability import markets

RECEIVED, UNDER_ASSESSMENT, CLOSED = "RECEIVED", "UNDER_ASSESSMENT", "CLOSED"
STATUS_LABELS = {RECEIVED: "Received", UNDER_ASSESSMENT: "Under assessment", CLOSED: "Closed"}
READ_LIMIT = dispositions.READ_LIMIT


def _iso_day(value) -> str | None:
    return value.date().isoformat() if isinstance(value, datetime) else (value.isoformat() if value else None)


def _latest(*values):
    found = [value for value in values if value is not None]
    return max(found) if found else None


def _assessments(db: Session, tenant_id: uuid.UUID, ids: list) -> dict:
    """``{complaint id: [assessment rows, by version]}``."""
    found: dict = {}
    if not ids:
        return found
    for row in (
        db.query(ComplaintMarketAssessment)
        .filter(ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.complaint_id.in_(ids))
        .order_by(ComplaintMarketAssessment.version)
    ):
        found.setdefault(row.complaint_id, []).append(row)
    return found


def submitter_status(db: Session, tenant_id: uuid.UUID, complaints: list[Complaint], assessments=None) -> dict:
    """``{complaint id: {"status", "label", "last_change"}}``. Closed: a signed service-level disposition, or closed or
    cancelled in the quality system. Under assessment: a disposition, a market assessment or a case holds it.
    Received: nothing yet. The last change is the latest of those records and the complaint's own update."""
    ids = [row.id for row in complaints]
    if not ids:
        return {}
    current = dispositions.current_by_complaint(db, tenant_id, ids)
    assessments = assessments if assessments is not None else _assessments(db, tenant_id, ids)
    linked = dict(
        db.query(InvestigationComplaint.complaint_id, func.max(InvestigationComplaint.created_at))
        .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id.in_(ids))
        .group_by(InvestigationComplaint.complaint_id)
        .all()
    )
    found = {}
    for complaint in complaints:
        disposition = current.get(complaint.id)
        rows = assessments.get(complaint.id, [])
        if (disposition is not None and disposition.branch == disposition_rules.SERVICE_LEVEL) or (
            review_rules.is_closed(complaint.status) or review_rules.is_cancelled(complaint.status)
        ):
            status = CLOSED
        elif disposition is not None or rows or complaint.id in linked:
            status = UNDER_ASSESSMENT
        else:
            status = RECEIVED
        last = _latest(
            complaint.updated_at,
            complaint.created_at,
            disposition.signed_at if disposition is not None else None,
            *(row.signed_at or row.updated_at for row in rows),
            linked.get(complaint.id),
        )
        found[complaint.id] = {"status": status, "label": STATUS_LABELS[status], "last_change": _iso_day(last)}
    return found


def _complaints(db: Session, tenant_id: uuid.UUID, product_ids) -> list[tuple[Complaint, str | None]]:
    if not product_ids:
        return []
    return (
        db.query(Complaint, Product.name)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .filter(Complaint.tenant_id == tenant_id, Complaint.product_id.in_(list(product_ids)))
        .order_by(dispositions.RECEIVED_AT.desc(), Complaint.complaint_identifier)
        .limit(READ_LIMIT)
        .all()
    )


def received_day(complaint: Complaint) -> str | None:
    return _iso_day(complaint.complaint_timestamp or complaint.event_timestamp or complaint.created_at)


def _eu_assessment(rows: list[ComplaintMarketAssessment], country) -> dict:
    """The EU/NI assessment's state and date: its latest version, signed or saved; else whether one is expected."""
    eu = [row for row in rows if row.market == markets.EU_NI]
    if not eu:
        expected = markets.market_of(country) == markets.EU_NI
        return {"state": "NOT_STARTED" if expected else "NONE", "label": "Not started" if expected else "—"}
    row = eu[-1]
    if row.conclusion:
        return {
            "state": "SIGNED",
            "label": f"Signed: {markets.CONCLUSION_LABELS[row.conclusion].lower()}",
            "date": _iso_day(row.signed_at),
            "due_on": _iso_day(row.due_on),
        }
    return {
        "state": "SAVED",
        "label": f"Saved: {markets.CONCLUSION_LABELS.get(row.suggested_conclusion, row.suggested_conclusion).lower()}",
        "date": _iso_day(row.updated_at),
        "due_on": _iso_day(row.due_on),
    }


def portfolio(db: Session, tenant_id: uuid.UUID, product_ids) -> dict:
    """Every complaint on the product set (ID, product, country, state, dates) with its EU/NI assessment, and the
    three panels' inputs read once: ``{"complaints": [...], "high_risk": [...]}``."""
    rows = _complaints(db, tenant_id, product_ids)
    ids = [complaint.id for complaint, _ in rows]
    assessments = _assessments(db, tenant_id, ids)
    statuses = submitter_status(db, tenant_id, [complaint for complaint, _ in rows], assessments)
    legacy = (
        {
            row.complaint_id: row
            for row in db.query(ComplaintReportability).filter(
                ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id.in_(ids)
            )
        }
        if ids
        else {}
    )
    complaints, risky = [], []
    for complaint, product_name in rows:
        found = assessments.get(complaint.id, [])
        item = {
            "id": str(complaint.id),
            "ref": dispositions.ref_of(complaint),
            "identifier": complaint.complaint_identifier,
            "product": product_name,
            "country": complaint.country,
            "status": statuses[complaint.id]["status"],
            "state": statuses[complaint.id]["label"],
            "received": received_day(complaint),
            "last_change": statuses[complaint.id]["last_change"],
            "eu_assessment": _eu_assessment(found, complaint.country),
        }
        complaints.append(item)
        reasons = high_risk_reasons(
            triggers.Facts(
                complaint,
                item["ref"],
                product_name,
                [markets.EU_NI],
                found,
                legacy.get(complaint.id),
            )
        )
        if reasons:
            risky.append({key: item[key] for key in ("id", "ref", "identifier", "product", "country")} | reasons)
    return {"complaints": complaints, "high_risk": risky}


def high_risk_reasons(facts: triggers.Facts) -> dict:
    """Why a complaint is high-risk for the EU authorised representative: a safety or injury trigger (with the EU
    threshold for the harm level) or a reportable conclusion; ``{}`` when none holds."""
    met = [*triggers.safety(facts), *triggers.injury(facts), *triggers.reportable(facts)]
    if not met:
        return {}
    return {"codes": triggers.codes(met), "reasons": [item["fact"] for item in met]}


def recurring_issues(db: Session, tenant_id: uuid.UUID, product_ids) -> dict:
    """The open signals on the product set, and its recurring service-level matters (the Readiness rule)."""
    wanted = {str(value) for value in product_ids}
    if not wanted:
        return {"signals": [], "service_level": []}
    signals = (
        db.query(Signal, Product.name)
        .outerjoin(Product, (Product.tenant_id == Signal.tenant_id) & (Product.id == Signal.product_id))
        .filter(
            Signal.tenant_id == tenant_id,
            Signal.product_id.in_(list(product_ids)),
            Signal.status.in_(OPEN_SIGNAL_STATUSES),
        )
        .order_by(Signal.last_event_at.desc().nullslast(), Signal.business_id)
        .all()
    )
    today = datetime.now(timezone.utc).date()
    return {
        "signals": [
            {
                "id": str(signal.id),
                "ref": signal.business_id,
                "title": signal.title,
                "product": product_name,
                "complaints": signal.complaint_count,
                "status": signal.status,
                "last_event": _iso_day(signal.last_event_at),
            }
            for signal, product_name in signals
        ],
        "service_level": [
            item for item in dispositions.recurring(db, tenant_id, today) if item["product_id"] in wanted
        ],
        "rule": f"{triggers.RECURRING_COUNT} or more service-level resolutions on one product and problem code within "
        f"{triggers.RECURRING_DAYS} days that no open investigation covers",
    }
