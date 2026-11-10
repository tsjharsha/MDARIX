"""Post-market data and the risk file, per product.

Why it matters: since 2 February 2026 FDA inspects under the QMSR (Compliance Program 7382.850), following the
manufacturer's risk file, and names post-market surveillance not used as input to risk management as a significant
deficiency; the first QMSR-based warning letter cited exactly this. ISO 14971:2019 clause 10 asks the manufacturer to
collect and review production and post-production information and feed it back into risk management.

For each product, over a period, this reads:
- its post-market data: complaints received (those reporting a death or serious injury, a malfunction), signals raised
  or decided, and significant rises on the trend check;
- its risk file in MDARIX: the risks of its register, which of them a completed risk review of one of its cases
  assessed in the period (and when, with which outcome), and the risk reassessments signed decisions asked for that
  are still open (overdue when past their due date).

A product's state, most urgent first:
- NOT_REVIEWED: post-market data that matters (harm, a malfunction, a significant rise or a decided signal) and no
  completed risk review in the period;
- REASSESSMENT_OVERDUE / REASSESSMENT_OPEN: risk reassessments asked for by signed decisions, not done;
- NO_RISK_REGISTER: post-market data that matters, but none of the product's risks are in MDARIX to link it to;
- REVIEWED: a risk review completed in the period and nothing open;
- QUIET: nothing in the period that a risk review must look at.
Reading only; MDARIX never changes a risk or decides what the risk file must say.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import Complaint, Investigation, Product, Risk
from backend.app.db.models.reviews import CaseReview
from backend.app.db.models.signals import Signal

PERIOD_DEFAULT, PERIOD_MIN, PERIOD_MAX = 365, 90, 1095
REASSESSMENT = "RISK_REASSESSMENT_REQUIRED"
OPEN_FOLLOW_UP = ("OPEN", "IN_PROGRESS")
DECIDED_SIGNALS = ("DECISION_RECORDED", "CLOSED")
# Risk review outcomes that ask for the risk file to be changed (backend/app/db/models/reviews.py RISK_OUTCOMES).
CHANGE_OUTCOMES = ("RISK_FILE_REASSESSMENT_REQUIRED", "RISK_CONTROL_REVIEW_REQUIRED", "ESCALATE_SAFETY_CONCERN")

NOT_REVIEWED, OVERDUE, OPEN, NO_REGISTER, REVIEWED, QUIET = (
    "NOT_REVIEWED",
    "REASSESSMENT_OVERDUE",
    "REASSESSMENT_OPEN",
    "NO_RISK_REGISTER",
    "REVIEWED",
    "QUIET",
)
STATE_ORDER = {NOT_REVIEWED: 0, OVERDUE: 1, OPEN: 2, NO_REGISTER: 3, REVIEWED: 4, QUIET: 5}
STATE_LABELS = {
    NOT_REVIEWED: "Post-market data not reviewed against the risk file",
    OVERDUE: "Risk reassessment overdue",
    OPEN: "Risk reassessment open",
    NO_REGISTER: "No risks in MDARIX to link to",
    REVIEWED: "Reviewed against the risk file",
    QUIET: "Nothing for the risk file in the period",
}


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def state_of(*, matters: bool, reviewed: bool, overdue: int, open_count: int, risks: int) -> str:
    """A product's state from its facts (see the module docstring)."""
    if matters and not reviewed:
        return NOT_REVIEWED
    if overdue:
        return OVERDUE
    if open_count:
        return OPEN
    if matters and not risks:
        return NO_REGISTER
    return REVIEWED if reviewed else QUIET


