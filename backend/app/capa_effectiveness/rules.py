"""The rules of CAPA effectiveness checks, as plain functions.

Why it matters: CAPA was cited in 9 of 17 device warning letters in Q1 2026 and 5 of 12 in Q2, and closing a CAPA without
verifying that the action worked is a recurring finding. Each CAPA here gets a check: what will show the
action worked (the criteria), the day to check, and the day the measurement starts; a reminder before the day; and a
result a person signs (EFFECTIVE or NOT_EFFECTIVE) with what they saw. MDARIX shows the complaint recurrence on the
CAPA's product and problem codes before and after the action as observed counts, never as a statistical verdict; the
person judges against the criteria.
"""

from __future__ import annotations

from datetime import date, timedelta

PLANNED, EFFECTIVE, NOT_EFFECTIVE = "PLANNED", "EFFECTIVE", "NOT_EFFECTIVE"
RESULTS = (EFFECTIVE, NOT_EFFECTIVE)
# How a CAPA's check stands, most urgent first.
OVERDUE, DUE_SOON, NOT_PLANNED, SCHEDULED = "OVERDUE", "DUE_SOON", "NOT_PLANNED", "SCHEDULED"
STATE_ORDER = {OVERDUE: 0, DUE_SOON: 1, NOT_PLANNED: 2, NOT_EFFECTIVE: 3, SCHEDULED: 4, EFFECTIVE: 5}
# The plan was made in MDARIX, or only a date came from the customer's quality system (capas.effectiveness_check_at).
MDARIX, SOURCE_SYSTEM = "MDARIX", "SOURCE_SYSTEM"

DUE_SOON_DAYS = 14
CRITERIA_MIN, CRITERIA_MAX = 10, 2000
SUMMARY_MIN, SUMMARY_MAX = 10, 4000
REASON_MIN = 10
PLAN_PAST_DAYS = 3650
PLAN_FUTURE_DAYS = 3 * 365
TOO_EARLY_DAYS = 14
BASELINE_MIN_DAYS, BASELINE_MAX_DAYS = 30, 365

# CAPA statuses as source systems write them (lower case). A cancelled or rejected CAPA needs no check; a closed one
# still does (closing a CAPA without verifying it is the finding).
EXCLUDED_STATUSES = frozenset({"cancelled", "canceled", "rejected", "void", "voided", "withdrawn"})
CLOSED_STATUSES = frozenset({"closed", "resolved", "completed", "complete", "done", "archived"})

# The signature: what a person signs, and the codes the signature record keeps (12 characters at most).
DECISION_TYPE = "CAPA_EFFECTIVENESS"
SIGNATURE_CODES = {EFFECTIVE: "EFFECTIVE", NOT_EFFECTIVE: "INEFFECTIVE"}
OBJECT_TYPE = "CapaEffectivenessCheck"


def status_of(value: object) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def is_excluded(status: object) -> bool:
    return status_of(status) in EXCLUDED_STATUSES


def is_closed(status: object) -> bool:
    return status_of(status) in CLOSED_STATUSES


def state_of(check_status: str | None, planned_on: date | None, today: date) -> str:
    """How a CAPA's current check stands: its signed result, or from its planned day (none: NOT_PLANNED)."""
    if check_status in (EFFECTIVE, NOT_EFFECTIVE):
        return check_status
    if planned_on is None:
        return NOT_PLANNED
    left = (planned_on - today).days
    if left < 0:
        return OVERDUE
    if left <= DUE_SOON_DAYS:
        return DUE_SOON
    return SCHEDULED


def plan_problem(criteria: str, planned_on: date, measured_from: date, today: date) -> str | None:
    """Why a plan cannot be saved, or None."""
    if not CRITERIA_MIN <= len(criteria) <= CRITERIA_MAX:
        return f"Say in {CRITERIA_MIN} to {CRITERIA_MAX} characters what will show the action worked"
    if planned_on > today + timedelta(days=PLAN_FUTURE_DAYS):
        return "Plan the check within three years"
    if measured_from < today - timedelta(days=PLAN_PAST_DAYS):
        return "Start the measurement within the last ten years"
    if measured_from > planned_on:
        return "The measurement starts on or before the day of the check"
    return None


def per_30(count: int, days: int) -> float:
    return round(count * 30 / days, 1) if days > 0 else 0.0


def recurrence(before: int, before_days: int, after: int, after_days: int) -> dict:
    """The complaint recurrence before and since the measurement start, as observed counts and a rate per 30 days.
    ``direction`` says only which way the rate moved; it is not a statistical test."""
    too_early = after_days < TOO_EARLY_DAYS
    before_rate, after_rate = per_30(before, before_days), per_30(after, after_days)
    if before == 0 and after == 0:
        direction = "NONE"
    elif after_rate < before_rate:
        direction = "FEWER"
    elif after_rate > before_rate:
        direction = "MORE"
    else:
        direction = "SAME"
    return {
        "before": {"complaints": before, "days": before_days, "per_30_days": before_rate},
        "since": {"complaints": after, "days": after_days, "per_30_days": after_rate},
        "direction": direction,
        "too_early": too_early,
        "note": "Observed from complaint records; not a statistical test. Judge against the criteria.",
    }


def baseline_days(after_days: int) -> int:
    """The length of the period before the measurement start compared with the period since: as long, 30 to 365 days."""
    return max(BASELINE_MIN_DAYS, min(BASELINE_MAX_DAYS, after_days))


def default_criteria(product_name: str | None, problem_codes: list[str], days: int = 90) -> str:
    """A suggested criterion the person edits: no recurrence of the case's problem on the product for a period."""
    product = product_name or "the product"
    if problem_codes:
        codes = ", ".join(problem_codes[:5])
        return f"No new complaints with problem code {codes} on {product} for {days} days after the action."
    return f"No recurrence of the problem on {product} for {days} days after the action."


def signature_meaning(capa_ref: str, round_number: int, result: str) -> str:
    verdict = "effective" if result == EFFECTIVE else "not effective"
    return (
        f"I have reviewed effectiveness check {round_number} of {capa_ref} against its criteria and the evidence shown, "
        f"and record that the action was {verdict}."
    )


def signature_material(
    *,
    capa_id: str,
    capa_ref: str,
    check_id: str,
    round_number: int,
    criteria: str,
    planned_on: str,
    measured_from: str,
    result: str,
    summary: str,
    evidence: dict,
) -> dict:
    """Exactly what is signed (its SHA-256 is the signature's content fingerprint)."""
    return {
        "capa_id": capa_id,
        "capa": capa_ref,
        "check_id": check_id,
        "round": round_number,
        "criteria": criteria,
        "planned_on": planned_on,
        "measured_from": measured_from,
        "result": result,
        "summary": summary,
        "evidence": evidence,
    }
