"""The escalation triggers (T-G36T): the MVP's codes, computed in the trial from fields it already has, one function per
source so that the MVP swaps a source (G32's first-contact answers, G19's triage flag, G15's thresholds, G17's trend
signal, G2a's Annex A codes) without changing the codes, the table or the screen.

| Code | Trial source |
|---|---|
| SAFETY | Death recorded Yes; or a harm level at catastrophic |
| INJURY | Serious injury Yes, or Unknown with a patient involved; a harm level at or above an enabled market's threshold |
| REPORTABLE | Any market concluded reportable; US question 5 answered Yes; or an earlier single "reported" decision |
| RECURRENCE | An open signal, or a recurring service-level matter, on the same product and problem code no open case covers |
| NEW_FAILURE_MODE | A problem code not recorded before on that product, and not covered by an open case |

Each met trigger keeps the field, the value and the record it came from. The starter triggers cannot be switched off;
the trial has no customer triggers. A classification never sets a trigger. Reading only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.foundation import Complaint, Investigation, InvestigationComplaint
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES, Signal
from backend.app.reportability import markets

SAFETY, INJURY, REPORTABLE, RECURRENCE, NEW_FAILURE_MODE = (
    "SAFETY",
    "INJURY",
    "REPORTABLE",
    "RECURRENCE",
    "NEW_FAILURE_MODE",
)
CODES = (SAFETY, INJURY, REPORTABLE, RECURRENCE, NEW_FAILURE_MODE)
LABELS = {
    SAFETY: "Safety issue",
    INJURY: "Injury",
    REPORTABLE: "Reportable outcome",
    RECURRENCE: "Recurrence no case covers",
    NEW_FAILURE_MODE: "New failure mode",
}
DEFINITIONS = {
    SAFETY: "A death is recorded, or the harm level is catastrophic.",
    INJURY: "A serious injury is recorded Yes, or Unknown with a patient involved, or the harm level is at or above an "
    "enabled market's serious threshold.",
    REPORTABLE: 'A market is concluded reportable, US question 5 is Yes, or an earlier single decision says "reported".',
    RECURRENCE: "An open signal, or two or more service-level resolutions in 30 days, on the same product and problem "
    "code, and no open case covers it.",
    NEW_FAILURE_MODE: "The problem code was never recorded before on this product, and no open case covers it.",
}
# A recurring service-level matter: this many service-level resolutions on one product and problem code within the
# window (starter threshold, shown on screen).
RECURRING_COUNT = 2
RECURRING_DAYS = 30
OPEN_CASE = func.lower(func.coalesce(Investigation.status, "open")).notin_(("closed", "cancelled"))


@dataclass
class Facts:
    """What the triggers read of one complaint."""

    complaint: Complaint
    ref: str
    product_name: str | None
    enabled: list[str]
    assessments: list[ComplaintMarketAssessment] = field(default_factory=list)
    legacy: ComplaintReportability | None = None


def _met(code: str, field_name: str, value: object, record: str, fact: str) -> dict:
    return {
        "code": code,
        "label": LABELS[code],
        "field": field_name,
        "value": value if isinstance(value, (int, float)) else str(value),
        "record": record,
        "fact": fact,
    }


def _latest(rows: list[ComplaintMarketAssessment]) -> list[ComplaintMarketAssessment]:
    """Each market's latest version (signed or draft)."""
    found: dict[str, ComplaintMarketAssessment] = {}
    for row in sorted(rows, key=lambda item: item.version):
        found[row.market] = row
    return list(found.values())


def _harm_levels(facts: Facts) -> list[tuple[str, str]]:
    """``(level, where it comes from)``: each market assessment's harm level, and the QMS severity's mapped level."""
    found = [(row.harm_level, f"{facts.ref} {row.market} v{row.version}") for row in _latest(facts.assessments)]
    mapped = markets.level_of_severity(facts.complaint.severity)
    if mapped:
        found.append((mapped, f"{facts.ref} severity {facts.complaint.severity}"))
    return [(level, source) for level, source in found if level]


def safety(facts: Facts) -> list[dict]:
    found = []
    if facts.complaint.death is True:
        found.append(_met(SAFETY, "death", "Yes", facts.ref, "Death recorded Yes"))
    for level, source in _harm_levels(facts):
        if level == markets.CATASTROPHIC:
            found.append(_met(SAFETY, "harm_level", level, source, "Harm level catastrophic"))
            break
    return found


def injury(facts: Facts) -> list[dict]:
    complaint = facts.complaint
    found = []
    if complaint.serious_injury is True:
        found.append(_met(INJURY, "serious_injury", "Yes", facts.ref, "Serious injury recorded Yes"))
    elif complaint.patient_involved and (complaint.serious_injury is None or complaint.death is None):
        found.append(
            _met(INJURY, "serious_injury", "Unknown", facts.ref, "A patient was involved and the outcome is unknown")
        )
    thresholds = [markets.THRESHOLDS[market] for market in (facts.enabled or markets.MARKETS)]
    lowest = min((markets.rank(level) for level in thresholds), default=markets.rank(markets.SERIOUS))
    for level, source in _harm_levels(facts):
        if markets.rank(level) >= lowest:
            label = markets.LEVEL_LABELS.get(level, level)
            found.append(_met(INJURY, "harm_level", level, source, f"Harm level {label}, at or above a threshold"))
            break
    return found


