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
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.reportability import assessments, markets, rules, service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training import service as training
from backend.app.signer_training.router import is_trial
from backend.app.standards import STARTER_MARK

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


class DraftRequest(BaseModel):
    answers: dict[str, AnswerIn] = Field(default_factory=dict, max_length=40)
    harm_level: str | None = Field(default=None, max_length=20)
    harm_code: str | None = Field(default=None, max_length=60)
    harm_level_reason: str = Field(default="", max_length=2000)
    scale_disagreement_reason: str = Field(default="", max_length=2000)


class SignRequest(BaseModel):
    conclusion: str = Field(max_length=30)
    override_reason: str = Field(default="", max_length=2000)
    # The draft the person read: a draft saved again meanwhile is refused, so nobody signs what they did not see.
    version: int = Field(ge=1)
    saved_at: str = Field(max_length=40)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


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


def _versions(db: Session, tenant_id, complaint_id, market: str, lock: bool = False):
    query = db.query(ComplaintMarketAssessment).filter(
        ComplaintMarketAssessment.tenant_id == tenant_id,
        ComplaintMarketAssessment.complaint_id == complaint_id,
        ComplaintMarketAssessment.market == market,
    )
    if lock:
        query = query.with_for_update()
    return query.order_by(ComplaintMarketAssessment.version).all()


