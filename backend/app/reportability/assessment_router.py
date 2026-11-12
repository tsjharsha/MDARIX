"""Per-market seriousness and causation assessment API (T-G15S, T-G15H, T-G40P).

For a complaint on the reportability watch: each market the organization enabled gets its own assessment, with the
market's starter questions (each with its definition and clause), the harm-severity scale, the suggested conclusion
and the person's signed conclusion. Reading is open to every signed-in member; saving and signing need
regulatory.review or regulatory.approve, like the single decision did. A conclusion is signed with the current
password and, when signatures require it, an authenticator code; in a free trial only, after a practice
acknowledgement of the current version of the market's question set and of the scale (owner decision 6, 31 Oct 2026:
other organisations may record one but are not refused without it). Administrators never sign.
A signed version is never edited; a change is a new version. MDARIX never answers, never signs and never submits.

These routes serve a free trial and a pilot alike: they are not part of mvp-1.0's ``_PILOT_API`` gate (T-B1).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.access.permissions import REGULATORY_APPROVE, REGULATORY_REVIEW
from backend.app.complaint_review.service import people
from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.db.session import get_db
from backend.app.decision_guides import service as guides
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.reportability import assessments, deadlines, facts, markets, rules, service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training import service as training
from backend.app.signer_training.router import is_trial
from backend.app.standards import STARTER_MARK
from backend.app.business_ids import complaint_ref

logger = logging.getLogger("mdarix.reportability.markets")
router = APIRouter(prefix="/api/v1/complaints", tags=["Per-market assessment"])

OBJECT_TYPE = "ComplaintMarketAssessment"
DECISION_TYPE = "MARKET_REPORTABILITY_CONCLUSION"
# signed_approval_records.decision is at most 12 characters.
SIGNATURE_CODES = {markets.REPORTABLE: "REPORTABLE", markets.NOT_REPORTABLE: "NOT_REPORT"}
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})
LEGACY_NOTE = "Single decision, recorded before per-market assessment"
DECIDERS = Depends(require_any_permission(REGULATORY_REVIEW, REGULATORY_APPROVE))


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _collapse(value) -> str:
    return " ".join(str(value or "").split())


class AnswerIn(BaseModel):
    answer: str | None = Field(default=None, max_length=20)
    rationale: str = Field(default="", max_length=markets.RATIONALE_MAX * 2)
    evidence: list[str] = Field(default_factory=list, max_length=markets.EVIDENCE_MAX * 2)
    # The person pressed Confirm on the answer the complaint's record suggested (0.10.72, B1).
    confirmed: bool = False


class DraftRequest(BaseModel):
    answers: dict[str, AnswerIn] = Field(default_factory=dict, max_length=40)
    harm_level: str | None = Field(default=None, max_length=20)
    harm_code: str | None = Field(default=None, max_length=60)
    harm_level_reason: str = Field(default="", max_length=2000)
    scale_disagreement_reason: str = Field(default="", max_length=2000)


class SignRequest(BaseModel):
    conclusion: str = Field(max_length=30)
    override_reason: str = Field(default="", max_length=2000)
    # Why a re-signed conclusion changes (OD-4, 0.10.88): needed when a signed version is superseded.
    change_reason: str = Field(default="", max_length=2000)
    # The draft the person read: a draft saved again meanwhile is refused, so nobody signs what they did not see.
    version: int = Field(ge=1)
    saved_at: str = Field(max_length=40)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


class FactsRequest(BaseModel):
    country: str | None = Field(default=None, max_length=rules.MARKET_MAX_LENGTH)
    awareness_date: date | None = None


class FilingRequest(BaseModel):
    filing_reference: str = Field(max_length=rules.REFERENCE_MAX * 2)
    filed_on: date


def _found(db: Session, tenant_id: uuid.UUID, complaint_id: uuid.UUID, today: date):
    found = service.one(db, tenant_id, complaint_id, today)
    if found is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    return found


def _on_watch(complaint, record, second_look) -> bool:
    return rules.watched(record) and service.counts_as_complaint(
        complaint.status, complaint.complaint_type, second_look
    )


def _same_moment(saved, seen: str) -> bool:
    try:
        return saved is not None and saved == datetime.fromisoformat(seen)
    except ValueError:
        return False


def _market(market: str) -> str:
    code = str(market or "").strip().upper()
    if code not in markets.MARKETS:
        raise _error(404, "MARKET_UNKNOWN", "Assess the US, EU and Northern Ireland, Great Britain or India")
    return code


def _settle_open_reports(db: Session, ctx, tenant_id, complaint_id, market: str, signed, now) -> list:
    """J14 and 0.10.81 (F1): a signed reportable conclusion gives every open initial report of its market its report
    type, due date and provisional flag (authority_reports/router.py ``follow_signed``); a submitted one is flagged,
    never changed. Returns the pending snapshots whose approval tasks end."""
    from backend.app.authority_reports import router as reports
    from backend.app.db.models.authority_reports import ReportObligation

    if signed.conclusion != markets.REPORTABLE:
        return []
    ended = []
    for obligation in (
        db.query(ReportObligation)
        .filter(
            ReportObligation.tenant_id == tenant_id,
            ReportObligation.complaint_id == complaint_id,
            ReportObligation.market == market,
            ReportObligation.kind == "INITIAL",
        )
        .with_for_update()
    ):
        ended += reports.follow_signed(db, ctx, obligation, signed, now)
    return ended


def _versions(db: Session, tenant_id, complaint_id, market: str, lock: bool = False):
    query = db.query(ComplaintMarketAssessment).filter(
        ComplaintMarketAssessment.tenant_id == tenant_id,
        ComplaintMarketAssessment.complaint_id == complaint_id,
        ComplaintMarketAssessment.market == market,
    )
    if lock:
        # Fresh values, not the identity map's copies read before the lock (code audit 6).
        query = query.with_for_update().populate_existing()
    return query.order_by(ComplaintMarketAssessment.version).all()


def _severity_level(db: Session, tenant_id, complaint_id, severity) -> dict:
    """The harm level the questions start from: the QMS severity's mapped level, else the level the triage record
    already chose on the same scale (stage 8: the harm is not asked twice), with where it came from."""
    from backend.app.oversight.closure import triage_record

    level = markets.level_of_severity(severity)
    if level:
        return {"severity_level": level, "severity_source": "Your QMS severity"}
    record = triage_record(db, tenant_id, complaint_id)
    chosen = (record.severity or "").upper() if record is not None and record.completed_at else ""
    if chosen in markets.LEVELS:
        return {"severity_level": chosen, "severity_source": "The triage record"}
    return {"severity_level": None, "severity_source": None}


def detail(db: Session, control_db: Session, ctx, complaint_id: uuid.UUID, today: date | None = None) -> dict:
    """Everything the assessment screen shows for one complaint: each market's questions, versions and draft, the
    scale with the complaint's mapped level, the person's training on what a signature relies on, and any earlier
    single decision."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    today = deadlines.as_moment(today)
    complaint, record, seen, second_look = _found(db, tenant_id, complaint_id, today)
    windows = service.settings_of(db, tenant_id)["windows"]
    by_market = assessments.rows_by_complaint(db, tenant_id, [complaint_id]).get(complaint_id, {})
    enabled = markets.enabled_markets(windows)
    aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
    summary = {
        item["market"]: item
        for item in assessments.markets_summary(record, windows, by_market, aware, today, seen.get("org_zone"))
    }
    shown = [market for market in markets.MARKETS if market in enabled or market in by_market]
    refs = {row.signed_by for rows in by_market.values() for row in rows} | {
        row.created_by for rows in by_market.values() for row in rows
    }
    legacy = (
        db.query(ComplaintReportability)
        .filter(ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id == complaint_id)
        .first()
    )
    if legacy is not None:
        refs.add(legacy.decided_by)
    wanted_holders: dict[str, list[str]] = {}
    codes = guides.current_codes(db, tenant_id)
    for market in shown:
        wanted_holders[market] = training.holders(
            db, tenant_id, training.for_market(market, db, tenant_id), exclude=str(ctx.user_id)
        )
        refs |= set(wanted_holders[market])
    names = people(control_db, tenant_id, [ref for ref in refs if ref])
    trial = is_trial(control_db, tenant_id)
    items = []
    for market in shown:
        versions = by_market.get(market, [])
        current, draft = assessments.current_and_draft(versions)
        evaluation = markets.evaluate(market, draft.answers or {}) if draft is not None else None
        # A draft keeps the guide version it was started with; a new assessment uses the one published now (T-G15).
        question_set = guides.by_code(db, tenant_id, market, draft.question_set if draft is not None else None)
        items.append(
            {
                "market": market,
                "label": markets.MARKET_LABELS[market],
                "enabled": market in enabled,
                "preselected": market in markets.markets_of(record.get("country")),
                "required": market in summary,
                "question_set": question_set.as_dict(),
                "suggestions": markets.suggestions(question_set, record),
                # Beside a judgement question, what the record says, never its answer (0.10.83, D2).
                "record_notes": markets.record_notes(question_set, record),
                "question_set_current": question_set.version == codes[market],
                "threshold": {"level": markets.THRESHOLDS[market], "label": markets.THRESHOLD_LABELS[market]},
                "current": assessments.row_view(current, names, codes[market]),
                "draft": assessments.row_view(draft, names, codes[market]),
                "evaluation": evaluation,
                "disagreement": markets.disagreement(market, draft.answers or {}, draft.harm_level) if draft else None,
                "history": [
                    assessments.row_view(row, names, codes[market])
                    for row in reversed(versions)
                    if row not in (current, draft)
                ],
                "clock": (summary.get(market) or {}).get("clock"),
                "training": training.status(db, tenant_id, ctx.user_id, training.for_market(market, db, tenant_id)),
                "trained_colleagues": [names.get(ref) or "A colleague" for ref in wanted_holders[market]],
            }
        )
    return {
        "complaint": {**record, **seen},
        "on_watch": _on_watch(complaint, record, second_look),
        "enabled_markets": enabled,
        "preselected": markets.market_of(record.get("country")),
        "markets": items,
        "scale": markets.scale(),
        "severity": record.get("severity"),
        **_severity_level(db, tenant_id, complaint_id, record.get("severity")),
        "answer_labels": markets.ANSWER_LABELS,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
        "training_required": True,  # RSK-011: every organization (owner, 12 Nov 2026)
        "legacy_decision": (
            {**service.decision_view(legacy, names), "note": LEGACY_NOTE} if legacy is not None else None
        ),
    }


