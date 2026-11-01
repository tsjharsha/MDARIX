"""Authority report worksheets and the obligation lifecycle API (T-G2c, T-G2b; MVP G2c, G2b).

- ``GET /api/v1/reports``: every report obligation from a market assessment (reportable, or pending with its
  provisional deadline), started or not, with its state, deadline and next step (``complaint_id`` narrows);
- ``POST /api/v1/reports``: start the worksheet of one complaint and market (US: Form FDA 3500A; India: the MvPI
  MDAE form, Version 1.2);
- ``GET /api/v1/reports/{id}``: the worksheet in the authority's field order, every field with its status and source,
  the snapshots, the complete submission record and any response obligation;
- ``PUT /api/v1/reports/{id}/fields/{field}``: enter a value or confirm a record's value (never a patient or reporter
  field: those are entered in the authority's route, T-B9);
- ``POST /api/v1/reports/{id}/snapshots`` and ``/snapshots/{sid}/approve``: freeze the worksheet, and a second person
  approves it with password and authenticator code: never the preparer, never the signer of the market conclusion
  behind it, never an administrator (D-T19: the trial enforces it, as G2b does);
- ``POST /api/v1/reports/{id}/reopen``: back to draft before submission (a correction needs a new approval);
- ``POST /api/v1/reports/{id}/submissions``: record what the person submitted outside MDARIX: the route, the time, the
  submitted content and the difference review; ``.../evidence``: receipts, acknowledgements, acceptance or rejection;
- ``POST /api/v1/reports/{id}/follow-up``, ``/complete`` and ``/requests`` (a request for information creates a
  separate response obligation);
- ``GET /api/v1/reports/{id}/worksheet.pdf`` and ``.docx`` (``snapshot`` for an approved one), and an evidence file.

MDARIX never submits: no route here sends anything anywhere. Snapshots, attempts and evidence are never edited or
deleted through the API. Reading is open to every signed-in member; changes need regulatory.review or
regulatory.approve. These routes serve a free trial and a pilot alike (T-B1).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.access.permissions import DATA_EXPORT, REGULATORY_APPROVE, REGULATORY_REVIEW, require_permission
from backend.app.authority_reports import forms, rules, worksheet
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.authority_reports import ReportEvidence, ReportObligation, ReportSnapshot, ReportSubmission
from backend.app.db.models.foundation import Complaint, SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.reportability import assessments, markets, service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.standards import STARTER_MARK, chips

logger = logging.getLogger("mdarix.authority_reports")
router = APIRouter(prefix="/api/v1/reports", tags=["Authority reports"])

OBJECT_TYPE = "ReportSnapshot"
DECISION_TYPE = "REPORT_SNAPSHOT_APPROVAL"
DECIDERS = Depends(require_any_permission(REGULATORY_REVIEW, REGULATORY_APPROVE))
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SAMPLE_NAMES = {"system:trial-sample": "MDARIX sample data"}


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _text(value, limit: int = rules.NOTE_MAX) -> str | None:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise _error(422, "TEXT_TOO_LONG", f"Keep it to {limit} characters")
    return text or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _tenant(ctx) -> uuid.UUID:
    return uuid.UUID(ctx.tenant_id)


def _trial(control_db, tenant_id) -> bool:
    from backend.app.signer_training.router import is_trial

    return is_trial(control_db, tenant_id)


def _names(control_db, tenant_id, refs) -> dict[str, str]:
    found = people(control_db, tenant_id, [ref for ref in refs if ref])
    return {**SAMPLE_NAMES, **found}


def _audit(db, ctx, action: str, obligation: ReportObligation, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=obligation.tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="ReportObligation",
            entity_id=obligation.id,
            correlation_id=ctx.correlation_id,
            details={"complaint_id": str(obligation.complaint_id), "market": obligation.market, **details},
        )
    )


def _obligation(db, tenant_id, obligation_id, *, lock: bool = False) -> ReportObligation:
    query = db.query(ReportObligation).filter(
        ReportObligation.tenant_id == tenant_id, ReportObligation.id == obligation_id
    )
    found = (query.with_for_update() if lock else query).one_or_none()
    if found is None:
        raise _error(404, "REPORT_NOT_FOUND", "No such report in your organization")
    return found


def _form(obligation: ReportObligation) -> forms.Form:
    return forms.FORMS[obligation.form_code]


def _snapshots(db, obligation: ReportObligation) -> list[ReportSnapshot]:
    return (
        db.query(ReportSnapshot)
        .filter(ReportSnapshot.tenant_id == obligation.tenant_id, ReportSnapshot.obligation_id == obligation.id)
        .order_by(ReportSnapshot.version)
        .all()
    )


def _submissions(db, obligation: ReportObligation) -> list[ReportSubmission]:
    return (
        db.query(ReportSubmission)
        .filter(ReportSubmission.tenant_id == obligation.tenant_id, ReportSubmission.obligation_id == obligation.id)
        .order_by(ReportSubmission.attempt)
        .all()
    )


def _evidence(db, tenant_id, submission_ids) -> dict[uuid.UUID, list[ReportEvidence]]:
    found: dict[uuid.UUID, list[ReportEvidence]] = {}
    if submission_ids:
        for row in (
            db.query(ReportEvidence)
            .filter(ReportEvidence.tenant_id == tenant_id, ReportEvidence.submission_id.in_(list(submission_ids)))
            .order_by(ReportEvidence.received_at, ReportEvidence.recorded_at)
        ):
            found.setdefault(row.submission_id, []).append(row)
    return found


def _context(db, control_db, obligation: ReportObligation) -> dict:
    context = worksheet.load(db, control_db, obligation.tenant_id, obligation.complaint_id, obligation.market)
    if context is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "The complaint of this report no longer exists")
    return context


def _preparers(obligation: ReportObligation, extra: str | None = None) -> set[str]:
    found = {obligation.created_by, *(entry.get("by") for entry in (obligation.entries or {}).values())}
    if extra:
        found.add(extra)
    return {ref for ref in found if ref}


def _deadline(obligation: ReportObligation, context: dict, today: date) -> dict:
    """The obligation's deadline: the one it was given (a rejection never moves it); while it is provisional, the
    market assessment's current one."""
    due = obligation.due_on
    provisional = obligation.due_provisional
    if provisional:
        row = context["current"] or context["draft"]
        if row is not None and row.due_on is not None:
            due = row.due_on
            provisional = row.conclusion is None
    return {
        "due_on": _iso(due),
        "provisional": provisional,
        "days_left": (due - today).days if due else None,
        "overdue": bool(due and due < today and obligation.state not in rules.MET),
    }


