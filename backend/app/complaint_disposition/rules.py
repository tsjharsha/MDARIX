"""The rules of complaint disposition (T-G36), the routine path (T-U13) and the root-cause attribution, as plain
functions and code constants.

A complaint's disposition decides only how it is resolved; a complaint on the reportability watch still needs its
per-market assessment, whatever its disposition. The person answers in a fixed order, each answer with its rationale:

1. Is an escalation trigger met? (triggers.py) Then ``ESCALATED_BY_TRIGGER``: a case opens at once, the other branches
   are refused.
2. Is it a known issue? An open case whose scope holds a complaint with the same product and problem code, or the same
   lot: the complaint joins that case's scope as a contributing complaint (a new scope version). ``KNOWN_ISSUE``.
3. Was it resolved at service level? The service-level record and the root-cause attribution. ``SERVICE_LEVEL``.
4. Otherwise ``ESCALATED_BY_CHOICE``, with a reason: a case opens.

The rules (``disposition-starter-1``) and the classification's coding criteria (``coding-starter-1``) are starter
text (T-B6) and documents a signer acknowledges before signing (T-G40P). MDARIX never answers, never signs and never
submits a report. Codes are the MVP's (G36), so the MVP swaps sources without renaming anything stored.
"""

from __future__ import annotations

from backend.app.db.models.complaint_disposition import ATTRIBUTIONS
from backend.app.standards import version_words

RULES_VERSION = "disposition-starter-1"
ESCALATED_BY_TRIGGER, KNOWN_ISSUE, SERVICE_LEVEL, ESCALATED_BY_CHOICE = (
    "ESCALATED_BY_TRIGGER",
    "KNOWN_ISSUE",
    "SERVICE_LEVEL",
    "ESCALATED_BY_CHOICE",
)
BRANCHES = (ESCALATED_BY_TRIGGER, KNOWN_ISSUE, SERVICE_LEVEL, ESCALATED_BY_CHOICE)
ESCALATED = (ESCALATED_BY_TRIGGER, ESCALATED_BY_CHOICE)
# A signed SERVICE_LEVEL or KNOWN_ISSUE disposition takes the complaint off the Backlog.
RESOLVED = (SERVICE_LEVEL, KNOWN_ISSUE)
BRANCH_LABELS = {
    ESCALATED_BY_TRIGGER: "Escalated: trigger met",
    KNOWN_ISSUE: "Known issue, linked to an open investigation",
    SERVICE_LEVEL: "Resolved at service level",
    ESCALATED_BY_CHOICE: "Escalated by choice",
}
# signed_approval_records.decision is at most 12 characters.
SIGNATURE_CODES = {
    ESCALATED_BY_TRIGGER: "ESC_TRIGGER",
    KNOWN_ISSUE: "KNOWN_ISSUE",
    SERVICE_LEVEL: "SERVICE_LVL",
    ESCALATED_BY_CHOICE: "ESC_CHOICE",
}
# The four questions of the decision tree, in order.
QUESTIONS = (
    ("TRIGGER", "Is an escalation trigger met?"),
    ("KNOWN_ISSUE", "Is it a known issue?"),
    ("SERVICE_LEVEL", "Was it resolved at service level?"),
    ("CHOICE", "Otherwise: escalate by choice"),
)

DEVICE_RELATED, USE_RELATED, ENVIRONMENT_RELATED, UNDETERMINED = ATTRIBUTIONS
ATTRIBUTION_LABELS = {
    DEVICE_RELATED: "Device-related",
    USE_RELATED: "Use-related",
    ENVIRONMENT_RELATED: "Environment-related",
    UNDETERMINED: "Undetermined",
}
ATTRIBUTION_DEFINITIONS = {
    DEVICE_RELATED: "The device, a part or its software did not perform as specified.",
    USE_RELATED: "How the device was set up, operated or maintained by its user.",
    ENVIRONMENT_RELATED: "Where it was used: power, interference, temperature, cleaning agents, transport.",
    UNDETERMINED: "The evidence does not show which: say why.",
}
CORRECTIONS = ("PART_REPLACED", "SETTING_CORRECTED", "USER_INSTRUCTED", "OTHER")
CORRECTION_LABELS = {
    "PART_REPLACED": "Part replaced",
    "SETTING_CORRECTED": "Setting corrected",
    "USER_INSTRUCTED": "User instructed",
    "OTHER": "Other (describe it)",
}
NO_INVESTIGATION_CLAUSE = "ISO 13485:2016 clause 8.2.2"
CLAUSE_IDS = ("ISO13485_8_2_2",)

