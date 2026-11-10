"""The Case's rules (release 0.10.93, B2), as plain functions: its states and the moves between them, the Case check
with versioned questions, the awareness of a Case, and its device identifiers (ID-1).

- **States** (``intake_events.status``): OPEN (to check), PENDING (waiting for the reporter), IN_REVIEW (QA review),
  CLOSED, ESCALATED (became or joined a Complaint), VOIDED (withdrawn: entered in error). ``TRANSITIONS`` is the whole
  list of allowed moves; ``intake.service.set_case_status`` is the only writer and refuses any other move.
- **The Case check** (``case-check-starter-2``): the same ten questions with the same stable IDs (Q1-Q10); every
  answer stores the version of the question it answers. Unknown is never No; Not applicable is never No (it needs its
  note on questions 1-6 and 8 to count as "not alleged"); an unanswered question is never Unknown: while any of
  questions 1-9 is unanswered there is no outcome (``UNANSWERED``). The outcome is a pure function of the answers, the
  request and the follow-up result, so a recalculation is deterministic; each one is kept in the version's history.
- **Outcomes v2**: the outcomes table of ``rules.outcome`` (unchanged), with "Service only" split by what was asked
  for (OD-5): service work asked for -> Service only; information or nothing -> Inquiry. "Not a complaint (no
  deficiency confirmed)" is a signed choice only when the answers give "confirm no deficiency" and the reporter's
  follow-up closed answered with no deficiency.
- **Awareness (H1)**: the earliest of the receipt and the first knowledge of someone acting for the manufacturer or
  counted by its procedure; "not acting for us" stays in the chronology only.
- **Device identifiers (ID-1, S-3)**: product, version, software version, hardware revision, firmware version, lot,
  serial number and UDI each carry a status
  (confirmed / unconfirmed) and a source; version, lot and serial may be "Not sure", never forced. Unconfirmed or Not
  sure identifiers are missing information (A3).

MDARIX never answers a question and never signs.
"""

from __future__ import annotations

from datetime import datetime

from backend.app.intake import rules

GUIDE_VERSION = "case-check-starter-2"
# Each question's own version: a change of a question's wording raises its number, so every answer says which wording
# it answered. All ten keep the wording of first-contact-starter-1.
QUESTION_VERSIONS = {question: 1 for question, _ in rules.QUESTIONS}

UNANSWERED = "UNANSWERED"
INQUIRY, NOT_A_COMPLAINT = "INQUIRY", "NOT_A_COMPLAINT"
OUTCOMES = (
    rules.COMPLAINT,
    rules.BOTH,
    rules.SERVICE_ONLY,
    INQUIRY,
    rules.PENDING,
    rules.PENDING_CONFIRM,
    NOT_A_COMPLAINT,
)
OUTCOME_LABELS = {
    rules.COMPLAINT: "Complaint",
    rules.BOTH: "Complaint and service",
    rules.SERVICE_ONLY: "Service only",
    INQUIRY: "Inquiry",
    rules.PENDING: "Pending",
    rules.PENDING_CONFIRM: "Pending: confirm no deficiency",
    NOT_A_COMPLAINT: "Not a complaint (no deficiency confirmed)",
    UNANSWERED: "Answer every question first",
}
INFORMATION_REQUESTS = ("INFORMATION", "NONE")
# The outcomes a second person reviews (OD-5: every time in B2).
REVIEWED_OUTCOMES = (rules.SERVICE_ONLY, INQUIRY, NOT_A_COMPLAINT)
# Outcomes no override reaches: only the answers give them.
ANSWER_ONLY = (rules.SERVICE_ONLY, INQUIRY, rules.PENDING_CONFIRM, NOT_A_COMPLAINT)

# ------------------------------------------------------------------------------------------------------------ states

