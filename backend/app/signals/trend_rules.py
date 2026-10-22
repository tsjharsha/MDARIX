"""The statistical trend check, as plain functions.

Why it matters (FDA warning letters, 2026): a manufacturer trended only 10 of 28 complaints and by root-cause code,
so its threshold was never reached; another's overall top complaint hid each device's real top problem. The count
rule (3 complaints about one problem within 30 days) catches clusters; this check adds the question an inspector
asks: is this product version's complaint rate now higher than its own history?

For each group (a product version, or a version and one problem or complaint type), the complaints of the last
``RECENT_DAYS`` are compared with the version's rate over the history before them (up to ``HISTORY_DAYS``, never
before the version was released). If the rate had not changed, the number expected in the recent window is the history
rate times its length; the check reports the Poisson probability of seeing at least the observed number by chance.
Every complaint counts, whatever its status; only records a person dismissed on the second look as not a complaint are
left out.

It is a check, never a verdict, and never raises a signal on its own: it runs beside the count rule, needs at least
``MIN_COMPLAINTS`` recent complaints and ``MIN_HISTORY_DAYS`` of history, and a person decides.

Two refinements (md43):

- The denominator. When every lot of the versions compared has a quantity (devices released, ``lot_batches.quantity``),
  the expected number follows the units in the field over each window (unit-days: each lot counts from its release for
  its quantity) instead of the calendar, so a version shipped in growing numbers does not look like a rising trend for
  that reason alone (``basis: UNITS``). Without quantities the check counts by calendar days (``basis: TIME``) and says
  that a growing installed base can raise the rate by itself.
- A new version. A version younger than ``RECENT_DAYS + MIN_HISTORY_DAYS`` has too little history of its own, yet its
  first months are when a design or supplier change shows. It is then compared with the version it replaced: the
  previous version's complaints over the ``HISTORY_DAYS`` before the new version's release (``baseline:
  PREVIOUS_VERSION``). Is the new version worse than the one it replaced?
"""

from __future__ import annotations

import math
from dataclasses import dataclass

RECENT_DAYS = 30
HISTORY_DAYS = 180
MIN_HISTORY_DAYS = 60
MIN_COMPLAINTS = 3
SIGNIFICANT_P = 0.01
ELEVATED_P = 0.05

# The result of one group, most notable first.
SIGNIFICANT, ELEVATED, STEADY, TOO_FEW, SHORT_HISTORY = (
    "SIGNIFICANT",
    "ELEVATED",
    "STEADY",
    "TOO_FEW",
    "SHORT_HISTORY",
)
RESULT_ORDER = {SIGNIFICANT: 0, ELEVATED: 1, STEADY: 2, TOO_FEW: 3, SHORT_HISTORY: 4}
RESULT_LABELS = {
    SIGNIFICANT: "Rate significantly higher than its history",
    ELEVATED: "Rate higher than its history",
    STEADY: "In line with its history",
    TOO_FEW: f"Fewer than {MIN_COMPLAINTS} recent complaints: not assessed",
    SHORT_HISTORY: f"Less than {MIN_HISTORY_DAYS} days of history: not assessed",
}
GROUPINGS = ("version", "problem", "type")
# What the expected number is scaled by, and what it is compared with.
UNITS, TIME = "UNITS", "TIME"
OWN_HISTORY, PREVIOUS_VERSION = "OWN_HISTORY", "PREVIOUS_VERSION"


def poisson_tail(observed: int, expected: float) -> float:
    """P(X >= observed) for X ~ Poisson(expected), computed exactly (1 for observed <= 0)."""
    if observed <= 0:
        return 1.0
    if expected <= 0:
        return 0.0
    # 1 - P(X <= observed - 1), summed in log space for stability.
    term = math.exp(-expected)
    below = term
    for k in range(1, observed):
        term *= expected / k
        below += term
    return max(0.0, min(1.0, 1.0 - below))


def unit_days(lots, start, end) -> float | None:
    """Units in the field times days over ``start``..``end`` (dates, both included): each lot counts from the day it
    was released for its quantity. ``lots`` is ``[(released date, quantity)]``. None when there is no lot, a lot's
    release or quantity is unknown, or no unit was in the field: the calendar is used then."""
    if not lots or end < start:
        return None
    total = 0.0
    for released, quantity in lots:
        if released is None or quantity is None:
            return None
        first = max(start, released)
        if first > end:
            continue
        total += quantity * ((end - first).days + 1)
    return total or None