def _facts(db: Session, tenant_id: uuid.UUID, start: date, today: date) -> dict:
    """Everything per product for the period: post-market data, risks, completed risk reviews, open follow-ups."""
    from backend.app.oversight.service import calendar_of
    from backend.app.signals.insight import trend_board

    day_end = calendar_of(db, tenant_id).day_end  # MDARIX's own due times end with the organization's day (J16)

    begin, end = _midnight(start), _midnight(today + timedelta(days=1))
    received = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)
    facts: dict = defaultdict(
        lambda: {
            "complaints": 0,
            "harm": 0,
            "malfunction": 0,
            "signals_raised": 0,
            "signals_decided": 0,
            "rising": [],
            "risks": [],
            "reviews": [],
            "follow_ups": [],
        }
    )
    for product_id, death, injury, malfunction in (
        db.query(Complaint.product_id, Complaint.death, Complaint.serious_injury, Complaint.malfunction)
        .filter(Complaint.tenant_id == tenant_id, Complaint.product_id.isnot(None), received >= begin, received < end)
        .all()
    ):
        item = facts[product_id]
        item["complaints"] += 1
        item["harm"] += 1 if (death or injury) else 0
        item["malfunction"] += 1 if malfunction else 0
    for product_id, status in (
        db.query(Signal.product_id, Signal.status)
        .filter(
            Signal.tenant_id == tenant_id,
            Signal.product_id.isnot(None),
            Signal.created_at >= begin,
            Signal.created_at < end,
        )
        .all()
    ):
        facts[product_id]["signals_raised"] += 1
        facts[product_id]["signals_decided"] += 1 if status in DECIDED_SIGNALS else 0
    for item in trend_board(db, tenant_id, grouping="problem", today=today)["items"]:
        if item["result"] == "SIGNIFICANT":
            facts[uuid.UUID(item["product"]["id"])]["rising"].append(item["name"])
    for risk in (
        db.query(Risk.id, Risk.business_id, Risk.risk_identifier, Risk.description, Risk.product_id, Risk.status)
        .filter(Risk.tenant_id == tenant_id, Risk.product_id.isnot(None))
        .all()
    ):
        facts[risk.product_id]["risks"].append(risk)
    for review, product_id, case_ref in (
        db.query(CaseReview, Investigation.product_id, Investigation.business_id)
        .join(
            Investigation,
            (Investigation.tenant_id == CaseReview.tenant_id) & (Investigation.id == CaseReview.investigation_id),
        )
        .filter(
            CaseReview.tenant_id == tenant_id,
            CaseReview.review_type == "RISK",
            CaseReview.status == "COMPLETED",
            CaseReview.completed_at >= begin,
            CaseReview.completed_at < end,
        )
        .order_by(CaseReview.completed_at.desc())
        .all()
    ):
        facts[product_id]["reviews"].append((review, case_ref))
        # A risk file update a risk review asked for (T-G1aR): open, and overdue past its day.
        for key, finding in ((review.assessed or {}).get("findings") or {}).items():
            update = finding.get("risk_file_update")
            if update:
                due = day_end(date.fromisoformat(update["due_on"]))
                title = f"Risk file update: {finding.get('description') or finding.get('reason')}"
                facts[product_id]["follow_ups"].append(
                    (
                        SimpleNamespace(
                            business_id=f"{review.business_id} {key}", title=title, status="OPEN", due_at=due
                        ),
                        case_ref,
                    )
                )
    for follow_up, product_id, case_ref in (
        db.query(DecisionFollowUp, Investigation.product_id, Investigation.business_id)
        .join(
            Investigation,
            (Investigation.tenant_id == DecisionFollowUp.tenant_id)
            & (Investigation.id == DecisionFollowUp.investigation_id),
        )
        .filter(
            DecisionFollowUp.tenant_id == tenant_id,
            DecisionFollowUp.action_type == REASSESSMENT,
            DecisionFollowUp.status.in_(OPEN_FOLLOW_UP),
        )
        .all()
    ):
        facts[product_id]["follow_ups"].append((follow_up, case_ref))
    return facts


def _product_view(product, item: dict, now: datetime) -> dict:
    reviews = item["reviews"]
    assessed = {ref for review, _ in reviews for ref in ((review.assessed or {}).get("risk_ids") or [])}
    risks = [
        risk for risk in item["risks"] if str(risk.status or "").lower() not in ("retired", "obsolete", "inactive")
    ]
    overdue = [
        follow_up
        for follow_up, _ in item["follow_ups"]
        if follow_up.due_at is not None
        and (follow_up.due_at if follow_up.due_at.tzinfo else follow_up.due_at.replace(tzinfo=timezone.utc)) < now
    ]
    matters = bool(item["harm"] or item["malfunction"] or item["rising"] or item["signals_decided"])
    state = state_of(
        matters=matters,
        reviewed=bool(reviews),
        overdue=len(overdue),
        open_count=len(item["follow_ups"]),
        risks=len(risks),
    )
    outcomes = Counter(review.outcome for review, _ in reviews if review.outcome)
    return {
        "product": {
            "id": str(product.id) if product else None,
            "business_id": getattr(product, "business_id", None),
            "name": getattr(product, "name", None) or "Product",
        },
        "state": state,
        "label": STATE_LABELS[state],
        "post_market": {
            "complaints": item["complaints"],
            "harm": item["harm"],
            "malfunction": item["malfunction"],
            "signals_raised": item["signals_raised"],
            "signals_decided": item["signals_decided"],
            "significant_rises": item["rising"][:10],
        },
        "risk_file": {
            "risks": len(risks),
            "risks_assessed": sum(1 for risk in risks if str(risk.id) in assessed),
            "risk_reviews": len(reviews),
            "last_review_at": _iso(reviews[0][0].completed_at) if reviews else None,
            "outcomes": dict(outcomes),
            "change_asked": sum(outcomes.get(code, 0) for code in CHANGE_OUTCOMES),
            "reassessments_open": len(item["follow_ups"]),
            "reassessments_overdue": len(overdue),
        },
    }