def _assessment_view(context: dict, names: dict) -> dict | None:
    row = context["current"] or context["draft"]
    if row is None:
        return None
    kind = markets.REPORT_TYPES.get(row.report_type or "")
    return {
        "id": str(row.id),
        "version": row.version,
        "state": row.conclusion or "DRAFT",
        "conclusion": row.conclusion,
        "suggested": row.suggested_conclusion,
        "report_type_label": kind.label if kind else None,
        "signed_by": names.get(row.signed_by) if row.signed_by else None,
        "signed_by_id": row.signed_by,
        "signed_at": _iso(row.signed_at),
        "due_on": _iso(row.due_on),
        "filed_on": _iso(row.filed_on),
        "filing_reference": row.filing_reference,
    }


def _snapshot_view(row: ReportSnapshot, names: dict) -> dict:
    return {
        "id": str(row.id),
        "version": row.version,
        "state": row.state,
        "form_version": row.form_version,
        "content_fingerprint": row.content_fingerprint,
        "requested_by": names.get(row.requested_by) or "A colleague",
        "requested_at": _iso(row.requested_at),
        "approved_by": (names.get(row.approved_by) or "A colleague") if row.approved_by else None,
        "approved_at": _iso(row.approved_at),
        "signed_record_id": str(row.signed_record_id) if row.signed_record_id else None,
        "preparers": [names.get(ref) or "A colleague" for ref in row.preparers or []],
        "sample": row.source_system is not None,
    }


def _evidence_view(row: ReportEvidence, names: dict) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "kind_label": forms.EVIDENCE_LABELS.get(row.kind, row.kind),
        "outcome": row.outcome,
        "note": row.note,
        "file_name": row.file_name,
        "size": row.size,
        "sha256": row.sha256,
        "received_at": _iso(row.received_at),
        "recorded_by": names.get(row.recorded_by) or "A colleague",
        "recorded_at": _iso(row.recorded_at),
    }


def _submission_view(row: ReportSubmission, evidence: list[ReportEvidence], names: dict, due_on) -> dict:
    return {
        "id": str(row.id),
        "attempt": row.attempt,
        "route": row.route,
        "route_label": forms.ROUTE_LABELS.get(row.route, row.route),
        "submitted_at": _iso(row.submitted_at),
        "content_note": row.content_note,
        "differences": row.differences or [],
        "authority_reference": row.authority_reference,
        "result": row.result,
        "result_at": _iso(row.result_at),
        "late": row.late,
        "follow_up": rules.follow_up(row.submitted_at, due_on, row.route) if row.result == "PENDING" else None,
        "recorded_by": names.get(row.recorded_by) or "A colleague",
        "recorded_at": _iso(row.recorded_at),
        "evidence": [_evidence_view(item, names) for item in evidence],
        "receipt_only": row.result == "PENDING" and any(item.outcome == "RECEIPT" for item in evidence),
        "sample": row.source_system is not None,
    }


def _refs(obligation, snapshots, submissions, evidence, context) -> set:
    refs = _preparers(obligation)
    for row in snapshots:
        refs |= {row.requested_by, row.approved_by, *(row.preparers or [])}
    for row in submissions:
        refs.add(row.recorded_by)
    for rows in evidence.values():
        refs |= {item.recorded_by for item in rows}
    for row in (context["current"], context["draft"]):
        if row is not None:
            refs.add(row.signed_by)
    return refs