@router.get("/{complaint_id}/market-assessments")
def market_assessments(
    complaint_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return detail(db, control_db, ctx, complaint_id)


def _clean_draft(question_set: markets.QuestionSet, payload: DraftRequest, record: dict) -> dict:
    answers = markets.clean_answers(question_set, {key: value.model_dump() for key, value in payload.answers.items()})
    confirmed = {key for key, value in payload.answers.items() if value.confirmed}
    markets.mark_origins(answers, markets.suggestions(question_set, record), confirmed)
    return {
        "answers": answers,
        "harm_level": (payload.harm_level or "").strip().upper() or None,
        "harm_code": (payload.harm_code or "").strip().upper() or None,
        "harm_level_reason": _collapse(payload.harm_level_reason) or None,
        "scale_disagreement_reason": _collapse(payload.scale_disagreement_reason) or None,
    }


@router.put("/{complaint_id}/market-assessments/{market}", dependencies=[DECIDERS])
def save_draft(
    complaint_id: uuid.UUID,
    market: str,
    payload: DraftRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Save the market's answers and harm level as a draft (no conclusion yet); returns the suggestion so far."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    market = _market(market)
    today = deadlines.as_moment(None)
    complaint, record, seen, second_look = _found(db, tenant_id, complaint_id, today)
    versions = _versions(db, tenant_id, complaint_id, market, lock=True)
    if not versions and not _on_watch(complaint, record, second_look):
        raise _error(
            409,
            "NOT_ON_WATCH",
            "This complaint is not on the reportability watch: it reports no death, serious injury or malfunction, "
            "and no patient with an unknown outcome",
        )
    windows = service.settings_of(db, tenant_id)["windows"]
    if market not in markets.enabled_markets(windows) and not versions:
        raise _error(
            409,
            "MARKET_NOT_ENABLED",
            f"{markets.MARKET_LABELS[market]} is not enabled: enter its reporting window in Reporting windows first",
        )
    draft = next((row for row in versions if row.conclusion is None), None)
    question_set = guides.by_code(db, tenant_id, market, draft.question_set if draft is not None else None)
    clean = _clean_draft(question_set, payload, record)
    problem = markets.answers_problem(question_set, clean["answers"], complete=False) or markets.harm_problem(
        clean["harm_level"],
        clean["harm_code"],
        clean["harm_level_reason"] or "",
        record.get("severity"),
        complete=False,
    )
    if problem:
        raise _error(422, "ASSESSMENT_INVALID", problem)
    evaluation = markets.evaluate(market, clean["answers"])
    aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
    clock = markets.market_clock(
        market,
        evaluation["suggested"],
        evaluation["report_type"],
        windows,
        aware,
        today,
        seen.get("org_zone"),
        evaluation["report_type_if_reportable"],
    )
    now = datetime.now(timezone.utc)
    action = "COMPLAINT_MARKET_ASSESSMENT_SAVED"
    if draft is None:
        draft = ComplaintMarketAssessment(
            tenant_id=tenant_id,
            complaint_id=complaint_id,
            market=market,
            version=max((row.version for row in versions), default=0) + 1,
            created_by=str(ctx.user_id),
            created_at=now,
        )
        db.add(draft)
        action = "COMPLAINT_MARKET_ASSESSMENT_STARTED"
    draft.question_set, draft.scale_version = question_set.version, markets.SCALE_VERSION
    for key, value in clean.items():
        setattr(draft, key, value)
    draft.suggested_conclusion, draft.report_type = evaluation["suggested"], evaluation["report_type"]
    draft.window_name = clock["window"] if clock else None
    draft.due_on = date.fromisoformat(clock["due_date"]) if clock else None
    draft.updated_at = now
    db.flush()
    # Each Unknown on a question that drives the conclusion raises a request to the reporter (T-G30).
    from backend.app.communications.service import ensure_assessment_request

    unknown = [
        question.id
        for question in question_set.questions
        if not question.extra and (clean["answers"].get(question.id) or {}).get("answer") == markets.UNKNOWN
    ]
    ensure_assessment_request(db, tenant_id, complaint, market, unknown, {}, str(ctx.user_id), now)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            details={
                "complaint": complaint_ref(record),
                "market": market,
                "version": draft.version,
                "question_set": question_set.version,
                "suggested": evaluation["suggested"],
                "answered": len(clean["answers"]),
                "answer_origins": markets.origins(clean["answers"]),
            },
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "SAVED_MEANWHILE", "Someone saved this market a moment ago; reload to see it") from exc
    return detail(db, control_db, ctx, complaint_id, today)


@router.post("/{complaint_id}/market-assessments/{market}/sign", dependencies=[DECIDERS])
def sign_conclusion(
    complaint_id: uuid.UUID,
    market: str,
    payload: SignRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Sign the market's conclusion on the saved draft: every answer with its rationale, the harm level and the scale
    version, the question-set version, the suggestion, the conclusion and any override reason are what is signed."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import fingerprint, signature_hash

    tenant_id = uuid.UUID(ctx.tenant_id)
    market = _market(market)
    today = deadlines.as_moment(None)
    complaint, record, seen, _ = _found(db, tenant_id, complaint_id, today)
    ref = record["business_id"] or record["complaint_identifier"]
    if seen["needs"]:
        # Never signed on a guessed fact (0.10.81, F3, F4): the country or the awareness date first.
        raise _error(
            409,
            "FACT_NEEDED",
            f"Enter {facts.labels(seen['needs'])} before signing: "
            + " ".join(item["message"] for item in seen["needs"]),
            needs=seen["needs"],
        )
    versions = _versions(db, tenant_id, complaint_id, market)
    draft = next((row for row in versions if row.conclusion is None), None)
    if draft is None:
        raise _error(409, "NO_DRAFT", "Save the answers before signing the conclusion")
    if draft.version != payload.version or not _same_moment(draft.updated_at, payload.saved_at):
        raise _error(409, "DRAFT_CHANGED", "The answers changed since you opened them; reload and read them again")
    # The draft keeps the guide version it was started with (T-G15); the scale is fixed in the trial.
    question_set = guides.by_code(db, tenant_id, market, draft.question_set)
    if draft.scale_version != markets.SCALE_VERSION:
        raise _error(409, "QUESTIONS_CHANGED", "The harm-severity scale has a new version: save the answers again")
    answers = draft.answers or {}
    evaluation = markets.evaluate(market, answers)
    conclusion = str(payload.conclusion or "").strip().upper()
    override_reason = _collapse(payload.override_reason)
    disagreement = markets.disagreement(market, answers, draft.harm_level)
    problem = (
        markets.answers_problem(question_set, answers, complete=True)
        or markets.harm_problem(
            draft.harm_level, draft.harm_code, draft.harm_level_reason or "", record.get("severity"), complete=True
        )
        or (
            f"{disagreement}: give the written reason in at least {markets.REASON_MIN} characters"
            if disagreement and len(draft.scale_disagreement_reason or "") < markets.REASON_MIN
            else None
        )
        or markets.conclusion_problem(evaluation["suggested"], conclusion, override_reason)
    )
    if problem:
        raise _error(422, "ASSESSMENT_INCOMPLETE", problem)
    # Re-signing (a new version over a signed one) says why the conclusion changes, as a disposition does (OD-4).
    resigning = any(row.conclusion is not None and row.superseded_by is None for row in versions)
    change_reason = _collapse(payload.change_reason) if resigning else ""
    if resigning and len(change_reason) < markets.REASON_MIN:
        raise _error(
            422,
            "CHANGE_REASON_NEEDED",
            f"This market's conclusion is signed already: say in at least {markets.REASON_MIN} characters why it "
            "changes",
        )
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign market conclusions")
    needed = training.for_market(market, db, tenant_id)
    untrained = training.missing(db, tenant_id, ctx.user_id, needed)
    trial = is_trial(control_db, tenant_id)
    # RSK-011 (owner, 12 Nov 2026, replacing decision 6 of 31 Oct): the record on the current versions comes first in
    # every organization; in a free trial it is a practice acknowledgement (T-G40P).
    if untrained:
        trained = training.holders(db, tenant_id, needed, exclude=str(ctx.user_id))
        names = people(control_db, tenant_id, trained)
        raise _error(
            409,
            "TRAINING_REQUIRED",
            f"Before you sign, record your {'practice ' if trial else ''}training on "
            + " and ".join(f"{document.title}, version {document.version}" for document in untrained)
            + ". Read each one and confirm it on this screen (Signer training).",
            missing=[document.as_dict() for document in untrained],
            trained_colleagues=[names.get(user) or "A colleague" for user in trained],
        )
    draft_id = draft.id

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="Complaint",
                entity_id=complaint_id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "MARKET_CONCLUSION_SIGN", "complaint": ref, "market": market},
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )

    now = datetime.now(timezone.utc)
    versions = _versions(db, tenant_id, complaint_id, market, lock=True)
    draft = next((row for row in versions if row.id == draft_id and row.conclusion is None), None)
    if draft is None or not _same_moment(draft.updated_at, payload.saved_at):
        raise _error(409, "DRAFT_CHANGED", "The answers changed a moment ago; reload and read them again")
    report_type = evaluation["report_type_if_reportable"] if conclusion == markets.REPORTABLE else None
    if not disagreement:
        draft.scale_disagreement_reason = None  # a reason typed for answers since changed is not part of the record
    windows = service.settings_of(db, tenant_id)["windows"]
    aware = datetime.fromisoformat(seen["aware_at"]) if seen["aware_at"] else None
    clock = markets.market_clock(market, conclusion, report_type, windows, aware, today, seen.get("org_zone"))
    material = {
        "complaint_id": str(complaint_id),
        "complaint": ref,
        "market": market,
        "version": draft.version,
        "question_set": draft.question_set,
        "questions": {
            question.id: {
                "text": question.text,
                "clause": question.clause,
                **({"extra": True} if question.extra else {}),
            }
            for question in question_set.questions
        },
        "answers": answers,
        "harm_level": draft.harm_level,
        "harm_code": draft.harm_code,
        "harm_level_reason": draft.harm_level_reason,
        "scale_version": draft.scale_version,
        "scale_disagreement": disagreement,
        "scale_disagreement_reason": draft.scale_disagreement_reason,
        "suggested": evaluation["suggested"],
        "conclusion": conclusion,
        "override_reason": override_reason or None,
        # Signed with a re-signed version only, so a first signature's content is as before (OD-4).
        **({"change_reason": change_reason} if change_reason else {}),
        "report_type": report_type,
        "due_on": clock["due_date"] if clock else None,
        "due_label": clock["due_label"] if clock else None,
        "training": [document.as_dict() for document in needed if document not in untrained],
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
    }
    content_fingerprint = fingerprint(material)
    object_version = str(draft.version)
    record_row = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=draft.id,
        object_version=object_version,
        decision_type=DECISION_TYPE,
        decision=SIGNATURE_CODES[conclusion],
        remarks=override_reason or f"Suggested {markets.CONCLUSION_LABELS[evaluation['suggested']].lower()}; confirmed",
        signer_user_id=str(ctx.user_id),
        signer_role=role or "UNKNOWN",
        signature_meaning=markets.signature_meaning(ref, market, draft.question_set, conclusion),
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, str(ctx.user_id), object_version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record_row)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMPLAINT_MARKET_CONCLUSION_SIGNED",
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            reason=change_reason or override_reason or None,
            details={
                "complaint": ref,
                "market": market,
                "change_reason": change_reason or None,
                "version": draft.version,
                "question_set": draft.question_set,
                "scale_version": draft.scale_version,
                "suggested": evaluation["suggested"],
                "conclusion": conclusion,
                "overridden": conclusion != evaluation["suggested"],
                "answer_origins": markets.origins(answers),
                "report_type": report_type,
                "signature_id": str(record_row.id),
                "fingerprint": content_fingerprint,
                "signer_role": role,
            },
            new_values={"conclusion": conclusion},
            created_at=now,
        )
    )
    for earlier in versions:
        if earlier.conclusion is not None and earlier.superseded_by is None:
            earlier.superseded_by = draft.id
    draft.conclusion, draft.override_reason, draft.report_type = conclusion, override_reason or None, report_type
    draft.change_reason = change_reason or None
    draft.suggested_conclusion = evaluation["suggested"]
    draft.window_name = clock["window"] if clock else None
    draft.due_on = date.fromisoformat(clock["due_date"]) if clock else None
    draft.signed_record_id, draft.content_fingerprint = record_row.id, content_fingerprint
    draft.signed_by, draft.signed_at, draft.updated_at = str(ctx.user_id), now, now
    retyped = _settle_open_reports(db, ctx, tenant_id, complaint_id, market, draft, now)
    # 0.10.75 (C3), the new navigation: the signed conclusion creates the market's report, or cancels an unsubmitted
    # one when it says not reportable, in this same transaction. Never on a draft (saving answers never comes here).
    from backend.app.authority_reports import router as reports

    ended = (
        reports.follow_conclusion(db, ctx, tenant_id, complaint_id, market, draft, now)
        if reports.new_navigation(control_db, tenant_id)
        else []
    )
    try:
        signing_commit.commit(db, control_db, "market conclusion")
    except IntegrityError as exc:
        db.rollback()
        control_db.rollback()
        raise _error(409, "SIGNED_MEANWHILE", "This market was signed a moment ago; reload to see it") from exc
    reports.end_cancelled_approvals(db, ctx, tenant_id, ended)
    reports.end_cancelled_approvals(db, ctx, tenant_id, retyped, "Replaced: the conclusion was signed again")
    if assessments.settled(
        assessments.markets_summary(
            record,
            windows,
            assessments.rows_by_complaint(db, tenant_id, [complaint_id]).get(complaint_id, {}),
            aware,
            today,
            seen.get("org_zone"),
        )
    ):
        from backend.app.reportability.router import _finish_reminders

        _finish_reminders(db, tenant_id, complaint_id, "MARKETS_CONCLUDED", ctx)
    return detail(db, control_db, ctx, complaint_id, today)


