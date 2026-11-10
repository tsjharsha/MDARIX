"""Before and after an action, as plain functions (B5 spec 3.3-3.4, rule version 1).

For one group (a version, or a cohort of lots) and one action date (a CAPA's measurement start, a field action's
effective date, a new version's release): complaints in a window before and an equal window after, the exposure in
each, and how surprising the split is if the rate per unit (or per day) had not changed. An exact conditional test:
given ``n = before + after``, the after-count is Binomial(n, exposure after / total exposure); one-sided p in each
direction. Across the groups of one view, Benjamini-Hochberg (as the trend board does).

Denominator, in this order (B5-D6): units shipped with ship dates when every lot of the group has shipments; else
units released with release dates when every lot has both; else "units unknown": counts by calendar days only, never
a rate from partial units. Result words are never verdicts: "Too early", "Too few to tell", "Fewer", "More", "No
change seen"; only a person's signed effectiveness check says "effective".
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from backend.app.signals.trend_rules import unit_days

RULE_VERSION = 1
MIN_WINDOW_DAYS = 90
MAX_WINDOW_DAYS = 365
MIN_EXPECTED = 5.0
P_LIMIT = 0.05
# Days between the action date and the start of the after window (B5-D5).
SETTLING_DAYS = {"CAPA": 0, "FIELD_ACTION": 30, "PRODUCT_CHANGE": 0}
DAYS_PER_MONTH = 30
# -ln(0.05): with no complaint after, the rate could still be up to this many over the exposure (95% upper bound).
ZERO_BOUND = -math.log(0.05)

SHIPPED, RELEASED, UNKNOWN = "SHIPPED", "RELEASED", "UNKNOWN"
TOO_EARLY, TOO_FEW, FEWER, MORE, NO_CHANGE = "TOO_EARLY", "TOO_FEW", "FEWER", "MORE", "NO_CHANGE"
# Two cohorts over the same period with units unknown: their counts are shown, never tested by calendar days.
COUNTS_ONLY = "COUNTS_ONLY"
WORDS = {
    TOO_EARLY: "Too early",
    TOO_FEW: "Too few to tell",
    FEWER: "Fewer",
    MORE: "More",
    NO_CHANGE: "No change seen",
    COUNTS_ONLY: "Counts only (units unknown)",
}
NOTICE = "Counts from your records; not a verdict. Only your signed effectiveness check says whether an action worked."
LIMITS = (
    "Reporting lag: recent events may not be reported yet.",
    "A change in how complaints are coded changes these counts.",
    "Seasonality: the two windows cover different months.",
    "Several actions at once: every action date is marked; the counts cannot tell them apart.",
    "You judge the result against the CAPA's own criteria and sign it.",
)
UNITS_UNKNOWN_NOTE = (
    "Units unknown: counts by calendar days; a change in units in the field can change these counts by itself."
)


def windows(action_on: date, today: date, settling_days: int = 0) -> dict:
    """Equal before and after windows by event date. The after window starts ``settling_days`` after the action and
    runs to today, at most ``MAX_WINDOW_DAYS``; the before window has the same length and ends the day before the
    action. ``after_days`` under ``MIN_WINDOW_DAYS`` means too early."""
    after_start = action_on + timedelta(days=settling_days)
    after_days = max(0, min(MAX_WINDOW_DAYS, (today - after_start).days + 1))
    after_end = after_start + timedelta(days=after_days - 1)
    length = max(after_days, 1)
    before_end = action_on - timedelta(days=1)
    return {
        "before": (before_end - timedelta(days=length - 1), before_end),
        "after": (after_start, after_end) if after_days else (after_start, after_start - timedelta(days=1)),
        "after_days": after_days,
        "days": length,
    }


def exposure(lots: list[dict], start: date, end: date, use_days: int | None = None) -> dict:
    """Unit-days over ``start``..``end`` for a group's lots, with the basis used. A lot is ``{"released_on", "units",
    "shipments": [(ship date, units)]}``. Shipped when every lot has shipments; released when every lot has a release
    date and units; else unknown, with how many lots lack what was needed (never a partial denominator)."""
    if not lots:
        return {"basis": UNKNOWN, "unit_days": None, "unknown_lots": 0, "lots": 0}
    if all(lot.get("shipments") for lot in lots):
        shipped = [(day, units) for lot in lots for day, units in lot["shipments"]]
        value = unit_days(shipped, start, end, use_days)
        if all(day is not None and units is not None for day, units in shipped):
            return {"basis": SHIPPED, "unit_days": value or 0.0, "unknown_lots": 0, "lots": len(lots)}
    missing = sum(1 for lot in lots if lot.get("released_on") is None or lot.get("units") is None)
    if not missing:
        value = unit_days([(lot["released_on"], lot["units"]) for lot in lots], start, end, use_days)
        return {"basis": RELEASED, "unit_days": value or 0.0, "unknown_lots": 0, "lots": len(lots)}
    return {"basis": UNKNOWN, "unit_days": None, "unknown_lots": missing, "lots": len(lots)}


def _log_pmf(k: int, n: int, p: float) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log1p(-p)


def binomial_tails(after: int, n: int, p: float) -> tuple[float, float]:
    """``(P(X <= after), P(X >= after))`` for X ~ Binomial(n, p), summed in log space so large n never underflows."""
    if n <= 0:
        return 1.0, 1.0
    if p <= 0:
        return 1.0, 1.0 if after <= 0 else 0.0
    if p >= 1:
        return (1.0 if after >= n else 0.0), 1.0
    logs = [_log_pmf(k, n, p) for k in range(n + 1)]
    top = max(logs)
    weights = [math.exp(value - top) for value in logs]
    total = sum(weights)
    lower = sum(weights[: after + 1]) / total
    upper = sum(weights[after:]) / total
    return min(1.0, lower), min(1.0, upper)


def word(after_days: int, expected_after: float, p_fewer: float | None, p_more: float | None) -> str:
    """The result word at the spec's boundaries: under 90 days too early; expected under 5 too few; p <= 0.05."""
    if after_days < MIN_WINDOW_DAYS:
        return TOO_EARLY
    if expected_after < MIN_EXPECTED:
        return TOO_FEW
    if p_fewer is not None and p_fewer <= P_LIMIT:
        return FEWER
    if p_more is not None and p_more <= P_LIMIT:
        return MORE
    return NO_CHANGE