def detail(db: Session, control_db: Session, ctx, complaint_id: uuid.UUID, today: date | None = None) -> dict:
    """Everything the assessment screen shows for one complaint: each market's questions, versions and draft, the
    scale with the complaint's mapped level, the person's training on what a signature relies on, and any earlier
    single decision."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    today = today or service.today_utc()
    complaint, record, seen, second_look = _found(db, tenant_id, complaint_id, today)
    windows = service.settings_of(db, tenant_id)["windows"]
    by_market = assessments.rows_by_complaint(db, tenant_id, [complaint_id]).get(complaint_id, {})
    enabled = markets.enabled_markets(windows)
    aware = date.fromisoformat(seen["aware_date"]) if seen["aware_date"] else None
    summary = {item["market"]: item for item in assessments.markets_summary(record, windows, by_market, aware, today)}
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
    for market in shown:
        wanted_holders[market] = training.holders(db, tenant_id, training.for_market(market), exclude=str(ctx.user_id))
        refs |= set(wanted_holders[market])
    names = people(control_db, tenant_id, [ref for ref in refs if ref])
    trial = is_trial(control_db, tenant_id)
    items = []
    for market in shown:
        versions = by_market.get(market, [])
        current, draft = assessments.current_and_draft(versions)
        evaluation = markets.evaluate(market, draft.answers or {}) if draft is not None else None
        items.append(
            {
                "market": market,
                "label": markets.MARKET_LABELS[market],
                "enabled": market in enabled,
                "preselected": market == markets.market_of(record.get("country")),
                "required": market in summary,
                "question_set": markets.QUESTION_SETS[market].as_dict(),
                "threshold": {"level": markets.THRESHOLDS[market], "label": markets.THRESHOLD_LABELS[market]},
                "current": assessments.row_view(current, names),
                "draft": assessments.row_view(draft, names),
                "evaluation": evaluation,
                "disagreement": markets.disagreement(market, draft.answers or {}, draft.harm_level) if draft else None,
                "history": [
                    assessments.row_view(row, names) for row in reversed(versions) if row not in (current, draft)
                ],
                "clock": (summary.get(market) or {}).get("clock"),
                "training": training.status(db, tenant_id, ctx.user_id, training.for_market(market)),
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
        "severity_level": markets.level_of_severity(record.get("severity")),
        "answer_labels": markets.ANSWER_LABELS,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
        "training_required": trial,
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


def _clean_draft(market: str, payload: DraftRequest) -> dict:
    question_set = markets.QUESTION_SETS[market]
    answers = markets.clean_answers(question_set, {key: value.model_dump() for key, value in payload.answers.items()})
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
    today = service.today_utc()
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
    clean = _clean_draft(market, payload)
    question_set = markets.QUESTION_SETS[market]
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
    aware = date.fromisoformat(seen["aware_date"]) if seen["aware_date"] else None
    clock = markets.market_clock(market, evaluation["suggested"], evaluation["report_type"], windows, aware, today)
    now = datetime.now(timezone.utc)
    draft = next((row for row in versions if row.conclusion is None), None)
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
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            details={
                "complaint": record["business_id"] or record["complaint_identifier"],
                "market": market,
                "version": draft.version,
                "question_set": question_set.version,
                "suggested": evaluation["suggested"],
                "answered": len(clean["answers"]),
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
    today = service.today_utc()
    complaint, record, seen, _ = _found(db, tenant_id, complaint_id, today)
    ref = record["business_id"] or record["complaint_identifier"]
    versions = _versions(db, tenant_id, complaint_id, market)
    draft = next((row for row in versions if row.conclusion is None), None)
    if draft is None:
        raise _error(409, "NO_DRAFT", "Save the answers before signing the conclusion")
    if draft.version != payload.version or not _same_moment(draft.updated_at, payload.saved_at):
        raise _error(409, "DRAFT_CHANGED", "The answers changed since you opened them; reload and read them again")
    question_set = markets.QUESTION_SETS[market]
    if draft.question_set != question_set.version or draft.scale_version != markets.SCALE_VERSION:
        raise _error(409, "QUESTIONS_CHANGED", "The questions or the scale have a new version: save the answers again")
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
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign market conclusions")
    needed = training.for_market(market)
    untrained = training.missing(db, tenant_id, ctx.user_id, needed)
    trial = is_trial(control_db, tenant_id)
    # Decision 6 (31 Oct 2026): the practice-training rule binds trial organisations only; pilots get G40 later.
    if untrained and trial:
        trained = training.holders(db, tenant_id, needed, exclude=str(ctx.user_id))
        names = people(control_db, tenant_id, trained)
        raise _error(
            409,
            "TRAINING_REQUIRED",
            "Before you sign, record your practice training on "
            + " and ".join(f"{document.title}, version {document.version}" for document in untrained)
            + ".",
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
    aware = date.fromisoformat(seen["aware_date"]) if seen["aware_date"] else None
    clock = markets.market_clock(market, conclusion, report_type, windows, aware, today)
    material = {
        "complaint_id": str(complaint_id),
        "complaint": ref,
        "market": market,
        "version": draft.version,
        "question_set": draft.question_set,
        "questions": {
            question.id: {"text": question.text, "clause": question.clause} for question in question_set.questions
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
        "report_type": report_type,
        "due_on": clock["due_date"] if clock else None,
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
            reason=override_reason or None,
            details={
                "complaint": ref,
                "market": market,
                "version": draft.version,
                "question_set": draft.question_set,
                "scale_version": draft.scale_version,
                "suggested": evaluation["suggested"],
                "conclusion": conclusion,
                "overridden": conclusion != evaluation["suggested"],
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
    draft.suggested_conclusion = evaluation["suggested"]
    draft.window_name = clock["window"] if clock else None
    draft.due_on = date.fromisoformat(clock["due_date"]) if clock else None
    draft.signed_record_id, draft.content_fingerprint = record_row.id, content_fingerprint
    draft.signed_by, draft.signed_at, draft.updated_at = str(ctx.user_id), now, now
    try:
        if db is control_db:
            control_db.commit()  # the shared plane: everything in one transaction
        else:
            # A dedicated plane: the signature and its audit trail first (as decision signing does), then the record.
            control_db.commit()
            try:
                db.commit()
            except Exception:
                logger.exception("Signature %s was saved but its market conclusion %s was not", record_row.id, draft_id)
                raise
    except IntegrityError as exc:
        db.rollback()
        control_db.rollback()
        raise _error(409, "SIGNED_MEANWHILE", "This market was signed a moment ago; reload to see it") from exc
    if assessments.settled(
        assessments.markets_summary(
            record,
            windows,
            assessments.rows_by_complaint(db, tenant_id, [complaint_id]).get(complaint_id, {}),
            aware,
            today,
        )
    ):
        from backend.app.reportability.router import _finish_reminders

        _finish_reminders(db, tenant_id, complaint_id, "MARKETS_CONCLUDED", ctx)
    return detail(db, control_db, ctx, complaint_id, today)


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
                "complaint": record["business_id"] or record["complaint_identifier"],
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
