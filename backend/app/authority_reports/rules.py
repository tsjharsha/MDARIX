"""The obligation lifecycle's rules (T-G2b, MVP G2b), as plain functions: the states and what each allows, who may
approve a snapshot, the difference review, and the follow-up after a submission (G2b's decision table, rows 1-4).

MDARIX never submits: a person submits through the authority's route and records here what was done.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

DRAFT, CORRECTION, APPROVED = "DRAFT", "CORRECTION_REQUIRED", "APPROVED"
PENDING, ACCEPTED, NO_ACK = "SUBMITTED_PENDING", "ACCEPTED", "SUBMITTED_NO_ACK"
FOLLOW_UP, COMPLETE = "FOLLOW_UP_DUE", "COMPLETE"
NOT_STARTED, NO_WORKSHEET = "NOT_STARTED", "NO_WORKSHEET"
STATE_LABELS = {
    NOT_STARTED: "Not started",
    NO_WORKSHEET: "Worksheet comes later",
    DRAFT: "Draft",
    CORRECTION: "Draft: correction required",
    APPROVED: "Approved snapshot",
    PENDING: "Submitted, acceptance pending",
    ACCEPTED: "Accepted",
    NO_ACK: "Submitted, no acknowledgement expected",
    FOLLOW_UP: "Follow-up due",
    COMPLETE: "Complete",
}
# The order the screen shows the steps in.
STEPS = (DRAFT, APPROVED, PENDING, ACCEPTED, COMPLETE)
EDITABLE = (DRAFT, CORRECTION)
SUBMITTED = (PENDING, ACCEPTED, NO_ACK, FOLLOW_UP, COMPLETE)
# A request for information comes after a valid submission (G2b).
VALID_SUBMISSION = (ACCEPTED, NO_ACK, FOLLOW_UP, COMPLETE)
MET = (ACCEPTED, NO_ACK, FOLLOW_UP, COMPLETE)
MATERIAL, NON_MATERIAL = "MATERIAL", "NON_MATERIAL"
REASON_MIN = 10
NOTE_MAX = 4000
FILE_MAX = 2 * 1024 * 1024
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})
NEVER_SUBMITS = (
    "Prepared by MDARIX, submitted by you: MDARIX never submits a report. You enter it in the authority's route."
)

# G2b's route settings, the defaults: W the wait, E the earliest follow-up, M the resubmission margin.
WAIT = {"EMDR": timedelta(hours=1)}
EARLIEST = {"EMDR": timedelta(minutes=15)}
WAIT_DEFAULT, EARLIEST_DEFAULT, MARGIN = timedelta(days=1), timedelta(hours=1), timedelta(hours=4)


def next_step(state: str, has_pending_snapshot: bool = False) -> str:
    if state == NOT_STARTED:
        return "Start the worksheet"
    if state == NO_WORKSHEET:
        return "Record the filing on the market's signed conclusion"
    if state in EDITABLE:
        return (
            "A second person approves the snapshot"
            if has_pending_snapshot
            else "Check the fields, then ask for approval"
        )
    return {
        APPROVED: "Submit in the authority's route, then record the submission",
        PENDING: "Record the receipt and the acceptance when they arrive",
        ACCEPTED: "Complete it, or record a follow-up or a request for information",
        NO_ACK: "Complete it, or record a follow-up",
        FOLLOW_UP: "Complete the follow-up",
        COMPLETE: "Nothing: the obligation is complete",
    }[state]


def approver_problem(approver: str, role: str | None, preparers: set[str], signer: str | None) -> str | None:
    """Why this person may not approve the snapshot (G2b, G33), or None: never the preparer, never the signer of the
    market conclusion behind it, never an administrator."""
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        return "An administrator cannot approve a report snapshot"
    if approver in preparers:
        return "You prepared this worksheet: a second person must approve the snapshot"
    if signer and approver == signer:
        return "You signed the market conclusion behind this report: a second person must approve the snapshot"
    return None


def difference_problem(differences: list[dict], no_differences: bool) -> str | None:
    """The difference review at submission (G2b): say there are none, or classify each; a material difference needs
    the approver's re-approval before submission; a non-material one needs its reason."""
    if no_differences and differences:
        return "Either say the submitted content matches the approved snapshot, or list the differences"
    if not no_differences and not differences:
        return "Say whether the submitted content matches the approved snapshot"
    for item in differences:
        if item.get("classification") not in (MATERIAL, NON_MATERIAL):
            return "Classify each difference as material or not material"
        if item["classification"] == MATERIAL:
            return (
                "A material difference needs the approver's re-approval before submission: reopen the draft, correct "
                "it and ask for approval again"
            )
        if len(" ".join(str(item.get("reason") or "").split())) < REASON_MIN:
            return f"Give the reason for each difference that is not material, in at least {REASON_MIN} characters"
    return None


def deadline_end(due_on: date) -> datetime:
    # shortcut: the legal latest date ends at midnight UTC; the counting rule's own time zone (5.1a) comes with G25.
    return datetime.combine(due_on + timedelta(days=1), time.min, tzinfo=timezone.utc)


def follow_up(submitted_at: datetime, due_on: date | None, route: str) -> dict:
    """G2b's decision table, rows 1-4: when to check for acceptance after a submission at S, with D the end of the
    legal latest date. Row 1 ample time; 2 the wait would end inside the margin; 3 inside the margin with at least
    twice E left; 4 less than twice E left, or past D: act at once."""
    wait, earliest = WAIT.get(route, WAIT_DEFAULT), EARLIEST.get(route, EARLIEST_DEFAULT)
    if due_on is None:
        return {"row": 1, "at": (submitted_at + wait).isoformat(), "late": False}
    end = deadline_end(due_on)
    late = submitted_at > end
    if not late and submitted_at + wait <= end - MARGIN:
        row, at = 1, submitted_at + wait
    elif not late and submitted_at < end - MARGIN:
        row, at = 2, max(end - MARGIN, submitted_at + earliest)
    elif not late and submitted_at + 2 * earliest <= end:
        row, at = 3, submitted_at + earliest
    else:
        row, at = 4, submitted_at
    return {"row": row, "at": at.isoformat(), "late": late}