REASON_MIN = 10
RATIONALE_MIN = 20
TEXT_MAX = 2000
TICKET_MAX = 120
HANDS_ON_MAX = 24 * 3600
# The routine path's target (U13): under ten minutes from opening the screen to signing.
ROUTINE_TARGET_SECONDS = 600
ROUTINE_QUESTION_SET = "ROUTINE-BASIS"
ROUTINE_BASIS = (
    "Not on the reportability watch: no death, serious injury or malfunction recorded; patient outcome known"
)

# The written disposition rules a signer acknowledges (starter text, T-B6): shown on the screen behind "show".
DISPOSITION_RULES = (
    "Answer in order. An escalation trigger met (safety, injury, a reportable outcome, a recurrence no open case "
    "covers, a new failure mode) escalates the complaint: a case opens at once and no other branch is allowed.",
    "A known issue is an open case whose scope holds a complaint with the same product and problem code, or the same "
    "lot. Link the complaint to it with your reason; no second case is opened.",
    "Resolved at service level: record the troubleshooting, the discrete correction, its result, the service ticket and "
    "why no investigation is needed (ISO 13485:2016 clause 8.2.2), and the root-cause attribution.",
    "Otherwise escalate by choice, with your reason: a case opens.",
    "The disposition never replaces the reportability assessment: a complaint on the watch is still assessed for each "
    "market.",
    "A signed disposition is never edited. A change is a new version with its reason; the earlier one stays visible.",
)


def collapse(value: object) -> str:
    return " ".join(str(value or "").split())


def attribution_problem(attribution: str | None, reason: str | None) -> str | None:
    """Why a root-cause attribution cannot be signed (the service-level close and the case decision share it)."""
    if attribution not in ATTRIBUTIONS:
        return "Choose the root-cause attribution: device-related, use-related, environment-related or undetermined"
    if attribution == UNDETERMINED and len(collapse(reason)) < REASON_MIN:
        return f"Undetermined: say in at least {REASON_MIN} characters why the cause cannot be attributed"
    if len(collapse(reason)) > TEXT_MAX:
        return f"Keep the attribution reason under {TEXT_MAX} characters"
    return None


def clean_service_record(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "troubleshooting": collapse(raw.get("troubleshooting")),
        "correction_type": collapse(raw.get("correction_type")).upper(),
        "correction": collapse(raw.get("correction")),
        "result": collapse(raw.get("result")),
        "service_ticket": collapse(raw.get("service_ticket")),
        "no_investigation_rationale": collapse(raw.get("no_investigation_rationale")),
        "clause": NO_INVESTIGATION_CLAUSE,
    }


def service_record_problem(record: dict) -> str | None:
    """Why a service-level record is not complete: every field is needed, and the no-investigation rationale is the
    reason ISO 13485:2016 clause 8.2.2 asks to be documented."""
    if len(record["troubleshooting"]) < REASON_MIN:
        return f"Describe the troubleshooting done in at least {REASON_MIN} characters"
    if record["correction_type"] not in CORRECTIONS:
        return "Choose the correction: part replaced, setting corrected, user instructed or other"
    if len(record["correction"]) < REASON_MIN:
        return f"Describe the correction in at least {REASON_MIN} characters"
    if len(record["result"]) < 5:
        return "Say what the correction achieved (for example: alarm cleared, device in use)"
    if not record["service_ticket"] or len(record["service_ticket"]) > TICKET_MAX:
        return f"Give the service ticket reference (at most {TICKET_MAX} characters)"
    if len(record["no_investigation_rationale"]) < RATIONALE_MIN:
        return (
            f"Write why no investigation is needed ({NO_INVESTIGATION_CLAUSE}) in at least {RATIONALE_MIN} characters"
        )
    for key in ("troubleshooting", "correction", "result", "no_investigation_rationale"):
        if len(record[key]) > TEXT_MAX:
            return f"Keep each field of the service record under {TEXT_MAX} characters"
    return None


