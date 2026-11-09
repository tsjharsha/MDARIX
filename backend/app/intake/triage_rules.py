"""Triage at two speeds (release 0.10.93, B2; spec 3.4, T-D1 to T-D13, plan A1 and A6), as plain functions.

- **Speed.** Fast track: an urgent Case, a death, a serious injury, any harm alleged, harm not known (or "Not known
  yet"), a potential harm of Serious or above, a possible public health threat, a manual escalation or an automatic
  reopening. Target: ``triage_fast_hours`` clock hours (default 4, nights and weekends count, OD-7). Everything else
  is routine: due at the end of the next working day on the organization's calendar, one click to confirm.
- **Severity.** "Not known yet" and the harm scale. The floor comes from the facts (death: Catastrophic; serious
  injury: Serious); a severity below it is refused. Lowering a saved severity needs a reason.
- **Downgrade of a fast-track (critical) triage** (A6): lowering the severity or the potential harm, leaving the fast
  track, or a later awareness than the earliest known. It needs the approval of a second person outside the trial.
- **Acknowledgement** (A1): a fast-track item needs a named owner to acknowledge it within ``ACK_HOURS``; unacknowledged
  it becomes overdue and the alert sweep escalates it to the backup and the escalation role.
- **Automatic reopening** (T-D7): a death, a serious injury or a threat that was not there at completion, or a higher
  floor, reopens a finished triage on the fast track.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.intake import rules
from backend.app.reportability import markets

NOT_KNOWN = "NOT_KNOWN"
SCALE = (NOT_KNOWN, *markets.LEVELS)
SCALE_LABELS = {NOT_KNOWN: "Not known yet", **markets.LEVEL_LABELS}
FAST, ROUTINE = "FAST", "ROUTINE"
SPEED_LABELS = {FAST: "Fast-track triage", ROUTINE: "Routine triage"}
# shortcut: a fixed acknowledgement window; make it an oversight setting when a pilot asks for another value.
ACK_HOURS = 1
FOLLOW_UP_TASK = "TRIAGE_HARM_FOLLOW_UP"
DOWNGRADE_TASK = "TRIAGE_DOWNGRADE_APPROVAL"

CONTAINMENT = {
    "NONE_NEEDED": "None needed",
    "USER_TOLD": "User told how to stay safe",
    "OUT_OF_USE": "Device taken out of use",
    "HOLD_LOT": "Hold the lot",
    "FIELD_ACTION": "Consider a field action",
    "OTHER": "Other",
}
# The containment choices that open a task (T-D11): (task type, title).
CONTAINMENT_TASKS = {
    "HOLD_LOT": ("LOT_HOLD", "Lot impact: decide whether to hold the lot of {ref}"),
    "FIELD_ACTION": ("FIELD_ACTION_DECISION", "Field action decision for {ref}: yes or no, with a reason"),
}
ROUTINE_PREFILL = {
    "severity": markets.NEGLIGIBLE,
    "harm_now_label": "No health consequence",
    "containment": ["NONE_NEEDED"],
    "no_action_reason": "None needed: no harm alleged",
}


FAST_FACTS = ("urgent", "death", "serious_injury", "harm", "harm_unknown", "serious_potential", "threat", "manual")


def rank(level: str | None) -> int:
    """The level's place on the scale; "Not known yet" and nothing rank below Negligible."""
    return markets.rank(level) if level in markets.LEVELS else -1


def facts(flags: list[dict], threat: bool = False) -> dict:
    """The facts triage decides on, read from a record's triage flags (intake/rules.py)."""
    codes = {flag["code"] for flag in flags}
    answers = {flag.get("question"): flag.get("answer") for flag in flags if flag["code"] == "FIRST_CONTACT"}
    death = "DEATH" in codes
    serious = "SERIOUS_INJURY" in codes or answers.get("Q5") == rules.YES
    harm = death or serious or "HARM_LEVEL" in codes or answers.get("Q4") == rules.YES
    unknown = (
        "HARM_UNKNOWN" in codes
        or "HARM_WORDS" in codes
        or any(answers.get(q) in (rules.UNKNOWN, rules.NOT_STATED) for q in ("Q4", "Q5"))
    )
    return {
        "urgent": "URGENT_INTAKE" in codes,
        "death": death,
        "serious_injury": serious,
        "harm": harm,
        "harm_unknown": unknown and not harm,
        "malfunction": "MALFUNCTION" in codes or answers.get("Q6") in (rules.YES, rules.UNKNOWN),
        # A recorded malfunction (it could cause a death or serious injury if it recurred) or question 6 answered Yes:
        # the potential harm is serious by the facts.
        "serious_potential": "MALFUNCTION" in codes or answers.get("Q6") == rules.YES,
        "manual": "MANUAL" in codes,
        "threat": bool(threat),
    }