OPEN, PENDING, IN_REVIEW, CLOSED, ESCALATED, VOIDED = "OPEN", "PENDING", "IN_REVIEW", "CLOSED", "ESCALATED", "VOIDED"
# S-2 (owner 10 Nov): waiting for engineering or technical support, beside PENDING (waiting for the reporter).
WAITING_INTERNAL = "WAITING_INTERNAL"
STATES = (OPEN, PENDING, WAITING_INTERNAL, IN_REVIEW, CLOSED, ESCALATED, VOIDED)
STATE_LABELS = {
    OPEN: "To check",
    PENDING: "Waiting for the reporter",
    WAITING_INTERNAL: "Waiting for internal team",
    IN_REVIEW: "QA review",
    CLOSED: "Closed",
    ESCALATED: "Complaint",
    VOIDED: "Withdrawn: entered in error",
}
# Every allowed move and what makes it (spec 3.2). Escalation is upward and always open; every way down is reviewed.
TRANSITIONS = {
    (OPEN, ESCALATED): "Signed a complaint, or complaint and service",
    (OPEN, PENDING): "Signed pending",
    (OPEN, IN_REVIEW): "Signed service only, inquiry or not a complaint",
    (OPEN, VOIDED): "Withdrawn: entered in error",
    (PENDING, OPEN): "Follow-up closed: re-answer and sign",
    (PENDING, ESCALATED): "Re-signed a complaint, or the follow-up stayed unresolved",
    (PENDING, IN_REVIEW): "Re-signed service only, inquiry or not a complaint",
    (PENDING, VOIDED): "Withdrawn: entered in error",
    (IN_REVIEW, CLOSED): "QA review agreed",
    (IN_REVIEW, ESCALATED): "QA review reclassified it as a complaint",
    (OPEN, WAITING_INTERNAL): "Sent to engineering or technical support",
    (PENDING, WAITING_INTERNAL): "Sent to engineering or technical support",
    (IN_REVIEW, WAITING_INTERNAL): "Sent to engineering or technical support before closing",
    (WAITING_INTERNAL, OPEN): "Internal team answered: re-answer and sign",
    (WAITING_INTERNAL, PENDING): "Internal team answered: the reporter is asked",
    (WAITING_INTERNAL, IN_REVIEW): "Internal team answered: back to the QA review",
    (WAITING_INTERNAL, ESCALATED): "Signed a complaint, or complaint and service",
    (WAITING_INTERNAL, VOIDED): "Withdrawn: entered in error",
    (CLOSED, OPEN): "Reopened: new information",
    (CLOSED, IN_REVIEW): "Reopened for review: a harm or fault word",
}


def transition_problem(current: str, target: str) -> str | None:
    """Why a Case may not move from ``current`` to ``target``; None when the move is allowed."""
    if target not in STATES:
        return f"Unknown case state {target}"
    if (current, target) in TRANSITIONS:
        return None
    if current == ESCALATED:
        return "This case is a complaint: its life continues on the complaint"
    if current == VOIDED:
        return "This case was withdrawn"
    return f'A case cannot go from "{STATE_LABELS.get(current, current)}" to "{STATE_LABELS[target]}"'


def close_problem(classification: str | None, resolution_summary: str | None) -> str | None:
    """S-2: a Case signed "service only" is closed only with a resolution summary (what was done for the customer)."""
    if classification == rules.SERVICE_ONLY and len(rules.clean(resolution_summary)) < rules.REASON_MIN:
        return f"Write the resolution summary (at least {rules.REASON_MIN} characters) before a service-only case is closed"
    return None


def state_after(classification: str) -> str:
    """The state a signed classification moves the Case to."""
    if classification in rules.COMPLAINT_OUTCOMES:
        return ESCALATED
    if classification in REVIEWED_OUTCOMES:
        return IN_REVIEW
    return PENDING


# ------------------------------------------------------------------------------------------------- the Case check


def clean_answers(raw: dict | None) -> dict:
    """The guide's questions, each with its answer (or none), its note and the version of the question it answers."""
    found = rules.clean_answers(raw)
    for question, item in found.items():
        item["question_version"] = QUESTION_VERSIONS[question]
    return found


def unanswered(answers: dict) -> list[str]:
    return [question for question in rules.QUESTION_IDS if not rules.answer_of(answers, question)]


def case_outcome(answers: dict, requested: str | None = None, unresolved: bool = False) -> str:
    """The suggestion: UNANSWERED while any of questions 1-9 is unanswered; else the outcomes table, with "service
    only" read as Inquiry when information or nothing was asked for (OD-5)."""
    if unanswered(answers):
        return UNANSWERED
    found = rules.outcome(answers, unresolved)
    if found == rules.SERVICE_ONLY and (requested or "NONE") in INFORMATION_REQUESTS:
        return INQUIRY
    return found


def follow_up_questions(answers: dict) -> list[str]:
    """What a follow-up asks the reporter: only questions answered Unknown or Not stated (never unanswered ones)."""
    return [
        question
        for question in rules.QUESTION_IDS
        if rules.answer_of(answers, question) in (rules.UNKNOWN, rules.NOT_STATED)
    ]


