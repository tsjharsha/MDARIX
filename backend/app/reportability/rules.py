"""The rules of the reportability watch, as plain functions.

Why it matters (FDA warning letters, 2026): a manufacturer filed a Medical Device Report about nine months late
against a 30-day deadline, another never followed up choking complaints and filed none. The watch shows, for every
complaint that reports a death, a serious injury or a malfunction, how many days are left in the reporting windows
the organization entered from its own procedure, and flags complaints whose answers are missing (a patient was
involved, but nobody recorded whether they were injured). A person decides reportability; MDARIX keeps the clock, never
decides, and never submits a report.

The windows are the organization's, not MDARIX's: nothing is set until someone enters them. ``TEMPLATES`` offers the
FDA and EU windows that complaint fields can start (to check against the procedure before saving); windows that rest on
a judgment (an FDA 5-work-day report, an EU serious public health threat) cannot be read from complaint fields and are
left to the reviewer.

A clock starts at the moment the organization became aware of the complaint (the earliest of its awareness, received
and recorded times, as the case's regulatory review reads it) and ends by the market's counting rule
(backend/app/reportability/deadlines.py, one computation for every screen): calendar days or work days (Monday to
Friday; public holidays are not known to MDARIX and are counted as work days, which only makes a due date earlier),
counted in the authority's and the organization's time zones, ending at whichever end of day comes first.

Each template names its regulatory basis (``basis``: ids of the one catalog, backend/app/standards.py); a window made
from a template keeps it, and the watch shows it beside the window's name. A window entered by hand has none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from datetime import date, datetime

from backend.app.reportability import deadlines
from backend.app.reportability.deadlines import add_work_days, soon_days  # noqa: F401 (callers read them here)
from backend.app.standards import known

DEATH, SERIOUS_INJURY, MALFUNCTION = "DEATH", "SERIOUS_INJURY", "MALFUNCTION"
TRIGGERS = (DEATH, SERIOUS_INJURY, MALFUNCTION)
TRIGGER_LABELS = {DEATH: "a death", SERIOUS_INJURY: "a serious injury", MALFUNCTION: "a malfunction"}
CALENDAR, WORK = "CALENDAR", "WORK"
DAY_BASES = (CALENDAR, WORK)

WINDOWS_MAX = 20
NAME_MIN, NAME_MAX = 3, 100
MARKETS_MAX = 100
MARKET_MAX_LENGTH = 60
NOTE_MAX = 300
DAYS_MIN, DAYS_MAX = 1, 365
LOOKBACK_DEFAULT, LOOKBACK_MIN, LOOKBACK_MAX = 365, 30, 3650
REASON_MIN = 10
REFERENCE_MAX = 120

# The person's decision on a complaint's reportability.
REPORTED, NOT_REPORTABLE = "REPORTED", "NOT_REPORTABLE"
DECISIONS = (REPORTED, NOT_REPORTABLE)

# A clock's state, most urgent first.
OVERDUE, DUE_SOON, RUNNING = "OVERDUE", "DUE_SOON", "RUNNING"
# A watched complaint's state: one of the clock states, or
IN_REVIEW = "IN_REVIEW"  # its case's regulatory review is requested or in progress (the clock still runs)
NO_WINDOW = "NO_WINDOW"  # it reports harm, but no window of the organization applies to it
FOLLOW_UP = "FOLLOW_UP"  # answers are missing and nothing starts a clock yet
DECIDED = "DECIDED"
STATE_ORDER = {OVERDUE: 0, DUE_SOON: 1, IN_REVIEW: 2, RUNNING: 3, NO_WINDOW: 4, FOLLOW_UP: 5, DECIDED: 6}

# Regulatory review outcomes of a case (backend/app/db/models/reviews.py) that settle a complaint's reportability;
# "reporting required" does not: the clock runs until the report is recorded as filed.
SETTLING_OUTCOMES = frozenset({"NO_REPORTABILITY_CONCERN_IDENTIFIED", "REPORTABILITY_ASSESSMENT_COMPLETE"})

_US = ["US", "USA", "United States", "United States of America"]
# EU member states and the EEA countries where the EU MDR applies, by name and by code.
_EU = [
    "EU",
    "European Union",
    "Austria",
    "AT",
    "Belgium",
    "BE",
    "Bulgaria",
    "BG",
    "Croatia",
    "HR",
    "Cyprus",
    "CY",
    "Czechia",
    "Czech Republic",
    "CZ",
    "Denmark",
    "DK",
    "Estonia",
    "EE",
    "Finland",
    "FI",
    "France",
    "FR",
    "Germany",
    "DE",
    "Greece",
    "GR",
    "EL",
    "Hungary",
    "HU",
    "Ireland",
    "IE",
    "Italy",
    "IT",
    "Latvia",
    "LV",
    "Lithuania",
    "LT",
    "Luxembourg",
    "LU",
    "Malta",
    "MT",
    "Netherlands",
    "NL",
    "Poland",
    "PL",
    "Portugal",
    "PT",
    "Romania",
    "RO",
    "Slovakia",
    "SK",
    "Slovenia",
    "SI",
    "Spain",
    "ES",
    "Sweden",
    "SE",
    "Iceland",
    "IS",
    "Liechtenstein",
    "LI",
    "Norway",
    "NO",
]

_GB = ["Great Britain", "GB", "England", "Scotland", "Wales"]
# The United Kingdom is two markets: Great Britain (UK MDR 2002) and Northern Ireland (EU MDR). Named whole, it is asked,
# never read as one of them (owner decision OD-2, 0.10.88; markets.markets_of, facts.needed).
UK_WHOLE = ("United Kingdom", "UK", "United Kingdom of Great Britain and Northern Ireland")
UK_PARTS = ["Great Britain", "Northern Ireland"]


def names_the_uk_whole(value: object) -> bool:
    """Whether a country cell, or any country it names, is the United Kingdom as a whole."""
    whole = {normalize(name) for name in UK_WHOLE}
    return normalize(value) in whole or any(normalize(part) in whole for part in countries(value))


_CA = ["Canada", "CA", "CAN"]
_IN = ["India", "IN", "IND"]

# Starting points to check against the organization's procedure; never applied until a person saves them. Sources:
# 21 CFR 803.50 and 803.53 (FDA); EU MDR Article 87; GB Medical Devices Regulations 2002 as amended, regulation 44ZH
# (from 16 June 2025); Canada Medical Devices Regulations SOR/98-282 section 60 (calendar days); India Medical Devices
# Rules 2017 Rule 26 (its period is starter text until the regulatory consultant confirms it).
TEMPLATES = (
    {
        "name": "FDA MDR: death, serious injury or malfunction (30 calendar days)",
        "markets": _US,
        "triggers": [DEATH, SERIOUS_INJURY, MALFUNCTION],
        "days": 30,
        "day_basis": CALENDAR,
        "note": "A 5-work-day report (remedial action to prevent an unreasonable risk of substantial harm, or an FDA "
        "request) rests on a judgment; your reviewer applies it.",
        # 803.50 sets the 30 days; 803.53 is the 5-work-day report the note names.
        "basis": ["CFR803_50", "CFR803_53"],
    },
    {
        "name": "EU MDR: serious incident (15 days)",
        "markets": _EU,
        "triggers": [DEATH, SERIOUS_INJURY],
        "days": 15,
        "day_basis": CALENDAR,
        "note": "A malfunction can also be a serious incident when it might have led to death or serious "
        "deterioration; a serious public health threat is 2 days. Your reviewer applies both.",
        "basis": ["MDR_87"],
    },
    {
        "name": "EU MDR: death (10 days)",
        "markets": _EU,
        "triggers": [DEATH],
        "days": 10,
        "day_basis": CALENDAR,
        "note": "An unanticipated serious deterioration in health is also 10 days; your reviewer applies it.",
        "basis": ["MDR_87"],
    },
    {
        "name": "MHRA (Great Britain): serious incident (15 days)",
        "markets": _GB,
        "triggers": [DEATH, SERIOUS_INJURY],
        "days": 15,
        "day_basis": CALENDAR,
        "note": "A serious public health threat is 2 days, and a malfunction can be a serious incident; your reviewer "
        "applies both. Northern Ireland follows the EU MDR but reports to the MHRA.",
        "basis": ["UK_MDR"],
    },
    {
        "name": "MHRA (Great Britain): death (10 days)",
        "markets": _GB,
        "triggers": [DEATH],
        "days": 10,
        "day_basis": CALENDAR,
        "note": "An unanticipated serious deterioration in health is also 10 days; your reviewer applies it.",
        "basis": ["UK_MDR"],
    },
    {
        "name": "Health Canada: death or serious deterioration (10 days)",
        "markets": _CA,
        "triggers": [DEATH, SERIOUS_INJURY],
        "days": 10,
        "day_basis": CALENDAR,
        "note": "For an incident in Canada; a foreign incident is reported as soon as possible after the decision.",
        "basis": ["CA_MDR"],
    },
    {
        "name": "Health Canada: could cause death or serious deterioration if it recurred (30 days)",
        "markets": _CA,
        "triggers": [MALFUNCTION],
        "days": 30,
        "day_basis": CALENDAR,
        "note": "Whether a recurrence could cause death or serious deterioration rests on a judgment; your reviewer "
        "applies it.",
        "basis": ["CA_MDR"],
    },
    {
        "name": "India MDR 2017: serious adverse event (15 days)",
        "markets": _IN,
        "triggers": [DEATH, SERIOUS_INJURY],
        "days": 15,
        "day_basis": CALENDAR,
        "note": "Starter, for your consultant to confirm: confirm the period against Rule 26 and the Materiovigilance Programme of India guidance "
        "before saving.",
        "basis": ["IN_MDR"],
    },
)
TEMPLATE_BASIS = {template["name"]: template["basis"] for template in TEMPLATES}


def normalize(value: object) -> str:
    """Lower case, dots removed, separators as spaces, single spaces: "U.S.A." and "usa" are the same market."""
    return _normalized(str(value or ""))


@lru_cache(maxsize=4096)
def _normalized(text: str) -> str:
    # Cached (0.10.88, DEV-13): the watch normalized the same few market and country names millions of times for a
    # trial of 5,000 complaints (100 s of a 173 s read).
    text = text.lower().replace(".", "")
    text = re.sub(r"[_\-/,;:]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_COUNTRY_SEPARATORS = re.compile(r"\s*(?:[,;/&|]|\band\b)\s*", re.I)


def countries(value: object) -> list[str]:
    """The countries a country cell names: "India, Germany" -> ["India", "Germany"]; one country stays one ("United
    States", "Bosnia and Herzegovina" is read whole when it is a known name: ``applies`` and markets_of try the whole
    cell first)."""
    text = str(value or "").strip()
    if not text:
        return []
    return [part for part in _COUNTRY_SEPARATORS.split(text) if part.strip()]


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_window(raw: dict) -> dict:
    """One window as stored: name and note tidied, markets tidied without repeats, triggers in their order, and its
    basis as catalog ids. A window saved before windows carried a basis (``basis`` absent) takes its template's when it
    still has the template's name."""
    markets: list[str] = []
    seen: set[str] = set()
    for market in raw.get("markets") or []:
        text = _clean_text(market)
        if text and normalize(text) not in seen:
            seen.add(normalize(text))
            markets.append(text)
    triggers = [code for code in TRIGGERS if code in {str(item).strip().upper() for item in raw.get("triggers") or []}]
    note = _clean_text(raw.get("note")) or None
    name = _clean_text(raw.get("name"))
    basis = raw.get("basis")
    return {
        "name": name,
        "markets": markets,
        "triggers": triggers,
        "days": raw.get("days"),
        "day_basis": str(raw.get("day_basis") or CALENDAR).strip().upper(),
        "note": note,
        "basis": known(TEMPLATE_BASIS.get(name, []) if basis is None else basis),
    }


