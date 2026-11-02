"""Reminders, escalation and the working calendar (T-G25, MVP G25), as plain functions.

- **The working calendar** of the organization: its time zone, its working weekdays and its holidays. "Working day"
  everywhere in MDARIX's own due times (a first-contact follow-up, the QMS-complaint task, the communications log's S4
  hour) is a day of this calendar. An authority's legal clock keeps its own counting rule.
- **The item's state:** overdue once its due time has passed; due soon within the organization's reminder hours.
- **Who is told** (the item's chain): the owner gets the reminder, or the owner's backup while the owner is away (the
  owner stays the owner). At the due time the item escalates: to the backup (the owner's while away, or the item's own
  backup, as a triage record names) and to the people holding the organization's escalation role. A person already
  told is skipped. When nobody else can be reached, the owner is told so, so a deadline never passes silently. An
  item with no owner, or whose owner can no longer sign in, goes to the escalation role at once.

An alert never closes or changes the item: it only tells people. MDARIX never decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

OVERDUE, DUE_SOON, LATER = "OVERDUE", "DUE_SOON", "LATER"
STATE_LABELS = {OVERDUE: "Overdue", DUE_SOON: "Due soon", LATER: "Later"}
REMINDER, ESCALATION = "REMINDER", "ESCALATION"
TIER_LABELS = {REMINDER: "Reminder", ESCALATION: "Escalation"}
# Why a person gets an alert.
OWNER, COVERING, BACKUP, ESCALATION_ROLE, NO_OWNER, OWNER_INACTIVE, NO_ONE_ELSE = (
    "OWNER",
    "COVERING",
    "BACKUP",
    "ESCALATION_ROLE",
    "NO_OWNER",
    "OWNER_INACTIVE",
    "NO_ONE_ELSE",
)
REASON_LABELS = {
    OWNER: "You own it",
    COVERING: "You cover for the owner, who is away",
    BACKUP: "You are its backup",
    ESCALATION_ROLE: "It escalates to your role",
    NO_OWNER: "Nobody owns it yet",
    OWNER_INACTIVE: "Its owner can no longer sign in: reassign it",
    NO_ONE_ELSE: "Nobody else can be reached: invite a colleague or name a backup",
}
CATEGORIES = {
    "TRIAGE": "Triage and first contact",
    "REPORTING": "Reporting deadlines",
    "OBLIGATION": "Report obligations",
    "COMMUNICATION": "Communications",
    "GUIDE": "Guide approvals",
    "CAPA": "CAPA",
    "TASK": "Other tasks",
}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
DEFAULT_ZONE, DEFAULT_DAYS, DEFAULT_HOURS, DEFAULT_ROLE = "UTC", (0, 1, 2, 3, 4), 24, "LEADER"
HOURS_MIN, HOURS_MAX, HOLIDAYS_MAX, HOLIDAY_NAME_MAX = 1, 168, 60, 80
NOTE_MAX, ABSENCE_DAYS_MAX = 300, 120


def _bundled():
    from dateutil.zoneinfo import get_zonefile_instance

    return get_zonefile_instance()


@cache
def zone_info(name: str) -> tzinfo | None:
    """The time zone ``name`` (IANA), or None when it is unknown. The system's time zone database comes first; where
    a machine has none (Windows without the tzdata package), the copy python-dateutil carries is used."""
    if name == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return _bundled().get(name)


# The old names the time zone database keeps as aliases, and browsers still report (Chrome in India says
# "Asia/Calcutta"): each is shown and stored under its current name (J16). shortcut: the aliases people meet, not the
# database's whole "backward" file; add one here when a browser reports another.
LEGACY_ZONES = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Dacca": "Asia/Dhaka",
    "Asia/Thimbu": "Asia/Thimphu",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Asia/Macao": "Asia/Macau",
    "Asia/Ujung_Pandang": "Asia/Makassar",
    "Asia/Ashkhabad": "Asia/Ashgabat",
    "Asia/Chongqing": "Asia/Shanghai",
    "Asia/Chungking": "Asia/Shanghai",
    "Asia/Harbin": "Asia/Shanghai",
    "Asia/Tel_Aviv": "Asia/Jerusalem",
    "Asia/Istanbul": "Europe/Istanbul",
    "Europe/Kiev": "Europe/Kyiv",
    "Europe/Belfast": "Europe/London",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Louisville": "America/Kentucky/Louisville",
    "America/Godthab": "America/Nuuk",
    "America/Montreal": "America/Toronto",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "Pacific/Truk": "Pacific/Chuuk",
    "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Enderbury": "Pacific/Kanton",
    "Africa/Asmera": "Africa/Asmara",
    "Australia/ACT": "Australia/Sydney",
    "Australia/Canberra": "Australia/Sydney",
    "Australia/NSW": "Australia/Sydney",
    "Australia/North": "Australia/Darwin",
    "Australia/Queensland": "Australia/Brisbane",
    "Australia/South": "Australia/Adelaide",
    "Australia/Tasmania": "Australia/Hobart",
    "Australia/Victoria": "Australia/Melbourne",
    "Australia/West": "Australia/Perth",
    "Australia/LHI": "Australia/Lord_Howe",
    "Australia/Yancowinna": "Australia/Broken_Hill",
}
# Regions of current names ("Area/Location"); names outside them (US/Eastern, Etc/GMT+5, GMT0, Navajo) are aliases.
_AREAS = ("Africa", "America", "Antarctica", "Arctic", "Asia", "Atlantic", "Australia", "Europe", "Indian", "Pacific")


def canonical_zone(name: str | None) -> str:
    """A time zone's current name ("Asia/Calcutta" is "Asia/Kolkata"); the name as given otherwise."""
    text = str(name or "").strip()
    return LEGACY_ZONES.get(text, text)