@router.put("/{complaint_id}/reporting-facts", dependencies=[DECIDERS])
def set_reporting_facts(
    complaint_id: uuid.UUID,
    payload: FactsRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Enter a fact the reporting steps need and the record does not give (0.10.81, facts.py): the incident country (a
    country by name or ISO code) or the awareness date (a day, kept as a day). Audited with before and after."""
    from datetime import time

    from backend.app.db.models.foundation import Complaint

    tenant_id = uuid.UUID(ctx.tenant_id)
    complaint = (
        db.query(Complaint)
        .filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id)
        .with_for_update()
        .one_or_none()
    )
    if complaint is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    old: dict = {}
    new: dict = {}
    if payload.country is not None:
        country = _collapse(payload.country)
        if rules.names_the_uk_whole(country):
            raise _error(
                422,
                "COUNTRY_UK_PART_NEEDED",
                "Choose Great Britain or Northern Ireland: Northern Ireland follows the EU MDR",
            )
        if not facts.country_known(country):
            raise _error(
                422,
                "COUNTRY_UNKNOWN",
                "Enter the country by name or by its two-letter ISO code, for example India, IN, Germany or GB",
            )
        if country != complaint.country:
            old["country"], new["country"] = complaint.country, country
            complaint.country = country
    if payload.awareness_date is not None:
        if payload.awareness_date > service.today_utc():
            raise _error(422, "AWARENESS_IN_FUTURE", "The awareness date cannot be in the future")
        event = service._day(complaint.event_timestamp)
        if event is not None and payload.awareness_date < event:
            raise _error(
                422,
                "AWARENESS_BEFORE_EVENT",
                f"The awareness date cannot be before the event ({event.isoformat()}): check both dates",
            )
        # A day without a time, kept as the import keeps one (12:00 UTC: the same day in every market's time zone).
        moment = datetime.combine(payload.awareness_date, time(12), timezone.utc)
        if moment != complaint.awareness_timestamp:
            old["awareness_date"] = (
                service._day(complaint.awareness_timestamp).isoformat() if complaint.awareness_timestamp else None
            )
            new["awareness_date"] = payload.awareness_date.isoformat()
            complaint.awareness_timestamp = moment
    if not new:
        raise _error(422, "NOTHING_TO_CHANGE", "Enter the country or the awareness date")
    now = datetime.now(timezone.utc)
    complaint.updated_at = now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMPLAINT_REPORTING_FACTS_SET",
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            details={"complaint": complaint_ref(complaint), "fields": sorted(new)},
            old_values=old,
            new_values=new,
            created_at=now,
        )
    )
    db.commit()
    return detail(db, control_db, ctx, complaint_id)


@router.post("/{complaint_id}/market-assessments/{market}/filing", dependencies=[DECIDERS])
def record_filing(
    complaint_id: uuid.UUID,
    market: str,
    payload: FilingRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record where and when the organization reported (outside MDARIX) on the market's signed reportable conclusion."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    market = _market(market)
    today = service.today_utc()
    _, record, seen, _ = _found(db, tenant_id, complaint_id, today)
    reference = _collapse(payload.filing_reference)
    if not reference or len(reference) > rules.REFERENCE_MAX:
        raise _error(422, "REPORT_DETAILS_REQUIRED", "Give the report's reference (for example the MDR number)")
    if payload.filed_on > today:
        raise _error(422, "REPORTED_IN_FUTURE", "The day the report was filed cannot be in the future")
    aware = date.fromisoformat(seen["aware_date"]) if seen["aware_date"] else None
    if aware is not None and payload.filed_on < aware:
        raise _error(
            422, "REPORTED_BEFORE_AWARENESS", "The report cannot be filed before the organization became aware"
        )
    current, _ = assessments.current_and_draft(_versions(db, tenant_id, complaint_id, market, lock=True))
    if current is None or current.conclusion != markets.REPORTABLE:
        raise _error(409, "NOT_REPORTABLE_CONCLUSION", "Record a filing on a signed reportable conclusion")
    from backend.app.db.models.authority_reports import ReportObligation

    if (
        db.query(ReportObligation.id)
        .filter(
            ReportObligation.tenant_id == tenant_id,
            ReportObligation.complaint_id == complaint_id,
            ReportObligation.market == market,
            ReportObligation.kind == "INITIAL",
        )
        .first()
        is not None
    ):
        # G2b: a report with a worksheet is met only by its submission record (a receipt is not acceptance).
        raise _error(
            409,
            "REPORT_OBLIGATION_OPEN",
            "This market's report has a worksheet: record the submission on it in Reports",
        )
    old = {
        "filing_reference": current.filing_reference,
        "filed_on": current.filed_on.isoformat() if current.filed_on else None,
    }
    if (current.filing_reference, current.filed_on) == (reference, payload.filed_on):
        raise _error(422, "NOTHING_TO_CHANGE", "This filing is already recorded")
    now = datetime.now(timezone.utc)
    current.filing_reference, current.filed_on, current.updated_at = reference, payload.filed_on, now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMPLAINT_MARKET_FILING_RECORDED",
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            details={
                "complaint": complaint_ref(record),
                "market": market,
                "version": current.version,
            },
            old_values=old if old["filed_on"] else None,
            new_values={"filing_reference": reference, "filed_on": payload.filed_on.isoformat()},
            created_at=now,
        )
    )
    db.commit()
    return detail(db, control_db, ctx, complaint_id, today)
