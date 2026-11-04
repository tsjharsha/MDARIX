"""One story, from the first call to the signed report (release 0.10.82, round D1 of the approved redesign).

Getting started tells one complaint's story in ten steps, first on the sample (SAMPLE-RV-11), then on the trial's own
most urgent imported complaint: the most serious harm, then the shortest clock. Each step opens the real screen with
the record in place, and each tick is read from the saved record, never from the screen on show:

1. the call: the person opened it from the story (their own mark), or its triage is recorded;
2. triage: the triage record is complete;
3. the decision tree: an assessment of the complaint's own market is saved (a draft or signed);
4. reportable or not: that market's conclusion is signed;
5. the form for the country: the authority report exists and the person opened it (skipped when not reportable);
6. fill what is missing: every mandatory field is filled (the report's status path is past "Created");
7. approval: a second person approved it;
8. PDF and submission: the submission is recorded (MDARIX never submits);
9. records: the person opened Records once the submission (or the "not reportable" conclusion) is recorded;
10. trends: the person opened Trends.

The story is the team's, as the record is (0.10.84, M6): every colleague reads the same step. The marks (steps 1, 5, 9
and 10) are kept on the trial's request (``profile["one_story"]``, keyed by the person who opened the step and the run,
tied to the complaint's id so "Restart the sample story" starts them again), and a step any colleague opened counts for
everyone, from the earliest time it was opened. A step the
complaint cannot take yet because the import lacks a fact says so (``needs``); the ask itself stays on the step's own
screen (the complaint page, 0.10.81).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint

PROFILE_KEY = "one_story"
RUNS = ("sample", "yours")
STEPS = (
    # The owner's names for the ten steps (4 Nov 2026), shown as a vertical list on Getting started.
    ("call", "Review the call"),
    ("triage", "Triage"),
    ("tree", "Assess reportability"),
    ("reportable", "Sign conclusion"),
    ("form", "Prepare report"),
    ("fill", "Complete details"),
    ("approval", "Approve report"),
    ("submit", "Record submission"),
    ("records", "Review records"),
    ("trends", "Explore trends"),
)
MARKS = ("call", "form", "records", "trends")
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


def subject(data: Session, control_db: Session, tenant_id, run: str) -> Complaint | None:
    from backend.app.trial.short_story import flagship

    return flagship(data, tenant_id) if run == "sample" else most_urgent(data, control_db, tenant_id)


def _marks(request, user_id: str, run: str, complaint_id) -> dict:
    """One person's own marks on the run's complaint."""
    mine = (((request.profile or {}).get(PROFILE_KEY) or {}).get(str(user_id)) or {}).get(run) or {}
    return mine if mine.get("complaint_id") == str(complaint_id) else {}


def team_marks(request, run: str, complaint_id) -> dict:
    """Every colleague's marks on the run's complaint, merged: a step anyone opened, at the earliest time it was."""
    found: dict = {}
    for person in ((request.profile or {}).get(PROFILE_KEY) or {}).values():
        mine = (person or {}).get(run) or {}
        if mine.get("complaint_id") != str(complaint_id):
            continue
        for step in MARKS:
            if mine.get(step) and (not found.get(step) or mine[step] < found[step]):
                found[step] = mine[step]
    return found


def record_mark(request, user_id: str, run: str, complaint_id, step: str, now: datetime) -> None:
    """Keep the person's mark on the trial's request (the caller holds the row and commits)."""
    profile = dict(request.profile or {})
    story = dict(profile.get(PROFILE_KEY) or {})
    person = dict(story.get(str(user_id)) or {})
    mine = _marks(request, user_id, run, complaint_id) or {"complaint_id": str(complaint_id)}
    person[run] = {**mine, step: mine.get(step) or now.isoformat()}
    story[str(user_id)] = person
    profile[PROFILE_KEY] = story
    request.profile = profile


def steps_done(
    marks: dict, triaged: bool, versions: list, report_stage: str | None, *, triage_needed: bool = True
) -> list:
    """Per step: True (done), False, or "skip" (not needed: the triage of a complaint not flagged for it, the report's
    steps after a signed "not reportable" conclusion). Pure, so its rules are tested apart from the records."""
    from backend.app.reportability.markets import NOT_REPORTABLE

    signed = next((v for v in reversed(versions) if v.signed_at is not None and v.superseded_by is None), None)
    not_reportable = signed is not None and signed.conclusion == NOT_REPORTABLE
    at = REPORT_PATH.index(report_stage) if report_stage in REPORT_PATH else -1
    skip = "skip" if not_reportable else None
    submitted = not_reportable or at >= 4
    # A step the record shows done says the person's own steps before it were taken (0.10.85): any later work on the
    # complaint means its call was read; a report past "Created" means its form was opened.
    return [
        bool(marks.get("call")) or triaged or bool(versions) or at >= 0,
        # A complaint not on the triage list has no triage form (its page reads "Triage: not needed", 0.10.88).
        "skip" if not triaged and not triage_needed else triaged,
        bool(versions),
        signed is not None,
        skip or (at >= 0 and (bool(marks.get("form")) or at >= 1)),
        skip or at >= 1,
        skip or at >= 3,
        skip or at >= 4,
        bool(marks.get("records")) and submitted,
        bool(marks.get("trends")),
    ]


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

    complaint = subject(data, control_db, tenant_id, run)
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
    done, earlier = in_order(steps_done(marks, triaged, versions, stage, triage_needed=triage_needed))
    current = next((index for index, value in enumerate(done) if value is False), len(done))
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
        "steps": [
            {"key": key, "label": label, "done": value is True, "skipped": value == "skip", "earlier": early}
            for (key, label), value, early in zip(STEPS, done, earlier)
        ],
        "current": current,
        "finished": current == len(STEPS),
    }


def progress(data: Session, control_db: Session, ctx, tenant_id, request) -> dict:
    return {run: run_progress(data, control_db, ctx, tenant_id, request, run) for run in RUNS}
