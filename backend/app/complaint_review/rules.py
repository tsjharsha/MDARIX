"""The rules of the second look and the backlog board, as plain functions.

Why it matters (FDA warning letters, 2026): complaints were cancelled or logged as inquiries although they met the
firm's own complaint definition (3B Medical: 7 of 11 cancelled records, 13 of 15 inquiries), and complaints coded
"No Fault Found" or "User Error" hid a recurring problem (Zoll). The second look finds such records and shows why; a
person decides. MDARIX never decides that a record is a complaint and never changes the record.

Statuses, types and codes are free text from each organization's system ("Cancelled", "CANCELED", "Void",
"Inquiry", "Service request", "NFF", "No fault found"), so every value is normalized (lower case, separators as
spaces) and compared against families of spellings rather than one code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

DEFAULT_TARGET_DAYS = 30
TARGET_DAYS_MIN, TARGET_DAYS_MAX = 1, 365
# Days before the target when a complaint is "due soon" on the backlog board.
DUE_SOON_DAYS = 7
# A No Fault Found or User Error code is flagged when it recurs this often on one product within the window.
NFF_RECURRENCE_MIN = 3
NFF_WINDOW_DAYS = 365
WORDS_MAX = 100
WORD_MAX_LENGTH = 60
REASON_MIN = 10

# Words in a description that suggest a complaint (harm, a failure, a hazard). Each organization can replace them.
DEFAULT_WORDS = (
    "injury",
    "injured",
    "burn",
    "burned",
    "choke",
    "choking",
    "shortness of breath",
    "short of breath",
    "breathing",
    "death",
    "died",
    "hospital",
    "emergency",
    "bleeding",
    "infection",
    "pain",
    "overdose",
    "underdose",
    "wrong dose",
    "shock",
    "smoke",
    "fire",
    "overheat",
    "overheated",
    "leak",
    "leaking",
    "broken",
    "cracked",
    "failed",
    "failure",
    "malfunction",
    "stopped working",
    "error code",
    "alarm",
)

CANCELLED_STATUSES = frozenset(
    {
        "cancelled",
        "canceled",
        "void",
        "voided",
        "rejected",
        "withdrawn",
        "invalid",
        "not a complaint",
        "not a valid complaint",
        "no action",
        "closed no action",
        "closed no issue",
        "closed no issue found",
    }
)
CLOSED_STATUSES = frozenset({"closed", "resolved", "completed", "complete", "done", "archived"})
INQUIRY_KINDS = frozenset(
    {
        "inquiry",
        "enquiry",
        "question",
        "information request",
        "info request",
        "service",
        "service request",
        "repair",
        "return",
        "rma",
        "feedback",
    }
)
# No Fault Found and User Error, in the spellings systems use. Matched as whole words in a status, type or code.
_NFF = re.compile(
    r"\b(nff|no fault found|no problem found|no defect found|no issue found|"
    r"(could not|cannot|can not|unable to) (reproduce|duplicate|replicate))\b"
)
_USER_ERROR = re.compile(r"\b(user error|use error|operator error|misuse|customer misuse|user misuse)\b")
SERIOUS_SEVERITIES = frozenset({"high", "critical", "serious", "major", "severe"})

# Substrings for the database's first, broad filter (service.py); the functions below then decide exactly.
CANDIDATE_PATTERNS = (
    "%cancel%",
    "%void%",
    "%reject%",
    "%withdraw%",
    "%invalid%",
    "%not a%complaint%",
    "%no action%",
    "%no issue%",
    "%inquir%",
    "%enquir%",
    "%question%",
    "%service%",
    "%repair%",
    "%return%",
    "%rma%",
    "%feedback%",
    "%info%request%",
    "%nff%",
    "%no fault%",
    "%no problem%",
    "%no defect%",
    "%reproduc%",
    "%duplicat%",
    "%replicat%",
    "%user error%",
    "%use error%",
    "%operator error%",
    "%misuse%",
)

# Reason and sign codes, with their weight in the order of the list (a death outranks a word).
CANCELLED = "CANCELLED"
INQUIRY = "INQUIRY"
NFF_RECURRING = "NFF_RECURRING"
# T-D13 (0.10.93, B2; TR-23): closed in the QMS with a death or a serious injury and no signed market conclusion.
CLOSED_NO_DECISION = "CLOSED_NO_DECISION"
CLOSED_NO_DECISION_LABEL = "Closed without a reportability decision?"
NO_FAULT_FOUND, USER_ERROR = "NO_FAULT_FOUND", "USER_ERROR"
SIGN_WEIGHTS = {
    "DEATH": 100,
    "SERIOUS_INJURY": 80,
    "PATIENT_INVOLVED": 50,
    "MALFUNCTION": 40,
    "SEVERITY": 30,
    "WORDS": 30,
    "PROBLEM_CODE": 20,
}
REASON_WEIGHTS = {CLOSED_NO_DECISION: 50, NFF_RECURRING: 35, CANCELLED: 10, INQUIRY: 10}


def normalize(value: object) -> str:
    """Lower case, separators (_ - / .) as spaces, single spaces."""
    text = str(value or "").lower()
    text = re.sub(r"[_\-/.:;,]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_cancelled(status: object) -> bool:
    return normalize(status) in CANCELLED_STATUSES


def is_closed(status: object) -> bool:
    return normalize(status) in CLOSED_STATUSES


def is_inquiry(status: object, complaint_type: object) -> bool:
    for value in (normalize(status), normalize(complaint_type)):
        if value in INQUIRY_KINDS or "inquiry" in value or "enquiry" in value:
            return True
    return False


def nff_family(*values: object) -> str | None:
    """NO_FAULT_FOUND or USER_ERROR when a status, type or code says so, else None."""
    for value in values:
        text = normalize(value)
        if not text:
            continue
        if _NFF.search(text):
            return NO_FAULT_FOUND
        if _USER_ERROR.search(text):
            return USER_ERROR
    return None


def clean_words(words: object) -> list[str]:
    """An organization's word list: trimmed, lower case, without blanks or repeats, in their order."""
    if not isinstance(words, (list, tuple)):
        return []
    seen: list[str] = []
    for word in words:
        text = re.sub(r"\s+", " ", str(word or "").strip().lower())
        if text and text not in seen:
            seen.append(text)
    return seen


