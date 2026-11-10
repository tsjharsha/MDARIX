"""The rules of the first contact (G32), urgent intake and triage (G19) and duplicates (G20), as plain functions and
code constants. The trial behaves as the MVP items (T-B11); it differs only where the trial docs say so.

- **The first-contact guide** (``first-contact-starter-1``, starter text, T-B6): ten questions. Questions 1-9 are
  answered Yes, No, Unknown or Not applicable; questions 4-6 may also be Not stated. The desk records what the reporter
  alleges: No means "not alleged". **Unknown is never No, and Not stated is never No.**
- **The outcomes table** (``outcome``) is fixed in code, in G32's order. Every combination of answers has one outcome.
  "Service only" is offered only by row 2; no override reaches it.
- **The triage flag** (``intake_flags``, ``complaint_flags``): death or serious injury; a malfunction that could cause
  them; a possible public health threat; a harm level at or above a market's "serious" threshold; a harm word; a Yes
  or an Unknown on first-contact question 4, 5 or 6 (a Not stated only with a harm word or an alleged deficiency); an
  urgent intake; a manual escalation. The harm-word and fault-word lists are MDARIX's starter lists, fixed in the
  trial (the customer's versions come with G15).
- **The awareness rule** (``awareness``): the awareness time when recorded; otherwise the earliest of first knowledge,
  receipt and the source date ("awareness unresolved: deadline provisional"); the time it reached MDARIX only when
  none exists.
- **Provisional deadlines** (``provisional_deadlines``, MVP 5.1b): each market's shortest plausible category, from
  awareness, in three tiers (possible serious public health threat, flagged, unflagged), counted by the market's rule
  (reportability/deadlines.py). The event's own market comes first; the other enabled markets only "if also
  reportable"; a signed market conclusion replaces its market's provisional deadline (0.10.63, J3). Starter text until
  the consultant confirms each cell: the shorter reading applies.
- **The triage target**: 24 clock hours from availability in MDARIX (or the reopening), beside the regulatory clocks.
- **Possible duplicates** (``duplicate_reasons``): the same product and lot or serial number; an event within
  ``DUPLICATE_DAYS``; and the same site (or country). Starter values, fixed in the trial.

MDARIX never answers a question, never signs and never submits a report.
"""

from __future__ import annotations

import functools
import re
from datetime import datetime, timedelta, timezone

from backend.app.complaint_review.rules import normalize
from backend.app import feature_set
from backend.app.reportability import deadlines, markets
from backend.app.reportability import rules as reporting
from backend.app.rule_register import register

GUIDE_VERSION = "first-contact-starter-1"
HARM_WORDS_VERSION = "harm-words-starter-1"
FAULT_WORDS_VERSION = "fault-words-starter-1"
PROVISIONAL_VERSION = "provisional-starter-1"
REASON_MIN = 10
TEXT_MAX = 2000
WORDS_MAX = 4000
TRIAGE_TARGET_HOURS = 24
DUPLICATE_DAYS = 2

KINDS = ("CONTACT", "URGENT", "SERVICE_RECORD")
KIND_LABELS = {"CONTACT": "Logged contact", "URGENT": "Urgent intake", "SERVICE_RECORD": "Imported service record"}

