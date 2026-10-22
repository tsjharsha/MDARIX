"""The rules of signals without a database: a complaint's problem key and event time, how complaints group, the
suggested priority and due date of a signal, its title, and which triage decisions are allowed.

Everything here is pure (no session, no clock unless one is passed), so the rules are tested on their own
(tests/test_signals_unit.py) and the detection, the API and the script share them.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from backend.app.signals.labels import (
    CASE_FROM,
    DISPOSITION_FROM,
    DISPOSITIONS,
    DUE_DAYS,
    ESCALATED_NEXT,
    HIGH_SEVERITIES,
    OPEN_SIGNAL_STATUSES,
    PRIORITY_RANK,
    SEVERITY_RANK,
    THRESHOLD_DEFAULTS,
)

UNSPECIFIED_PROBLEM = "UNSPECIFIED"
PROBLEM_KEY_LENGTH = 160
TITLE_LENGTH = 300


class SignalRuleError(Exception):
    """A request the signal rules refuse: the HTTP status, a stable code and a message for people."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


# ------------------------------------------------------------------------------------------------ complaints


def problem_key(problem_code: str | None, complaint_type: str | None) -> str:
    """What a complaint is about: its problem code, else its complaint type, else UNSPECIFIED (trimmed, upper case,
    inner whitespace collapsed)."""
    for value in (problem_code, complaint_type):
        text = " ".join(str(value or "").split()).upper()
        if text:
            return text[:PROBLEM_KEY_LENGTH]
    return UNSPECIFIED_PROBLEM


def event_time(event_timestamp, complaint_timestamp=None, created_at=None):
    """When a complaint happened: its event time, else when it was received, else when it was recorded."""
    return event_timestamp or complaint_timestamp or created_at


def severity_rank(value: str | None) -> int:
    """A recorded severity's rank (-1 when empty or not a known severity)."""
    return SEVERITY_RANK.get(" ".join(str(value or "").split()).upper(), -1)


def highest_severity(values: Iterable[str | None]) -> str | None:
    """The most severe of the recorded severities (upper case); a known severity outranks an unknown one. Between two of
    the same rank (two unknown ones, or SERIOUS and SEVERE) the first in alphabetical order is kept, so the answer never
    depends on the order the complaints are read in (it did before 0.10.43: the reads have no order). None when none
    is recorded."""
    best, best_rank = None, -2
    for value in values:
        text = " ".join(str(value or "").split()).upper()
        if not text:
            continue
        rank = severity_rank(text)
        if rank > best_rank or (rank == best_rank and text < best):
            best, best_rank = text, rank
    return best


@dataclass(frozen=True)
class ComplaintFacts:
    """The facts of one complaint that grouping and prioritising read."""

    id: uuid.UUID
    product_id: uuid.UUID | None
    product_version_id: uuid.UUID | None
    problem_key: str
    event_at: datetime | None
    severity: str | None = None
    serious_injury: bool = False
    death: bool = False

    @property
    def key(self) -> tuple:
        return (self.product_id, self.product_version_id, self.problem_key)


@dataclass(frozen=True)
class Facts:
    """What a set of complaints adds up to, as a signal records it."""

    count: int
    first_event_at: datetime | None
    last_event_at: datetime | None
    highest_severity: str | None
    death: bool
    serious_injury: bool

    @property
    def serious_harm(self) -> bool:
        return self.death or self.serious_injury


def summarize(complaints: Iterable[ComplaintFacts]) -> Facts:
    rows = list(complaints)
    times = [row.event_at for row in rows if row.event_at is not None]
    return Facts(
        count=len(rows),
        first_event_at=min(times) if times else None,
        last_event_at=max(times) if times else None,
        highest_severity=highest_severity(row.severity for row in rows),
        death=any(row.death for row in rows),
        serious_injury=any(row.serious_injury for row in rows),
    )


# ------------------------------------------------------------------------------------------------- priority


def suggested_priority(facts: Facts, min_complaints: int | None = None) -> str:
    """CRITICAL when a complaint reports a death; HIGH for a serious injury or a high severity (HIGH, CRITICAL,
    SERIOUS, MAJOR, SEVERE); MEDIUM when the count reaches twice the rule's threshold; else LOW."""
    threshold = int(min_complaints or THRESHOLD_DEFAULTS["min_complaints"])
    if facts.death:
        return "CRITICAL"
    if facts.serious_injury or (facts.highest_severity or "") in HIGH_SEVERITIES:
        return "HIGH"
    if facts.count >= 2 * threshold:
        return "MEDIUM"
    return "LOW"