def per_thousand(count: int, unit_days_value: float | None) -> float | None:
    """Complaints per 1,000 unit-months, or None without units."""
    if not unit_days_value:
        return None
    return round(count / (unit_days_value / DAYS_PER_MONTH) * 1000, 3)


def compare(before: int, after: int, window: dict, before_exposure: dict, after_exposure: dict) -> dict:
    """One group before and after. With units known on both sides the test weighs unit-days; otherwise (units unknown
    on either side) calendar days, and the group shows counts only."""
    counts_only = before_exposure["basis"] == UNKNOWN or after_exposure["basis"] == UNKNOWN
    if counts_only:
        weight_before, weight_after = float(window["days"]), float(max(window["after_days"], 0))
    else:
        weight_before, weight_after = before_exposure["unit_days"] or 0.0, after_exposure["unit_days"] or 0.0
    n = before + after
    total = weight_before + weight_after
    share = weight_after / total if total else 0.0
    expected_after = n * share
    p_fewer = p_more = None
    if window["after_days"] >= MIN_WINDOW_DAYS and expected_after >= MIN_EXPECTED:
        p_fewer, p_more = binomial_tails(after, n, share)
    result = word(window["after_days"], expected_after, p_fewer, p_more)
    found = {
        "before": before,
        "after": after,
        "basis": UNKNOWN if counts_only else after_exposure["basis"],
        "counts_only": counts_only,
        "unknown_lots": max(before_exposure["unknown_lots"], after_exposure["unknown_lots"]),
        "expected_after": round(expected_after, 3),
        "p_fewer": p_fewer,
        "p_more": p_more,
        "result": result,
        "word": WORDS[result] + (" (by calendar days)" if counts_only else ""),
        "rate_before": None if counts_only else per_thousand(before, weight_before),
        "rate_after": None if counts_only else per_thousand(after, weight_after),
        "per_30_days_before": round(before / window["days"] * DAYS_PER_MONTH, 3) if counts_only else None,
        "per_30_days_after": round(after / window["after_days"] * DAYS_PER_MONTH, 3)
        if counts_only and window["after_days"]
        else None,
        "upper_bound_after": None,
    }
    if after == 0 and not counts_only and weight_after:
        # "0 complaints; with this exposure the rate could still be up to X per 1,000 unit-months." Never "eliminated".
        found["upper_bound_after"] = round(ZERO_BOUND / (weight_after / DAYS_PER_MONTH) * 1000, 4)
    return found


def adjust(rows: list[dict]) -> list[dict]:
    """Benjamini-Hochberg across the groups of one view, each direction apart; the word follows the adjusted values.
    Groups not tested (too early, too few) are returned as they are."""
    adjusted = [dict(row) for row in rows]
    for key in ("p_fewer", "p_more"):
        tested = sorted((row[key], index) for index, row in enumerate(adjusted) if row[key] is not None)
        m = len(tested)
        running = 1.0
        for rank in range(m, 0, -1):
            value, index = tested[rank - 1]
            running = min(running, value * m / rank)
            adjusted[index][f"{key}_adjusted"] = running
    for row in adjusted:
        if row["p_fewer"] is None:
            continue
        result = (
            FEWER if row["p_fewer_adjusted"] <= P_LIMIT else MORE if row["p_more_adjusted"] <= P_LIMIT else NO_CHANGE
        )
        row["result"] = result
        row["word"] = WORDS[result] + (" (by calendar days)" if row["counts_only"] else "")
    return adjusted