def words_problem(words: list[str]) -> str | None:
    if not words:
        return "Keep at least one word"
    if len(words) > WORDS_MAX:
        return f"Keep at most {WORDS_MAX} words"
    long = next((word for word in words if len(word) > WORD_MAX_LENGTH), None)
    if long:
        return f'"{long[:20]}…" is longer than {WORD_MAX_LENGTH} characters'
    return None


def matched_words(description: object, words: list[str] | tuple[str, ...]) -> list[str]:
    """The words (or phrases) the description contains as whole words, in the list's order."""
    text = normalize(description)
    found = []
    for word in words:
        pattern = r"\b" + re.escape(normalize(word)).replace(r"\ ", r"\s+") + r"\b"
        if normalize(word) and re.search(pattern, text):
            found.append(word)
    return found


@dataclass
class Flag:
    """Why a record deserves a second look: its reasons, its complaint signs and their weight."""

    reasons: list[dict] = field(default_factory=list)
    signs: list[dict] = field(default_factory=list)
    words: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(REASON_WEIGHTS.get(item["code"], 0) for item in self.reasons) + sum(
            SIGN_WEIGHTS.get(item["code"], 0) for item in self.signs
        )

    def as_dict(self) -> dict:
        return {"reasons": self.reasons, "signs": self.signs, "words": self.words, "score": self.score}