def detail(db, control_db, ctx, obligation: ReportObligation) -> dict:
    tenant_id = obligation.tenant_id
    today = service.today_utc()
    form = _form(obligation)
    context = _context(db, control_db, obligation)
    snapshots = _snapshots(db, obligation)
    submissions = _submissions(db, obligation)
    evidence = _evidence(db, tenant_id, [row.id for row in submissions])
    names = _names(control_db, tenant_id, _refs(obligation, snapshots, submissions, evidence, context))
    sections = worksheet.build(form, context, obligation.entries or {}, names, obligation.request_text)
    deadline = _deadline(obligation, context, today)
    due = date.fromisoformat(deadline["due_on"]) if deadline["due_on"] else None
    pending = next((row for row in snapshots if row.state == "PENDING"), None)
    children = (
        db.query(ReportObligation)
        .filter(ReportObligation.tenant_id == tenant_id, ReportObligation.parent_id == obligation.id)
        .order_by(ReportObligation.created_at)
        .all()
    )
    signer = (context["current"].signed_by if context["current"] else None) or None
    trial = _trial(control_db, tenant_id)
    record = context["record"]
    return {
        "id": str(obligation.id),
        "kind": obligation.kind,
        "complaint": {
            "id": record["id"],
            "ref": record["business_id"] or record["complaint_identifier"],
            "complaint_identifier": record["complaint_identifier"],
            "product_name": record["product_name"],
            "version": record["version"],
            "country": record["country"],
            "description": record["description"],
            "aware_date": context["seen"].get("aware_date"),
            "sample": context["sample"],
        },
        "market": obligation.market,
        "market_label": markets.MARKET_LABELS.get(obligation.market, obligation.market),
        "form": {
            "code": form.code,
            "title": form.title,
            "version": obligation.form_version,
            "authority": form.authority,
            "source_document": form.source_document,
            "clauses": chips(form.basis),
        },
        "routes": [
            {
                "code": route.code,
                "label": route.label,
                "note": route.note,
                "acknowledgement_expected": route.acknowledgement_expected,
                "evidence": [
                    {"kind": kind, "label": forms.EVIDENCE_LABELS[kind], "outcomes": list(outcomes)}
                    for kind, outcomes in route.evidence.items()
                ],
            }
            for route in forms.routes_for(form)
        ],
        "state": obligation.state,
        "state_label": rules.STATE_LABELS[obligation.state],
        "next_step": rules.next_step(obligation.state, pending is not None),
        "steps": [{"state": step, "label": rules.STATE_LABELS[step]} for step in rules.STEPS],
        "deadline": deadline,
        "report_type": obligation.report_type,
        "assessment": _assessment_view(context, names),
        "case": worksheet.SOURCES["case"](context)[0] if context["case"] else None,
        "sections": sections,
        "counts": worksheet.counts(sections),
        "status_labels": worksheet.STATUS_LABELS,
        "editable": obligation.state in rules.EDITABLE,
        "snapshots": [_snapshot_view(row, names) for row in reversed(snapshots)],
        "pending_snapshot": _snapshot_view(pending, names) if pending else None,
        "cannot_approve": sorted({names.get(ref) or "A colleague" for ref in (*_preparers(obligation), signer) if ref}),
        "submissions": [_submission_view(row, evidence.get(row.id, []), names, due) for row in reversed(submissions)],
        "request": (
            {"text": obligation.request_text, "received_on": _iso(obligation.request_received_on)}
            if obligation.kind == "RESPONSE"
            else None
        ),
        "parent_id": str(obligation.parent_id) if obligation.parent_id else None,
        "responses": [
            {
                "id": str(row.id),
                "state": row.state,
                "state_label": rules.STATE_LABELS[row.state],
                "due_on": _iso(row.due_on),
                "request_text": row.request_text,
            }
            for row in children
        ],
        "note": obligation.note,
        "follow_up_due_on": _iso(obligation.follow_up_due_on),
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
        "never_submits": rules.NEVER_SUBMITS,
        "sample": obligation.source_system is not None,
    }


# --------------------------------------------------------------------------------------------- the list


def _candidates(db, tenant_id, complaint_id=None) -> list[ComplaintMarketAssessment]:
    """Each complaint and market whose assessment says reportable (signed, current) or pending (a draft): the market
    obligations G2b tracks."""
    query = db.query(ComplaintMarketAssessment).filter(ComplaintMarketAssessment.tenant_id == tenant_id)
    if complaint_id:
        query = query.filter(ComplaintMarketAssessment.complaint_id == complaint_id)
    rows = query.order_by(ComplaintMarketAssessment.version).all()
    by_key: dict[tuple, list] = {}
    for row in rows:
        by_key.setdefault((row.complaint_id, row.market), []).append(row)
    found = []
    for versions in by_key.values():
        current, draft = assessments.current_and_draft(versions)
        if current is not None and current.conclusion == markets.REPORTABLE:
            found.append(current)
        elif (
            current is None
            and draft is not None
            and draft.suggested_conclusion in (markets.REPORTABLE, markets.PENDING)
        ):
            found.append(draft)
    return found


@router.get("")
def report_list(
    complaint_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    today = service.today_utc()
    obligations_query = db.query(ReportObligation).filter(ReportObligation.tenant_id == tenant_id)
    if complaint_id:
        obligations_query = obligations_query.filter(ReportObligation.complaint_id == complaint_id)
    obligations = obligations_query.all()
    started = {(row.complaint_id, row.market): row for row in obligations if row.kind == "INITIAL"}
    candidates = _candidates(db, tenant_id, complaint_id)
    complaint_ids = {row.complaint_id for row in candidates} | {row.complaint_id for row in obligations}
    complaints = {
        row.id: row
        for row in (
            db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(list(complaint_ids))).all()
            if complaint_ids
            else []
        )
    }
    items = []

    def base(complaint, market):
        return {
            "complaint_id": str(complaint.id),
            "complaint_ref": complaint.business_id or complaint.complaint_identifier,
            "complaint_identifier": complaint.complaint_identifier,
            "description": complaint.description,
            "market": market,
            "market_label": markets.MARKET_LABELS.get(market, market),
            "sample": complaint.source_system is not None,
        }

    for row in candidates:
        complaint = complaints.get(row.complaint_id)
        if complaint is None or (row.complaint_id, row.market) in started:
            continue
        form = forms.BY_MARKET.get(row.market)
        state = rules.NOT_STARTED if form else rules.NO_WORKSHEET
        if row.filed_on:
            state = rules.NO_WORKSHEET if not form else rules.NOT_STARTED
        items.append(
            {
                **base(complaint, row.market),
                "id": None,
                "kind": "INITIAL",
                "form_title": form.title if form else None,
                "form_version": form.version if form else None,
                "state": state,
                "state_label": rules.STATE_LABELS[state] if not row.filed_on else f"Filed {row.filed_on.isoformat()}",
                "next_step": rules.next_step(state),
                "due_on": _iso(row.due_on),
                "provisional": row.conclusion is None,
                "days_left": (row.due_on - today).days if row.due_on else None,
                "overdue": bool(row.due_on and row.due_on < today and not row.filed_on),
                "assessment": markets.CONCLUSION_LABELS.get(row.conclusion or row.suggested_conclusion),
                "can_start": bool(form) and not row.filed_on,
            }
        )
    for row in obligations:
        complaint = complaints.get(row.complaint_id)
        if complaint is None:
            continue
        due = row.due_on
        items.append(
            {
                **base(complaint, row.market),
                "id": str(row.id),
                "kind": row.kind,
                "form_title": forms.FORMS[row.form_code].title,
                "form_version": row.form_version,
                "state": row.state,
                "state_label": rules.STATE_LABELS[row.state],
                "next_step": rules.next_step(row.state),
                "due_on": _iso(due),
                "provisional": row.due_provisional,
                "days_left": (due - today).days if due else None,
                "overdue": bool(due and due < today and row.state not in rules.MET),
                "assessment": None,
                "can_start": False,
            }
        )
    items.sort(key=lambda item: (item["state"] in rules.MET, item["due_on"] or "9999", item["complaint_ref"] or ""))
    return {
        "items": items,
        "forms": [
            {"market": market, "title": form.title, "version": form.version} for market, form in forms.BY_MARKET.items()
        ],
        "never_submits": rules.NEVER_SUBMITS,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if _trial(control_db, tenant_id) else None,
    }