def reportable(facts: Facts) -> list[dict]:
    found = []
    for row in _latest(facts.assessments):
        signed = [item for item in facts.assessments if item.market == row.market and item.conclusion]
        current = signed[-1] if signed else None
        if current is not None and current.conclusion == markets.REPORTABLE:
            found.append(
                _met(
                    REPORTABLE,
                    "conclusion",
                    "REPORTABLE",
                    f"{facts.ref} {row.market} v{current.version}",
                    f"{markets.MARKET_LABELS[row.market]} concluded reportable",
                )
            )
        elif ((row.answers or {}).get("US5") or {}).get("answer") == markets.YES:
            found.append(
                _met(
                    REPORTABLE,
                    "US5",
                    "Yes",
                    f"{facts.ref} US v{row.version}",
                    "US question 5: a recurrence would be likely to cause or contribute to a death or serious injury",
                )
            )
    if facts.legacy is not None and facts.legacy.decision == "REPORTED":
        found.append(_met(REPORTABLE, "decision", "REPORTED", facts.ref, 'An earlier single decision says "reported"'))
    return found


def covering_cases(db: Session, tenant_id: uuid.UUID, product_id, problem_code: str | None) -> list:
    """The open cases whose scope holds a complaint with this product and problem code."""
    if product_id is None or not problem_code:
        return []
    return (
        db.query(Investigation.id, Investigation.business_id, Investigation.investigation_identifier)
        .join(
            InvestigationComplaint,
            (InvestigationComplaint.tenant_id == Investigation.tenant_id)
            & (InvestigationComplaint.investigation_id == Investigation.id),
        )
        .join(
            Complaint,
            (Complaint.tenant_id == InvestigationComplaint.tenant_id)
            & (Complaint.id == InvestigationComplaint.complaint_id),
        )
        .filter(
            Investigation.tenant_id == tenant_id,
            OPEN_CASE,
            Complaint.product_id == product_id,
            func.upper(Complaint.problem_code) == problem_code.upper(),
        )
        .distinct()
        .all()
    )


def service_level_resolutions(
    db: Session, tenant_id: uuid.UUID, product_id, problem_code: str, today: date, exclude=None
) -> list:
    """Current signed service-level dispositions in the last RECURRING_DAYS on this product and problem code."""
    since = datetime.combine(today - timedelta(days=RECURRING_DAYS), time.min, tzinfo=timezone.utc)
    query = (
        db.query(ComplaintDisposition.complaint_id, Complaint.business_id, Complaint.complaint_identifier)
        .join(
            Complaint,
            (Complaint.tenant_id == ComplaintDisposition.tenant_id)
            & (Complaint.id == ComplaintDisposition.complaint_id),
        )
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.superseded_by.is_(None),
            ComplaintDisposition.branch == "SERVICE_LEVEL",
            ComplaintDisposition.signed_at >= since,
            Complaint.product_id == product_id,
            func.upper(Complaint.problem_code) == problem_code.upper(),
        )
    )
    if exclude is not None:
        query = query.filter(ComplaintDisposition.complaint_id != exclude)
    return query.all()


def recurrence(db: Session, tenant_id: uuid.UUID, facts: Facts, today: date) -> list[dict]:
    complaint = facts.complaint
    code = (complaint.problem_code or "").strip()
    if complaint.product_id is None or not code or covering_cases(db, tenant_id, complaint.product_id, code):
        return []
    found = []
    signal = (
        db.query(Signal.business_id, Signal.complaint_count)
        .filter(
            Signal.tenant_id == tenant_id,
            Signal.product_id == complaint.product_id,
            Signal.problem_key == code.upper(),
            Signal.status.in_(OPEN_SIGNAL_STATUSES),
        )
        .first()
    )
    if signal is not None:
        found.append(
            _met(
                RECURRENCE,
                "signal",
                signal.complaint_count,
                signal.business_id,
                f"Open signal {signal.business_id} on {facts.product_name or 'this product'}, {code}: no open case "
                "covers it",
            )
        )
    resolved = service_level_resolutions(db, tenant_id, complaint.product_id, code, today, exclude=complaint.id)
    if len(resolved) >= RECURRING_COUNT:
        refs = ", ".join(row.business_id or row.complaint_identifier for row in resolved)
        found.append(
            _met(
                RECURRENCE,
                "service_level_resolutions",
                len(resolved),
                refs,
                f"{len(resolved)} service-level resolutions on {facts.product_name or 'this product'}, {code}, in "
                f"{RECURRING_DAYS} days ({refs}): no open case covers them",
            )
        )
    return found


def new_failure_mode(db: Session, tenant_id: uuid.UUID, facts: Facts) -> list[dict]:
    complaint = facts.complaint
    code = (complaint.problem_code or "").strip()
    if complaint.product_id is None or not code:
        return []
    before = (
        db.query(Complaint.id)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.product_id == complaint.product_id,
            func.upper(Complaint.problem_code) == code.upper(),
            Complaint.id != complaint.id,
        )
        .first()
    )
    if before is not None or covering_cases(db, tenant_id, complaint.product_id, code):
        return []
    return [
        _met(
            NEW_FAILURE_MODE,
            "problem_code",
            code,
            facts.ref,
            f"Problem code {code} not recorded before on {facts.product_name or 'this product'}, and no open case "
            "covers it",
        )
    ]


def evaluate(db: Session, tenant_id: uuid.UUID, facts: Facts, today: date) -> list[dict]:
    """Every trigger met, in the order of CODES."""
    return [
        *safety(facts),
        *injury(facts),
        *reportable(facts),
        *recurrence(db, tenant_id, facts, today),
        *new_failure_mode(db, tenant_id, facts),
    ]


def codes(met: list[dict]) -> list[str]:
    return [code for code in CODES if any(item["code"] == code for item in met)]
