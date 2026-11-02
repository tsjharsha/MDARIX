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

0.10.63 (quality plan stage 2):

- The probability is computed in log space (``poisson_tail``), so a large expected number no longer reads "in line"
  for any count (S1).
- A version younger than ``RECENT_DAYS`` is expected only the days it has existed (``recent_days``, S3).
- The groups tested on one board are allowed for together (``adjust``, Benjamini-Hochberg); the result follows the
  adjusted value at the same 1% and 5% thresholds, and both values are shown (S4).
- A version with its own history and a version it replaced is compared with both, and the stronger comparison is
  reported, naming the other (``stronger``, J26).
- A single-use or consumable product (``single_use``) is counted by calendar days: its units are used up, so the units
  ever released are not the units in the field (J27). 0.10.64: the product's own single-use field (else its device
  category, product_facts.single_use) decides, and the words only when neither is set; with a use period each lot's
  units count only that many days after its release (``unit_days(use_days=...)``).
- The board (signals/insight.py) counts an event a person linked from several records once, at its earliest record
  (S2), and leaves complaints dated in the future out of both windows (S5).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import timedelta

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
    """P(X >= observed) for X ~ Poisson(expected), in log space so it never underflows (0.10.63, S1: from
    ``exp(-expected)``, an expected number above ~745 gave 1.0 for any count). Above the expected number the tail is
    summed upwards from ``observed``; at or below it, 1 minus the sum below ``observed``. 1 for observed <= 0."""
    if observed <= 0:
        return 1.0
    if expected <= 0:
        return 0.0
    log_expected = math.log(expected)
    if observed > expected:
        # Terms fall from P(X = observed) on: sum them as multiples of the first, then scale by it.
        log_first = -expected + observed * log_expected - math.lgamma(observed + 1)
        total = term = 1.0
        k = observed
        while term > 1e-17 * total:
            k += 1
            term *= expected / k
            total += term
        return max(0.0, min(1.0, math.exp(log_first + math.log(total))))
    # Terms fall from P(X = observed - 1) down to P(X = 0).
    log_last = -expected + (observed - 1) * log_expected - math.lgamma(observed)
    total = term = 1.0
    for k in range(observed - 1, 0, -1):
        term *= k / expected
        total += term
        if term <= 1e-17 * total:
            break
    return max(0.0, min(1.0, 1.0 - math.exp(log_last + math.log(total))))


def unit_days(lots, start, end, use_days: int | None = None) -> float | None:
    """Units in the field times days over ``start``..``end`` (dates, both included): each lot counts from the day it
    was released for its quantity, and with ``use_days`` (a single-use product's use period) only for that many days.
    ``lots`` is ``[(released date, quantity)]``. None when there is no lot, a lot's release or quantity is unknown, or
    no unit was in the field: the calendar is used then."""
    if not lots or end < start:
        return None
    total = 0.0
    for released, quantity in lots:
        if released is None or quantity is None:
            return None
        first = max(start, released)
        last = end if use_days is None else min(end, released + timedelta(days=use_days - 1))
        if first > last:
            continue
        total += quantity * ((last - first).days + 1)
    return total or None


def history_days(version_age_days: int | None) -> int:
    """How many days before the recent window count as history: up to HISTORY_DAYS, never before the release."""
    if version_age_days is None:
        return HISTORY_DAYS
    return max(0, min(HISTORY_DAYS, version_age_days - RECENT_DAYS))


# Words that mark a single-use or consumable product (its name, family, GMDN term or description): its units are used
# up, so the units ever released are not all still in the field (J27). shortcut: a word list, until product records
# carry a single-use field and a use period (owner decision); a reusable product named with one of these words is
# counted by calendar days, the more cautious basis here.
SINGLE_USE_WORDS = re.compile(
    r"(?i)\b(single[- ]use|single[- ]patient|disposables?|consumables?|ivds?|in[- ]vitro|reagents?|test strips?|"
    r"cartridges?|kits?|syringes?|catheters?|lancets?|cannulas?)\b"
)
SINGLE_USE_NOTE = (
    "Single-use or consumable product: its units are used up, so the units released are not all still in use. "
    "Counted by calendar days instead of units in the field."
)