def signs_of(record: dict, words: list[str] | tuple[str, ...]) -> tuple[list[dict], list[str]]:
    """The complaint signs a record carries: harm and failure flags, severity, a problem code, words."""
    signs = []
    if record.get("death"):
        signs.append({"code": "DEATH", "label": "Death reported"})
    if record.get("serious_injury"):
        signs.append({"code": "SERIOUS_INJURY", "label": "Serious injury"})
    if record.get("patient_involved"):
        signs.append({"code": "PATIENT_INVOLVED", "label": "Patient involved"})
    if record.get("malfunction"):
        signs.append({"code": "MALFUNCTION", "label": "Malfunction"})
    if normalize(record.get("severity")) in SERIOUS_SEVERITIES:
        signs.append({"code": "SEVERITY", "label": f"Severity: {str(record.get('severity')).strip()}"})
    code = str(record.get("problem_code") or "").strip()
    if code and not nff_family(code):
        # The value lets the screen show the IMDRF term first and the customer's own code as its detail (0.10.70).
        signs.append({"code": "PROBLEM_CODE", "label": f"Problem code: {code}", "value": code})
    found = matched_words(record.get("description"), words)
    if found:
        signs.append({"code": "WORDS", "label": "Mentions " + ", ".join(found[:6])})
    return signs, found


def flag(record: dict, words: list[str] | tuple[str, ...], nff_count: int = 0) -> Flag | None:
    """Why ``record`` deserves a second look, or None. ``nff_count`` is how many records of the same product carry
    the same No Fault Found or User Error family within the window (this one included)."""
    status, kind = record.get("status"), record.get("complaint_type")
    reasons = []
    if is_cancelled(status):
        reasons.append({"code": CANCELLED, "label": f"Cancelled or rejected (status: {str(status).strip()})"})
    if is_inquiry(status, kind):
        shown = str(kind or status).strip()
        reasons.append({"code": INQUIRY, "label": f"Logged as an inquiry or service record ({shown})"})
    family = nff_family(record.get("problem_code"), kind, status)
    if family and nff_count >= NFF_RECURRENCE_MIN:
        name = "No Fault Found" if family == NO_FAULT_FOUND else "User Error"
        product = record.get("product_name") or "this product"
        reasons.append(
            {
                "code": NFF_RECURRING,
                "label": f"{name} recurs: {nff_count} records on {product} in 12 months",
                "count": nff_count,
            }
        )
    if closed_without_decision(record):
        reasons.append({"code": CLOSED_NO_DECISION, "label": CLOSED_NO_DECISION_LABEL})
    if not reasons:
        return None
    signs, found = signs_of(record, words)
    # A cancelled record or an inquiry needs a complaint sign to be worth a second look; a recurring No Fault Found or
    # User Error is one by itself.
    if not signs and not any(item["code"] == NFF_RECURRING for item in reasons):
        return None
    return Flag(reasons=reasons, signs=signs, words=found)


def closed_without_decision(record: dict) -> bool:
    """A record closed with a death or a serious injury and no signed market conclusion (``market_concluded``, set by
    the service): it is never triaged, so the second look asks whether anyone decided its reportability."""
    return (
        is_closed(record.get("status"))
        and bool(record.get("death") or record.get("serious_injury"))
        and not record.get("market_concluded")
    )


def counts_as_open(status: object, complaint_type: object, decision: str | None) -> bool:
    """Whether a complaint belongs on the backlog board: open, not cancelled or an inquiry, unless a person confirmed
    on the second look that it is a complaint (then it counts until it is closed); a dismissed record never does."""
    if decision == "DISMISSED":
        return False
    if is_closed(status):
        return False
    if decision == "CONFIRMED":
        return True
    return not is_cancelled(status) and not is_inquiry(status, complaint_type)


AGE_BANDS = (("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None))


def age_days(received: date | None, today: date) -> int | None:
    return None if received is None else max(0, (today - received).days)


def age_band(age: int) -> str:
    for name, low, high in AGE_BANDS:
        if age >= low and (high is None or age <= high):
            return name
    return AGE_BANDS[-1][0]


def backlog_state(age: int, target_days: int) -> str:
    """PAST_TARGET, DUE_SOON (fewer than DUE_SOON_DAYS days left before the target) or ON_TRACK."""
    if age > target_days:
        return "PAST_TARGET"
    if target_days - age < DUE_SOON_DAYS:
        return "DUE_SOON"
    return "ON_TRACK"