def classification_problem(
    suggestion: str,
    classification: str,
    override_reason: str,
    reason: str,
    *,
    no_deficiency_confirmed: bool = False,
) -> str | None:
    """What may be signed: the suggestion, or another outcome with a reason; never an answer-only outcome by
    override. Not a complaint needs "confirm no deficiency" from the answers and a follow-up that confirmed it."""
    if suggestion == UNANSWERED:
        return OUTCOME_LABELS[UNANSWERED]
    if classification not in OUTCOMES:
        return "Choose the classification"
    if classification == NOT_A_COMPLAINT:
        if suggestion != rules.PENDING_CONFIRM or not no_deficiency_confirmed:
            return (
                '"Not a complaint" is offered only when the answers give "confirm no deficiency" and the reporter\'s '
                "follow-up confirmed no deficiency"
            )
    elif classification in ANSWER_ONLY and classification != suggestion:
        return f'"{OUTCOME_LABELS[classification]}" is offered only when the answers give it'
    elif classification != suggestion and len(override_reason) < rules.REASON_MIN:
        return f"You override the suggestion: say in at least {rules.REASON_MIN} characters why"
    if classification in REVIEWED_OUTCOMES and len(reason) < rules.REASON_MIN:
        return f'"{OUTCOME_LABELS[classification]}" needs a written reason of at least {rules.REASON_MIN} characters'
    return None


# ------------------------------------------------------------------------- how it came in, patients (spec 4.2)

CHANNELS = {
    "PHONE": "Phone",
    "EMAIL": "E-mail",
    "WEB_FORM": "Web form",
    "FIELD_SERVICE": "Field service visit",
    "DISTRIBUTOR": "Distributor or agent",
    "RETURNED_PRODUCT": "Returned product",
    "LITERATURE": "Literature",
    "SOCIAL_MEDIA": "Social media",
    "REGULATOR": "Regulator notice",
    "OTHER": "Other",
    "SERVICE_RECORD_IMPORT": "Imported service record",  # set by the 0.10.93 data script, not offered on the form
}
# intake_events.patients (tr19 check patients_known).
PATIENTS = {"NONE": "None", "ONE": "One", "SEVERAL": "Several", "NOT_KNOWN": "Not known"}

# The six classifications the Case check shows (spec 4.4), in order; "Pending" reads the suggestion's own wording
# when the answers give "confirm no deficiency".
CHOICES = (rules.COMPLAINT, rules.BOTH, rules.SERVICE_ONLY, INQUIRY, rules.PENDING, NOT_A_COMPLAINT)


def choices(suggestion: str | None, *, no_deficiency_confirmed: bool = False) -> list[dict]:
    """Each classification with why it is disabled (None when it may be signed, given a reason where one is asked):
    the same rule the signature applies, so the screen never offers what the server refuses."""
    filled = "-" * rules.REASON_MIN
    found = []
    for code in CHOICES:
        if code == rules.PENDING and suggestion == rules.PENDING_CONFIRM:
            code = rules.PENDING_CONFIRM
        found.append(
            {
                "code": code,
                "label": OUTCOME_LABELS[code],
                "suggested": code == suggestion,
                "escalates": state_after(code) == ESCALATED,
                "disabled_reason": classification_problem(
                    suggestion or UNANSWERED, code, filled, filled, no_deficiency_confirmed=no_deficiency_confirmed
                ),
            }
        )
    return found


def recalculation(before: dict | None, after: dict, old: str | None, new: str, actor: str, at: datetime) -> dict:
    """One entry of a check version's history: which answers changed and the suggestion before and after."""
    changed = [
        question
        for question in rules.QUESTION_IDS
        if ((before or {}).get(question) or {}).get("answer") != (after.get(question) or {}).get("answer")
        or rules.note_of(before or {}, question) != rules.note_of(after, question)
    ]
    return {"at": at.isoformat(), "by": str(actor), "changed": changed, "before": old, "after": new}


# ----------------------------------------------------------------------------------- service issue category (S-1)