def single_use(*texts: str | None) -> bool:
    """Whether a product's name, family, GMDN term or description marks it single-use or consumable."""
    return any(SINGLE_USE_WORDS.search(str(text or "")) for text in texts)


def use_note(days: int) -> str:
    return (
        f"Single-use product with a {days}-day use period: each lot's units count as in use for {days} days after "
        "its release."
    )


def product_basis(product) -> tuple[bool, int | None]:
    """(single-use, use period in days or None) of a product: its single-use field and use period, else its device
    category, else its words (the fallback for a product whose category is not set)."""
    from backend.app.product_facts import single_use as from_fields

    if product is None:
        return False, None
    found = from_fields(product)
    if found is None:
        found = single_use(product.name, product.product_family, product.gmdn_term, product.description)
    period = getattr(product, "use_period_days", None) if found else None
    return found, period or None


def _result(p_value: float) -> str:
    if p_value < SIGNIFICANT_P:
        return SIGNIFICANT
    if p_value < ELEVATED_P:
        return ELEVATED
    return STEADY


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
    # The days of the recent window the group existed (S3: a version younger than RECENT_DAYS, the days since release).
    recent_days: int = RECENT_DAYS
    # S4: the Benjamini-Hochberg adjusted value across the groups tested on one board (``adjust``) and how many were
    # tested; the result follows the adjusted value. A check on its own is one group tested: adjusted = raw.
    p_adjusted: float | None = None
    groups_tested: int = 1
    # Why the expected number follows the calendar although its lots have quantities (J27: single-use), or None.
    basis_note: str | None = None
    # J26: the other baseline also compared when the group has both; the stronger comparison is the one reported.
    also_compared: str | None = None

    @property
    def label(self) -> str:
        label = RESULT_LABELS[self.result]
        if self.baseline == PREVIOUS_VERSION and self.result in (SIGNIFICANT, ELEVATED, STEADY):
            return label.replace("its history", "the previous version")
        return label

    def as_dict(self) -> dict:
        adjusted = self.p_value if self.p_adjusted is None else self.p_adjusted
        return {
            "recent": self.recent,
            "recent_days": self.recent_days,
            "history": self.history,
            "history_days": self.history_days,
            "expected": round(self.expected, 2),
            "p_value": None if self.p_value is None else round(self.p_value, 4),
            "p_adjusted": None if adjusted is None else round(adjusted, 4),
            "groups_tested": self.groups_tested,
            "ratio": None if self.ratio is None else round(self.ratio, 1),
            "result": self.result,
            "label": self.label,
            "basis": self.basis,
            "basis_note": self.basis_note,
            "baseline": self.baseline,
            "baseline_name": self.baseline_name,
            "also_compared": self.also_compared,
        }


def check(
    recent: int,
    history: int,
    days_of_history: int,
    *,
    scale: float | None = None,
    baseline: str = OWN_HISTORY,
    baseline_name: str | None = None,
    recent_days: int = RECENT_DAYS,
    basis_note: str | None = None,
) -> Check:
    """The trend check of one group: ``recent`` complaints in the last RECENT_DAYS against ``history`` complaints in the
    ``days_of_history`` days of its baseline (its own history, or the previous version's). With no history complaint
    at all, one is assumed, so the expected number is never zero (a cautious upper estimate of the history rate) and
    the probability stays meaningful. ``scale``: the recent window's unit-days over the baseline's (``unit_days``); the
    expected number follows the units in the field then, else the calendar. ``recent_days``: the days of the recent
    window the group existed (S3: a version released 12 days ago is expected 12 days of complaints, not 30)."""
    basis = UNITS if scale is not None else TIME
    recent_days = max(1, min(RECENT_DAYS, recent_days))
    extra = {
        "basis": basis,
        "baseline": baseline,
        "baseline_name": baseline_name,
        "recent_days": recent_days,
        "basis_note": basis_note,
    }
    if days_of_history < MIN_HISTORY_DAYS:
        return Check(recent, history, days_of_history, 0.0, None, None, SHORT_HISTORY, **extra)
    expected = max(history, 1) * (scale if scale is not None else recent_days / days_of_history)
    if recent < MIN_COMPLAINTS:
        return Check(recent, history, days_of_history, expected, None, None, TOO_FEW, **extra)
    p_value = poisson_tail(recent, expected)
    ratio = recent / expected if expected else None
    return Check(recent, history, days_of_history, expected, p_value, ratio, _result(p_value), **extra)


