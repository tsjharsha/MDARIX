"""One story, from the first contact to the submission (release 0.10.82, round D1; Part 1 in 0.10.93, B2 spec 4.8).

Getting started tells one complaint's story in ten steps, first on the sample (SAMPLE-RV-11 and its call
SAMPLE-CASE-11), then on the trial's own most urgent imported complaint: the most serious harm, then the shortest
clock. Each step opens the real screen with the record in place, and each tick is read from the saved record, never
from the screen on show (OD-2):

1. review the case: all nine questions answered and saved on the story's Case check (a person saved them: the
   sample's pre-filled answers do not count);
2. classify service or complaint: that Case check signed, and the Case escalated to (or attached to) a complaint;
3. triage: the triage record is complete;
4. the decision tree: an assessment of the complaint's own market is saved (a draft or signed);
5. sign the conclusion: that market's conclusion is signed;
6. prepare the report: the authority report exists and the person opened it (skipped when not reportable);
7. complete and approve: the report is approved (every field filled, then a second person);
8. record the submission: the submission is recorded (MDARIX never submits);
9. records: the person opened Records once the submission (or the "not reportable" conclusion) is recorded;
10. trends: the person opened Trends.

Later work on the complaint (a triage, an assessment, a report) means steps 1 and 2 were taken, so progress never goes
backwards on a trial running before 0.10.93. The story's Case: on the sample, the Case that became or joined RV-11, else
SAMPLE-CASE-11; on your data, the Case linked to the complaint, else steps 1 and 2 are "Classified in your QMS". Branches
at step 2: a Case signed service only, inquiry or not a complaint skips steps 3 to 8 ("Not needed: not a complaint")
and adds the QA review; a pending Case keeps step 2 open, waiting for the reporter.

The story is the team's, as the record is (0.10.84, M6): every colleague reads the same step. The marks (steps 6, 9
and 10) are kept on the trial's request (``profile["one_story"]``, keyed by the person who opened the step and the run,
tied to the complaint's id so "Restart the sample story" starts them again), and a step any colleague opened counts for
everyone, from the earliest time it was opened. The mark "call" of earlier releases is ignored (steps 1 and 2 read the
records). A step the complaint cannot take yet because the import lacks a fact says so (``needs``); the ask itself
stays on the step's own screen (the complaint page, 0.10.81).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint

PROFILE_KEY = "one_story"
RUNS = ("sample", "yours")
STEPS = (
    # Part 1's ten steps (B2 spec 4.8), shown as a vertical list on Getting started.
    ("case", "Review the case"),
    ("classify", "Classify service or complaint"),
    ("triage", "Triage"),
    ("tree", "Assess reportability"),
    ("reportable", "Sign the conclusion"),
    ("form", "Prepare the report"),
    ("approval", "Complete and approve"),
    ("submit", "Record the submission"),
    ("records", "Review records"),
    ("trends", "Explore trends"),
)
MARKS = ("form", "records", "trends")
MARK_STEP = {key: index for index, (key, _) in enumerate(STEPS) if key in MARKS}
# The report's status path (authority_reports/rules.py STAGES), in order: where steps 6 to 8 are done.
REPORT_PATH = ("CREATED", "COMPLETE", "APPROVAL", "APPROVED", "SUBMITTED", "ACKNOWLEDGED")


def _imported(data: Session, tenant_id) -> list[Complaint]:
    from backend.app.trial.imports import UPLOAD_SOURCE

    return (
        data.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.source_system == UPLOAD_SOURCE).all()
    )


def harm_rank(complaint) -> int:
    """How serious the reported harm is: a death, a serious injury, a malfunction or patient involvement, nothing."""
    if complaint.death:
        return 3
    if complaint.serious_injury:
        return 2
    return 1 if (complaint.malfunction or complaint.patient_involved) else 0


def reported_harm(complaint) -> str | None:
    """The harm the record states: DEATH, SERIOUS_INJURY, NONE (both stated as no), or None when the record does not
    say. Getting started shows None as not recorded, never as "None reported" (0.10.87)."""
    if complaint.death:
        return "DEATH"
    if complaint.serious_injury:
        return "SERIOUS_INJURY"
    return "NONE" if complaint.death is False and complaint.serious_injury is False else None


def most_urgent(data: Session, control_db: Session, tenant_id) -> Complaint | None:
    """The trial's own most urgent imported complaint: the most serious harm, then the shortest clock, then the
    reference (so the choice holds while nothing changes)."""
    from backend.app.oversight.router import complaint_work

    rows = _imported(data, tenant_id)
    if not rows:
        return None
    top = max(harm_rank(row) for row in rows)
    serious = [row for row in rows if harm_rank(row) == top]
    work = complaint_work(data, control_db, tenant_id, serious)

    def clock(row) -> str:
        due = work.get(str(row.id), {}).get("due") or []
        return due[0]["due_at"] if due else "9999"

    return min(serious, key=lambda row: (clock(row), row.complaint_identifier or ""))


def under_way(request, run: str, rows: list):
    """The imported complaint the team's walkthrough is under way on (0.10.88): the one the latest marks name, until
    its last step (Trends) is marked. Followed while no complaint reports a more serious harm, so concluding it (which
    closes its clock) never sends the walkthrough back to another complaint in the middle of its steps."""
    latest = None
    for person in ((request.profile or {}).get(PROFILE_KEY) or {}).values():
        mine = (person or {}).get(run) or {}
        stamp = max((mine[step] for step in MARKS if mine.get(step)), default=None)
        if stamp and (latest is None or stamp > latest[0]):
            latest = (stamp, mine)
    if latest is None or latest[1].get("trends"):
        return None
    kept = next((row for row in rows if str(row.id) == latest[1].get("complaint_id")), None)
    if kept is None or harm_rank(kept) < max(harm_rank(row) for row in rows):
        return None
    return kept


def subject(data: Session, control_db: Session, tenant_id, run: str, request=None) -> Complaint | None:
    from backend.app.trial.short_story import flagship

    if run == "sample":
        return flagship(data, tenant_id)
    kept = under_way(request, run, _imported(data, tenant_id)) if request is not None else None
    return kept or most_urgent(data, control_db, tenant_id)


def _slot(person: dict, run: str, complaint_id) -> dict:
    """A person's marks on one complaint of the run: the current one's, or an earlier one's, kept when the story
    moved on (0.10.88: a story back on it keeps its ticks)."""
    mine = (person or {}).get(run) or {}
    if mine.get("complaint_id") == str(complaint_id):
        return mine
    return ((person or {}).get(f"{run}_earlier") or {}).get(str(complaint_id)) or {}


def _marks(request, user_id: str, run: str, complaint_id) -> dict:
    """One person's own marks on the run's complaint."""
    return _slot(((request.profile or {}).get(PROFILE_KEY) or {}).get(str(user_id)) or {}, run, complaint_id)


def team_marks(request, run: str, complaint_id) -> dict:
    """Every colleague's marks on the run's complaint, merged: a step anyone opened, at the earliest time it was."""
    found: dict = {}
    for person in ((request.profile or {}).get(PROFILE_KEY) or {}).values():
        mine = _slot(person, run, complaint_id)
        for step in MARKS:
            if mine.get(step) and (not found.get(step) or mine[step] < found[step]):
                found[step] = mine[step]
    return found


def record_mark(request, user_id: str, run: str, complaint_id, step: str, now: datetime) -> None:
    """Keep the person's mark on the trial's request (the caller holds the row and commits)."""
    profile = dict(request.profile or {})
    story = dict(profile.get(PROFILE_KEY) or {})
    person = dict(story.get(str(user_id)) or {})
    mine = _slot(person, run, complaint_id) or {"complaint_id": str(complaint_id)}
    earlier = dict(person.get(f"{run}_earlier") or {})
    current = person.get(run) or {}
    if current.get("complaint_id") and current["complaint_id"] != str(complaint_id):
        earlier[current["complaint_id"]] = current
    earlier.pop(str(complaint_id), None)
    if earlier:
        person[f"{run}_earlier"] = earlier
    person[run] = {**mine, step: mine.get(step) or now.isoformat()}
    story[str(user_id)] = person
    profile[PROFILE_KEY] = story
    request.profile = profile


NOT_NEEDED = {
    "case": "Classified in your QMS",
    "complaint": "Not needed: not a complaint",
    "triage": "Not needed: not flagged for triage",
    "reportable": "Not needed: not reportable",
}
WAITING = "Waiting for the reporter"
# The branch card shown when the Case was signed service only, inquiry or not a complaint (spec 4.8).
QA_REVIEW = {
    "key": "qa_review",
    "label": "QA review",
    "who": "Quality Leader",
    "evidence": "The signed review",
    "why": "A service-only case skips reporting. A second person reviews it: hidden complaints are the most cited "
    "intake failure.",
}


def not_a_complaint(case: dict | None) -> bool:
    from backend.app.intake import case_rules

    return case is not None and case.get("classification") in case_rules.REVIEWED_OUTCOMES


def steps_done(
    marks: dict,
    triaged: bool,
    versions: list,
    report_stage: str | None,
    *,
    triage_needed: bool = True,
    case: dict | None = None,
) -> list:
    """Per step: True (done), False, or "skip" (not needed: steps 1-2 of a complaint with no Case, steps 3-8 of a Case
    signed not a complaint, the triage of a complaint not flagged for it, the report's steps after a signed "not
    reportable" conclusion). ``case``: the story's Case, ``{"answered", "classification", "escalated"}`` (None: no
    Case). Pure, so its rules are tested apart from the records."""
    from backend.app.reportability.markets import NOT_REPORTABLE

    signed = next((v for v in reversed(versions) if v.signed_at is not None and v.superseded_by is None), None)
    not_reportable = signed is not None and signed.conclusion == NOT_REPORTABLE
    at = REPORT_PATH.index(report_stage) if report_stage in REPORT_PATH else -1
    # A step the record shows done says the steps before it were taken (0.10.85): any later work on the complaint means
    # its case was reviewed and classified; a report past "Created" means its form was opened.
    later = triaged or bool(versions) or at >= 0
    if case is None:
        first = ["skip", "skip"]
    else:
        classified = case.get("classification") is not None
        first = [
            later or bool(case.get("answered")) or classified,
            later or (classified and (bool(case.get("escalated")) or not_a_complaint(case))),
        ]
    if not_a_complaint(case):
        return [*first, *["skip"] * 6, bool(marks.get("records")), bool(marks.get("trends"))]
    skip = "skip" if not_reportable else None
    submitted = not_reportable or at >= 4
    return [
        *first,
        # A complaint not on the triage list has no triage form (its page reads "Triage: not needed", 0.10.88).
        "skip" if not triaged and not triage_needed else triaged,
        bool(versions),
        signed is not None,
        skip or (at >= 0 and (bool(marks.get("form")) or at >= 1)),
        skip or at >= 3,
        skip or at >= 4,
        bool(marks.get("records")) and submitted,
        bool(marks.get("trends")),
    ]


def step_notes(done: list, case: dict | None, waiting: str | None) -> list:
    """What each step says besides done or not: why it is not needed, or what an open step 2 waits for."""
    notes = []
    for index, value in enumerate(done):
        if value == "skip":
            notes.append(
                NOT_NEEDED[
                    "case"
                    if index < 2
                    else "complaint"
                    if not_a_complaint(case)
                    else "triage"
                    if index == 2
                    else "reportable"
                ]
            )
        else:
            notes.append(waiting if index == 1 and value is False else None)
    return notes


def in_order(done: list) -> tuple[list, list[bool]]:
    """The story's ticks in order (0.10.85): a step is ticked only once every step before it is done or not needed, so
    the count, the ticks and the current step agree. A step the team did out of order (a tree signed before the
    triage) is not ticked: it is flagged "done earlier by your team", and ticks once the steps before it are done."""
    ticked, earlier, gap = [], [], False
    for value in done:
        # "Not needed" stays so wherever it is: it is no tick and no gap.
        ticked.append(value if value == "skip" or (value is True and not gap) else False)
        earlier.append(value is True and gap)
        gap = gap or value is False
    return ticked, earlier


def run_progress(data: Session, control_db: Session, ctx, tenant_id, request, run: str) -> dict | None:
    """One run of the story for this person (None when it has no complaint: the sample removed, nothing imported)."""
    from backend.app.authority_reports.router import _list_paths
    from backend.app.oversight import closure
    from backend.app.reportability import facts, markets
    from backend.app.reportability import service as reporting_service

    from backend.app.db.models.foundation import Product

    complaint = subject(data, control_db, tenant_id, run, request)
    if complaint is None:
        return None
    # The product's own identifier, which the trend check opens on (0.10.84, M4: your data's trend, not the sample's),
    # and its name, which the step's complaint summary shows (0.10.87).
    product_ref, product_name = (
        data.query(Product.product_identifier, Product.name)
        .filter(Product.tenant_id == tenant_id, Product.id == complaint.product_id)
        .one_or_none()
        if complaint.product_id
        else None
    ) or (None, None)
    market = markets.market_of(complaint.country)
    found = closure.facts(data, tenant_id, complaint)
    record = found["record"]
    triaged = record is not None and record.completed_at is not None
    triage_needed = bool(found["on_triage"]) or record is not None
    versions = found["assessments"].get(market, []) if market else []
    report = next(
        (row for row in found["obligations"] if row.market == market and row.kind == "INITIAL"),
        None,
    )
    stage = _list_paths(data, control_db, ctx, tenant_id, [report])[report.id]["stage"] if report else None
    marks = team_marks(request, run, complaint.id)
    event = story_case(data, tenant_id, complaint, run)
    case = case_facts(data, control_db, tenant_id, event) if event is not None else None
    raw = steps_done(marks, triaged, versions, stage, triage_needed=triage_needed, case=case)
    done, earlier = in_order(raw)
    current = next((index for index, value in enumerate(done) if value is False), len(done))
    notes = step_notes(raw, case, case.get("waiting") if case else None)
    signed = next((v for v in reversed(versions) if v.signed_at is not None and v.superseded_by is None), None)
    return {
        "run": run,
        "complaint": {
            "id": str(complaint.id),
            "ref": complaint.complaint_identifier,
            "description": complaint.description,
            "product_id": str(complaint.product_id) if complaint.product_id else None,
            "product_ref": product_ref,
            "product_name": product_name,
            "serious_injury": bool(complaint.serious_injury),
            "death": bool(complaint.death),
            "harm": reported_harm(complaint),
            "service_status": complaint.service_status,
        },
        "market": market,
        "market_label": markets.MARKET_LABELS.get(market, market) if market else None,
        "conclusion": signed.conclusion if signed is not None else None,
        "report_id": str(report.id) if report else None,
        "report_stage": stage,
        # The facts the import did not give; each is asked on the complaint page, where the step needs it.
        "needs": facts.of_complaint(complaint, reporting_service._record(complaint, None, None)),
        # The story's Case (steps 1 and 2 open its Case check), or None: "Classified in your QMS".
        "case": {key: case[key] for key in ("id", "ref", "classification", "state")} if case else None,
        # The QA review of a Case signed service only, inquiry or not a complaint (spec 4.8's branch card).
        "branch": {**QA_REVIEW, "done": bool(case.get("reviewed"))} if not_a_complaint(case) else None,
        "steps": [
            {
                "key": key,
                "label": label,
                "done": value is True,
                "skipped": value == "skip",
                "earlier": early,
                "note": note,
            }
            for (key, label), value, early, note in zip(STEPS, done, earlier, notes)
        ],
        "current": current,
        "finished": current == len(STEPS),
    }


def story_case(data: Session, tenant_id, complaint: Complaint, run: str):
    """The story's Case: the one that became or joined the complaint, else one a person linked to it; on the sample,
    else SAMPLE-CASE-11 (not yet attached)."""
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.intake import service
    from backend.app.trial.sample_data import SAMPLE_SOURCE
    from backend.app.trial.sample_intake import STORY_CASE

    found = (
        data.query(IntakeEvent)
        .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.complaint_id == complaint.id)
        .order_by(IntakeEvent.created_at)
        .first()
    )
    if found is not None:
        return found
    for link in service.links_of(data, tenant_id):
        if link.state != "LINKED" or complaint.id not in (link.left_id, link.right_id):
            continue
        kind, other = (
            (link.left_kind, link.left_id) if link.right_id == complaint.id else (link.right_kind, link.right_id)
        )
        if kind == service.INTAKE:
            event = data.get(IntakeEvent, other)
            if event is not None and event.tenant_id == tenant_id:
                return event
    if run != "sample":
        return None
    return (
        data.query(IntakeEvent)
        .filter(
            IntakeEvent.tenant_id == tenant_id,
            IntakeEvent.reference == STORY_CASE,
            IntakeEvent.source_system == SAMPLE_SOURCE,
        )
        .first()
    )


def case_facts(data: Session, control_db: Session, tenant_id, event) -> dict:
    """What steps 1 and 2 read from the Case: every question answered and saved by a person (the sample's pre-filled
    answers count only once someone saved them), the signed classification, the escalation, the QA review, and what a
    pending Case waits for."""
    from backend.app.intake import case_rules, rules, service
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    versions = service.checks_of(data, tenant_id, [event.id]).get(event.id, [])
    latest = versions[-1] if versions else None
    signed = service.current_signed(versions)
    answered = (
        latest is not None
        and not case_rules.unanswered(latest.answers or {})
        and (latest.source_system != SAMPLE_SOURCE or bool(latest.history))
    )
    waiting = None
    if signed is not None and signed.classification in rules.PENDING_OUTCOMES:
        task = service.open_task(service.tasks_of(data, tenant_id, [event.id]).get(event.id, []), service.FOLLOW_UP)
        owner = task.assigned_user_id if task is not None else None
        name = service.names_of(control_db, tenant_id, [str(owner)]).get(str(owner)) if owner else None
        due = rules.utc(task.due_at) if task is not None and task.due_at else None
        waiting = " · ".join([WAITING, name or "No owner yet", f"due {due.day} {due:%b %Y}" if due else "no due date"])
    return {
        "id": str(event.id),
        "ref": event.reference,
        "state": event.status,
        "answered": answered,
        "classification": signed.classification if signed is not None else None,
        "escalated": event.complaint_id is not None,
        "reviewed": signed is not None and signed.review_outcome is not None,
        "waiting": waiting,
    }


def more_cases(data: Session, tenant_id, sample: dict | None) -> list[dict]:
    """More cases to try (spec 4.8): the sample's other calls, each with its outcome as its record says; and
    SAMPLE-CASE-11 too while the sample story is not on it (a trial running before 0.10.93 got past steps 1 and 2)."""
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.intake import case_rules, rules, service
    from backend.app.trial.sample_data import SAMPLE_SOURCE
    from backend.app.trial.sample_intake import MORE_CASES, STORY_CASE

    refs = list(MORE_CASES)
    if sample and ((sample.get("case") or {}).get("ref") != STORY_CASE or sample["steps"][1]["done"]):
        refs.append(STORY_CASE)
    events = {
        row.reference: row
        for row in data.query(IntakeEvent).filter(
            IntakeEvent.tenant_id == tenant_id,
            IntakeEvent.source_system == SAMPLE_SOURCE,
            IntakeEvent.reference.in_(refs),
        )
    }
    checks = service.checks_of(data, tenant_id, [row.id for row in events.values()])
    found = []
    for ref in refs:
        event = events.get(ref)
        if event is None or (ref == STORY_CASE and event.complaint_id is not None):
            continue
        versions = checks.get(event.id, [])
        signed = service.current_signed(versions)
        outcome = signed.classification if signed else versions[-1].suggestion if versions else None
        label = (
            "Urgent: a complaint by definition"
            if event.kind == "URGENT"
            else case_rules.OUTCOME_LABELS.get(outcome or "", rules.OUTCOME_LABELS.get(outcome or "", "To check"))
        )
        found.append({"id": str(event.id), "ref": ref, "label": label, "signed": signed is not None})
    routine = _routine_try(data, tenant_id)
    return found + ([routine] if routine else [])


def _routine_try(data: Session, tenant_id) -> dict | None:
    """B7a: the sample's routine complaint (SAMPLE-RT-01), offered for "Resolve and close" (one screen, one signature);
    it opens its Dispositions drawer, with its state as the record says."""
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.oversight import EventClosure
    from backend.app.trial.sample_data import SAMPLE_SOURCE
    from backend.app.feature_set import routine_path
    from backend.app.trial.sample_dispositions import MARKER

    if not routine_path():
        return None
    complaint = (
        data.query(Complaint.id)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.complaint_identifier == MARKER,
            Complaint.source_system == SAMPLE_SOURCE,
        )
        .scalar()
    )
    if complaint is None:
        return None
    closed = (
        data.query(EventClosure.closed_at)
        .filter(EventClosure.tenant_id == tenant_id, EventClosure.complaint_id == complaint)
        .scalar()
    )
    resolved = (
        data.query(ComplaintDisposition.id)
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.complaint_id == complaint,
            ComplaintDisposition.signed_at.isnot(None),
        )
        .first()
    )
    label = "Closed in MDARIX" if closed else "Resolved" if resolved else "Routine: resolve and close"
    return {"id": str(complaint), "ref": MARKER, "label": label, "signed": bool(closed or resolved), "complaint": True}


def progress(data: Session, control_db: Session, ctx, tenant_id, request) -> dict:
    runs = {run: run_progress(data, control_db, ctx, tenant_id, request, run) for run in RUNS}
    return {**runs, "more_cases": more_cases(data, tenant_id, runs["sample"])}