def board(db: Session, tenant_id: uuid.UUID, *, period_days: int = PERIOD_DEFAULT, today: date | None = None) -> dict:
    """Every product with post-market data or risks, the most urgent first."""
    today = today or today_utc()
    start = today - timedelta(days=period_days - 1)
    facts = _facts(db, tenant_id, start, today)
    products = {
        row.id: row
        for row in db.query(Product.id, Product.business_id, Product.name)
        .filter(Product.tenant_id == tenant_id, Product.id.in_(list(facts) or [uuid.uuid4()]))
        .all()
    }
    now = datetime.now(timezone.utc)
    items = [_product_view(products.get(product_id), item, now) for product_id, item in facts.items()]
    items.sort(
        key=lambda view: (
            STATE_ORDER[view["state"]],
            -view["post_market"]["harm"],
            -view["post_market"]["complaints"],
            view["product"]["name"],
        )
    )
    states = Counter(view["state"] for view in items)
    return {
        "period": {"from": start.isoformat(), "to": today.isoformat(), "days": period_days},
        "summary": {"products": len(items), **{state.lower(): states.get(state, 0) for state in STATE_ORDER}},
        "note": "Read from your records in MDARIX: complaints, signals, the trend check, your risk register and the "
        "risk reviews and risk reassessments of your investigations. A person decides what the risk file must say.",
        "items": items,
    }


def detail(
    db: Session, tenant_id: uuid.UUID, product_id: uuid.UUID, *, period_days: int = PERIOD_DEFAULT, today=None
) -> dict | None:
    """One product: its view, each risk with the risk reviews that assessed it in the period, the reviews and the open
    reassessments."""
    today = today or today_utc()
    product = (
        db.query(Product.id, Product.business_id, Product.name)
        .filter(Product.tenant_id == tenant_id, Product.id == product_id)
        .first()
    )
    if product is None:
        return None
    start = today - timedelta(days=period_days - 1)
    item = _facts(db, tenant_id, start, today)[product_id]  # a product without any facts reads as empty
    view = _product_view(product, item, datetime.now(timezone.utc))
    by_risk: dict = defaultdict(list)
    for review, case_ref in item["reviews"]:
        for ref in (review.assessed or {}).get("risk_ids") or []:
            by_risk[str(ref)].append(
                {
                    "review": review.business_id,
                    "case": case_ref,
                    "outcome": review.outcome,
                    "at": _iso(review.completed_at),
                }
            )
    return {
        **view,
        "period": {"from": start.isoformat(), "to": today.isoformat(), "days": period_days},
        "risks": sorted(
            (
                {
                    "id": str(risk.id),
                    "business_id": risk.business_id,
                    "risk_identifier": risk.risk_identifier,
                    "description": risk.description,
                    "status": risk.status,
                    "assessed": by_risk.get(str(risk.id), []),
                }
                for risk in item["risks"]
            ),
            key=lambda entry: (bool(entry["assessed"]), entry["risk_identifier"] or ""),
        ),
        "reviews": [
            {
                "review": review.business_id,
                "case": case_ref,
                "outcome": review.outcome,
                "at": _iso(review.completed_at),
                "risks_assessed": len((review.assessed or {}).get("risk_ids") or []),
            }
            for review, case_ref in item["reviews"]
        ],
        "reassessments": [
            {
                "follow_up": follow_up.business_id,
                "case": case_ref,
                "title": follow_up.title,
                "status": follow_up.status,
                "due_at": _iso(follow_up.due_at),
            }
            for follow_up, case_ref in item["follow_ups"]
        ],
    }