def windows_problem(windows: list[dict]) -> str | None:
    """Why a list of cleaned windows cannot be saved, or None."""
    if len(windows) > WINDOWS_MAX:
        return f"Keep at most {WINDOWS_MAX} windows"
    names: set[str] = set()
    for index, window in enumerate(windows, 1):
        label = f"Window {index}"
        name = window["name"]
        if not NAME_MIN <= len(name) <= NAME_MAX:
            return f"{label}: give it a name of {NAME_MIN} to {NAME_MAX} characters"
        if name.lower() in names:
            return f'{label}: another window is already called "{name}"'
        names.add(name.lower())
        if len(window["markets"]) > MARKETS_MAX:
            return f"{label}: keep at most {MARKETS_MAX} markets"
        long = next((market for market in window["markets"] if len(market) > MARKET_MAX_LENGTH), None)
        if long:
            return f'{label}: "{long[:20]}…" is longer than {MARKET_MAX_LENGTH} characters'
        if not window["triggers"]:
            return f"{label}: choose what starts its clock (a death, a serious injury or a malfunction)"
        days = window["days"]
        if isinstance(days, bool) or not isinstance(days, int) or not DAYS_MIN <= days <= DAYS_MAX:
            return f"{label}: the window is a whole number of days from {DAYS_MIN} to {DAYS_MAX}"
        if window["day_basis"] not in DAY_BASES:
            return f"{label}: count calendar days or work days"
        if window["note"] and len(window["note"]) > NOTE_MAX:
            return f"{label}: keep the note under {NOTE_MAX} characters"
    return None