def stronger(own: Check, previous: Check | None) -> Check:
    """J26: a version with both its own history and a version it replaced is compared with both; the stronger
    comparison (the lower chance) is reported and names the other, so a lasting rise since the change does not fade
    once the version's own history holds it. Without an assessed comparison: its own history, as before (the previous
    version when its own history is too short)."""
    if previous is None:
        return own
    if own.p_value is None and previous.p_value is None:
        return previous if own.result == SHORT_HISTORY else own
    if own.p_value is None or (previous.p_value is not None and previous.p_value < own.p_value):
        return replace(previous, also_compared="its own history" if own.result != SHORT_HISTORY else None)
    return replace(own, also_compared=previous.baseline_name or "the previous version")


def adjust(checks: list[Check]) -> list[Check]:
    """S4: the Benjamini-Hochberg adjusted value of every assessed check across the groups tested on one board, in
    the same order; the result follows the adjusted value at the same thresholds (under 1% significant, under 5%
    higher). Checks not assessed are returned as they are. The adjusted value of the i-th smallest of m values is the
    least of p(j) * m / j over j >= i, at most 1."""
    tested = sorted((item.p_value, index) for index, item in enumerate(checks) if item.p_value is not None)
    m = len(tested)
    adjusted: dict[int, float] = {}
    running = 1.0
    for rank in range(m, 0, -1):
        p_value, index = tested[rank - 1]
        running = min(running, p_value * m / rank)
        adjusted[index] = running
    return [
        replace(item, p_adjusted=adjusted[index], groups_tested=m, result=_result(adjusted[index]))
        if index in adjusted
        else item
        for index, item in enumerate(checks)
    ]


def _p(value: float) -> str:
    """A chance in three decimals; "under 0.001" where three decimals would read 0.000."""
    return "under 0.001" if value < 0.0005 else f"{value:.3f}"


def _chance(item: Check) -> str:
    text = f"chance of at least this many if nothing changed: {_p(item.p_value)}"
    if item.groups_tested > 1 and item.p_adjusted is not None:
        text += f" ({_p(item.p_adjusted)} allowing for the {item.groups_tested} groups checked)"
    return text


def sentence(name: str, item: Check) -> str:
    """The check in one plain sentence, e.g. for a signal's detail or an export."""
    if item.result == SHORT_HISTORY:
        return f"{name}: less than {MIN_HISTORY_DAYS} days of history, so the rate is not compared."
    window = (
        f"in the last {RECENT_DAYS} days"
        if item.recent_days >= RECENT_DAYS
        else f"in the {item.recent_days} day{'s' if item.recent_days != 1 else ''} since its release"
    )
    if item.result == TOO_FEW:
        return f"{name}: {item.recent:,} complaint(s) {window}, too few to compare."
    if item.baseline == PREVIOUS_VERSION:
        text = (
            f"{name}: {item.recent:,} complaints {window} against {item.expected:,.1f} expected from "
            f"{item.baseline_name or 'the previous version'} over the {item.history_days} days before this version's "
            f"release ({item.history:,} complaints); {_chance(item)}."
        )
    else:
        text = (
            f"{name}: {item.recent:,} complaints {window} against {item.expected:,.1f} expected from "
            f"the previous {item.history_days} days ({item.history:,} complaints); {_chance(item)}."
        )
    if item.also_compared:
        text += f" Also compared with {item.also_compared}; the stronger comparison is shown."
    if item.basis == UNITS:
        text += " Scaled by the units in the field (lot quantities)."
    elif item.basis_note:
        text += f" {item.basis_note}"
    return text