YES, NO, UNKNOWN, NOT_APPLICABLE, NOT_STATED = "YES", "NO", "UNKNOWN", "NOT_APPLICABLE", "NOT_STATED"
ANSWERS = (YES, NO, UNKNOWN, NOT_APPLICABLE, NOT_STATED)
ANSWER_LABELS = {YES: "Yes", NO: "No", UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable", NOT_STATED: "Not stated"}

QUESTIONS = (
    (
        "Q1",
        "Is the device alleged not to perform as intended, or to fall short in identity, quality, durability, "
        "reliability, usability, safety or performance?",
    ),
    ("Q2", "Is an output or measurement alleged to be inaccurate?"),
    ("Q3", "Did the device malfunction or behave abnormally?"),
    ("Q4", "Was anyone harmed, or could they have been?"),
    ("Q5", "Was there a death or a serious injury?"),
    ("Q6", "Could the malfunction cause serious harm if it happened again?"),
    (
        "Q7",
        "Is the request only routine maintenance, installation, calibration, training or information (for example a "
        "copy of the instructions for use), with no fault alleged?",
    ),
    ("Q8", "Is a repair, or any intervention beyond the routine work of question 7, needed?"),
    ("Q9", "Has this happened before on this device or lot, or is there a related complaint?"),
    ("Q10", "What is still unknown and needs a follow-up with the reporter?"),
)
QUESTION_IDS = tuple(question for question, _ in QUESTIONS[:9])
HARM_QUESTIONS = ("Q4", "Q5", "Q6")
DEFICIENCY_QUESTIONS = ("Q1", "Q2", "Q3")
GUIDE_NOTE = (
    'Record what the reporter alleges: No means "not alleged". Unknown is never No. Not stated (questions 4-6) means '
    "the reporter said nothing about harm; it is never No."
)

COMPLAINT, BOTH, SERVICE_ONLY, PENDING, PENDING_CONFIRM = (
    "COMPLAINT",
    "BOTH",
    "SERVICE_ONLY",
    "PENDING",
    "PENDING_CONFIRM",
)
OUTCOMES = (COMPLAINT, BOTH, SERVICE_ONLY, PENDING, PENDING_CONFIRM)
OUTCOME_LABELS = {
    COMPLAINT: "Complaint",
    BOTH: "Both: complaint and service",
    SERVICE_ONLY: "Service only",
    PENDING: "Pending",
    PENDING_CONFIRM: "Pending: confirm no deficiency",
}
# Outcomes that start the normal journey: the QMS-complaint task, then the complaint's disposition.
COMPLAINT_OUTCOMES = (COMPLAINT, BOTH)
PENDING_OUTCOMES = (PENDING, PENDING_CONFIRM)
OUTCOME_TABLE = (
    (1, "A Yes on any of questions 1-3, whatever else is Unknown", 'Complaint; "both" when question 8 is Yes'),
    (
        2,
        "Question 7 Yes; questions 1-6 and 8 each No, or Not applicable with a reason; question 9 No or Not applicable",
        '"Service only" is offered',
    ),
    (
        3,
        "An Unknown on any of questions 1-9, or a Not stated on question 4, 5 or 6, and no Yes on questions 1-3",
        "Pending, with a follow-up asking what is unknown or not stated",
    ),
    (
        4,
        "Questions 1-3 and 7-9 each No or Not applicable, and questions 4-6 each No or Not applicable",
        "Pending: confirm no deficiency",
    ),
    (5, "Any other combination", 'Complaint; "both" when question 8 is Yes'),
)

REQUESTS = ("REPAIR", "MAINTENANCE", "INSTALLATION", "CALIBRATION", "TRAINING", "INFORMATION", "NONE")
REQUEST_LABELS = {
    "REPAIR": "Repair",
    "MAINTENANCE": "Maintenance",
    "INSTALLATION": "Installation",
    "CALIBRATION": "Calibration",
    "TRAINING": "Training",
    "INFORMATION": "Information",
    "NONE": "Nothing asked for",
}
# Spec 4.2 (H1): who knew first; an importer and an authorised representative added in 0.10.93 (B2).
FIRST_KNOWLEDGE_PARTIES = (
    "MANUFACTURER",
    "DISTRIBUTOR",
    "IMPORTER",
    "AUTHORISED_REPRESENTATIVE",
    "SERVICE_AGENT",
)
FIRST_KNOWLEDGE_BASES = ("ACTS_FOR_MANUFACTURER", "PROCEDURE_DEEMS", "NOT_ACTING_FOR")

# MDARIX's starter harm words (G19), fixed in the trial: death, injury and hospitalisation, with abbreviations. One
# list for intake, imported complaints and set-aside rows (import_quarantine.harm_words reads it too).
HARM_WORDS = (
    "death",
    "died",
    "dead",
    "deceased",
    "fatal",
    "injury",
    "injured",
    "injuries",
    "harm",
    "harmed",
    "hurt",
    "burn",
    "burned",
    "burnt",
    "choke",
    "choking",
    "shortness of breath",
    "short of breath",
    "desaturated",
    "cardiac arrest",
    "resuscitated",
    "intubated",
    "unconscious",
    "seizure",
    "hospital",
    "hospitalised",
    "hospitalized",
    "intensive care",
    "ICU",
    "emergency",
    "A&E",
    "pt",
    "bleeding",
    "infection",
    "overdose",
    "underdose",
    "under infused",
    "over infused",
    "wrong dose",
    "shock",
    # B7 step 12 (G18): the ways people say a death or an injury without the words above.
    "passed away",
    "passed on",
    "fatality",
    "killed",
    "life-threatening",
    "life threatening",
    "hospitalisation",
    "hospitalization",
    "admitted to hospital",
    "emergency room",
    "anaphylaxis",
    "anaphylactic",
    "stroke",
    "heart attack",
    "fracture",
    "laceration",
    "amputation",
    "electrocuted",
)
# MDARIX's starter fault words (G32): a "service only" record whose text matches one is always in the QA review.
FAULT_WORDS = (
    "inaccurate",
    "wrong reading",
    "drift",
    "error",
    "error code",
    "alarm",
    "stopped",
    "shut down",
    "switched off",
    "failed",
    "leak",
    "crack",
    "broken",
    "overheat",
    "smoke",
    "no output",
)
# A word directly after one of these is negated ("no harm", "no patient injury", "without injury") and does not count.
# Starter rule: "not" is never a negation here ("not breathing" is harm).
_NEGATIONS = (
    "no",
    "nil",
    "without",
    "no patient",
    "without any",
    "nobody",
    "nobody was",
    "no one",
    "no one was",
    "no sign of",
    "no signs of",
)
# B7 step 12 (G18): "not" (or "never") negates only these, directly after it: "the patient was not harmed" is no harm,
# "not breathing" still is.
_NOT_NEGATES = frozenset({"harmed", "injured", "hurt", "burned", "burnt", "hospitalised", "hospitalized", "killed"})


def clean(value: object, limit: int = TEXT_MAX) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _match(text: str, words) -> list[str]:
    plain = normalize(text)
    found = []
    for word in words:
        target = normalize(word)
        if not target:
            continue
        pattern = re.compile(r"(?<![\w&])" + re.escape(target).replace(r"\ ", r"\s+") + r"(?![\w&])")
        for hit in pattern.finditer(plain):
            before = plain[: hit.start()].split()
            negated = any(before[-len(n.split()) :] == n.split() for n in _NEGATIONS) or (
                target in _NOT_NEGATES and before[-1:] in (["not"], ["never"])
            )
            if not negated:
                found.append(word)
                break
    return found


def harm_words(text: object) -> list[str]:
    """The starter harm words the text holds, as whole words, a directly negated mention left out."""
    return _match(str(text or ""), HARM_WORDS)


def fault_words(text: object) -> list[str]:
    return _match(str(text or ""), FAULT_WORDS)


_ENGLISH = frozenset(
    "the a an and or of to in on at is was were it he she they we i you my our his her their not no with for from "
    "this that after before when device pump patient said".split()
)


def may_not_be_english(text: object) -> bool:
    """B7 step 12 (G18, IN-15): the words may not be English, so the harm words may have missed something: mostly
    letters outside the Latin alphabet, or six or more words with almost no common English word. Shown, never
    guessed further; a person adds a translation addendum (the original is always kept)."""
    value = str(text or "")
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return False
    if sum(1 for char in letters if ord(char) > 0x24F) / len(letters) > 0.3:
        return True
    words = re.findall(r"[a-zA-Z]+", value.lower())
    return len(words) >= 6 and sum(1 for word in words if word in _ENGLISH) / len(words) < 0.1


# --------------------------------------------------------------------------------------------- the first-contact check


def answer_of(answers: dict, question: str) -> str | None:
    return ((answers or {}).get(question) or {}).get("answer")


def note_of(answers: dict, question: str) -> str:
    return clean(((answers or {}).get(question) or {}).get("note"))


def clean_answers(raw: dict | None) -> dict:
    """Only the guide's questions, each with a known answer and its note; Not stated only on questions 4-6."""
    found = {}
    for question in QUESTION_IDS:
        item = (raw or {}).get(question) or {}
        answer = str(item.get("answer") or "").strip().upper() or None
        if answer not in ANSWERS or (answer == NOT_STATED and question not in HARM_QUESTIONS):
            answer = None
        found[question] = {"answer": answer, "note": clean(item.get("note"))}
    return found


def answers_problem(answers: dict) -> str | None:
    missing = [question for question in QUESTION_IDS if not answer_of(answers, question)]
    if missing:
        return "Answer every question first: " + ", ".join(f"question {q[1:]}" for q in missing)
    return None


def outcome(answers: dict, unresolved: bool = False) -> str:
    """G32's outcomes table, in its order. An unanswered question counts as Unknown (never as No). ``unresolved``: a
    "confirm no deficiency" follow-up was closed unresolved after attempts, so the contact ends as a complaint."""
    value = {question: answer_of(answers, question) or UNKNOWN for question in QUESTION_IDS}

    def no_or_reasoned(question: str) -> bool:
        return value[question] == NO or (value[question] == NOT_APPLICABLE and bool(note_of(answers, question)))

    complaint = BOTH if value["Q8"] == YES else COMPLAINT
    if any(value[question] == YES for question in DEFICIENCY_QUESTIONS):
        return complaint
    if (
        value["Q7"] == YES
        and all(no_or_reasoned(question) for question in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q8"))
        and value["Q9"] in (NO, NOT_APPLICABLE)
    ):
        return SERVICE_ONLY
    if any(value[question] == UNKNOWN for question in QUESTION_IDS) or any(
        value[question] == NOT_STATED for question in HARM_QUESTIONS
    ):
        return PENDING
    if all(value[question] in (NO, NOT_APPLICABLE) for question in QUESTION_IDS):
        return COMPLAINT if unresolved else PENDING_CONFIRM
    return complaint


def outcome_row(answers: dict) -> int:
    """The table's row that gives the outcome (for the screen)."""
    value = {question: answer_of(answers, question) or UNKNOWN for question in QUESTION_IDS}
    result = outcome(answers)
    if any(value[question] == YES for question in DEFICIENCY_QUESTIONS):
        return 1
    if result == SERVICE_ONLY:
        return 2
    if result == PENDING:
        return 3
    if result == PENDING_CONFIRM:
        return 4
    return 5


def follow_up_questions(answers: dict) -> list[str]:
    """The questions a follow-up with the reporter asks: every Unknown, and every Not stated."""
    return [question for question in QUESTION_IDS if (answer_of(answers, question) or UNKNOWN) in (UNKNOWN, NOT_STATED)]


def classification_problem(suggestion: str, classification: str, override_reason: str, reason: str) -> str | None:
    """What the coordinator may sign: the suggestion, or another outcome with a reason; never "service only" or
    "confirm no deficiency" unless the guide suggests it (no override maps a deficiency, an Unknown, a Not stated or a
    harm answer to "service only")."""
    if classification not in OUTCOMES:
        return "Choose the classification"
    if classification in (SERVICE_ONLY, PENDING_CONFIRM) and classification != suggestion:
        return f'"{OUTCOME_LABELS[classification]}" is offered only when the answers give it'
    if classification != suggestion and len(override_reason) < REASON_MIN:
        return f"You override the suggestion: say in at least {REASON_MIN} characters why"
    if classification == SERVICE_ONLY and len(reason) < REASON_MIN:
        return f'"Service only" needs a written reason of at least {REASON_MIN} characters'
    return None


# --------------------------------------------------------------------------------------------- the triage flag


def _reason(code: str, label: str, **extra) -> dict:
    return {"code": code, "label": label, **extra}


def intake_flags(kind: str, words: str, answers: dict) -> list[dict]:
    """Why an intake event is flagged for triage, at once, before any signature."""
    found = []
    if kind == "URGENT":
        found.append(_reason("URGENT_INTAKE", "Urgent intake: a complaint by definition, triaged at once"))
    words_found = harm_words(words)
    deficiency = any(answer_of(answers, question) == YES for question in DEFICIENCY_QUESTIONS)
    for question in HARM_QUESTIONS:
        answer = answer_of(answers, question)
        if answer in (YES, UNKNOWN):
            found.append(
                _reason(
                    "FIRST_CONTACT",
                    f"Question {question[1:]} answered {ANSWER_LABELS[answer]}",
                    question=question,
                    answer=answer,
                )
            )
        elif answer == NOT_STATED and (words_found or deficiency):
            found.append(
                _reason(
                    "FIRST_CONTACT",
                    f"Question {question[1:]} not stated, with "
                    + ("a harm word" if words_found else "a deficiency alleged"),
                    question=question,
                    answer=answer,
                )
            )
    if words_found:
        found.append(_reason("HARM_WORDS", "Mentions " + ", ".join(words_found[:6]), words=words_found))
    return found


def complaint_flags(record: dict) -> list[dict]:
    """Why an imported complaint is flagged for triage: its harm fields, its severity and its words."""
    found = []
    if record.get("death"):
        found.append(_reason("DEATH", "Death recorded"))
    if record.get("serious_injury"):
        found.append(_reason("SERIOUS_INJURY", "Serious injury recorded"))
    elif record.get("patient_involved") and (record.get("serious_injury") is None or record.get("death") is None):
        found.append(_reason("HARM_UNKNOWN", "A patient was involved and the outcome is not known"))
    if record.get("malfunction"):
        found.append(_reason("MALFUNCTION", "Malfunction: it could cause a death or serious injury if it recurred"))
    level = markets.level_of_severity(record.get("severity"))
    if level and markets.rank(level) >= markets.rank(markets.SERIOUS):
        found.append(_reason("HARM_LEVEL", f"Severity {record.get('severity')}: at or above a serious threshold"))
    words_found = harm_words(record.get("description"))
    if words_found:
        found.append(_reason("HARM_WORDS", "Mentions " + ", ".join(words_found[:6]), words=words_found))
    return found


def quarantine_flags(harm: list[str]) -> list[dict]:
    if not harm:
        return []
    return [_reason("HARM_WORDS", "Set aside, but suggests harm: " + ", ".join(harm[:6]), words=list(harm))]


# --------------------------------------------------------------------------------------------- awareness and clocks


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def awareness(
    awareness_at: datetime | None,
    candidates: list[tuple[datetime | None, str]],
    available_at: datetime,
    earliest: bool = False,
) -> dict:
    """The awareness time a clock counts from: the recorded awareness; else the earliest of the candidates (first
    knowledge, receipt, the source date), unresolved; else the time it reached MDARIX, unresolved. ``earliest``: an
    imported complaint counts from the earliest of its awareness, received and recorded days even when awareness is
    recorded, as the reportability watch does (reportability/service.py ``awareness``)."""
    if awareness_at is not None and not earliest:
        return {"at": utc(awareness_at), "source": "AWARENESS", "unresolved": False}
    found = [(awareness_at, "AWARENESS"), *candidates] if awareness_at is not None else candidates
    known = [(utc(moment), source) for moment, source in found if moment is not None]
    if known:
        moment, source = min(known, key=lambda item: item[0])
        return {"at": moment, "source": source, "unresolved": awareness_at is None}
    return {"at": utc(available_at), "source": "AVAILABLE", "unresolved": True}


AWARENESS_LABELS = {
    "AWARENESS": "awareness recorded",
    "CONFIRMED": "awareness confirmed at triage",
    "CONTACT": "the time of the contact",
    "FIRST_KNOWLEDGE": "first knowledge",
    "RECEIVED": "receipt",
    "EVENT_DATE": "the event date (no awareness or received date)",
    "SOURCE_DATE": "the source record's date",
    "AVAILABLE": "the time it reached MDARIX",
    "LINKED": "an earlier linked source",
}
UNRESOLVED_LABEL = "Awareness unresolved: deadline provisional"

THREAT, FLAGGED, UNFLAGGED = "THREAT", "FLAGGED", "UNFLAGGED"
TIER_LABELS = {
    THREAT: "Possible serious public health threat",
    FLAGGED: "Flagged",
    UNFLAGGED: "Unflagged complaint",
}
# MVP 5.1b for the trial's markets: (days, day basis, basis). The shorter reading applies until the consultant
# confirms a cell (starter text).
PROVISIONAL = {
    markets.US: {
        THREAT: (5, reporting.WORK, "5 work days (21 CFR 803.53)"),
        FLAGGED: (30, reporting.CALENDAR, "30 calendar days (21 CFR 803.50)"),
        UNFLAGGED: (30, reporting.CALENDAR, "30 calendar days (21 CFR 803.50)"),
    },
    markets.EU_NI: {
        THREAT: (2, reporting.CALENDAR, "2 days (EU MDR Art. 87(4))"),
        FLAGGED: (10, reporting.CALENDAR, "10 days (EU MDR Art. 87(5))"),
        UNFLAGGED: (15, reporting.CALENDAR, "15 days (EU MDR Art. 87(3))"),
    },
    markets.GB: {
        THREAT: (2, reporting.CALENDAR, "2 days (UK MDR 2002 as amended)"),
        FLAGGED: (10, reporting.CALENDAR, "10 days (UK MDR 2002 as amended)"),
        UNFLAGGED: (15, reporting.CALENDAR, "15 days (UK MDR 2002 as amended)"),
    },
    markets.IN: {
        THREAT: (15, reporting.CALENDAR, "15 days (India MDR 2017 Rule 26)"),
        FLAGGED: (15, reporting.CALENDAR, "15 days (India MDR 2017 Rule 26)"),
        UNFLAGGED: (15, reporting.CALENDAR, "15 days (India MDR 2017 Rule 26; MvPI default)"),
    },
    # Canada (0.10.76): no 2-day threat report; the shorter 10 days until the consultant confirms (starter).
    markets.CA: {
        THREAT: (10, reporting.CALENDAR, "10 days (SOR/98-282 s. 60(1)(a)(i))"),
        FLAGGED: (10, reporting.CALENDAR, "10 days (SOR/98-282 s. 60(1)(a)(i))"),
        UNFLAGGED: (30, reporting.CALENDAR, "30 days (SOR/98-282 s. 60(1)(a)(ii))"),
    },
}
US_REMEDIAL = (5, reporting.WORK, "5 work days: remedial action may be needed (21 CFR 803.53)")
# The EU clocks of an in-vitro diagnostic cite the IVDR (Regulation (EU) 2017/746, Art. 82): starter text, for the
# consultant to confirm (the MVP requirements give no IVDR article).
IVDR_82 = "EU IVDR Art. 82, starter"


def _provisional(market: str, level: str, remedial: bool, aware, org_zone: str | None) -> tuple:
    """A tier's (days, day basis, label, what rules the earliest report out) from the market's floor in force at
    awareness (B4); today's constants when the rule register is off."""
    table, remedy, ruled_out = PROVISIONAL[market], US_REMEDIAL if market == markets.US else None, RULED_OUT.get(market)
    floor = register.floor_at(market, utc(aware), org_zone) if feature_set.rule_register() else None
    if floor:
        table = floor["content"]["provisional"]
        remedy, ruled_out = table["remedial"], table["ruled_out"]
    days, basis, label = remedy if remedy and remedial and level == FLAGGED else table[level]
    return days, basis, label, ruled_out


def tier(flagged: bool, threat: bool) -> str:
    return THREAT if threat else FLAGGED if flagged else UNFLAGGED


# Check 3a (owner, 10 Nov 2026): until triage answers the question that decides the shorter report, a market's clock
# is its earliest possible report: the market rules' own result with no answer yet (markets.evaluate), "unless" this.
RULED_OUT = {
    markets.US: "remedial action is ruled out",
    markets.EU_NI: "a public health threat is ruled out",
    markets.GB: "a public health threat is ruled out",
    markets.CA: "death or serious deterioration is ruled out",
}


def earliest_report(market: str, aware=None, org_zone: str | None = None) -> markets.ReportType | None:
    """The report the market's rules start when no question is answered yet (US 5 work days, EU/NI and GB 2 days,
    Canada 10 days); None for a market without one (India: the tier date already is its only window). From the
    market's floor in force at awareness (B4; today's without one)."""
    if market not in RULED_OUT:
        return None
    floor = register.floor_at(market, utc(aware), org_zone) if feature_set.rule_register() else None
    return _earliest(market, floor["code"] if floor else None, str(register._DIRECTORY))


@functools.cache
def _earliest(market: str, floor_code: str | None, directory: str) -> markets.ReportType | None:
    floor = register.get(floor_code) if floor_code else None
    types = markets._in_force(directory, (floor_code,))[1] if floor else markets.REPORT_TYPES
    kind = types.get(markets.evaluate(market, {}, floor)["report_type_if_reportable"] or "")
    return kind if kind and kind.days else None


OWN, ALSO, SIGNED, NO_COUNTRY, NO_WINDOW = "OWN", "IF_ALSO", "SIGNED", "NO_COUNTRY", "OWN_NO_WINDOW"
ROLE_LABELS = {
    OWN: "The event's market",
    ALSO: "If also reportable",
    SIGNED: "Signed market conclusion",
    NO_COUNTRY: "No country recorded: each enabled market",
    NO_WINDOW: "No reporting window for the event's own market: each enabled market",
}


def provisional_deadlines(
    aware: datetime,
    enabled: list[str],
    level: str,
    today,
    remedial: bool = False,
    *,
    own: str | None = None,
    signed: dict | None = None,
    org_zone: str | None = None,
    ivd: bool = False,
    answered: bool = True,
) -> list[dict]:
    """Each enabled market's deadline for triage (MVP 5.1b; J3), counted by the market's rule (reportability/deadlines.py):
    the event's own market (``own``, from its country) first; the other enabled markets after it, only "if also
    reportable"; a market with a signed conclusion (``signed``: market -> its clock, or None when concluded not
    reportable) shows that conclusion's deadline instead of the provisional one. ``ivd``: an in-vitro diagnostic,
    whose EU clocks cite the IVDR (starter). ``today``: now (a day in older callers). ``answered``: triage has
    answered the threat, remedial and harm questions; until then each market shows its earliest possible report when
    that is earlier than the tier's date, with ``earliest_note`` (check 3a)."""
    found = []
    signed = signed or {}
    listed = enabled or list(markets.MARKETS)
    for market in listed:
        role = (
            SIGNED
            if market in signed
            else OWN
            if market == own
            else ALSO
            if own in listed
            else NO_WINDOW
            if own
            else NO_COUNTRY
        )
        if market in signed:
            clock = signed[market]
            found.append(
                {
                    "market": market,
                    "label": markets.MARKET_LABELS[market],
                    "role": role,
                    "role_label": ROLE_LABELS[role],
                    "own": market == own,
                    "tier": level,
                    "tier_label": "Concluded not reportable" if clock is None else "Signed: reportable",
                    "not_reportable": clock is None,
                    "days": clock["days"] if clock else None,
                    "day_basis": clock["day_basis"] if clock else None,
                    "basis": clock["window"] if clock else "Concluded not reportable (signed)",
                    "conservative": False,
                    **(
                        {
                            key: clock[key]
                            for key in ("due_date", "due_at", "due_zone", "due_label", "days_left", "state")
                        }
                        if clock
                        else {k: None for k in ("due_date", "due_at", "due_zone", "due_label", "days_left", "state")}
                    ),
                }
            )
            continue
        days, basis, label, ruled_out = _provisional(market, level, remedial, aware, org_zone)
        due = deadlines.count(utc(aware), days, basis, market, org_zone)
        note, kind = None, None if answered else earliest_report(market, aware, org_zone)
        if kind is not None:
            sooner = deadlines.count(utc(aware), kind.days, kind.day_basis, market, org_zone)
            if sooner.at < due.at:
                days, basis, label, due = kind.days, kind.day_basis, kind.label, sooner
                unit = "work days" if basis == reporting.WORK else "days"
                note = f"{days} {unit} unless {ruled_out}"
        if ivd and market == markets.EU_NI:
            label = label.replace("EU MDR Art. 87(4)", IVDR_82).replace("EU MDR Art. 87(5)", IVDR_82)
            label = label.replace("EU MDR Art. 87(3)", IVDR_82)
        found.append(
            {
                "market": market,
                "label": markets.MARKET_LABELS[market],
                "role": role,
                "role_label": ROLE_LABELS[role],
                "own": market == own,
                "tier": level,
                "tier_label": TIER_LABELS[level],
                "not_reportable": False,
                "days": days,
                "day_basis": basis,
                "basis": label,
                "earliest_note": note,
                **deadlines.view(due, today, days),
                "conservative": True,
            }
        )
    return sorted(found, key=lambda item: (not item["own"], item["not_reportable"], item["due_at"] or "9999"))


def triage_clock(available: datetime, now: datetime, target_hours: int = TRIAGE_TARGET_HOURS) -> dict:
    """The triage target: an outer limit in clock hours from availability in MDARIX (or the reopening)."""
    due = utc(available) + timedelta(hours=target_hours)
    left = (due - now).total_seconds() / 3600
    state = "OVERDUE" if left < 0 else "DUE_SOON" if left <= target_hours / 4 else "RUNNING"
    return {
        "from": utc(available).isoformat(),
        "target_hours": target_hours,
        "due_at": due.isoformat(),
        "hours_left": round(left, 1),
        "state": state,
    }


def delay_text(aware: datetime, available: datetime) -> dict:
    """The time from awareness to availability in MDARIX: an old event imported today never looks newly received."""
    hours = max(0.0, (utc(available) - utc(aware)).total_seconds() / 3600)
    days = int(hours // 24)
    text = f"{days} day{'s' if days != 1 else ''}" if days else f"{int(hours)} hour{'s' if int(hours) != 1 else ''}"
    return {"hours": round(hours, 1), "text": text}


# --------------------------------------------------------------------------------------------- possible duplicates


def duplicate_reasons(left: dict, right: dict) -> list[str]:
    """Why two records from different sources may be one occurrence (G20): the same product; the same lot or serial
    number; events within DUPLICATE_DAYS (or no event date on one); and the same reporter's site, or the same country
    where a site is not recorded. Empty when they may not be."""
    if not left.get("product_id") or left.get("product_id") != right.get("product_id"):
        return []
    dates = [left.get("event_on"), right.get("event_on")]
    if all(dates) and abs((dates[0] - dates[1]).days) > DUPLICATE_DAYS:
        return []

    def same(key: str) -> bool:
        a, b = normalize(left.get(key)), normalize(right.get(key))
        return bool(a) and a == b

    unit = [label for key, label in (("lot_id", "same lot"), ("serial", "same serial number")) if same(key)]
    place = "same site" if same("site") else "same country" if same("country") else None
    if not unit or not place:
        return []
    when = f"event dates within {DUPLICATE_DAYS} days" if all(dates) else "no event date on one of them"
    return ["same product", *unit, when, place]
