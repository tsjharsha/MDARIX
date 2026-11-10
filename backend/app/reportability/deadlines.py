"""A legal deadline, counted one way for every screen (0.10.63, quality plan stage 2; MVP 5.1a).

Every market clock MDARIX shows (the reportability watch, a market assessment, triage's provisional deadlines, a report
obligation, its reminders and the oversight view, worksheets and exports) is counted here:

- **The authority's time zone** (``AUTHORITY_ZONES``): US FDA America/New_York, EU and Northern Ireland
  Europe/Brussels, Great Britain Europe/London, India Asia/Kolkata.
- **The day counting starts**: awareness is converted into a time zone before its day is taken. The US and the EU count
  from the day after awareness (awareness is day 0); **Great Britain and India count the awareness day as day 1**
  (``DAY_ONE_MARKETS``, the MVP's conservative rule).
- **The latest day** is the earlier of the day counted in the authority's time zone and in the organization's (its
  working calendar, Settings); **it ends** at the earlier of the end of that day in the two time zones. A market without
  an authority time zone here (Canada, or a country outside the four markets) counts in the organization's time zone,
  from the day after awareness.
- **Every label is written in the organization's time zone** (0.10.84), whichever zone's end of day binds: a person
  reads every deadline on every screen in one zone ("Thu 12 Nov 2026, 18:59 EST", never GMT on one screen and EST on
  the next). The moment itself is unchanged.
- Work days are Monday to Friday; public holidays are not known and count as work days, which only makes a date
  earlier. No weekend or holiday extension is applied (EU Regulation 1182/71 is left out: conservative).

Starter rules, for the regulatory consultant to confirm per market (``STARTER``): the conservative reading applies until
then. MDARIX keeps the clock; a person decides, signs and submits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from backend.app import feature_set
from backend.app.oversight.rules import zone_info
from backend.app.rule_register import register

STARTER = "Starter counting rule: conservative until your regulatory consultant confirms it."
WORK = "WORK"
OVERDUE, DUE_SOON, RUNNING = "OVERDUE", "DUE_SOON", "RUNNING"
# The markets of backend/app/reportability/markets.py (named here as text: markets.py imports this module's users).
AUTHORITY_ZONES = {
    "US": "America/New_York",
    "EU_NI": "Europe/Brussels",
    "GB": "Europe/London",
    "IN": "Asia/Kolkata",
}
DAY_ONE_MARKETS = frozenset({"GB", "IN"})
# How each market counts, in words (worksheets, the consultant's table, the screen's note).
COUNTING_WORDS = {
    "US": "from the day after awareness; US Eastern time or yours, whichever ends first",
    "EU_NI": "from the day after awareness; Brussels time or yours, whichever ends first; no weekend extension",
    "GB": "the awareness day is day 1; UK time or yours, whichever ends first",
    "IN": "the awareness day is day 1; India time (IST) or yours, whichever ends first",
    "CA": "from the day after awareness (awareness is day zero); your time zone",
}
END_OF_DAY = time(23, 59, 59)
# A day given without a time (an imported date, a date entered as a reporting fact) is kept at 12:00 UTC.
DAY_ONLY = time(12)


def day_only(moment) -> bool:
    """Whether a stored moment is a day given without a time (``DAY_ONLY``, 0.10.81, U-06): shown as a date, and
    counted as that day everywhere. shortcut: a time typed as exactly 12:00:00 UTC reads as a day too, which counts
    from the same day in every authority's time zone anyway; a day-only column comes with a migration if needed."""
    if not isinstance(moment, datetime):
        return False
    utc = _utc(moment).astimezone(timezone.utc)
    return utc.time() == DAY_ONLY


def add_work_days(start: date, days: int) -> date:
    """``days`` work days (Monday to Friday) after ``start``."""
    current = start
    left = days
    while left > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            left -= 1
    return current