@cache
def zone_names() -> tuple[str, ...]:
    """The time zones to choose from: current names only, UTC first (no alias beside its current name)."""
    every = available_timezones() or _bundled().zones
    current = {name for name in every if name.split("/", 1)[0] in _AREAS and "/" in name and name not in LEGACY_ZONES}
    return ("UTC", *sorted(current))


# The organization's time zone from its sign-up country, before the sample is seeded (J16). A country with several
# time zones gets the one most of its people live in; the organization changes it in Settings.
COUNTRY_ZONES = {
    "india": "Asia/Kolkata",
    "in": "Asia/Kolkata",
    "united states": "America/New_York",
    "united states of america": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "united kingdom": "Europe/London",
    "uk": "Europe/London",
    "great britain": "Europe/London",
    "england": "Europe/London",
    "scotland": "Europe/London",
    "wales": "Europe/London",
    "northern ireland": "Europe/London",
    "ireland": "Europe/Dublin",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
    "netherlands": "Europe/Amsterdam",
    "belgium": "Europe/Brussels",
    "italy": "Europe/Rome",
    "spain": "Europe/Madrid",
    "portugal": "Europe/Lisbon",
    "switzerland": "Europe/Zurich",
    "austria": "Europe/Vienna",
    "sweden": "Europe/Stockholm",
    "denmark": "Europe/Copenhagen",
    "norway": "Europe/Oslo",
    "finland": "Europe/Helsinki",
    "poland": "Europe/Warsaw",
    "czechia": "Europe/Prague",
    "czech republic": "Europe/Prague",
    "greece": "Europe/Athens",
    "israel": "Asia/Jerusalem",
    "united arab emirates": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh",
    "singapore": "Asia/Singapore",
    "malaysia": "Asia/Kuala_Lumpur",
    "japan": "Asia/Tokyo",
    "south korea": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "china": "Asia/Shanghai",
    "taiwan": "Asia/Taipei",
    "hong kong": "Asia/Hong_Kong",
    "sri lanka": "Asia/Colombo",
    "bangladesh": "Asia/Dhaka",
    "nepal": "Asia/Kathmandu",
    "pakistan": "Asia/Karachi",
    "canada": "America/Toronto",
    "australia": "Australia/Sydney",
    "new zealand": "Pacific/Auckland",
    "south africa": "Africa/Johannesburg",
    "brazil": "America/Sao_Paulo",
    "mexico": "America/Mexico_City",
}


def zone_for_country(country: str | None) -> str:
    """The time zone a new organization starts with from its country (``COUNTRY_ZONES``), else UTC."""
    key = " ".join(str(country or "").lower().replace(".", "").split())
    return COUNTRY_ZONES.get(key, DEFAULT_ZONE)