def triggers_of(record: dict) -> list[str]:
    """What a complaint reports that can start a clock, in the order of TRIGGERS."""
    return [code for code in TRIGGERS if record.get(code.lower())]


def applies(window: dict, record: dict) -> bool:
    """Whether ``window`` covers the complaint: one of its triggers is reported, and the complaint's country is one of
    the window's markets (a window without markets covers every market, a complaint without a country included)."""
    if not set(window["triggers"]) & set(triggers_of(record)):
        return False
    if not window["markets"]:
        return True
    names = {normalize(market) for market in window["markets"]}
    country = normalize(record.get("country"))
    # A cell naming several countries ("India, Germany") is covered when one of them is (J41).
    return bool(country) and (
        country in names or any(normalize(part) in names for part in countries(record.get("country")))
    )


def due_date(aware: date, window: dict, market: str | None = None) -> date:
    """The latest day of ``window`` from an awareness day, by the market's counting rule (deadlines.py)."""
    return deadlines.count(aware, window["days"], window["day_basis"], market, None).day


def clock_state(due: date, today: date, window_days: int) -> str:
    """A clock's state from its latest day and a day (deadlines.state reads the time of day too)."""
    return deadlines.state(deadlines.end_of(due, None, None), today, window_days)


@dataclass(frozen=True)
class Clock:
    name: str
    days: int
    day_basis: str
    due: date
    state: str
    days_left: int
    triggers: tuple[str, ...]
    basis: tuple[str, ...] = ()
    due_at: str | None = None
    due_zone: str | None = None
    due_label: str | None = None
    market: str | None = None

    def as_dict(self) -> dict:
        return {
            "window": self.name,
            "days": self.days,
            "day_basis": self.day_basis,
            "due_date": self.due.isoformat(),
            "due_at": self.due_at,
            "due_zone": self.due_zone,
            "due_label": self.due_label,
            "market": self.market,
            "state": self.state,
            "days_left": self.days_left,
            "triggers": list(self.triggers),
            "basis": list(self.basis),
        }