class StartRequest(BaseModel):
    complaint_id: uuid.UUID
    market: str = Field(max_length=10)


def start(db, tenant_id, complaint_id, market: str, actor: str, now: datetime, source_system: str | None = None):
    """A new initial obligation for the complaint and market, from its market assessment (shared with the sample)."""
    form = forms.BY_MARKET.get(market)
    if form is None:
        raise _error(
            409, "NO_WORKSHEET", "This market's worksheet comes later: record the filing on its signed conclusion"
        )
    candidate = next((row for row in _candidates(db, tenant_id, complaint_id) if row.market == market), None)
    if candidate is None:
        raise _error(
            409,
            "NOT_AN_OBLIGATION",
            "Assess the market first: a report is drafted for a market assessed reportable or pending information",
        )
    obligation = ReportObligation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_id=complaint_id,
        market=market,
        kind="INITIAL",
        assessment_id=candidate.id,
        form_code=form.code,
        form_version=form.version,
        report_type=candidate.report_type,
        due_on=candidate.due_on,
        due_provisional=candidate.conclusion is None,
        state=rules.DRAFT,
        entries={},
        source_system=source_system,
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    db.add(obligation)
    db.flush()
    return obligation


@router.post("", dependencies=[DECIDERS])
def start_report(
    payload: StartRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    market = str(payload.market or "").strip().upper()
    if (
        db.query(Complaint.id).filter(Complaint.tenant_id == tenant_id, Complaint.id == payload.complaint_id).first()
        is None
    ):
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    try:
        obligation = start(db, tenant_id, payload.complaint_id, market, str(ctx.user_id), _now())
        _audit(db, ctx, "REPORT_WORKSHEET_STARTED", obligation, form=obligation.form_code)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "REPORT_EXISTS", "This market's report is already started: open it from the list") from exc
    return detail(db, control_db, ctx, obligation)


