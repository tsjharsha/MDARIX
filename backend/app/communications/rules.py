"""The external communications log's rules (T-G30, MVP G30), as plain functions: what an entry may be, how unanswered
attempts move a request to the party's second contact and then to "unresolved after attempts", when a request is
overdue, and when an entry counts as done in MDARIX (S4).

MDARIX never sends anything to an external contact: people send from their own mail or phone and record it here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

REPORTER, DISTRIBUTOR, HOSPITAL, SERVICE_PARTNER = "REPORTER", "DISTRIBUTOR", "HOSPITAL", "SERVICE_PARTNER"
PARTY_LABELS = {
    REPORTER: "Reporter",
    DISTRIBUTOR: "Distributor",
    HOSPITAL: "Hospital",
    SERVICE_PARTNER: "Service partner",
}
SENT, RECEIVED = "SENT", "RECEIVED"
DIRECTION_LABELS = {SENT: "Sent", RECEIVED: "Received"}
REQUEST, UPDATE, RESPONSE = "INFORMATION_REQUEST", "UPDATE", "RESPONSE"
PURPOSE_LABELS = {REQUEST: "Information request", UPDATE: "Update", RESPONSE: "Response"}
OPEN, ANSWERED, UNRESOLVED, CLOSED = "OPEN", "ANSWERED", "UNRESOLVED", "CLOSED"
STATUS_LABELS = {
    OPEN: "Open",
    ANSWERED: "Answered",
    UNRESOLVED: "Unresolved after attempts",
    CLOSED: "Closed",
}
PRIMARY, SECOND = "PRIMARY", "SECOND"
CHANNELS = {
    "EMAIL": "E-mail",
    "PHONE": "Phone",
    "LETTER": "Letter",
    "PORTAL": "Customer portal",
    "IN_PERSON": "In person",
    "OTHER": "Other",
}
# An attempt that reached nobody counts as unanswered; "sent, waiting" counts once a later attempt is made.
WAITING = "SENT"
ATTEMPT_OUTCOMES = {
    WAITING: "Sent, waiting for a reply",
    "NO_ANSWER": "No answer",
    "MESSAGE_LEFT": "Message left, no answer",
    "BOUNCED": "Bounced or wrong address",
}
ATTEMPTS_DEFAULT, ATTEMPTS_MIN, ATTEMPTS_MAX = 3, 1, 10
SUBJECT_MAX, NOTE_MAX, EVIDENCE_MAX, EVIDENCE_ITEM_MAX = 400, 4000, 10, 200
REASON_MIN = 10
NEVER_SENDS = (
    "MDARIX sends nothing to your contacts: send from your own mail or phone, then record it here at once. Formal "
    "responses to the complainant and field safety notices stay records of your QMS: link them by their ID."
)


def unanswered(attempts: list[dict], contact: str) -> int:
    """The attempts to ``contact`` that got no answer: every one reaching nobody, and a "sent, waiting" one once a
    later attempt was made."""
    count = 0
    for index, attempt in enumerate(attempts):
        if attempt.get("contact") != contact:
            continue
        latest = index == len(attempts) - 1
        if attempt.get("outcome") != WAITING or not latest:
            count += 1
    return count


def after_attempts(attempts: list[dict], contact: str, has_second: bool, limit: int) -> tuple[str, str]:
    """``(status, contact)`` after the attempts so far: still open with the same contact; moved to the party's second
    contact once ``limit`` attempts to the primary went unanswered (where a second contact is recorded); then
    unresolved after attempts once ``limit`` to the second (or to the primary, when there is none) did."""
    if unanswered(attempts, contact) < limit:
        return OPEN, contact
    if contact == PRIMARY and has_second:
        return OPEN, SECOND
    return UNRESOLVED, contact


def overdue(status: str, reply_due_on: date | None, today: date) -> bool:
    return status == OPEN and reply_due_on is not None and reply_due_on < today


def working_hour_after(moment: datetime) -> datetime:
    """One working hour after ``moment``. shortcut: working time is Monday to Friday, all day, in UTC; the
    organization's own calendar and hours come with G25's reminders."""
    moment = moment.astimezone(timezone.utc)
    if moment.weekday() >= 5:
        moment = datetime.combine(
            moment.date() + timedelta(days=7 - moment.weekday()), datetime.min.time(), tzinfo=timezone.utc
        )
    end = moment + timedelta(hours=1)
    if end.weekday() >= 5:
        end += timedelta(days=7 - end.weekday())
    return end


def in_mdarix(occurred_at: datetime | None, logged_at: datetime | None) -> bool | None:
    """S4: done in MDARIX when logged before the message was sent or received, or within one working hour of it."""
    if occurred_at is None or logged_at is None:
        return None
    return logged_at <= working_hour_after(occurred_at)


def entry_problem(direction: str, purpose: str, channel: str, subject: str, owner: str | None, due: date | None):
    """Why an entry cannot be recorded, or None. A request sent needs an owner and a reply due date."""
    if direction not in DIRECTION_LABELS:
        return "Say whether it was sent or received"
    if purpose not in PURPOSE_LABELS:
        return "Choose its purpose: an information request, an update or a response"
    if channel not in CHANNELS:
        return "Choose how it was sent or received"
    if len(subject) < 5:
        return "Say in a few words what was asked or said"
    if len(subject) > SUBJECT_MAX:
        return f"Keep the summary to {SUBJECT_MAX} characters"
    if direction == SENT and purpose == REQUEST and (not owner or due is None):
        return "A request needs its owner and the date a reply is due"
    if direction == RECEIVED and purpose == REQUEST:
        return "A message you received is a response or an update; record your own question as sent"
    return None


def status_for(direction: str, purpose: str) -> str:
    """A request sent is open until answered; anything else is a record, closed when made."""
    return OPEN if direction == SENT and purpose == REQUEST else CLOSED