def clocks(
    record: dict, windows: list[dict], aware: datetime | date | None, now: datetime | date, org_zone: str | None = None
) -> list[Clock]:
    """The clocks the complaint's windows start, the earliest end first; none without awareness. Each counts by the
    complaint's market (its country) and the organization's time zone (deadlines.py)."""
    from backend.app.reportability.markets import market_of

    if aware is None:
        return []
    found = []
    reported = set(triggers_of(record))
    market = market_of(record.get("country"))
    for window in windows:
        if not applies(window, record):
            continue
        due = deadlines.count(aware, window["days"], window["day_basis"], market, org_zone)
        seen = deadlines.view(due, now, window["days"])
        found.append(
            Clock(
                name=window["name"],
                days=window["days"],
                day_basis=window["day_basis"],
                due=due.day,
                state=seen["state"],
                days_left=seen["days_left"],
                triggers=tuple(code for code in window["triggers"] if code in reported),
                basis=tuple(window.get("basis") or ()),
                due_at=seen["due_at"],
                due_zone=seen["due_zone"],
                due_label=seen["due_label"],
                market=market,
            )
        )
    return sorted(found, key=lambda clock: (clock.due_at or "", clock.name))


def follow_ups(record: dict, windows: list[dict], aware_recorded: bool) -> list[dict]:
    """The answers a complaint is missing for its reportability to be judged."""
    found = []
    if record.get("patient_involved") and (record.get("serious_injury") is None or record.get("death") is None):
        found.append(
            {
                "code": "PATIENT_OUTCOME",
                "label": "A patient was involved, but whether anyone was seriously injured or died is not recorded",
            }
        )
    harm = bool(triggers_of(record))
    if harm and not normalize(record.get("country")) and any(window["markets"] for window in windows):
        found.append(
            {"code": "NO_COUNTRY", "label": "No country recorded, so no market's reporting window can be applied"}
        )
    if harm and not aware_recorded:
        found.append(
            {"code": "NO_AWARENESS_DATE", "label": "No awareness date recorded: the clock starts on the received date"}
        )
    return found


def watched(record: dict) -> bool:
    """Whether a complaint belongs on the watch: it reports harm or a malfunction, or a patient's outcome is unknown."""
    if triggers_of(record):
        return True
    return bool(record.get("patient_involved")) and (
        record.get("serious_injury") is None or record.get("death") is None
    )


def watch_state(binding_state: str | None, decided: bool, in_review: bool, harm: bool) -> str:
    """A watched complaint's state from its binding (earliest) clock's state, if any."""
    if decided:
        return DECIDED
    if binding_state:
        if binding_state in (OVERDUE, DUE_SOON):
            return binding_state
        return IN_REVIEW if in_review else RUNNING
    if in_review:
        return IN_REVIEW
    return NO_WINDOW if harm else FOLLOW_UP


def on_time(decided_on: date | None, due: date | None) -> bool | None:
    """Whether a decision (or the filed report) came inside the binding window; None without a window."""
    if decided_on is None or due is None:
        return None
    return decided_on <= due
