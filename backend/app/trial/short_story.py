"""The short story on SAMPLE-RV-11 (release 0.10.71, Release A, A4): four steps ending in the intake decision summary.

1. **Read the call:** the reporter's words, the phrases that make it a possible complaint marked, the known facts.
2. **Decide the route:** a complaint, with its linked service work; both get owners (the triage record and the service
   work, existing records).
3. **Name the open question:** the one thing needed to judge the consequence, asked of the hospital with an owner and a
   reply date (a request in the communications log). Until it is answered the consequence stays unknown.
4. **The intake decision summary:** the route, the fact it rests on, the open question, the service state, the market
   assessments still open with their deadlines, who acts next, and who prepared, may approve and approved.

Progress comes from what was saved on the record, never from the screen on show: a step is done when its record
exists. Steps 2 and 3 are the organization's records (a colleague's triage counts for everyone); steps 1 and 4 are the
person's own marks, kept per person on the trial's request (``profile["short_story"]``, keyed by the person and tied to
this SAMPLE-RV-11, so "Restart the sample story" starts them again), so they survive refresh and other devices.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint
from backend.app.trial.sample_data import FLAGSHIP, SAMPLE_SOURCE
from backend.app.workflow.approvals import PRACTICE_APPROVAL

PROFILE_KEY = "short_story"
STEPS = (
    ("read", "Read the call"),
    ("route", "Decide the route"),
    ("question", "Name the open question"),
    ("summary", "The intake decision summary"),
)
# The person's own marks; the other steps are records.
MARKS = ("read", "summary")
ROUTE = "Complaint, with linked service work"
ROUTE_FACT = "Malfunction recorded: yes. A claim that the device did not perform as intended is a complaint."
# The phrases of the call that make it a possible complaint (the hidden-complaint highlighting marks them), each with
# why. Starter wording, for the consultant to confirm.
PHRASES = (
    ("SpO2 read 4 to 6 points high", "A wrong reading: the device did not perform as intended."),
    ("two patients", "It was in use on patients."),
    ("No harm was reported", "No harm is known so far; whether the readings changed any treatment is not known."),
    ("sent for service", "The hospital asked for service: linked service work."),
)
SOURCE_QUOTE = "its SpO2 read 4 to 6 points high on two patients"
QUESTION = "Did any treatment decision rely on the high SpO2 readings (for example oxygen reduced or withheld)?"
QUESTION_WHY = (
    "It decides the consequence: a wrong reading that changed treatment could have caused serious harm, which changes "
    "each market's question. Until the hospital answers, the consequence stays unknown."
)
CONSEQUENCE_UNKNOWN = "Not known until the hospital answers"
# The flagship asks "in the US and India?": the complaint's own market and India, where the organization enabled it.
MARKETS = ("US", "IN")
WHY_OTHER_MARKET = "Assessed because your procedure asks every market where this device is sold to be assessed."


def flagship(data: Session, tenant_id) -> Complaint | None:
    return (
        data.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier == FLAGSHIP,
        )
        .first()
    )


def _marks(request, user_id: str, complaint_id) -> dict:
    """This person's marks on this SAMPLE-RV-11 (none after a restart, which gives it a new id)."""
    mine = ((request.profile or {}).get(PROFILE_KEY) or {}).get(str(user_id)) or {}
    return mine if mine.get("complaint_id") == str(complaint_id) else {}


def record_mark(request, user_id: str, complaint_id, step: str, now: datetime) -> None:
    """Keep the person's mark on the trial's request (the caller holds the row and commits)."""
    profile = dict(request.profile or {})
    story = dict(profile.get(PROFILE_KEY) or {})
    mine = _marks(request, user_id, complaint_id) or {"complaint_id": str(complaint_id)}
    story[str(user_id)] = {**mine, step: mine.get(step) or now.isoformat()}
    profile[PROFILE_KEY] = story
    request.profile = profile


def _question(data: Session, tenant_id, complaint):
    """The open question asked of the reporter's side: the latest request on the complaint with an owner and a reply
    date, made in this trial (the sample's own requests do not count)."""
    from backend.app.communications import rules
    from backend.app.db.models.guides_communications import CommunicationEntry

    return (
        data.query(CommunicationEntry)
        .filter(
            CommunicationEntry.tenant_id == tenant_id,
            CommunicationEntry.complaint_id == complaint.id,
            CommunicationEntry.direction == rules.SENT,
            CommunicationEntry.purpose == rules.REQUEST,
            CommunicationEntry.owner_id.is_not(None),
            CommunicationEntry.reply_due_on.is_not(None),
            CommunicationEntry.source_system.is_(None),
        )
        .order_by(CommunicationEntry.logged_at.desc())
        .first()
    )


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def steps_done(marks: dict, triage, complaint, question) -> list[tuple[str, str | None]]:
    """``[(key, when)]`` per step, ``when`` None while it is not done. A later step done means the earlier reading
    was done too (a colleague may have triaged it already)."""
    route = (
        _iso(triage.completed_at)
        if triage is not None and triage.completed_at is not None and complaint.service_owner
        else None
    )
    asked = _iso(question.logged_at) if question is not None else None
    read = marks.get("read") or route or asked
    summary = marks.get("summary") if route and asked else None
    return [("read", read), ("route", route), ("question", asked), ("summary", summary)]


