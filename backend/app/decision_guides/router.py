"""Customer-owned decision guides API (T-G15, MVP G15).

- ``GET /api/v1/decision-guides``: each market's guide with its version in use, any version being prepared, and the
  version history (version 1 is MDARIX's starter);
- ``GET /api/v1/decision-guides/{market}/versions/{version}``: one version with every question (its clause and basis),
  its test cases and last results, what still blocks publication, and its approval;
- ``POST /api/v1/decision-guides/{market}/drafts``: a draft copied from the version in use;
- ``PUT /api/v1/decision-guides/{market}/versions/{version}``: save the draft's questions and test cases (a version
  waiting for approval returns to draft);
- ``POST .../tests``: run the test cases against the fixed conclusion logic and keep the results with the version;
- ``POST .../approval-request`` (each colleague who may approve gets a task in My Work, J13), ``.../withdraw`` (its
  author takes it back to draft), ``.../approve`` (a second person, with password and authenticator code; it publishes
  the version; working alone in a trial, one's own practice version, T-B8) and ``.../discard``;
- ``GET .../guide.pdf`` and ``.docx``: the version for an audit.

Reading is open to every signed-in member; changes need regulatory.review or regulatory.approve, and the export needs
data.export. A published version is never edited: a change is a new version. These routes serve a free trial and a
pilot alike (T-B1).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import standards
from backend.app.access.permissions import DATA_EXPORT, REGULATORY_APPROVE, REGULATORY_REVIEW, require_permission
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import SignedApprovalRecord
from backend.app.db.models.guides_communications import DecisionGuideVersion
from backend.app.db.session import get_db
from backend.app.decision_guides import rules
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.oversight.service import calendar_of
from backend.app.reportability import markets
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.standards import STARTER_MARK
from backend.app.workflow import approvals
from backend.app.workflow.tasks import run_hook

logger = logging.getLogger("mdarix.decision_guides")
router = APIRouter(prefix="/api/v1/decision-guides", tags=["Decision guides"])

OBJECT_TYPE = "DecisionGuideVersion"
DECISION_TYPE = "DECISION_GUIDE_APPROVAL"
DECIDERS = Depends(require_any_permission(REGULATORY_REVIEW, REGULATORY_APPROVE))
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SAMPLE_NAMES = {"system:trial-sample": "MDARIX sample data"}
NEVER_DECIDES = (
    "A guide points to a conclusion; a person confirms or overrides it with a reason, and signs. MDARIX never decides "
    "and never submits."
)
CORE_RULE = (
    "The questions that drive the conclusion can be reworded and clarified, not removed, and their conclusion logic "
    "stays fixed. Extra questions are recorded and printed with the answers; they never change the conclusion."
)
SCALE_NOTE = "The harm-severity scale stays MDARIX's fixed starter scale in the trial (scale-starter-1)."


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _tenant(ctx) -> uuid.UUID:
    return uuid.UUID(ctx.tenant_id)


def _market(market: str) -> str:
    code = str(market or "").strip().upper()
    if code not in markets.MARKETS:
        raise _error(404, "MARKET_UNKNOWN", "Choose the US, EU and Northern Ireland, Great Britain or India")
    return code


def _rows(db, tenant_id, market: str, *, lock: bool = False) -> list[DecisionGuideVersion]:
    query = db.query(DecisionGuideVersion).filter(
        DecisionGuideVersion.tenant_id == tenant_id, DecisionGuideVersion.market == market
    )
    return (query.with_for_update() if lock else query).order_by(DecisionGuideVersion.version).all()


def _row(db, tenant_id, market: str, version: int, *, lock: bool = False) -> DecisionGuideVersion:
    found = next((row for row in _rows(db, tenant_id, market, lock=lock) if row.version == version), None)
    if found is None:
        raise _error(404, "VERSION_NOT_FOUND", "No such version of this guide")
    return found


def _names(control_db, tenant_id, refs) -> dict[str, str]:
    return {**SAMPLE_NAMES, **people(control_db, tenant_id, [ref for ref in refs if ref])}


def _fingerprint(market: str, code: str, questions: list[dict], tests: list[dict]) -> str:
    from backend.app.human_decision.rules import fingerprint

    return fingerprint(rules.content(market, code, questions, tests))


def _audit(db, ctx, action: str, row: DecisionGuideVersion | None, market: str, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=_tenant(ctx),
            actor_ref=ctx.user_id,
            action=action,
            entity_type=OBJECT_TYPE,
            entity_id=row.id if row is not None else None,
            correlation_id=ctx.correlation_id,
            details={"market": market, **({"version": row.code} if row is not None else {}), **details},
        )
    )


def _trial(control_db, tenant_id) -> bool:
    from backend.app.signer_training.router import is_trial

    return is_trial(control_db, tenant_id)


def standing(control_db, ctx, tenant_id, row: DecisionGuideVersion, trial: bool) -> dict:
    """Whether this person may approve the waiting version, told before any password (J13, workflow/approvals.py):
    never an editor of it or an administrator, except that working alone in a trial one may approve one's own practice
    version ("same person", T-B8); the colleagues who may approve, by name."""
    me = str(ctx.user_id)
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    editors = set(row.editors or [])
    if person.holds_any(*approvals.PERMISSIONS):
        problem = rules.approver_problem(me, role, editors)
        separation = problem is not None and (role or "").upper() not in rules.ADMINISTRATOR_ROLES
    else:
        problem, separation = approvals.NO_RIGHTS, False
    others = [name for _, name in approvals.approvers(control_db, tenant_id, {*editors, me})]
    return {**approvals.standing(problem, separation, others, trial, role, "guide version"), "role": role}


def _end_tasks(db, tenant_id, row: DecisionGuideVersion, outcome: str, actor: str, approved: bool = False) -> None:
    run_hook(
        db,
        "guide approval task",
        approvals.finish,
        tenant_id,
        source_type=OBJECT_TYPE,
        source_id=row.id,
        outcome=outcome,
        actor=actor,
        approved=approved,
    )


# --------------------------------------------------------------------------------------------- views


def _starter_view(market: str, superseded: bool) -> dict:
    question_set = rules.starter(market)
    tests = rules.starter_tests(market)
    questions = [rules.question_dict(question) for question in question_set.questions]
    fingerprint = _fingerprint(market, question_set.version, questions, tests)
    results = rules.run(market, tests)
    return {
        "market": market,
        "market_label": markets.MARKET_LABELS[market],
        "version": 1,
        "code": question_set.version,
        "title": question_set.title,
        "state": rules.SUPERSEDED if superseded else rules.PUBLISHED,
        "state_label": "MDARIX starter: " + ("superseded by your version" if superseded else "in use"),
        "starter": True,
        "based_on": None,
        "question_set": question_set.as_dict(),
        "test_cases": tests,
        "test_results": {
            "fingerprint": fingerprint,
            "results": results,
            "passed": sum(item["passed"] for item in results),
            "failed": sum(not item["passed"] for item in results),
            "current": True,
            "run_at": None,
            "run_by": "MDARIX",
        },
        "problems": [],
        "change_reason": "MDARIX's starter guide, written from the regulation's definitions.",
        "editors": [],
        "requested_by": None,
        "requested_at": None,
        "approved_by": None,
        "approved_at": None,
        "signature": None,
        "published_at": None,
        "superseded_at": None,
        "editable": False,
        "sample": False,
    }


def version_view(control_db, row: DecisionGuideVersion, names: dict, signature: dict | None = None) -> dict:
    question_set = rules.build(row.market, row.code, row.questions or [])
    fingerprint = _fingerprint(row.market, row.code, row.questions or [], row.test_cases or [])
    results = row.test_results
    return {
        "id": str(row.id),
        "market": row.market,
        "market_label": markets.MARKET_LABELS[row.market],
        "version": row.version,
        "code": row.code,
        "title": question_set.title,
        "state": row.state,
        "state_label": rules.STATE_LABELS[row.state],
        "starter": False,
        "based_on": row.based_on,
        "question_set": question_set.as_dict(),
        "test_cases": row.test_cases or [],
        "test_results": (
            {
                **results,
                "current": results.get("fingerprint") == fingerprint,
                "run_by": names.get(results.get("run_by")) or "A colleague",
            }
            if results
            else None
        ),
        "problems": rules.publish_problems(row.questions or [], row.test_cases or [], results, fingerprint)
        if row.state in rules.OPEN_STATES
        else [],
        "change_reason": row.change_reason,
        "editors": [names.get(ref) or "A colleague" for ref in row.editors or []],
        "requested_by": names.get(row.requested_by) or "A colleague" if row.requested_by else None,
        "requested_at": _iso(row.requested_at),
        "approved_by": names.get(row.approved_by) or "A colleague" if row.approved_by else None,
        "approved_at": _iso(row.approved_at),
        "signature": signature,
        "published_at": _iso(row.published_at),
        "superseded_at": _iso(row.superseded_at),
        "editable": row.state in rules.OPEN_STATES,
        "sample": row.source_system is not None,
    }


def _signature(control_db, tenant_id, row: DecisionGuideVersion, names: dict) -> dict | None:
    if not row.signed_record_id:
        return None
    record = control_db.get(SignedApprovalRecord, row.signed_record_id)
    if record is None:
        return None
    return {
        "signer_name": names.get(record.signer_user_id) or "A colleague",
        "signer_role": (record.signer_role or "").replace("_", " ").title(),
        "signed_at": record.signed_at.isoformat(timespec="seconds") if record.signed_at else None,
        "meaning": record.signature_meaning,
        "record_business_id": record.business_id,
        "record_id": str(record.id),
        "content_fingerprint": record.content_fingerprint,
    }


def _summary(view: dict) -> dict:
    return {
        key: view[key]
        for key in ("version", "code", "state", "state_label", "starter", "approved_by", "published_at", "sample")
    }


def _catalog() -> list[dict]:
    return [{**item.as_dict()} for item in standards.CATALOG]


def detail(db, control_db, ctx, market: str, version: int) -> dict:
    tenant_id = _tenant(ctx)
    rows = _rows(db, tenant_id, market)
    published = any(row.state == rules.PUBLISHED for row in rows)
    if version == 1:
        view = _starter_view(market, published)
    else:
        row = next((item for item in rows if item.version == version), None)
        if row is None:
            raise _error(404, "VERSION_NOT_FOUND", "No such version of this guide")
        refs = {*(row.editors or []), row.requested_by, row.approved_by, (row.test_results or {}).get("run_by")}
        names = _names(control_db, tenant_id, refs)
        view = version_view(control_db, row, names, _signature(control_db, tenant_id, row, names))
        me = str(ctx.user_id)
        view["you_edited"] = me in set(row.editors or [])
        view["you_asked"] = row.state == rules.AWAITING and row.requested_by == me
    trial = _trial(control_db, tenant_id)
    if version != 1 and row.state == rules.AWAITING:
        view["approval"] = standing(control_db, ctx, tenant_id, row, trial)
    return {
        **view,
        "catalog": _catalog(),
        "answer_labels": markets.ANSWER_LABELS,
        "expected_labels": {code: markets.CONCLUSION_LABELS[code] for code in rules.EXPECTED},
        "report_types": [
            {"code": code, "label": kind.label}
            for code, kind in markets.REPORT_TYPES.items()
            if code.startswith(rules.PREFIX[market] + "_")
        ],
        "core_rule": CORE_RULE,
        "never_decides": NEVER_DECIDES,
        "scale_note": SCALE_NOTE,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
    }


@router.get("")
def guides(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Each market's guide: the version in use, any version being prepared, and the history (newest first)."""
    from backend.app.reportability import service as reporting

    tenant_id = _tenant(ctx)
    enabled = markets.enabled_markets(reporting.settings_of(db, tenant_id)["windows"])
    rows = (
        db.query(DecisionGuideVersion)
        .filter(DecisionGuideVersion.tenant_id == tenant_id)
        .order_by(DecisionGuideVersion.market, DecisionGuideVersion.version)
        .all()
    )
    names = _names(control_db, tenant_id, {ref for row in rows for ref in (row.approved_by, *(row.editors or []))})
    items = []
    for market in markets.MARKETS:
        mine = [row for row in rows if row.market == market]
        views = [version_view(control_db, row, names) for row in mine]
        published = next((view for view in views if view["state"] == rules.PUBLISHED), None)
        history = [_summary(_starter_view(market, published is not None))] + [_summary(view) for view in views]
        current = published or _starter_view(market, False)
        open_view = next((view for view in views if view["state"] in rules.OPEN_STATES), None)
        items.append(
            {
                "market": market,
                "label": markets.MARKET_LABELS[market],
                "enabled": market in enabled,
                "current": {
                    **_summary(current),
                    "title": current["title"],
                    "questions": len(current["question_set"]["questions"]),
                    "extra_questions": sum(1 for q in current["question_set"]["questions"] if q["extra"]),
                    "tests": len(current["test_cases"]),
                },
                "open": (
                    {**_summary(open_view), "problems": open_view["problems"], "editors": open_view["editors"]}
                    if open_view
                    else None
                ),
                "history": list(reversed(history)),
            }
        )
    return {
        "markets": items,
        "core_rule": CORE_RULE,
        "never_decides": NEVER_DECIDES,
        "scale_note": SCALE_NOTE,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if _trial(control_db, tenant_id) else None,
    }


