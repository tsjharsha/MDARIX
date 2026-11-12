"""B6a P2 Value Centre v0 (6.3, D9): outcome numbers from timestamps the records already hold, never anyone's time.

Four numbers, each as a median and a 90th percentile with its count, per month (UTC) and for the baseline:
time to triage, time to the reportability decision (every market concluded), time to an approved report, and the
completeness of report fields at approval. The baseline is the first 30 days after the organization's go-live
(activated, else created), fixed once those 30 days have passed. The triage history a QMS export brought (its received
and triage dates) is shown apart, labelled "from your QMS export, before MDARIX". Sample records are left out.

No figure is broken down by person: no actor is read. Switch ``MDARIX_B6_VALUE_CENTRE`` (on): off, the routes 404.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app import feature_set
from backend.app.trial.sample_source import SAMPLE_SOURCE, is_sample

SWITCH = "MDARIX_B6_VALUE_CENTRE"
BASELINE_DAYS = 30
QMS_SOURCE = "QMS"  # trial/imports.py: a triage the QMS recorded (T-D9)
METRICS = (
    ("TIME_TO_TRIAGE", "Time to triage", "hours", "From the record reaching MDARIX to its triage completed"),
    (
        "TIME_TO_DECISION",
        "Time to the reportability decision",
        "days",
        "From awareness to the last market conclusion signed (every market concluded)",
    ),
    ("TIME_TO_APPROVED_REPORT", "Time to an approved report", "days", "From the signed conclusion to approval"),
    (
        "REPORT_COMPLETENESS",
        "Completeness of report fields",
        "percent",
        "Mandatory fields with a value in the approved report",
    ),
)


def enabled() -> bool:
    return feature_set.switched_on(SWITCH)


def summary(values: list[float]) -> dict:
    """Count, median and 90th percentile (nearest rank), rounded to one decimal; None values when there is none."""
    if not values:
        return {"count": 0, "median": None, "p90": None}
    ordered = sorted(values)
    p90 = ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]
    return {"count": len(ordered), "median": round(statistics.median(ordered), 1), "p90": round(p90, 1)}


def periods(points: list[tuple[datetime, float]], go_live: datetime | None) -> dict:
    """``points`` (end time, value): the baseline window's summary and each month's, newest month first."""
    months: dict[str, list[float]] = {}
    for at, value in points:
        months.setdefault(at.strftime("%Y-%m"), []).append(value)
    baseline = None
    if go_live is not None:
        end = go_live + timedelta(days=BASELINE_DAYS)
        baseline = summary([value for at, value in points if go_live <= at < end])
    return {
        "baseline": baseline,
        "months": [{"month": month, **summary(values)} for month, values in sorted(months.items(), reverse=True)],
    }


def _hours(start: datetime | None, end: datetime | None) -> float | None:
    return (end - start).total_seconds() / 3600 if start and end and end >= start else None


def _triage(db: Session, tenant_id) -> tuple[list, list]:
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import TriageRecord

    rows = (
        db.query(
            TriageRecord.opened_at,
            TriageRecord.completed_at,
            TriageRecord.qms_triaged_at,
            TriageRecord.source_system,
            Complaint.complaint_timestamp,
        )
        .outerjoin(
            Complaint,
            (Complaint.tenant_id == TriageRecord.tenant_id)
            & (Complaint.id == TriageRecord.subject_id)
            & (TriageRecord.subject_kind == "COMPLAINT"),
        )
        .filter(TriageRecord.tenant_id == tenant_id)
        .all()
    )
    mine, imported = [], []
    for opened, completed, qms_at, source, received in rows:
        if is_sample(source):
            continue
        if source == QMS_SOURCE:  # completed at import time: only the QMS's own dates count, apart
            hours = _hours(received, qms_at)
            if hours is not None:
                imported.append((qms_at, hours))
        elif (hours := _hours(opened, completed)) is not None:
            mine.append((completed, hours))
    return mine, imported


def _decisions(db: Session, tenant_id) -> list:
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment as Conclusion

    rows = (
        db.query(
            Conclusion.complaint_id,
            Conclusion.market,
            Conclusion.signed_at,
            Complaint.awareness_timestamp,
            Complaint.complaint_timestamp,
            Complaint.source_system,
        )
        .join(Complaint, (Complaint.tenant_id == Conclusion.tenant_id) & (Complaint.id == Conclusion.complaint_id))
        .filter(Conclusion.tenant_id == tenant_id)
        .all()
    )
    first: dict = {}  # complaint -> market -> first signed (None while only a draft)
    aware: dict = {}
    for complaint_id, market, signed_at, awareness, received, source in rows:
        if is_sample(source):
            continue
        aware[complaint_id] = awareness or received
        markets = first.setdefault(complaint_id, {})
        if signed_at is not None:
            markets[market] = min(signed_at, markets.get(market) or signed_at)
        else:
            markets.setdefault(market, None)
    points = []
    for complaint_id, markets in first.items():
        if markets and all(markets.values()):
            last = max(markets.values())
            hours = _hours(aware[complaint_id], last)
            if hours is not None:
                points.append((last, hours / 24))
    return points


def _reports(db: Session, tenant_id) -> tuple[list, list]:
    from backend.app.authority_reports import worksheet
    from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment as Conclusion

    rows = (
        db.query(ReportSnapshot.obligation_id, ReportSnapshot.approved_at, ReportSnapshot.fields, Conclusion.signed_at)
        .join(
            ReportObligation,
            (ReportObligation.tenant_id == ReportSnapshot.tenant_id)
            & (ReportObligation.id == ReportSnapshot.obligation_id),
        )
        .outerjoin(
            Conclusion,
            (Conclusion.tenant_id == ReportObligation.tenant_id) & (Conclusion.id == ReportObligation.assessment_id),
        )
        .filter(
            ReportSnapshot.tenant_id == tenant_id,
            ReportSnapshot.approved_at.isnot(None),
            ReportObligation.source_system.is_distinct_from(SAMPLE_SOURCE),
        )
        .order_by(ReportSnapshot.approved_at)
        .all()
    )
    times, completeness, seen = [], [], set()
    for obligation_id, approved_at, fields, signed_at in rows:
        if obligation_id in seen:  # the first approval of each report
            continue
        seen.add(obligation_id)
        hours = _hours(signed_at, approved_at)
        if hours is not None:
            times.append((approved_at, hours / 24))
        meter = worksheet.mandatory((fields or {}).get("sections") or [])
        if meter["total"]:
            completeness.append((approved_at, 100 * meter["filled"] / meter["total"]))
    return times, completeness


def build(db: Session, control_db: Session, tenant_id, now: datetime) -> dict:
    from backend.app.signed_reviews.audit_review import started

    go_live = started(control_db, tenant_id)
    triage, imported = _triage(db, tenant_id)
    times, completeness = _reports(db, tenant_id)
    points = {
        "TIME_TO_TRIAGE": triage,
        "TIME_TO_DECISION": _decisions(db, tenant_id),
        "TIME_TO_APPROVED_REPORT": times,
        "REPORT_COMPLETENESS": completeness,
    }
    metrics = []
    for code, label, unit, definition in METRICS:
        metrics.append(
            {
                "code": code,
                "label": label,
                "unit": unit,
                "definition": definition,
                **periods(points[code], go_live),
                "imported": summary([value for _, value in imported]) if code == "TIME_TO_TRIAGE" else None,
            }
        )
    return {
        "go_live": go_live.isoformat() if go_live else None,
        "baseline": {
            "from": go_live.isoformat() if go_live else None,
            "to": (go_live + timedelta(days=BASELINE_DAYS)).isoformat() if go_live else None,
            "fixed": bool(go_live) and now >= go_live + timedelta(days=BASELINE_DAYS),
        },
        "metrics": metrics,
    }


CSV_FIELDS = ("metric", "unit", "period", "count", "median", "p90")


def csv_rows(found: dict) -> list[dict]:
    rows = []
    for metric in found["metrics"]:
        base = {"metric": metric["label"], "unit": metric["unit"]}
        if metric["baseline"] is not None:
            rows.append({**base, "period": "Your baseline (first 30 days after go-live)", **metric["baseline"]})
        if metric["imported"] is not None:
            rows.append({**base, "period": "From your QMS export, before MDARIX", **metric["imported"]})
        rows += [
            {**base, "period": item["month"], **{k: item[k] for k in ("count", "median", "p90")}}
            for item in metric["months"]
        ]
    return rows