def effective_priority(confirmed: str | None, suggested: str | None) -> str | None:
    """The priority people work to: the confirmed one when a person set it, else the suggested one."""
    return confirmed or suggested


def due_at(priority: str | None, start: datetime) -> datetime:
    """When triage is due: 1 day after ``start`` for CRITICAL, 3 for HIGH, 5 for MEDIUM, 10 for LOW."""
    return start + timedelta(days=DUE_DAYS.get(str(priority or "LOW").upper(), DUE_DAYS["LOW"]))


def priority_rank(priority: str | None) -> int:
    return PRIORITY_RANK.get(str(priority or "").upper(), 0)


# ------------------------------------------------------------------------------------------------- grouping


def humanize_problem(key: str | None) -> str:
    """A problem key as words in a title (OCCLUSION_ALARM -> "occlusion alarm")."""
    text = " ".join(str(key or "").replace("_", " ").split())
    if not text or text.upper() == UNSPECIFIED_PROBLEM:
        return "unspecified problem"
    return text.lower()


def rule_title(count: int, key: str | None, product_name: str | None, version: str | None, window_days: int) -> str:
    """The title of a rule signal, such as: 4 complaints: occlusion alarm on Aster Pump Rev C in 30 days. The count is
    grouped the en-US way ("2,290 complaints: ..."), as the import result says its counts (DEV-025)."""
    product = " ".join(part for part in (str(product_name or "").strip(), str(version or "").strip()) if part)
    noun = "complaint" if count == 1 else "complaints"
    title = f"{count:,} {noun}: {humanize_problem(key)} on {product or 'unknown product'} in {window_days} days"
    return title[:TITLE_LENGTH]


RULE_ORIGIN = "THRESHOLD_RULE"
# The leading count of a rule title written before 0.10.44, when counts were not grouped ("2290 complaints: ...").
_UNGROUPED_RULE_COUNT = re.compile(r"^([1-9][0-9]{3,})(?= complaints: )")
# A number written with thousands separators in a search ("2,290").
_GROUPED_NUMBER = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def display_title(title: str | None, origin: str | None) -> str | None:
    """A signal's title as the API shows it. A rule signal raised before 0.10.44 stored its count ungrouped ("2290
    complaints: ..."); that count is shown grouped ("2,290 complaints: ..."), as rule_title writes it now. Only a title
    MDARIX wrote is touched (a THRESHOLD_RULE signal's, which no one can edit), and only its leading count: any other
    title, a person's above all, is shown exactly as stored. The stored title is never rewritten (no migration)."""
    if origin != RULE_ORIGIN or not title:
        return title
    match = _UNGROUPED_RULE_COUNT.match(title)
    if match is None:
        return title
    return f"{int(match.group(1)):,}{title[match.end(1) :]}"


def display_task_title(title: str | None, signal_business_id: str | None, origin: str | None) -> str | None:
    """A signal's triage task title (``Triage <signal>: <its title>``, service.triage_task_title, stored when the task
    was queued) with the signal's title as display_title shows it."""
    prefix = f"Triage {signal_business_id}: "
    if origin != RULE_ORIGIN or not title or not signal_business_id or not title.startswith(prefix):
        return title
    return prefix + display_title(title[len(prefix) :], origin)


def ungrouped_search(text: str) -> str | None:
    """A search with grouped numbers ("2,290 complaints") as a rule title written before 0.10.44 has them ("2290
    complaints"), or None when the search has none."""
    plain = _GROUPED_NUMBER.sub("", text)
    return plain if plain != text else None


@dataclass
class GroupPlan:
    """What detection does for one group (product, version, problem): ``action`` is LINK (add the new complaints to
    the open signal ``signal_id``), CREATE (raise a new signal) or None (nothing yet)."""

    key: tuple
    complaints: list[ComplaintFacts] = field(default_factory=list)
    new: list[ComplaintFacts] = field(default_factory=list)
    action: str | None = None
    signal_id: uuid.UUID | None = None