def progress(data: Session, control_db: Session, tenant_id, user_id: str, request) -> dict:
    """The story's steps for this person, with the call, the route and the summary the screens show."""
    from backend.app.oversight import closure
    from backend.app.oversight.router import event_view
    from backend.app.reportability import markets

    complaint = flagship(data, tenant_id)
    if complaint is None or request is None:
        return {"available": False}
    found = closure.facts(data, tenant_id, complaint)
    triage, question = found["record"], _question(data, tenant_id, complaint)
    done = steps_done(_marks(request, user_id, complaint.id), triage, complaint, question)
    current = next((index for index, (_, when) in enumerate(done) if when is None), len(done))
    view = event_view(data, control_db, tenant_id, complaint, str(user_id))
    names = {person["id"]: person["name"] for person in view["people"]}
    event = view["event"]
    return {
        "available": True,
        "complaint": {"id": str(complaint.id), "ref": complaint.complaint_identifier},
        "steps": [
            {"key": key, "label": label, "done": when is not None, "done_at": when}
            for (key, label), (_, when) in zip(STEPS, done)
        ],
        "current": current,
        "started": any(when for _, when in done),
        "finished": current == len(STEPS),
        "call": {
            "words": complaint.description,
            "phrases": [
                {"text": text, "why": why}
                for text, why in PHRASES
                if text.lower() in (complaint.description or "").lower()
            ],
            "facts": _facts(event, complaint, view.get("service")),
        },
        "route": {
            "decision": ROUTE,
            "source_quote": SOURCE_QUOTE if SOURCE_QUOTE.lower() in (complaint.description or "").lower() else None,
            "source_fact": ROUTE_FACT,
            "owner_name": event["owner_name"],
            "recorded_by": names.get(triage.completed_by) if triage is not None and triage.completed_by else None,
            "immediate_action": (triage.immediate_action or triage.no_action_reason) if triage is not None else None,
        },
        "question": {
            "suggested": QUESTION,
            "why": QUESTION_WHY,
            "asked": {
                "id": str(question.id),
                "subject": question.subject,
                "owner_name": names.get(question.owner_id or ""),
                "due_on": question.reply_due_on.isoformat(),
                "status": question.status,
                "logged_by": names.get(question.logged_by or ""),
            }
            if question is not None
            else None,
            "consequence": CONSEQUENCE_UNKNOWN,
        },
        "service": view.get("service"),
        "markets": _markets(found, view, markets),
        "next": {
            "action": (view["summary"]["next_action"] or {}).get("label"),
            "who": (view.get("work") or {}).get("owner_name") or event["owner_name"],
        },
        "people": _people(view, triage, question, found, names, str(user_id)),
        "practice_label": view.get("practice_label"),
    }


def _facts(event: dict, complaint, service: dict | None) -> list[dict]:
    from backend.app.reportability import markets

    def yes(value) -> str:
        return "Not recorded" if value is None else ("Yes" if value else "No")

    return [
        {"label": "Product", "value": " · ".join(item for item in (event["product"], event["version"]) if item) or "—"},
        {"label": "Lot", "value": event["lot"] or "Not recorded"},
        {"label": "Market", "value": markets.MARKET_LABELS.get(event["market"] or "", event["country"] or "—")},
        {"label": "Awareness", "value": event["awareness_at"]},
        {"label": "Patient involved", "value": yes(complaint.patient_involved)},
        {"label": "Harm", "value": "Serious injury" if complaint.serious_injury else "None reported"},
        {"label": "Malfunction", "value": yes(complaint.malfunction)},
        {
            "label": "Service",
            "value": f"{service['status_label']} · {service['reference']}" if service else "None linked",
        },
    ]


def _markets(found: dict, view: dict, markets) -> list[dict]:
    """The US and India assessments, still open or signed, each with its deadline (a provisional one while it is
    not assessed); a market with no clock says why it is assessed at all."""
    own = view["event"]["market"]
    enabled = found["enabled"]
    due = [item for item in (view.get("work") or {}).get("due", []) if item["category"] in ("REPORTING", "OBLIGATION")]
    rows = []
    for market in MARKETS:
        if market != own and market not in enabled:
            continue
        versions = found["assessments"].get(market, [])
        signed = next((v for v in reversed(versions) if v.signed_at is not None and v.superseded_by is None), None)
        clock = next((item for item in due if item["market"] == market), None)
        rows.append(
            {
                "market": market,
                "label": markets.MARKET_LABELS.get(market, market),
                "state": "Signed: " + markets.CONCLUSION_LABELS.get(signed.conclusion, signed.conclusion).lower()
                if signed is not None
                else ("Being assessed" if versions else "Not assessed yet: still open"),
                "open": signed is None,
                "deadline": clock["due_label"] if clock else None,
                "deadline_title": clock["title"] if clock else None,
                "why": None if market == own else WHY_OTHER_MARKET,
            }
        )
    return rows


def _people(view: dict, triage, question, found: dict, names: dict, me: str) -> dict:
    """Who prepared the intake decision, who may approve its market assessments and who approved them (A6). Working
    alone in a trial the preparer approves their own practice work: it says so."""
    prepared = []
    for ref in (triage.completed_by if triage is not None else None, question.logged_by if question else None):
        if ref and names.get(ref) and names[ref] not in prepared:
            prepared.append(names[ref])
    signers = (view.get("signers") or {}).get("MARKETS") or {"people": []}
    may = [person["name"] for person in signers["people"]]
    approved = []
    for versions in found["assessments"].values():
        for version in versions:
            if version.signed_at is not None and names.get(version.signed_by or "") not in (None, *approved):
                approved.append(names[version.signed_by])
    alone = [person["id"] for person in signers["people"]] == [me]
    return {
        "prepared_by": prepared,
        "may_approve": may,
        "approved_by": approved,
        "practice": bool(view.get("practice_label")) and alone,
        "practice_note": PRACTICE_APPROVAL if view.get("practice_label") and alone else None,
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