def history_days(version_age_days: int | None) -> int:
    """How many days before the recent window count as history: up to HISTORY_DAYS, never before the release."""
    if version_age_days is None:
        return HISTORY_DAYS
    return max(0, min(HISTORY_DAYS, version_age_days - RECENT_DAYS))


@dataclass(frozen=True)
class Check:
    recent: int
    history: int
    history_days: int
    expected: float
    p_value: float | None
    ratio: float | None
    result: str
    basis: str = TIME
    baseline: str = OWN_HISTORY
    baseline_name: str | None = None

    @property
    def label(self) -> str:
        label = RESULT_LABELS[self.result]
        if self.baseline == PREVIOUS_VERSION and self.result in (SIGNIFICANT, ELEVATED, STEADY):
            return label.replace("its history", "the previous version")
        return label

    def as_dict(self) -> dict:
        return {
            "recent": self.recent,
            "recent_days": RECENT_DAYS,
            "history": self.history,
            "history_days": self.history_days,
            "expected": round(self.expected, 2),
            "p_value": None if self.p_value is None else round(self.p_value, 4),
            "ratio": None if self.ratio is None else round(self.ratio, 1),
            "result": self.result,
            "label": self.label,
            "basis": self.basis,
            "baseline": self.baseline,
            "baseline_name": self.baseline_name,
        }


def check(
    recent: int,
    history: int,
    days_of_history: int,
    *,
    scale: float | None = None,
    baseline: str = OWN_HISTORY,
    baseline_name: str | None = None,
) -> Check:
    """The trend check of one group: ``recent`` complaints in the last RECENT_DAYS against ``history`` complaints in the
    ``days_of_history`` days of its baseline (its own history, or the previous version's). With no history complaint
    at all, one is assumed, so the expected number is never zero (a cautious upper estimate of the history rate) and
    the probability stays meaningful. ``scale``: the recent window's unit-days over the baseline's (``unit_days``); the
    expected number follows the units in the field then, else the calendar."""
    basis = UNITS if scale is not None else TIME
    extra = {"basis": basis, "baseline": baseline, "baseline_name": baseline_name}
    if days_of_history < MIN_HISTORY_DAYS:
        return Check(recent, history, days_of_history, 0.0, None, None, SHORT_HISTORY, **extra)
    expected = max(history, 1) * (scale if scale is not None else RECENT_DAYS / days_of_history)
    if recent < MIN_COMPLAINTS:
        return Check(recent, history, days_of_history, expected, None, None, TOO_FEW, **extra)
    p_value = poisson_tail(recent, expected)
    ratio = recent / expected if expected else None
    if p_value < SIGNIFICANT_P:
        result = SIGNIFICANT
    elif p_value < ELEVATED_P:
        result = ELEVATED
    else:
        result = STEADY
    return Check(recent, history, days_of_history, expected, p_value, ratio, result, **extra)


def sentence(name: str, item: Check) -> str:
    """The check in one plain sentence, e.g. for a signal's detail or an export."""
    if item.result == SHORT_HISTORY:
        return f"{name}: less than {MIN_HISTORY_DAYS} days of history, so the rate is not compared."
    if item.result == TOO_FEW:
        return f"{name}: {item.recent:,} complaint(s) in the last {RECENT_DAYS} days, too few to compare."
    if item.baseline == PREVIOUS_VERSION:
        text = (
            f"{name}: {item.recent:,} complaints in the last {RECENT_DAYS} days against {item.expected:,.1f} expected from "
            f"{item.baseline_name or 'the previous version'} over the {item.history_days} days before this version's "
            f"release ({item.history:,} complaints); chance of at least this many if nothing changed: "
            f"{item.p_value:.3f}."
        )
    else:
        text = (
            f"{name}: {item.recent:,} complaints in the last {RECENT_DAYS} days against {item.expected:,.1f} expected from "
            f"the previous {item.history_days} days ({item.history:,} complaints); chance of at least this many if "
            f"nothing changed: {item.p_value:.3f}."
        )
    if item.basis == UNITS:
        text += " Scaled by the units in the field (lot quantities)."
    return text