def branch_problem(
    branch: str, triggered: bool, candidates: list[str], case_id: str | None, rationale: str, not_known_reason: str
) -> str | None:
    """Why ``branch`` cannot be signed, in the decision order: a met trigger allows only escalation by trigger; a
    known issue names one of the matching open cases; escalation needs its reason. ``candidates``: the open cases that
    match; ``not_known_reason``: why none of them is the issue, when there are some and another branch is taken."""
    if branch not in BRANCHES:
        return "Choose how the complaint is resolved"
    if triggered and branch != ESCALATED_BY_TRIGGER:
        return "An escalation trigger is met: the complaint is escalated and an investigation opens; the other branches are closed"
    if not triggered and branch == ESCALATED_BY_TRIGGER:
        return "No escalation trigger is met: choose a known issue, service level, or escalate by choice"
    if branch == KNOWN_ISSUE and case_id not in candidates:
        return "Choose one of the open investigations that match this complaint"
    if branch in (ESCALATED_BY_TRIGGER, KNOWN_ISSUE, ESCALATED_BY_CHOICE) and len(rationale) < REASON_MIN:
        what = {
            ESCALATED_BY_TRIGGER: "why the investigation is needed",
            KNOWN_ISSUE: "why it is the same issue",
            ESCALATED_BY_CHOICE: "why you escalate it",
        }[branch]
        return f"Say {what} in at least {REASON_MIN} characters"
    if len(rationale) > TEXT_MAX:
        return f"Keep the rationale under {TEXT_MAX} characters"
    if branch in (SERVICE_LEVEL, ESCALATED_BY_CHOICE) and candidates and len(not_known_reason) < REASON_MIN:
        return (
            f"An open investigation matches: say in at least {REASON_MIN} characters why this is not that known issue"
        )
    return None


def answers_of(branch: str, triggers: list[dict], candidates: list[str], rationale: str, not_known_reason: str) -> dict:
    """Each question's answer and rationale, as signed. A question after the branch taken is not reached; one a met
    trigger refuses says so."""
    triggered = bool(triggers)
    facts = "; ".join(item["fact"] for item in triggers) if triggers else "No escalation trigger is met"
    answers = {
        "TRIGGER": {"answer": "YES" if triggered else "NO", "facts": facts, "rationale": rationale if triggered else ""}
    }
    if triggered:
        for key in ("KNOWN_ISSUE", "SERVICE_LEVEL", "CHOICE"):
            answers[key] = {"answer": "REFUSED", "rationale": "Closed: a trigger is met"}
        return answers
    if branch == KNOWN_ISSUE:
        answers["KNOWN_ISSUE"] = {"answer": "YES", "rationale": rationale}
        return answers
    answers["KNOWN_ISSUE"] = {
        "answer": "NO",
        "rationale": not_known_reason
        if candidates
        else "No open investigation holds the same product and problem code or lot",
    }
    if branch == SERVICE_LEVEL:
        answers["SERVICE_LEVEL"] = {"answer": "YES", "rationale": "See the service-level record"}
        return answers
    answers["SERVICE_LEVEL"] = {"answer": "NO", "rationale": "Not resolved at service level"}
    answers["CHOICE"] = {"answer": "YES", "rationale": rationale}
    return answers


def hands_on(seconds: float | None) -> int | None:
    """The hands-on time recorded: from opening the screen to signing, whole seconds, within a day."""
    if seconds is None or seconds < 0:
        return None
    return int(min(seconds, HANDS_ON_MAX))


def signature_meaning(ref: str, branch: str, markets: list[str], classified: bool) -> str:
    from backend.app.complaint_classification.rules import CODING_CRITERIA_VERSION
    from backend.app.reportability.markets import MARKET_LABELS

    parts = [
        f"I have dispositioned {ref} as: {BRANCH_LABELS[branch].lower()}, under the complaint disposition rules, "
        f"{version_words(RULES_VERSION)}"
    ]
    if classified:
        parts.append(
            f"confirmed its classification under the classification coding criteria, "
            f"{version_words(CODING_CRITERIA_VERSION)}"
        )
    if markets:
        named = ", ".join(MARKET_LABELS.get(market, market) for market in markets)
        parts.append(f"and conclude not reportable on the routine basis for {named}")
    return "; ".join(parts) + "."