@router.get("/{market}/versions/{version}")
def guide_version(
    market: str,
    version: int,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return detail(db, control_db, ctx, _market(market), version)


# --------------------------------------------------------------------------------------------- writing


def start_draft(db, tenant_id, market: str, actor: str, now: datetime, source_system: str | None = None):
    """A draft copied from the version in use: its questions and test cases (shared with the sample). Flushes."""
    rows = _rows(db, tenant_id, market, lock=True)
    if any(row.state in rules.OPEN_STATES for row in rows):
        raise _error(409, "DRAFT_EXISTS", "A version of this guide is already being prepared: open it")
    published = next((row for row in rows if row.state == rules.PUBLISHED), None)
    if published is not None:
        questions, tests, based_on = published.questions, published.test_cases, published.code
    else:
        base = rules.starter(market)
        questions = [rules.question_dict(question) for question in base.questions]
        tests, based_on = rules.starter_tests(market), base.version
    number = max((row.version for row in rows), default=1) + 1
    row = DecisionGuideVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        market=market,
        version=number,
        code=rules.version_code(market, number),
        based_on=based_on,
        state=rules.DRAFT,
        questions=[dict(item) for item in questions],
        test_cases=[dict(item) for item in tests],
        editors=[actor],
        source_system=source_system,
        created_by=actor,
        created_at=now,
        updated_by=actor,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


@router.post("/{market}/drafts", dependencies=[DECIDERS])
def create_draft(
    market: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    market = _market(market)
    try:
        row = start_draft(db, _tenant(ctx), market, str(ctx.user_id), _now())
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "DRAFT_EXISTS", "A version of this guide was started a moment ago: reload") from exc
    _audit(db, ctx, "DECISION_GUIDE_DRAFT_STARTED", row, market, based_on=row.based_on)
    db.commit()
    return detail(db, control_db, ctx, market, row.version)


class QuestionIn(BaseModel):
    id: str = Field(default="", max_length=10)
    text: str = Field(max_length=rules.TEXT_MAX * 2)
    definition: str | None = Field(default="", max_length=rules.DEFINITION_MAX * 2)
    note: str | None = Field(default="", max_length=rules.NOTE_MAX * 2)
    clause: str | None = Field(default="", max_length=rules.CLAUSE_MAX * 2)
    basis: list[str] = Field(default_factory=list, max_length=10)


class TestIn(BaseModel):
    name: str = Field(max_length=rules.NAME_MAX * 2)
    answers: dict[str, str] = Field(default_factory=dict, max_length=40)
    expected: str = Field(max_length=30)
    expected_report_type: str | None = Field(default=None, max_length=40)


class SaveRequest(BaseModel):
    questions: list[QuestionIn] = Field(max_length=40)
    test_cases: list[TestIn] = Field(default_factory=list, max_length=rules.TESTS_MAX * 2)


def save(db, row: DecisionGuideVersion, questions: list[dict], tests: list[dict], actor: str, now: datetime) -> None:
    """Save a draft's content (shared with the sample). A version waiting for approval returns to draft."""
    row.questions, row.test_cases = questions, tests
    if row.state == rules.AWAITING:
        row.state, row.requested_by, row.requested_at, row.content_fingerprint = rules.DRAFT, None, None, None
    if actor not in (row.editors or []):
        row.editors = [*(row.editors or []), actor]
    row.updated_by, row.updated_at = actor, now
    db.flush()


@router.put("/{market}/versions/{version}", dependencies=[DECIDERS])
def save_version(
    market: str,
    version: int,
    payload: SaveRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    market = _market(market)
    row = _row(db, _tenant(ctx), market, version, lock=True)
    if row.state not in rules.OPEN_STATES:
        raise _error(409, "NOT_A_DRAFT", "A published version is never edited: start a new version")
    questions, problem = rules.clean_questions(market, [item.model_dump() for item in payload.questions])
    if problem:
        raise _error(422, "GUIDE_INVALID", problem)
    tests, problem = rules.clean_tests(market, [item.model_dump() for item in payload.test_cases])
    if problem:
        raise _error(422, "TESTS_INVALID", problem)
    returned = row.state == rules.AWAITING
    save(db, row, questions, tests, str(ctx.user_id), _now())
    _audit(
        db,
        ctx,
        "DECISION_GUIDE_DRAFT_SAVED",
        row,
        market,
        questions=len(questions),
        extra_questions=sum(1 for item in questions if item["extra"]),
        tests=len(tests),
        returned_to_draft=returned,
    )
    db.commit()
    if returned:
        _end_tasks(db, row.tenant_id, row, "Returned to draft", str(ctx.user_id))
    return detail(db, control_db, ctx, market, version)


def run_tests(db, row: DecisionGuideVersion, actor: str, now: datetime) -> dict:
    """Run the version's test cases and keep the results with it (shared with the sample)."""
    results = rules.run(row.market, row.test_cases or [])
    row.test_results = {
        "fingerprint": _fingerprint(row.market, row.code, row.questions or [], row.test_cases or []),
        "results": results,
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "run_at": now.isoformat(),
        "run_by": actor,
    }
    row.updated_at = now
    db.flush()
    return row.test_results


@router.post("/{market}/versions/{version}/tests", dependencies=[DECIDERS])
def run_version_tests(
    market: str,
    version: int,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    market = _market(market)
    row = _row(db, _tenant(ctx), market, version, lock=True)
    if row.state not in rules.OPEN_STATES:
        raise _error(409, "NOT_A_DRAFT", "The tests of a published version were run before its approval")
    if not row.test_cases:
        raise _error(422, "NO_TESTS", "Add at least one test case")
    results = run_tests(db, row, str(ctx.user_id), _now())
    _audit(db, ctx, "DECISION_GUIDE_TESTS_RUN", row, market, passed=results["passed"], failed=results["failed"])
    db.commit()
    return detail(db, control_db, ctx, market, version)


class ApprovalRequest(BaseModel):
    change_reason: str = Field(max_length=4000)


def request_approval(db, row: DecisionGuideVersion, reason: str, actor: str, now: datetime) -> None:
    """Ask a second person to approve (shared with the sample). Refused while anything blocks publication."""
    fingerprint = _fingerprint(row.market, row.code, row.questions or [], row.test_cases or [])
    problems = rules.publish_problems(row.questions or [], row.test_cases or [], row.test_results, fingerprint)
    if problems:
        raise _error(409, "NOT_READY_TO_PUBLISH", problems[0], problems=problems)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say in at least {rules.REASON_MIN} characters what changed and why")
    row.state, row.change_reason, row.content_fingerprint = rules.AWAITING, reason, fingerprint
    row.requested_by, row.requested_at, row.updated_at = actor, now, now
    if actor not in (row.editors or []):
        row.editors = [*(row.editors or []), actor]
    db.flush()


@router.post("/{market}/versions/{version}/approval-request", dependencies=[DECIDERS])
def ask_for_approval(
    market: str,
    version: int,
    payload: ApprovalRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    market = _market(market)
    row = _row(db, _tenant(ctx), market, version, lock=True)
    if row.state != rules.DRAFT:
        raise _error(409, "NOT_A_DRAFT", "Only a draft is sent for approval")
    actor = str(ctx.user_id)
    request_approval(db, row, " ".join(payload.change_reason.split()), actor, _now())
    _audit(db, ctx, "DECISION_GUIDE_APPROVAL_REQUESTED", row, market, fingerprint=row.content_fingerprint)
    db.commit()
    tenant_id = row.tenant_id
    run_hook(
        db,
        "guide approval task",
        lambda session: approvals.ask(
            session,
            control_db,
            tenant_id,
            source_type=OBJECT_TYPE,
            source_id=row.id,
            title=f"Approve decision guide version {row.code}",
            due_at=calendar_of(session, tenant_id).working_day_end(row.requested_at, 1),
            excluded=set(row.editors or []),
            requester=actor,
            trial=_trial(control_db, tenant_id),
            details={
                "reference": row.code,
                "market": market,
                "category": "GUIDE",
                "opens": {"section": "Complaints", "tab": "Decision guides"},
            },
        ),
    )
    return detail(db, control_db, ctx, market, version)


@router.post("/{market}/versions/{version}/withdraw", dependencies=[DECIDERS])
def withdraw(
    market: str,
    version: int,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Its author takes a version waiting for approval back to draft (J13): the approvers' tasks end."""
    market = _market(market)
    row = _row(db, _tenant(ctx), market, version, lock=True)
    me = str(ctx.user_id)
    if row.state != rules.AWAITING:
        raise _error(409, "NOT_AWAITING_APPROVAL", "This version is not waiting for approval")
    if row.requested_by != me:
        raise _error(403, "NOT_THE_AUTHOR", "Only the person who sent it for approval withdraws it")
    row.state, row.requested_by, row.requested_at, row.content_fingerprint = rules.DRAFT, None, None, None
    row.updated_by, row.updated_at = me, _now()
    _audit(db, ctx, "DECISION_GUIDE_APPROVAL_WITHDRAWN", row, market)
    db.commit()
    _end_tasks(db, row.tenant_id, row, "Withdrawn", me)
    return detail(db, control_db, ctx, market, version)


def publish(db, row: DecisionGuideVersion, approver: str, record_id: uuid.UUID, now: datetime) -> None:
    """The approved version becomes the one in use; the earlier one is superseded (shared with the sample)."""
    for other in _rows(db, row.tenant_id, row.market):
        if other.state == rules.PUBLISHED and other.id != row.id:
            other.state, other.superseded_at, other.updated_at = rules.SUPERSEDED, now, now
    db.flush()
    row.state, row.approved_by, row.approved_at, row.signed_record_id = rules.PUBLISHED, approver, now, record_id
    row.published_at, row.updated_at = now, now
    db.flush()


class ApproveRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


@router.post("/{market}/versions/{version}/approve", dependencies=[DECIDERS])
def approve(
    market: str,
    version: int,
    payload: ApproveRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The second person's approval with password and authenticator code; it publishes the version."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import signature_hash

    market = _market(market)
    tenant_id = _tenant(ctx)
    row = _row(db, tenant_id, market, version)
    if row.state != rules.AWAITING:
        raise _error(409, "NOT_AWAITING_APPROVAL", "This version is not waiting for approval")
    me = str(ctx.user_id)
    allowed = standing(control_db, ctx, tenant_id, row, _trial(control_db, tenant_id))
    role, same_person = allowed["role"], allowed["same_person"]
    if not allowed["may_approve"]:
        problem = allowed["message"]
        _audit(db, ctx, "DECISION_GUIDE_APPROVAL_REFUSED", row, market, reason=problem)
        db.commit()
        raise _error(403, "SECOND_PERSON_REQUIRED", problem)

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type=OBJECT_TYPE,
                entity_id=row.id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "DECISION_GUIDE_APPROVE", "version": row.code},
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    row = _row(db, tenant_id, market, version, lock=True)
    fingerprint = _fingerprint(market, row.code, row.questions or [], row.test_cases or [])
    if row.state != rules.AWAITING or row.content_fingerprint != fingerprint:
        raise _error(409, "VERSION_CHANGED", "This version changed a moment ago; reload it and read it again")
    now = _now()
    title = rules.build(market, row.code, row.questions or []).title
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=row.id,
        object_version=row.code,
        decision_type=DECISION_TYPE,
        decision="APPROVED",
        remarks=(
            ("Same person (trial practice: edited and approved by one person). " if same_person else "")
            + (row.change_reason or "")
        )[:500]
        or None,
        signer_user_id=me,
        signer_role=role or "UNKNOWN",
        signature_meaning=rules.signature_meaning(row.code, title),
        content_fingerprint=fingerprint,
        signature_hash=signature_hash(fingerprint, me, row.code),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="DECISION_GUIDE_APPROVED",
            entity_type=OBJECT_TYPE,
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details={
                "market": market,
                "version": row.code,
                "signature_id": str(record.id),
                "fingerprint": fingerprint,
                "same_person": same_person,
            },
            created_at=now,
        )
    )
    publish(db, row, me, record.id, now)
    if db is control_db:
        control_db.commit()
    else:
        control_db.commit()
        try:
            db.commit()
        except Exception:
            logger.exception("Signature %s was saved but guide version %s was not published", record.id, row.id)
            raise
    _end_tasks(db, tenant_id, row, "Approved", me, approved=True)
    return detail(db, control_db, ctx, market, version)


@router.post("/{market}/versions/{version}/discard", dependencies=[DECIDERS])
def discard(
    market: str,
    version: int,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    market = _market(market)
    row = _row(db, _tenant(ctx), market, version, lock=True)
    if row.state not in rules.OPEN_STATES:
        raise _error(409, "NOT_A_DRAFT", "Only a version being prepared can be discarded")
    row.state, row.updated_by, row.updated_at = rules.DISCARDED, str(ctx.user_id), _now()
    _audit(db, ctx, "DECISION_GUIDE_DRAFT_DISCARDED", row, market)
    db.commit()
    _end_tasks(db, row.tenant_id, row, "Discarded", str(ctx.user_id))
    return detail(db, control_db, ctx, market, version)


# --------------------------------------------------------------------------------------------- export


@router.get("/{market}/versions/{version}/guide.{kind}", dependencies=[Depends(require_permission(DATA_EXPORT))])
def export(
    market: str,
    version: int,
    kind: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The version as a PDF or DOCX for an audit: every question with its clause and basis, the test cases and their
    results, and the approval (the printed name, the date and time, the meaning)."""
    from backend.app.decision_guides import render
    from backend.app.stage3_workflow_router import _organization_name

    kind = kind.lower()
    if kind not in MEDIA:
        raise _error(404, "FORMAT_NOT_SUPPORTED", "Download the PDF or the DOCX")
    market = _market(market)
    tenant_id = _tenant(ctx)
    view = detail(db, control_db, ctx, market, version)
    body = render.render(view, kind, organization=_organization_name(control_db, tenant_id))
    _audit(db, ctx, "DECISION_GUIDE_DOWNLOADED", None, market, version=view["code"], format=kind.upper())
    db.commit()
    return Response(
        content=body,
        media_type=MEDIA[kind],
        headers={"Content-Disposition": f'attachment; filename="mdarix-guide-{view["code"]}.{kind}"'},
    )