def group(complaints: Iterable[ComplaintFacts]) -> dict[tuple, list[ComplaintFacts]]:
    """Complaints by (product, version, problem key); complaints without a product are left out."""
    groups: dict[tuple, list[ComplaintFacts]] = {}
    for row in complaints:
        if row.product_id is None:
            continue
        groups.setdefault(row.key, []).append(row)
    return groups


def plan_detection(
    complaints: Iterable[ComplaintFacts],
    linked_keys: dict[uuid.UUID, set[tuple]],
    open_signals: dict[tuple, uuid.UUID],
    min_complaints: int,
) -> list[GroupPlan]:
    """The threshold rule over the complaints of the window. A complaint is new to its group when it is not yet
    linked to a signal about the same (product, version, problem). New complaints of a group with an open signal
    are added to it; otherwise a group with at least ``min_complaints`` new complaints raises a signal. Running it
    again on the same data plans nothing, which is what makes detection idempotent."""
    plans = []
    for key, rows in sorted(group(complaints).items(), key=lambda item: tuple(str(part) for part in item[0])):
        new = [row for row in rows if key not in linked_keys.get(row.id, set())]
        plan = GroupPlan(key=key, complaints=rows, new=new)
        if new and key in open_signals:
            plan.action, plan.signal_id = "LINK", open_signals[key]
        elif len(new) >= min_complaints:
            plan.action = "CREATE"
        plans.append(plan)
    return plans


# ---------------------------------------------------------------------------------------------- dispositions


def check_disposition(
    disposition: str,
    status: str,
    *,
    signal_id=None,
    canonical: dict | None = None,
    canonical_signal_id=None,
    monitor_review_date: date | None = None,
    monitor_trigger: str | None = None,
    today: date,
) -> None:
    """Refuse a triage decision the rules do not allow (SignalRuleError):

    - from NEW, TRIAGE or MONITOR any disposition; from ESCALATED only INVESTIGATION_REQUIRED; nothing else;
    - DUPLICATE needs ``canonical_signal_id``: another signal of the organization (``canonical``: its ``id`` and
      ``status``, None when not found) that is not itself a duplicate or merged;
    - MONITOR needs a review date in the future and what would trigger a new look.
    """
    disposition = str(disposition or "").upper()
    if disposition not in DISPOSITIONS:
        raise SignalRuleError(422, "UNKNOWN_DISPOSITION", f"Choose one of: {', '.join(DISPOSITIONS)}")
    allowed = status in DISPOSITION_FROM or (status == "ESCALATED" and disposition in ESCALATED_NEXT)
    if not allowed:
        raise SignalRuleError(409, "SIGNAL_STATE_CONFLICT", f"A signal that is {status} cannot be {disposition} now")
    if disposition == "DUPLICATE":
        if canonical_signal_id is None:
            raise SignalRuleError(422, "CANONICAL_REQUIRED", "Name the signal this one duplicates")
        if signal_id is not None and str(canonical_signal_id) == str(signal_id):
            raise SignalRuleError(422, "CANONICAL_INVALID", "A signal cannot duplicate itself")
        if canonical is None:
            raise SignalRuleError(422, "CANONICAL_INVALID", "The signal it duplicates was not found")
        if canonical.get("status") in ("DUPLICATE", "MERGED"):
            raise SignalRuleError(
                422, "CANONICAL_INVALID", "Point at the original signal, not at another duplicate or merged one"
            )
    if disposition == "MONITOR":
        if monitor_review_date is None or not " ".join(str(monitor_trigger or "").split()):
            raise SignalRuleError(
                422, "MONITOR_DETAILS_REQUIRED", "Monitoring needs a review date and what would trigger a new look"
            )
        if monitor_review_date <= today:
            raise SignalRuleError(422, "REVIEW_DATE_NOT_FUTURE", "The review date must be in the future")


def needs_priority_reason(priority: str, suggested: str | None) -> bool:
    """A priority that differs from the suggested one needs a reason."""
    return str(priority or "").upper() != str(suggested or "").upper()


def can_open_case(status: str | None) -> bool:
    return status in CASE_FROM


def is_open(status: str | None) -> bool:
    return status in OPEN_SIGNAL_STATUSES