# Operational only: it sorts the service work and never decides whether a Case is a complaint or reportable.
ISSUE_CATEGORIES = {
    "MALFUNCTION": "Malfunction",
    "PERFORMANCE": "Performance",
    "SOFTWARE": "Software",
    "FIRMWARE": "Firmware",
    "HARDWARE": "Hardware",
    "CONNECTIVITY": "Connectivity",
    "INSTALLATION": "Installation",
    "CONFIGURATION": "Configuration",
    "USAGE_HELP": "Help with use",
    "MAINTENANCE": "Maintenance",
    "ACCESSORIES": "Accessories",
    "CONSUMABLES": "Consumables",
    "TRAINING": "Training",
    "DELIVERY": "Delivery",
    "DOCUMENTATION": "Documentation",
    "WARRANTY": "Warranty",
    "OTHER": "Other",
}


def issue_category(value: object) -> str | None:
    """A known category code, or None (never a guess)."""
    code = str(value or "").strip().upper()
    return code if code in ISSUE_CATEGORIES else None


# ------------------------------------------------------------------------------------------------------- awareness

COUNTED_BASES = ("ACTS_FOR_MANUFACTURER", "PROCEDURE_DEEMS")


def case_awareness(received_at: datetime, first_knowledge_at: datetime | None, basis: str | None) -> datetime:
    """H1: the earliest of the receipt and a first knowledge that counts (acting for us, or our procedure counts it)."""
    if first_knowledge_at is not None and basis in COUNTED_BASES:
        return min(rules.utc(received_at), rules.utc(first_knowledge_at))
    return rules.utc(received_at)


# --------------------------------------------------------------------------------------------- device identifiers

IDENTIFIERS = (
    "product",
    "version",
    "software_version",
    "hardware_revision",
    "firmware_version",
    "lot",
    "serial",
    "udi",
)
IDENTIFIER_LABELS = {
    "product": "Product",
    "version": "Version",
    "software_version": "Software version",
    "hardware_revision": "Hardware revision",
    "firmware_version": "Firmware version",
    "lot": "Lot",
    "serial": "Serial number",
    "udi": "UDI",
}
NOT_SURE_ALLOWED = ("version", "lot", "serial")
CONFIRMED, UNCONFIRMED = "CONFIRMED", "UNCONFIRMED"
SOURCES = ("CALLER", "LABEL_OR_PHOTO", "SHIPMENT_RECORD", "SERVICE_RECORD", "IMPORTED", "LOT")
SOURCE_LABELS = {
    "CALLER": "As told by the caller",
    "LABEL_OR_PHOTO": "Label or photo",
    "SHIPMENT_RECORD": "Shipment record",
    "SERVICE_RECORD": "Service record",
    "IMPORTED": "Imported",
    "LOT": "From the lot",  # PV-1 F2: Log a case takes the product from the lot
}


def clean_identifiers(raw: dict | None, given: dict) -> dict:
    """Each identifier's entry: Not sure (version, lot and serial only), its status and its source. ``given``: which
    identifiers have a value on the Case. A value told by the caller is unconfirmed until a record or label confirms
    it; a status without a source is unconfirmed."""
    found = {}
    for key in IDENTIFIERS:
        item = (raw or {}).get(key) or {}
        not_sure = bool(item.get("not_sure")) and key in NOT_SURE_ALLOWED and not given.get(key)
        if not given.get(key) and not not_sure:
            continue
        source = str(item.get("source") or "").strip().upper()
        source = source if source in SOURCES else None
        status = str(item.get("status") or "").strip().upper()
        status = CONFIRMED if status == CONFIRMED and source and not not_sure else UNCONFIRMED
        found[key] = {"not_sure": not_sure, "status": status, "source": source}
    return found


def missing_information(identifiers: dict, answers: dict | None = None) -> list[dict]:
    """What a Case still needs (A3): every Not sure or unconfirmed identifier, and every question answered Unknown or
    Not stated. Asked at follow-up; never blocks logging."""
    found = []
    for key in IDENTIFIERS:
        item = (identifiers or {}).get(key)
        if item is None:
            continue
        label = IDENTIFIER_LABELS[key]
        if item.get("not_sure"):
            found.append({"code": f"IDENTIFIER_NOT_SURE:{key}", "label": f"{label}: not sure"})
        elif item.get("status") != CONFIRMED:
            found.append({"code": f"IDENTIFIER_UNCONFIRMED:{key}", "label": f"{label}: unconfirmed"})
    for question in follow_up_questions(answers or {}):
        answer = rules.ANSWER_LABELS[rules.answer_of(answers, question)].lower()
        found.append({"code": f"QUESTION:{question}", "label": f"Question {question[1:]}: {answer}"})
    return found
