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

The rules (``disposition-starter-2`` since B7: the ticket rule, No fault found, the reasons list, the known-behaviour
answer) and the classification's coding criteria (``coding-starter-1``) are starter
text (T-B6) and documents a signer acknowledges before signing (T-G40P). MDARIX never answers, never signs and never
submits a report. Codes are the MVP's (G36), so the MVP swaps sources without renaming anything stored.
"""

from __future__ import annotations

from backend.app.db.models.complaint_disposition import ATTRIBUTIONS
from backend.app.standards import version_words

RULES_VERSION = "disposition-starter-2"
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
CORRECTIONS = ("PART_REPLACED", "SETTING_CORRECTED", "USER_INSTRUCTED", "NO_FAULT_FOUND", "OTHER")
CORRECTION_LABELS = {
    "PART_REPLACED": "Part replaced",
    "SETTING_CORRECTED": "Setting corrected",
    "USER_INSTRUCTED": "User instructed",
    "NO_FAULT_FOUND": "No fault found",
    "OTHER": "Other (describe it)",
}
# B7-D3: a service ticket is needed only when service work was done on the device.
TICKET_CORRECTIONS = ("PART_REPLACED", "SETTING_CORRECTED")
# The correction proposed from the Case's "What they asked for" (a person changes it); anything else: user instructed.
DEFAULT_CORRECTIONS = {
    "REPAIR": "PART_REPLACED",
    "CALIBRATION": "SETTING_CORRECTED",
    "MAINTENANCE": "SETTING_CORRECTED",
    "INSTALLATION": "SETTING_CORRECTED",
}
# B7-D2: why no investigation is needed (ISO 13485:2016 clause 8.2.2), a choice; free text only for Other.
OTHER_REASON, WITHDREW = "OTHER", "REPORTER_WITHDREW"
NO_INVESTIGATION_REASONS = {
    "USE_RELATED_INSTRUCTED": "Single event, use-related, resolved by instruction",
    "KNOWN_BEHAVIOUR_IFU": "Known behaviour described in the instructions for use",
    "SINGLE_RANDOM_FAILURE": "Single random failure, no trend",
    "NO_FAULT_FOUND": "No fault found after evaluation",
    WITHDREW: "Reporter withdrew, no deficiency confirmed",
    OTHER_REASON: "Other (describe it)",
}
DEVICE_RETURNED = {
    "EVALUATED": "Evaluated",
    "NOT_RETURNED": "Not returned after the set attempts",
    "NOT_NEEDED": "Not needed",
}
# B7-D5: how the customer was told, or that it was not possible (anonymous, unreachable after the set attempts).
NOT_POSSIBLE = "NOT_POSSIBLE"
TOLD_HOW = {
    "PHONE": "Phone",
    "EMAIL": "E-mail",
    "LETTER": "Letter",
    "DISTRIBUTOR": "Through the distributor",
    "IN_PERSON": "In person",
    NOT_POSSIBLE: "Not possible",
}
KNOWN_BEHAVIOUR_MIN = 3
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
    "Answer in order. An escalation trigger met (safety, injury, a reportable outcome, a recurrence no open investigation "
    "covers, a new failure mode) escalates the complaint: an investigation opens at once and no other branch is allowed.",
    "A known issue is an open investigation whose scope holds a complaint with the same product and problem code, or the same "
    "lot. Link the complaint to it with your reason; no second investigation is opened.",
    "Resolved at service level: record the troubleshooting, the discrete correction, its result, and the service ticket "
    "when a part was replaced or a setting corrected; choose why no investigation is needed (ISO 13485:2016 clause "
    "8.2.2), with your words for Other; and the root-cause attribution. No fault found keeps it a complaint and its "
    "cause is undetermined, with a reason.",
    "A new failure mode may be answered as known behaviour only with the reference of the instructions for use or the "
    "risk file that documents it; every other trigger escalates.",
    "Otherwise escalate by choice, with your reason: an investigation opens.",
    "The disposition never replaces the reportability assessment: a complaint on the watch is still assessed for each "
    "market.",
    "A signed disposition is never edited. A change is a new version with its reason; the earlier one stays visible.",
)


def routine_unrecorded(record: dict) -> list[dict]:
    """The facts ``ROUTINE_BASIS`` rests on that the complaint leaves unrecorded (0.10.87, DEV-09): whether the device
    malfunctioned, and the patient's outcome (no patient involved, or no death and no serious injury). A complaint off
    the watch may still leave them blank (an import without those columns); the routine path's "not reportable" is
    then not offered, because Unknown is never No."""
    found = []
    if record.get("malfunction") is None:
        found.append({"code": "MALFUNCTION", "label": "whether the device malfunctioned"})
    if record.get("patient_involved") is not False and (
        record.get("death") is None or record.get("serious_injury") is None
    ):
        found.append({"code": "PATIENT", "label": "whether a patient was involved, died or was seriously injured"})
    return found


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
        "no_investigation_reason": _reason_code(raw),
        "no_investigation_rationale": _rationale(raw),
        "device_returned": collapse(raw.get("device_returned")).upper() or None,
        "clause": NO_INVESTIGATION_CLAUSE,
    }


def _reason_code(raw: dict) -> str:
    # A client from before B7 sends the rationale only: it is the Other reason, in the signer's words.
    code = collapse(raw.get("no_investigation_reason")).upper()
    return code or (OTHER_REASON if collapse(raw.get("no_investigation_rationale")) else "")


def _rationale(raw: dict) -> str:
    text = collapse(raw.get("no_investigation_rationale"))
    code = _reason_code(raw)
    return text or (NO_INVESTIGATION_REASONS.get(code, "") if code != OTHER_REASON else "")


def default_correction(requested: str | None) -> str:
    return DEFAULT_CORRECTIONS.get((requested or "").strip().upper(), "USER_INSTRUCTED")


def service_record_problem(record: dict, on_watch: bool = False) -> str | None:
    """Why a service-level record is not complete. The ticket is needed only for a part replaced or a setting
    corrected (B7-D3); why no investigation is needed is a reason from the list, with words only for Other (B7-D2). The
    withdrawal reason is not open on the reportability watch."""
    if len(record["troubleshooting"]) < REASON_MIN:
        return f"Describe the troubleshooting done in at least {REASON_MIN} characters"
    if record["correction_type"] not in CORRECTIONS:
        return "Choose the correction: part replaced, setting corrected, user instructed or other"
    if len(record["correction"]) < REASON_MIN:
        return f"Describe the correction in at least {REASON_MIN} characters"
    if len(record["result"]) < 5:
        return "Say what the correction achieved (for example: alarm cleared, device in use)"
    ticket = record["service_ticket"]
    if len(ticket) > TICKET_MAX or (not ticket and record["correction_type"] in TICKET_CORRECTIONS):
        return f"Give the service ticket reference (at most {TICKET_MAX} characters): service work was done"
    reason = record.get("no_investigation_reason") or OTHER_REASON
    if reason not in NO_INVESTIGATION_REASONS:
        return f"Choose why no investigation is needed ({NO_INVESTIGATION_CLAUSE})"
    if reason == WITHDREW and on_watch:
        return "On the reportability watch a withdrawal does not settle it: choose another reason or escalate"
    if reason == OTHER_REASON and len(record["no_investigation_rationale"]) < RATIONALE_MIN:
        return (
            f"Write why no investigation is needed ({NO_INVESTIGATION_CLAUSE}) in at least {RATIONALE_MIN} characters"
        )
    if record.get("device_returned") and record["device_returned"] not in DEVICE_RETURNED:
        return "Choose whether the device was returned: evaluated, not returned after the set attempts, or not needed"
    for key in ("troubleshooting", "correction", "result", "no_investigation_rationale"):
        if len(record[key]) > TEXT_MAX:
            return f"Keep each field of the service record under {TEXT_MAX} characters"
    return None


def no_fault_problem(record: dict | None, attribution: str | None) -> str | None:
    """No fault found never undoes the complaint and never names a cause it did not find (RT-10)."""
    if record and record.get("correction_type") == "NO_FAULT_FOUND" and attribution != UNDETERMINED:
        return "No fault found: the cause is undetermined; say why"
    return None


def customer_told_problem(told: dict | None, connect: bool = False) -> str | None:
    """B7-D5: how and when the customer was told, or "not possible" with the reason. In MDARIX Connect the letter's ID
    in the QMS is enough."""
    told = told or {}
    how = collapse(told.get("how")).upper()
    if connect and collapse(told.get("qms_letter_id")) and how != NOT_POSSIBLE:
        return None
    if how not in TOLD_HOW:
        return "Record how the customer was told, or that it was not possible and why"
    if how == NOT_POSSIBLE and len(collapse(told.get("reason"))) < REASON_MIN:
        return f"Say in at least {REASON_MIN} characters why the customer could not be told (anonymous, unreachable)"
    if len(collapse(told.get("note"))) > TEXT_MAX or len(collapse(told.get("qms_letter_id"))) > TICKET_MAX:
        return f"Keep the note under {TEXT_MAX} characters and the letter ID under {TICKET_MAX}"
    return None


def answered_triggers(met: list[dict], known_behaviour_ref: str | None) -> list[dict]:
    """B7-D4: a new failure mode answered "known behaviour, documented in <reference>" no longer escalates; every other
    trigger stays."""
    if len(collapse(known_behaviour_ref)) < KNOWN_BEHAVIOUR_MIN:
        return met
    return [item for item in met if item["code"] != "NEW_FAILURE_MODE"]


def combined_offer(route_open: bool, blocked: list[dict], routine_markets: bool) -> dict:
    """Whether "Resolve and close" is offered in full: the route is open (the routine path, or on the watch with every
    relevant market signed not reportable, B7-D7) and every closure check passes except what the screen settles (the
    decision, customer told, and the markets when the routine basis concludes them). Otherwise only "Resolve" is
    offered, with what still blocks closing. Signing over an open item is never offered here."""
    settles = {"DECISION", "CUSTOMER_TOLD", *(("MARKETS",) if routine_markets else ())}
    still = [item for item in blocked if item["code"] not in settles]
    return {"full": route_open and not still, "blocking": [item["label"] for item in still]}


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