@dataclass(frozen=True)
class Calendar:
    zone: str = DEFAULT_ZONE
    work_days: tuple[int, ...] = DEFAULT_DAYS
    holidays: frozenset[date] = field(default_factory=frozenset)

    @property
    def tz(self) -> tzinfo:
        return zone_info(self.zone) or timezone.utc

    def working(self, day: date) -> bool:
        return day.weekday() in self.work_days and day not in self.holidays

    def next_working(self, day: date) -> date:
        """``day`` itself when it is a working day, else the next one."""
        for _ in range(400):
            if self.working(day):
                return day
            day += timedelta(days=1)
        return day  # no working day in a year: the settings forbid it, so this is never reached

    def add_working_days(self, day: date, days: int) -> date:
        day = self.next_working(day)
        for _ in range(days):
            day = self.next_working(day + timedelta(days=1))
        return day

    def local_day(self, moment: datetime) -> date:
        return moment.astimezone(self.tz).date()

    def day_end(self, day: date) -> datetime:
        """The last second of ``day`` in the organization's time zone, in UTC."""
        return datetime.combine(day, time(23, 59, 59), tzinfo=self.tz).astimezone(timezone.utc)

    def working_day_end(self, moment: datetime, days: int = 0) -> datetime:
        """The end of the working day ``days`` working days after ``moment``: day 0 is the same day, or the next working
        day when ``moment`` falls on a day off."""
        return self.day_end(self.add_working_days(self.local_day(moment), days))

    def working_hour_after(self, moment: datetime) -> datetime:
        """One working hour after ``moment``: time on a day off does not count (working days count all day, in the
        organization's time zone)."""
        local = moment.astimezone(self.tz)
        if not self.working(local.date()):
            start = self.next_working(local.date())
            local = datetime.combine(start, time.min, tzinfo=self.tz)
        end = local + timedelta(hours=1)
        if not self.working(end.date()):
            spill = end - datetime.combine(end.date(), time.min, tzinfo=self.tz)
            end = datetime.combine(self.next_working(end.date()), time.min, tzinfo=self.tz) + spill
        return end.astimezone(timezone.utc)


def calendar_problem(zone: str, work_days: list[int], holidays: list[dict]) -> str | None:
    """Why the calendar cannot be saved, or None."""
    if zone_info(zone) is None or zone not in zone_names():
        return "Choose the time zone from the list"
    if not work_days or any(day not in range(7) for day in work_days) or len(set(work_days)) != len(work_days):
        return "Choose at least one working weekday"
    if len(holidays) > HOLIDAYS_MAX:
        return f"Keep the holidays list to {HOLIDAYS_MAX} days"
    seen = set()
    for item in holidays:
        if not isinstance(item.get("date"), date):
            return "Give each holiday its date"
        if item["date"] in seen:
            return f"{item['date'].isoformat()} is listed twice"
        seen.add(item["date"])
        if len(item.get("name") or "") > HOLIDAY_NAME_MAX:
            return f"Keep each holiday's name to {HOLIDAY_NAME_MAX} characters"
    return None


def state_of(due_at: datetime, now: datetime, reminder_hours: int) -> str:
    if due_at <= now:
        return OVERDUE
    return DUE_SOON if due_at - now <= timedelta(hours=reminder_hours) else LATER


def hours_left(due_at: datetime, now: datetime) -> float:
    return round((due_at - now).total_seconds() / 3600, 1)


def absence_problem(user_id: str, backup_id: str, starts_on: date, ends_on: date, today: date) -> str | None:
    if not backup_id:
        return "Name the colleague who covers for you"
    if backup_id == user_id:
        return "Your backup must be someone else"
    if ends_on < starts_on:
        return "The absence ends before it starts"
    if ends_on < today:
        return "The absence is over already"
    if (ends_on - starts_on).days > ABSENCE_DAYS_MAX:
        return f"Record an absence of at most {ABSENCE_DAYS_MAX} days at a time"
    return None


def away_backup(absences: list[dict], user_id: str | None, today: date) -> str | None:
    """The backup of ``user_id`` on ``today`` when an absence covers it, else None."""
    for item in absences:
        if item["user_id"] == user_id and item["starts_on"] <= today <= item["ends_on"]:
            return item["backup_id"]
    return None


def recipients(
    item: dict, state: str, active: set[str], absences: list[dict], escalation_people: list[str], today: date
) -> list[tuple[str, str, str]]:
    """``[(tier, person, reason)]`` for an item that is due soon or overdue. ``active``: the people who can sign in;
    ``escalation_people``: those holding the escalation role (active ones). Each person is told once per tier."""
    if state == LATER:
        return []
    owner = item.get("owner_id")
    covering = away_backup(absences, owner, today) if owner else None
    if covering is not None and covering not in active:
        covering = None
    found: list[tuple[str, str, str]] = []

    def add(tier: str, person: str | None, reason: str) -> None:
        if person and person in active and not any(t == tier and p == person for t, p, _ in found):
            found.append((tier, person, reason))

    if covering:
        add(REMINDER, covering, COVERING)
    elif owner and owner in active:
        add(REMINDER, owner, OWNER)
    else:
        for person in escalation_people:
            add(REMINDER, person, OWNER_INACTIVE if owner else NO_OWNER)
    if state != OVERDUE:
        return found
    before = len(found)
    chain = [(covering, COVERING), (item.get("backup_id"), BACKUP), *((p, ESCALATION_ROLE) for p in escalation_people)]
    for person, reason in chain:
        if person != owner:
            add(ESCALATION, person, reason)
    if len(found) == before and owner in active:
        add(ESCALATION, owner, NO_ONE_ELSE)
    return found