def floor(found: dict) -> tuple[str | None, list[str]]:
    """The lowest severity the facts allow, and why."""
    if found.get("death"):
        return markets.CATASTROPHIC, ["At least Catastrophic: a death is recorded"]
    if found.get("serious_injury"):
        return markets.SERIOUS, ["At least Serious: a serious injury is recorded"]
    return None, []


def speed(found: dict, potential: str | None = None, severity: str | None = None, reopened: bool = False) -> str:
    fast = (
        reopened
        or severity == NOT_KNOWN
        or rank(potential) >= rank(markets.SERIOUS)
        or any(found.get(key) for key in FAST_FACTS)
    )
    return FAST if fast else ROUTINE


def why_fast(found: dict, potential: str | None = None, severity: str | None = None, reopened: bool = False) -> str:
    for test, text in (
        (reopened, "reopened by new information"),
        (found.get("death"), "a death is recorded"),
        (found.get("serious_injury"), "a serious injury is alleged"),
        (found.get("threat"), "a possible public health threat"),
        (found.get("urgent"), "an urgent case"),
        (found.get("harm"), "harm is alleged"),
        (found.get("harm_unknown") or severity == NOT_KNOWN, "the harm is not known yet"),
        (
            found.get("serious_potential") or rank(potential) >= rank(markets.SERIOUS),
            "a malfunction that could cause serious harm",
        ),
        (found.get("manual"), "escalated by hand"),
    ):
        if test:
            return f"Fast track: {text}"
    return "Routine: no harm alleged"


def due(kind: str, opened: datetime, fast_hours: int, calendar) -> datetime:
    """Fast track: clock hours from reaching triage (24/7). Routine: the end of the next working day."""
    if kind == FAST:
        return rules.utc(opened) + timedelta(hours=fast_hours)
    return calendar.working_day_end(rules.utc(opened), 1)


def ack_due(opened: datetime, target: datetime) -> datetime:
    return min(rules.utc(opened) + timedelta(hours=ACK_HOURS), rules.utc(target))


def clock(opened: datetime, target: datetime, now: datetime) -> dict:
    """The triage target (the shape of rules.triage_clock), from its stored or computed due time."""
    opened, target = rules.utc(opened), rules.utc(target)
    hours = max(1, round((target - opened).total_seconds() / 3600))
    left = (target - now).total_seconds() / 3600
    state = "OVERDUE" if left < 0 else "DUE_SOON" if left <= hours / 4 else "RUNNING"
    return {
        "from": opened.isoformat(),
        "target_hours": hours,
        "due_at": target.isoformat(),
        "hours_left": round(left, 1),
        "state": state,
    }


def severity_problem(
    severity: str, found_floor: str | None, previous: str | None, reason: str
) -> tuple[str, str] | None:
    """(code, message) when a severity cannot be saved: unknown, below the floor, or lowered without a reason."""
    if severity not in SCALE:
        return "SEVERITY_NEEDED", "Choose the harm now: Not known yet or a level on the harm scale"
    if found_floor and rank(severity) < rank(found_floor):
        return "BELOW_FLOOR", f"At least {SCALE_LABELS[found_floor]}: the facts set that floor"
    if previous and rank(severity) < rank(previous) and len(reason) < rules.REASON_MIN:
        return "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why the severity is lowered"
    return None


def is_downgrade(before: dict, after: dict) -> bool:
    """A6: a saved fast-track triage made less severe (severity or potential harm lowered, or off the fast track)."""
    if before.get("speed") != FAST:
        return False
    return (
        rank(after.get("severity")) < rank(before.get("severity"))
        or rank(after.get("potential_severity")) < rank(before.get("potential_severity"))
        or after.get("speed") == ROUTINE
    )


def reopen_trigger(before: dict | None, after: dict, floor_before: str | None, floor_after: str | None) -> str | None:
    """Why a finished triage reopens (T-D7), or None. ``before``: the facts stored at completion."""
    if before is None:
        return None
    for key, trigger in (("death", "DEATH"), ("serious_injury", "SERIOUS_INJURY"), ("threat", "THREAT")):
        if after.get(key) and not before.get(key):
            return trigger
    if rank(floor_after) > rank(floor_before):
        return "FLOOR_RAISED"
    if after.get("harm") and not before.get("harm"):
        return "MORE_HARM"
    return None


def backup_problem(kind: str, active_people: int, backup: str | None) -> str | None:
    """T-D12: a fast-track triage names a backup when two or more people are active (a one-person trial is allowed)."""
    if kind == FAST and active_people >= 2 and not backup:
        return "Name a backup: two or more people are active"
    return None


def containment(raw: list[str] | None) -> list[str]:
    return [choice for choice in dict.fromkeys(raw or []) if choice in CONTAINMENT]