def soon_days(window_days: int) -> int:
    """Days left at which a clock is "due soon": 5, or half a short window (at least 1)."""
    return max(1, min(5, window_days // 2))


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def counting(market: str | None, aware=None, org_zone: str | None = None) -> tuple[str | None, bool]:
    """(the authority's time zone, whether the awareness day is day 1) of the market's floor in force at awareness (B4;
    today's without one); today's constants when the rule register is off or for a market without a floor."""
    if market and feature_set.rule_register():
        floor = register.floor_at(market, aware, org_zone)
        if floor:
            found = floor["content"]["counting"]
            return found["authority_zone"], found["awareness_is_day_one"]
    return AUTHORITY_ZONES.get(market or ""), market in DAY_ONE_MARKETS


def _zones(market: str | None, org_zone: str | None, aware=None) -> list[str]:
    """The time zones a market's deadline is counted in: the authority's first, then the organization's."""
    found = [zone for zone in (counting(market, aware, org_zone)[0], org_zone or "UTC") if zone]
    return list(dict.fromkeys(found))


def zone_abbreviation(moment: datetime, zone: str) -> str:
    """ "IST", "EST", "CEST", "GMT"; "UTC+04" where the zone has no letters."""
    text = _utc(moment).astimezone(zone_info(zone) or timezone.utc).tzname() or "UTC"
    return f"UTC{text}" if text[:1] in "+-" else text


@dataclass(frozen=True)
class Deadline:
    day: date  # the latest day
    at: datetime  # its end, in UTC
    zone: str  # the time zone whose end of day binds
    market: str | None = None
    org: str | None = None  # the organization's time zone, which every label is written in

    @property
    def label(self) -> str:
        """ "Mon 30 Nov 2026, 23:59 IST": the moment in the organization's time zone (0.10.84), so a person reads every
        deadline on every screen in one zone; in the binding zone where no organization's is known."""
        return moment_label(self.at, self.org or self.zone)


def moment_label(at: datetime, zone: str) -> str:
    """A due time in a time zone, with the zone: "Mon 30 Nov 2026, 23:59 IST"."""
    local = _utc(at).astimezone(zone_info(zone) or timezone.utc)
    return f"{local:%a} {local.day} {local:%b %Y}, {local:%H:%M} {zone_abbreviation(at, zone)}"


def due_label(at: datetime, market: str | None, org_zone: str | None, legal: bool = False) -> str:
    """A due time's label on the oversight view and in alerts, in the organization's time zone like every deadline
    (0.10.84: the complaint page said EST and its triage table GMT for one clock). ``market`` and ``legal`` are kept for
    the callers; the zone no longer depends on them."""
    return moment_label(at, org_zone or "UTC")


def end_of(day: date, market: str | None, org_zone: str | None, aware=None) -> Deadline:
    """The end of a legal latest day: the earlier of its end in the authority's time zone and in the organization's
    (a tie keeps the authority's). ``aware``: the awareness that picks the market's floor (today's when None)."""
    ends = [
        (datetime.combine(day, END_OF_DAY, tzinfo=zone_info(zone) or timezone.utc).astimezone(timezone.utc), zone)
        for zone in _zones(market, org_zone, aware)
    ]
    at, zone = min(ends, key=lambda item: item[0])
    return Deadline(day, at, zone, market, org_zone)


def start_day(aware: datetime | date, market: str | None, org_zone: str | None) -> date:
    """The local day of awareness a market's deadline counts from: the earliest of its day in the authority's and the
    organization's time zones. A day without a time (an older stored day, or a day-only awareness: ``day_only``) is
    taken as that day everywhere: the conservative start of that day under the counting rule (0.10.81, U-06)."""
    if isinstance(aware, datetime) and day_only(aware):
        return _utc(aware).astimezone(timezone.utc).date()
    if isinstance(aware, datetime):
        return min(
            _utc(aware).astimezone(zone_info(zone) or timezone.utc).date() for zone in _zones(market, org_zone, aware)
        )
    return aware


def count(aware: datetime | date, days: int, day_basis: str, market: str | None, org_zone: str | None) -> Deadline:
    """The deadline ``days`` (calendar or work) days from awareness, by the market's counting rule (module docstring),
    from the local day of awareness (``start_day``)."""
    start = start_day(aware, market, org_zone)
    if day_basis == WORK:
        day = add_work_days(start, days)
    else:
        day = start + timedelta(days=days - 1 if counting(market, aware, org_zone)[1] else days)
    return end_of(day, market, org_zone, aware)


def days_left(deadline: Deadline, now: datetime | date) -> int:
    """Calendar days from today to the latest day, today taken in the time zone whose end binds (a day: that day)."""
    today = _utc(now).astimezone(zone_info(deadline.zone) or timezone.utc).date() if isinstance(now, datetime) else now
    return (deadline.day - today).days


def state(deadline: Deadline, now: datetime | date, window_days: int) -> str:
    """Overdue once its end has passed (a day: once that day is after the latest day); due soon within
    ``soon_days``."""
    overdue = _utc(now) > deadline.at if isinstance(now, datetime) else now > deadline.day
    if overdue:
        return OVERDUE
    return DUE_SOON if days_left(deadline, now) <= soon_days(window_days) else RUNNING


def view(deadline: Deadline, now: datetime | date, window_days: int) -> dict:
    """The fields every deadline carries on the wire."""
    return {
        "due_date": deadline.day.isoformat(),
        "due_at": deadline.at.isoformat(),
        "due_zone": deadline.zone,
        "due_label": deadline.label,
        "days_left": days_left(deadline, now),
        "state": state(deadline, now, window_days),
    }


def end_fields(day: date | None, market: str | None, org_zone: str | None) -> dict:
    """``due_at``, ``due_zone`` and ``due_label`` of a stored latest day (none without a day)."""
    if day is None:
        return {"due_at": None, "due_zone": None, "due_label": None}
    found = end_of(day, market, org_zone)
    return {"due_at": found.at.isoformat(), "due_zone": found.zone, "due_label": found.label}


def org_zone(db, tenant_id) -> str:
    """The organization's time zone: its working calendar's (Settings)."""
    from backend.app.oversight.service import calendar_of

    return calendar_of(db, tenant_id).zone


def as_moment(now: datetime | date | None) -> datetime | date:
    """``now`` as given, the current time when None."""
    return datetime.now(timezone.utc) if now is None else now


def day_of(now: datetime | date) -> date:
    """The UTC day of ``now`` (a day as it is), for filters that only need a day."""
    return _utc(now).date() if isinstance(now, datetime) else now