@router.get("/{obligation_id}")
def report_detail(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return detail(db, control_db, ctx, _obligation(db, _tenant(ctx), obligation_id))


# --------------------------------------------------------------------------------------------- the worksheet


class FieldRequest(BaseModel):
    value: str | None = Field(default=None, max_length=worksheet.VALUE_MAX * 2)
    confirmed: bool = False
    clear: bool = False


@router.put("/{obligation_id}/fields/{field_id}", dependencies=[DECIDERS])
def set_field(
    obligation_id: uuid.UUID,
    field_id: str,
    payload: FieldRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Enter a value, confirm a record's value, or clear what a person entered (a draft only)."""
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    if obligation.state not in rules.EDITABLE:
        raise _error(409, "NOT_A_DRAFT", "Only a draft is changed: reopen it first")
    field = next((item for item in _form(obligation).fields() if item.id == field_id), None)
    if field is None:
        raise _error(404, "FIELD_UNKNOWN", "No such field on this form")
    if field.personal:
        raise _error(
            422,
            "PERSONAL_FIELD",
            "Patient and reporter details are entered in the authority's route, never in MDARIX",
        )
    if field.missing == forms.NOT_USED:
        raise _error(422, "FIELD_NOT_USED", "This field is not used in this report")
    entries = dict(obligation.entries or {})
    value = None if payload.clear else _text(payload.value, worksheet.VALUE_MAX)
    if payload.clear:
        entries.pop(field_id, None)
    elif value:
        entries[field_id] = {"value": value, "by": str(ctx.user_id), "at": _iso(_now())}
    elif payload.confirmed:
        entries[field_id] = {"confirmed": True, "by": str(ctx.user_id), "at": _iso(_now())}
    else:
        raise _error(422, "NOTHING_TO_SAVE", "Enter a value, or confirm the record's value")
    obligation.entries, obligation.updated_at = entries, _now()
    _audit(db, ctx, "REPORT_FIELD_SET", obligation, field=field_id, cleared=payload.clear, confirmed=payload.confirmed)
    db.commit()
    return detail(db, control_db, ctx, obligation)


def _conclusion(context: dict, market: str):
    current = context["current"]
    if current is None or current.conclusion != markets.REPORTABLE:
        raise _error(
            409,
            "CONCLUSION_NOT_SIGNED",
            f"Sign the {markets.MARKET_LABELS.get(market, market)} conclusion as reportable first: a snapshot is "
            "approved on a signed conclusion",
        )
    return current


def request_snapshot(db, control_db, obligation: ReportObligation, actor: str, now: datetime, source_system=None):
    """Freeze the worksheet as the next snapshot, pending approval (shared with the sample)."""
    from backend.app.human_decision.rules import fingerprint

    context = _context(db, control_db, obligation)
    current = _conclusion(context, obligation.market)
    if obligation.kind == "INITIAL":
        obligation.assessment_id, obligation.report_type = current.id, current.report_type
        if obligation.due_provisional:
            obligation.due_on, obligation.due_provisional = current.due_on, False
    snapshots = _snapshots(db, obligation)
    for row in snapshots:
        if row.state == "PENDING":
            row.state = "SUPERSEDED"
    names = _names(control_db, obligation.tenant_id, _preparers(obligation))
    sections = worksheet.frozen(
        worksheet.build(_form(obligation), context, obligation.entries or {}, names, obligation.request_text)
    )
    material = {
        "obligation": str(obligation.id),
        "form": obligation.form_code,
        "form_version": obligation.form_version,
        "complaint": context["record"]["business_id"] or context["record"]["complaint_identifier"],
        "market": obligation.market,
        "conclusion": str(current.id),
        "sections": sections,
    }
    snapshot = ReportSnapshot(
        id=uuid.uuid4(),
        tenant_id=obligation.tenant_id,
        obligation_id=obligation.id,
        version=max((row.version for row in snapshots), default=0) + 1,
        form_version=obligation.form_version,
        fields={"sections": sections, "complaint": material["complaint"], "conclusion_signer": current.signed_by},
        content_fingerprint=fingerprint(material),
        preparers=sorted(_preparers(obligation, actor)),
        state="PENDING",
        requested_by=actor,
        requested_at=now,
        source_system=source_system,
    )
    db.add(snapshot)
    obligation.updated_at = now
    db.flush()
    return snapshot


@router.post("/{obligation_id}/snapshots", dependencies=[DECIDERS])
def ask_for_approval(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    if obligation.state not in rules.EDITABLE:
        raise _error(409, "NOT_A_DRAFT", "Only a draft is frozen for approval")
    snapshot = request_snapshot(db, control_db, obligation, str(ctx.user_id), _now())
    _audit(
        db,
        ctx,
        "REPORT_SNAPSHOT_REQUESTED",
        obligation,
        version=snapshot.version,
        fingerprint=snapshot.content_fingerprint,
    )
    db.commit()
    return detail(db, control_db, ctx, obligation)


class ApproveRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


def signature_meaning(form_title: str, version: int, ref: str) -> str:
    return (
        f"I approve snapshot {version} of the {form_title.lower()} for {ref} as the content to submit. MDARIX does not "
        "submit it."
    )


@router.post("/{obligation_id}/snapshots/{snapshot_id}/approve", dependencies=[DECIDERS])
def approve_snapshot(
    obligation_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    payload: ApproveRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The second person's approval of a pending snapshot, with password and authenticator code."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import signature_hash

    tenant_id = _tenant(ctx)
    obligation = _obligation(db, tenant_id, obligation_id)
    snapshot = next((row for row in _snapshots(db, obligation) if row.id == snapshot_id), None)
    if snapshot is None:
        raise _error(404, "SNAPSHOT_NOT_FOUND", "No such snapshot of this report")
    if snapshot.state != "PENDING" or obligation.state not in rules.EDITABLE:
        raise _error(409, "SNAPSHOT_NOT_PENDING", "This snapshot is not waiting for approval")
    me = str(ctx.user_id)
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    problem = rules.approver_problem(
        me,
        role,
        set(snapshot.preparers or []) | _preparers(obligation),
        (snapshot.fields or {}).get("conclusion_signer"),
    )
    if problem:
        _audit(db, ctx, "REPORT_SNAPSHOT_APPROVAL_REFUSED", obligation, version=snapshot.version, reason=problem)
        db.commit()
        raise _error(403, "SECOND_PERSON_REQUIRED", problem)

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="ReportObligation",
                entity_id=obligation.id,
                correlation_id=ctx.correlation_id,
                details={"attempt": "REPORT_SNAPSHOT_APPROVE", "version": snapshot.version},
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    obligation = _obligation(db, tenant_id, obligation_id, lock=True)
    snapshot = next((row for row in _snapshots(db, obligation) if row.id == snapshot_id), None)
    if snapshot is None or snapshot.state != "PENDING":
        raise _error(409, "SNAPSHOT_NOT_PENDING", "This snapshot changed a moment ago; reload it")
    now = _now()
    ref = (snapshot.fields or {}).get("complaint") or str(obligation.complaint_id)
    meaning = signature_meaning(_form(obligation).title, snapshot.version, ref)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=snapshot.id,
        object_version=str(snapshot.version),
        decision_type=DECISION_TYPE,
        decision="APPROVED",
        remarks=f"{obligation.form_version}, snapshot {snapshot.version}",
        signer_user_id=me,
        signer_role=role or "UNKNOWN",
        signature_meaning=meaning,
        content_fingerprint=snapshot.content_fingerprint,
        signature_hash=signature_hash(snapshot.content_fingerprint, me, str(snapshot.version)),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="REPORT_SNAPSHOT_APPROVED",
            entity_type="ReportObligation",
            entity_id=obligation.id,
            correlation_id=ctx.correlation_id,
            details={
                "market": obligation.market,
                "version": snapshot.version,
                "signature_id": str(record.id),
                "fingerprint": snapshot.content_fingerprint,
            },
            created_at=now,
        )
    )
    snapshot.state, snapshot.approved_by, snapshot.approved_at = "APPROVED", me, now
    snapshot.signed_record_id = record.id
    obligation.state, obligation.updated_at = rules.APPROVED, now
    if db is control_db:
        control_db.commit()
    else:
        control_db.commit()
        try:
            db.commit()
        except Exception:
            logger.exception("Signature %s was saved but its snapshot %s was not", record.id, snapshot.id)
            raise
    return detail(db, control_db, ctx, obligation)


class ReasonRequest(BaseModel):
    reason: str = Field(max_length=rules.NOTE_MAX * 2)


@router.post("/{obligation_id}/reopen", dependencies=[DECIDERS])
def reopen(
    obligation_id: uuid.UUID,
    payload: ReasonRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """An approved snapshot not yet submitted goes back to draft: the correction needs a new approval."""
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    reason = _text(payload.reason)
    if not reason or len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say why, in at least {rules.REASON_MIN} characters")
    if obligation.state != rules.APPROVED:
        raise _error(409, "NOT_APPROVED", "Only an approved snapshot not yet submitted is reopened")
    for row in _snapshots(db, obligation):
        if row.state == "APPROVED":
            row.state = "SUPERSEDED"
    obligation.state, obligation.note, obligation.updated_at = rules.DRAFT, reason, _now()
    _audit(db, ctx, "REPORT_REOPENED", obligation, reason=reason)
    db.commit()
    return detail(db, control_db, ctx, obligation)


# --------------------------------------------------------------------------------------------- the submission record


class FileIn(BaseModel):
    name: str = Field(max_length=200)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    data: str = Field(max_length=rules.FILE_MAX * 2)  # base64


class Difference(BaseModel):
    field: str = Field(max_length=40)
    classification: str = Field(max_length=20)
    reason: str = Field(default="", max_length=2000)


class SubmissionRequest(BaseModel):
    route: str = Field(max_length=40)
    submitted_at: datetime
    content_note: str = Field(default="", max_length=rules.NOTE_MAX * 2)
    file: FileIn | None = None
    no_differences: bool = False
    differences: list[Difference] = Field(default_factory=list, max_length=200)
    authority_reference: str = Field(default="", max_length=240)


def _file(payload: FileIn | None) -> dict:
    if payload is None:
        return {}
    try:
        data = base64.b64decode(payload.data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _error(422, "FILE_UNREADABLE", "The file could not be read") from exc
    if not data or len(data) > rules.FILE_MAX:
        raise _error(422, "FILE_TOO_LARGE", f"Attach a file of at most {rules.FILE_MAX // (1024 * 1024)} MB")
    return {
        "file_name": _text(payload.name, 200) or "evidence",
        "content_type": _text(payload.content_type, 120) or "application/octet-stream",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content": data,
    }


def record_submission(
    db,
    obligation,
    actor: str,
    route: str,
    submitted_at: datetime,
    *,
    note,
    file: dict,
    differences: list[dict],
    reference,
    now: datetime,
    source_system=None,
) -> ReportSubmission:
    """One attempt, recorded at once (shared with the sample). The state follows the route."""
    snapshot = next((row for row in reversed(_snapshots(db, obligation)) if row.state == "APPROVED"), None)
    route_spec = forms.route_of(_form(obligation), route)
    attempts = _submissions(db, obligation)
    submission = ReportSubmission(
        id=uuid.uuid4(),
        tenant_id=obligation.tenant_id,
        obligation_id=obligation.id,
        snapshot_id=snapshot.id if snapshot else None,
        attempt=max((row.attempt for row in attempts), default=0) + 1,
        route=route,
        submitted_at=submitted_at,
        content_note=note,
        differences=differences,
        authority_reference=reference,
        result="PENDING" if route_spec.acknowledgement_expected else "NO_ACK_EXPECTED",
        late=bool(obligation.due_on and submitted_at > rules.deadline_end(obligation.due_on)),
        recorded_by=actor,
        recorded_at=now,
        source_system=source_system,
    )
    db.add(submission)
    db.flush()
    if file or note:
        db.add(
            ReportEvidence(
                tenant_id=obligation.tenant_id,
                submission_id=submission.id,
                kind="SUBMITTED_CONTENT",
                outcome="CONTENT",
                note=note,
                received_at=submitted_at,
                recorded_by=actor,
                recorded_at=now,
                source_system=source_system,
                **file,
            )
        )
    obligation.state = rules.PENDING if route_spec.acknowledgement_expected else rules.NO_ACK
    obligation.updated_at = now
    db.flush()
    return submission


@router.post("/{obligation_id}/submissions", dependencies=[DECIDERS])
def submission(
    obligation_id: uuid.UUID,
    payload: SubmissionRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record what was submitted outside MDARIX, at once: the route, the time and the submitted content, with the
    difference review against the approved snapshot. MDARIX sends nothing."""
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    if obligation.state != rules.APPROVED:
        raise _error(
            409,
            "SNAPSHOT_NOT_APPROVED",
            "A second person approves the snapshot before the submission is recorded",
        )
    route = str(payload.route or "").strip().upper()
    if forms.route_of(_form(obligation), route) is None:
        raise _error(422, "ROUTE_UNKNOWN", "Choose the route you submitted through")
    submitted_at = payload.submitted_at
    if submitted_at.tzinfo is None:
        raise _error(422, "TIME_ZONE_REQUIRED", "Give the submission time with its time zone")
    if submitted_at > _now():
        raise _error(422, "SUBMITTED_IN_FUTURE", "The submission time cannot be in the future")
    differences = [
        {"field": item.field, "classification": item.classification.strip().upper(), "reason": _text(item.reason, 2000)}
        for item in payload.differences
    ]
    problem = rules.difference_problem(differences, payload.no_differences)
    if problem:
        raise _error(409 if "re-approval" in problem else 422, "DIFFERENCE_REVIEW", problem)
    note = _text(payload.content_note)
    file = _file(payload.file)
    if not note and not file:
        raise _error(422, "CONTENT_REQUIRED", "Attach the submitted content, or describe it in a note")
    row = record_submission(
        db,
        obligation,
        str(ctx.user_id),
        route,
        submitted_at,
        note=note,
        file=file,
        differences=differences,
        reference=_text(payload.authority_reference, 120),
        now=_now(),
    )
    _audit(db, ctx, "REPORT_SUBMISSION_RECORDED", obligation, attempt=row.attempt, route=route, late=row.late)
    db.commit()
    return detail(db, control_db, ctx, obligation)


class EvidenceRequest(BaseModel):
    kind: str = Field(max_length=30)
    outcome: str = Field(max_length=20)
    received_at: datetime
    note: str = Field(default="", max_length=rules.NOTE_MAX * 2)
    file: FileIn | None = None
    authority_reference: str = Field(default="", max_length=240)


def _filed(db, obligation: ReportObligation, submission_row: ReportSubmission) -> None:
    """An accepted initial report settles its market on the reportability watch: its filing is recorded on the
    signed conclusion (the submission's day and the authority's reference)."""
    if obligation.kind != "INITIAL":
        return
    versions = (
        db.query(ComplaintMarketAssessment)
        .filter(
            ComplaintMarketAssessment.tenant_id == obligation.tenant_id,
            ComplaintMarketAssessment.complaint_id == obligation.complaint_id,
            ComplaintMarketAssessment.market == obligation.market,
        )
        .order_by(ComplaintMarketAssessment.version)
        .all()
    )
    current, _ = assessments.current_and_draft(versions)
    if current is not None and current.conclusion == markets.REPORTABLE:
        current.filed_on = submission_row.submitted_at.date()
        current.filing_reference = (
            submission_row.authority_reference or f"Attempt {submission_row.attempt}, {submission_row.route}"
        )[:120]
        current.updated_at = _now()


def record_evidence(
    db,
    obligation,
    submission_row,
    actor: str,
    kind: str,
    outcome: str,
    received_at: datetime,
    *,
    note,
    file: dict,
    reference,
    now: datetime,
    source_system=None,
) -> ReportEvidence:
    """One piece of evidence as it arrives (shared with the sample). A receipt is not acceptance; an acceptance meets
    the obligation; a rejection returns it to draft with its original deadline."""
    row = ReportEvidence(
        tenant_id=obligation.tenant_id,
        submission_id=submission_row.id,
        kind=kind,
        outcome=outcome,
        note=note,
        received_at=received_at,
        recorded_by=actor,
        recorded_at=now,
        source_system=source_system,
        **file,
    )
    db.add(row)
    if reference and not submission_row.authority_reference:
        submission_row.authority_reference = reference
    if outcome == "ACCEPTED":
        submission_row.result, submission_row.result_at = "ACCEPTED", received_at
        obligation.state = rules.ACCEPTED
        _filed(db, obligation, submission_row)
    elif outcome == "REJECTED":
        submission_row.result, submission_row.result_at = "REJECTED", received_at
        obligation.state = rules.CORRECTION
    obligation.updated_at = now
    db.flush()
    return row


@router.post("/{obligation_id}/submissions/{submission_id}/evidence", dependencies=[DECIDERS])
def evidence(
    obligation_id: uuid.UUID,
    submission_id: uuid.UUID,
    payload: EvidenceRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    attempt = next((row for row in _submissions(db, obligation) if row.id == submission_id), None)
    if attempt is None:
        raise _error(404, "SUBMISSION_NOT_FOUND", "No such submission of this report")
    route = forms.route_of(_form(obligation), attempt.route)
    kind, outcome = str(payload.kind or "").strip().upper(), str(payload.outcome or "").strip().upper()
    allowed = route.evidence.get(kind) if route else None
    if not allowed or outcome not in allowed:
        raise _error(
            422, "EVIDENCE_UNKNOWN", f"On {forms.ROUTE_LABELS.get(attempt.route)}, this evidence cannot say that"
        )
    if attempt.result in ("ACCEPTED", "REJECTED") and outcome in ("ACCEPTED", "REJECTED"):
        raise _error(
            409, "RESULT_RECORDED", "This attempt's result is already recorded: a resubmission is a new attempt"
        )
    if payload.received_at.tzinfo is None or payload.received_at > _now():
        raise _error(422, "RECEIVED_TIME", "Give when it arrived, with its time zone, not in the future")
    note, file = _text(payload.note), _file(payload.file)
    if not note and not file:
        raise _error(422, "EVIDENCE_REQUIRED", "Attach the evidence, or describe it in a note")
    record_evidence(
        db,
        obligation,
        attempt,
        str(ctx.user_id),
        kind,
        outcome,
        payload.received_at,
        note=note,
        file=file,
        reference=_text(payload.authority_reference, 120),
        now=_now(),
    )
    _audit(db, ctx, "REPORT_EVIDENCE_RECORDED", obligation, attempt=attempt.attempt, kind=kind, outcome=outcome)
    db.commit()
    return detail(db, control_db, ctx, obligation)


@router.get("/{obligation_id}/submissions/{submission_id}/evidence/{evidence_id}/file")
def evidence_file(
    obligation_id: uuid.UUID,
    submission_id: uuid.UUID,
    evidence_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    obligation = _obligation(db, tenant_id, obligation_id)
    row = (
        db.query(ReportEvidence)
        .join(ReportSubmission, ReportSubmission.id == ReportEvidence.submission_id)
        .filter(
            ReportEvidence.tenant_id == tenant_id,
            ReportEvidence.id == evidence_id,
            ReportSubmission.id == submission_id,
            ReportSubmission.obligation_id == obligation.id,
        )
        .one_or_none()
    )
    if row is None or row.content is None:
        raise _error(404, "FILE_NOT_FOUND", "No file is kept for this evidence")
    return Response(
        content=bytes(row.content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row.file_name or "evidence"}"'},
    )


# --------------------------------------------------------------------------------------------- after acceptance


class FollowUpRequest(BaseModel):
    due_on: date
    note: str = Field(max_length=rules.NOTE_MAX * 2)


@router.post("/{obligation_id}/follow-up", dependencies=[DECIDERS])
def follow_up(
    obligation_id: uuid.UUID,
    payload: FollowUpRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A follow-up is due (for example a supplemental report, 21 CFR 803.56): the initial deadline stays met."""
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    note = _text(payload.note)
    if not note or len(note) < rules.REASON_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say what is due, in at least {rules.REASON_MIN} characters")
    if obligation.state not in (rules.ACCEPTED, rules.NO_ACK):
        raise _error(409, "NOT_ACCEPTED", "A follow-up is recorded after the report is accepted")
    obligation.state, obligation.follow_up_due_on, obligation.note = rules.FOLLOW_UP, payload.due_on, note
    obligation.updated_at = _now()
    _audit(db, ctx, "REPORT_FOLLOW_UP_DUE", obligation, due_on=payload.due_on.isoformat())
    db.commit()
    return detail(db, control_db, ctx, obligation)


@router.post("/{obligation_id}/complete", dependencies=[DECIDERS])
def complete(
    obligation_id: uuid.UUID,
    payload: ReasonRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    note = _text(payload.reason)
    if not note or len(note) < rules.REASON_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say why it is complete, in at least {rules.REASON_MIN} characters")
    if obligation.state not in (rules.ACCEPTED, rules.NO_ACK, rules.FOLLOW_UP):
        raise _error(409, "NOT_ACCEPTED", "An obligation is completed after its report is accepted")
    obligation.state, obligation.note, obligation.updated_at = rules.COMPLETE, note, _now()
    _audit(db, ctx, "REPORT_COMPLETED", obligation)
    db.commit()
    return detail(db, control_db, ctx, obligation)


class InformationRequest(BaseModel):
    request_text: str = Field(max_length=rules.NOTE_MAX * 2)
    received_on: date
    due_on: date


@router.post("/{obligation_id}/requests", dependencies=[DECIDERS])
def request_for_information(
    obligation_id: uuid.UUID,
    payload: InformationRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The authority asks for more after a valid submission: the submission stays valid, and a separate response
    obligation with its own deadline is created."""
    parent = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    text = _text(payload.request_text)
    if not text or len(text) < rules.REASON_MIN:
        raise _error(
            422, "REQUEST_REQUIRED", f"Write what the authority asked, in at least {rules.REASON_MIN} characters"
        )
    if parent.state not in rules.VALID_SUBMISSION:
        raise _error(409, "NO_VALID_SUBMISSION", "A request for information follows a valid (accepted) submission")
    if payload.due_on < payload.received_on:
        raise _error(422, "DUE_BEFORE_REQUEST", "The response cannot be due before the request arrived")
    now = _now()
    child = ReportObligation(
        id=uuid.uuid4(),
        tenant_id=parent.tenant_id,
        complaint_id=parent.complaint_id,
        market=parent.market,
        kind="RESPONSE",
        parent_id=parent.id,
        assessment_id=parent.assessment_id,
        form_code=forms.RESPONSE.code,
        form_version=forms.RESPONSE.version,
        due_on=payload.due_on,
        due_provisional=False,
        state=rules.DRAFT,
        entries={},
        request_text=text,
        request_received_on=payload.received_on,
        created_by=str(ctx.user_id),
        created_at=now,
        updated_at=now,
    )
    db.add(child)
    db.flush()
    _audit(db, ctx, "REPORT_INFORMATION_REQUESTED", parent, response=str(child.id), due_on=payload.due_on.isoformat())
    db.commit()
    return detail(db, control_db, ctx, child)


# --------------------------------------------------------------------------------------------- exports


@router.get("/{obligation_id}/worksheet.{kind}", dependencies=[Depends(require_permission(DATA_EXPORT))])
def export(
    obligation_id: uuid.UUID,
    kind: str,
    snapshot: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The worksheet as a PDF or DOCX: the draft as it is now, or an approved snapshot exactly as frozen. Marked
    draft, "MDARIX never submits", with its form version, the starter-text mark and, in a trial, the practice label."""
    from backend.app.authority_reports import render
    from backend.app.stage3_workflow_router import _organization_name

    kind = kind.lower()
    if kind not in MEDIA:
        raise _error(404, "FORMAT_NOT_SUPPORTED", "Download the PDF or the DOCX")
    tenant_id = _tenant(ctx)
    obligation = _obligation(db, tenant_id, obligation_id)
    view = detail(db, control_db, ctx, obligation)
    frozen = None
    if snapshot is not None:
        frozen = next((row for row in _snapshots(db, obligation) if row.id == snapshot), None)
        if frozen is None:
            raise _error(404, "SNAPSHOT_NOT_FOUND", "No such snapshot of this report")
        signature = None
        if frozen.signed_record_id:
            record = control_db.get(SignedApprovalRecord, frozen.signed_record_id)
            if record is not None:
                signature = {
                    "signer_name": _names(control_db, tenant_id, [record.signer_user_id]).get(record.signer_user_id)
                    or "A colleague",
                    "signer_role": (record.signer_role or "").replace("_", " ").title(),
                    "signed_at": _iso(record.signed_at),
                    "meaning": record.signature_meaning,
                    "record_business_id": record.business_id,
                    "record_id": str(record.id),
                    "content_fingerprint": record.content_fingerprint,
                }
        view = {
            **view,
            "sections": frozen.fields["sections"],
            "snapshot": _snapshot_view(frozen, {}),
            "signature": signature,
        }
    body = render.render(view, kind, organization=_organization_name(control_db, tenant_id))
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="REPORT_WORKSHEET_DOWNLOADED",
            entity_type="ReportObligation",
            entity_id=obligation.id,
            correlation_id=ctx.correlation_id,
            details={"format": kind.upper(), "snapshot": frozen.version if frozen else None},
        )
    )
    db.commit()
    stem = f"mdarix-{obligation.form_code.lower().replace('_', '-')}-{view['complaint']['ref']}"
    stem += f"-snapshot-{frozen.version}" if frozen else "-draft"
    return Response(
        content=body,
        media_type=MEDIA[kind],
        headers={"Content-Disposition": f'attachment; filename="{stem}.{kind}"'},
    )
