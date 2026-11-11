"""B9b steps 4-6 (OC spec 3.2, 3.3; plan B9b-N3, N4, N5): the "Other Regulatory Report" of a country outside the five
markets.

There is no form. A signed Reportable conclusion for the country creates the record (form ``ATTACHED``, market
``OTHER`` and the country); a later Not reportable cancels it while it is not yet submitted. The customer attaches
the report they made and records "Submitted" with its date and Report ID (or "Not issued yet", filled in later), signed
by the person recording it (password and MFA, the file's SHA-256 in the signed material; no second person, OC-D3). The
acknowledgement or rejection goes through the existing evidence route; follow-ups are child records (``RESPONSE`` with
``parent_id``), each with its own file, Report ID and status; Close needs a reason and is refused while a follow-up is
open. Every file is scanned and kept; a new file never overwrites an earlier one. MDARIX never submits.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app import signing_commit
from backend.app.access.permissions import REGULATORY_APPROVE, REGULATORY_REVIEW
from backend.app.authority_reports import forms, rules
from backend.app.authority_reports import router as reports
from backend.app.business_ids import complaint_ref
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import Complaint, SignedApprovalRecord
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person
from backend.app.reportability import deadlines, markets
from backend.app.reportability import other_countries as other
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.standards import STARTER_MARK

FORM, ROUTE = forms.ATTACHED.code, "AUTHORITY_ROUTE"
BANNER = "Report prepared outside MDARIX; MDARIX holds the copy as attached"
NOT_ISSUED = "Not issued yet"
OBJECT_TYPE, DECISION_TYPE = "ReportObligation", "ATTACHED_REPORT_SUBMITTED"
WINDOW, CUSTOMER = "WINDOW", "CUSTOMER"
LABELS = {
    rules.DRAFT: "To be submitted",
    rules.PENDING: "Submitted",
    rules.NO_ACK: "Submitted",
    rules.ACCEPTED: "Acknowledged",
    rules.CORRECTION: "Rejected by authority",
    rules.FOLLOW_UP: "Follow-up required",
    rules.COMPLETE: "Closed",
    rules.CANCELLED: "Cancelled: not reportable",
}
SUBMITTABLE = (rules.DRAFT, rules.CORRECTION)
OPEN_FOLLOW_UP = (rules.DRAFT, rules.CORRECTION, rules.PENDING, rules.NO_ACK, rules.ACCEPTED, rules.FOLLOW_UP)
CLOSABLE = (rules.PENDING, rules.NO_ACK, rules.ACCEPTED, rules.FOLLOW_UP)

router = APIRouter(prefix="/api/v1/reports", tags=["Other Regulatory Reports"])


def is_attached(obligation) -> bool:
    return obligation.form_code == FORM


def state_label(obligation) -> str:
    if obligation.state == rules.CANCELLED and obligation.parent_id is not None:
        return "Cancelled before it was sent"
    return LABELS.get(obligation.state, rules.STATE_LABELS.get(obligation.state, obligation.state))


def _due_source(obligation) -> str | None:
    return (obligation.entries or {}).get("due_source")


def _set_entries(obligation, **values) -> None:
    obligation.entries = {**(obligation.entries or {}), **values}  # a new dict: JSONB change tracking


def _audit(db, ctx, action: str, obligation, old=None, new=None, **details) -> None:
    reports._audit(db, ctx, action, obligation, old, new, country=obligation.country, **details)


def _children(db, obligation) -> list[ReportObligation]:
    return (
        db.query(ReportObligation)
        .filter(
            ReportObligation.tenant_id == obligation.tenant_id,
            ReportObligation.parent_id == obligation.id,
            ReportObligation.form_code == FORM,
        )
        .order_by(ReportObligation.created_at, ReportObligation.id)
        .all()
    )


# ------------------------------------------------------------------------------------- created from the conclusion


def follow_conclusion(db, ctx, tenant_id, complaint_id, country: str, signed, now: datetime) -> None:
    """What a signed conclusion for the country does to its report, in the signing's transaction (as the five markets'
    ``follow_conclusion``). Reportable: the report is created (one per complaint and country; a cancelled one is
    reopened; an unsubmitted one takes the new window date unless the customer entered one). Not reportable: a report
    not yet submitted is cancelled, its reason kept and audited; a submitted one stays as recorded."""
    existing = (
        db.query(ReportObligation)
        .filter(
            ReportObligation.tenant_id == tenant_id,
            ReportObligation.complaint_id == complaint_id,
            ReportObligation.market == other.OTHER,
            ReportObligation.country == country,
            ReportObligation.kind == "INITIAL",
        )
        .with_for_update()
        .one_or_none()
    )
    source = WINDOW if signed.due_on else None
    if signed.conclusion == markets.REPORTABLE:
        if existing is None:
            row = ReportObligation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_id=complaint_id,
                market=other.OTHER,
                country=country,
                kind="INITIAL",
                assessment_id=signed.id,
                form_code=FORM,
                form_version=forms.ATTACHED.version,
                report_type=signed.report_type,
                due_on=signed.due_on,
                state=rules.DRAFT,
                entries={"due_source": source},
                created_by=str(ctx.user_id),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            _audit(db, ctx, "REPORT_CREATED_FROM_CONCLUSION", row, form=FORM, version=signed.version)
        elif existing.state == rules.CANCELLED:
            old = {"state": existing.state, "note": existing.note}
            existing.state, existing.assessment_id, existing.note, existing.updated_at = (
                rules.DRAFT,
                signed.id,
                None,
                now,
            )
            if _due_source(existing) != CUSTOMER:
                existing.due_on = signed.due_on
                _set_entries(existing, due_source=source)
            _audit(
                db, ctx, "REPORT_REOPENED_BY_CONCLUSION", existing, old, {"state": rules.DRAFT}, version=signed.version
            )
        elif existing.state in SUBMITTABLE and _due_source(existing) != CUSTOMER and existing.due_on != signed.due_on:
            old = {"due_on": reports._iso(existing.due_on)}
            existing.due_on, existing.assessment_id, existing.updated_at = signed.due_on, signed.id, now
            _set_entries(existing, due_source=source)
            _audit(db, ctx, "REPORT_DUE_DATE_FROM_WINDOW", existing, old, {"due_on": reports._iso(signed.due_on)})
        return
    # Only a report never submitted: one rejected by the authority (CORRECTION) was received, so it stays.
    if existing is None or existing.state != rules.DRAFT:
        return
    reason = (
        f"The {other.name_of(country)} conclusion signed on {now.date().isoformat()} (version {signed.version}) says "
        "not reportable" + (f": {signed.override_reason}" if signed.override_reason else ".")
    )
    old = {"state": existing.state, "note": existing.note}
    existing.state, existing.note, existing.updated_at = rules.CANCELLED, reason, now
    _audit(db, ctx, "REPORT_CANCELLED", existing, old, {"state": rules.CANCELLED, "note": reason}, reason=reason)


# ---------------------------------------------------------------------------------------------------------- the view


def _submission_view(row, evidence: list, names: dict, signatures: dict) -> dict:
    signed = signatures.get(str(row.attempt)) or {}
    return {
        "id": str(row.id),
        "attempt": row.attempt,
        "submitted_at": reports._iso(row.submitted_at),
        "report_id": row.authority_reference or NOT_ISSUED,
        "report_id_pending": not row.authority_reference,
        "result": row.result,
        "late": row.late,
        "note": row.content_note,
        "recorded_by": names.get(row.recorded_by) or "A colleague",
        "recorded_at": reports._iso(row.recorded_at),
        "signature_id": signed.get("signature_id"),
        "evidence": [reports._evidence_view(item, names) for item in evidence],
    }


def detail(db, control_db, ctx, obligation) -> dict:
    """The record's page: the country, the status, the due date and where it came from, every submission with its files
    and signature, the acknowledgement, the follow-ups (or the parent), and what the person may do next."""
    tenant_id = reports._tenant(ctx)
    complaint = db.get(Complaint, obligation.complaint_id)
    submissions = reports._submissions(db, obligation)
    evidence = reports._evidence(db, tenant_id, [row.id for row in submissions])
    children = _children(db, obligation) if obligation.parent_id is None else []
    parent = db.get(ReportObligation, obligation.parent_id) if obligation.parent_id else None
    refs = {row.recorded_by for row in submissions} | {item.recorded_by for rows in evidence.values() for item in rows}
    names = reports._names(control_db, tenant_id, refs)
    signatures = {str(item["attempt"]): item for item in (obligation.entries or {}).get("signatures") or []}
    org_zone = deadlines.org_zone(db, tenant_id)
    source = _due_source(obligation)
    open_children = [row for row in children if row.state in OPEN_FOLLOW_UP]
    on = other.switched_on()
    return {
        "id": str(obligation.id),
        "kind": obligation.kind,
        "follow_up": obligation.parent_id is not None,
        "market": obligation.market,
        "country": obligation.country,
        "country_name": other.name_of(obligation.country),
        "market_label": other.label(obligation.country),
        "form_code": FORM,
        "form_title": forms.ATTACHED.title,
        "attached": True,
        "banner": BANNER,
        "never_submits": rules.NEVER_SUBMITS,
        "generic_note": other.GENERIC,
        "starter_mark": STARTER_MARK,
        "complaint": {
            "id": str(obligation.complaint_id),
            "ref": complaint_ref(complaint) if complaint is not None else None,
        },
        "state": obligation.state,
        "state_label": state_label(obligation),
        "note": obligation.note,
        **reports.due_fields(
            obligation.due_on,
            obligation.market,
            org_zone,
            deadlines.as_moment(None),
            False,
            obligation.state in rules.SUBMITTED,
            obligation.state,
        ),
        "due_source": source,
        "due_source_label": other.MANUAL_DUE if source == CUSTOMER else "Your reporting window" if source else None,
        "submissions": [
            _submission_view(row, evidence.get(row.id, []), names, signatures) for row in reversed(submissions)
        ],
        "evidence_kinds": {
            kind: list(outcomes) for kind, outcomes in forms.route_of(forms.ATTACHED, ROUTE).evidence.items()
        },
        "evidence_labels": forms.EVIDENCE_LABELS,
        "route_label": forms.ROUTE_LABELS[ROUTE],
        "parent": {"id": str(parent.id), "state_label": state_label(parent)} if parent is not None else None,
        "follow_ups": [
            {
                "id": str(row.id),
                "number": index,
                "state": row.state,
                "state_label": state_label(row),
                "due_on": reports._iso(row.due_on),
                "note": row.note,
            }
            for index, row in enumerate(children, start=1)
        ],
        "can": {
            "submit": on and obligation.state in SUBMITTABLE,
            "acknowledge": on and obligation.state in (rules.PENDING, rules.FOLLOW_UP) and bool(submissions),
            "enter_report_id": on and any(not row.authority_reference for row in submissions),
            "set_due_date": on and source != WINDOW and obligation.state in SUBMITTABLE,
            "follow_up": on and obligation.parent_id is None and obligation.state in CLOSABLE,
            "close": on and obligation.state in CLOSABLE and not open_children,
            # A follow-up never sent is cancelled with a reason (the shared cancel route).
            "cancel": on and obligation.parent_id is not None and obligation.state == rules.DRAFT,
        },
    }


# ---------------------------------------------------------------------------------------------------------- routes


def _attached(db, ctx, obligation_id, *, lock: bool = True) -> ReportObligation:
    obligation = reports._obligation(db, reports._tenant(ctx), obligation_id, lock=lock)
    if not is_attached(obligation):
        raise reports._error(404, "NOT_ATTACHED", "This report is not an Other Regulatory Report")
    return obligation


class AttachedSubmission(BaseModel):
    submitted_at: datetime
    report_id: str = Field(default="", max_length=120)
    not_issued_yet: bool = False
    file: reports.FileIn | None = None
    note: str = Field(default="", max_length=rules.NOTE_MAX * 2)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


def _local_day(db, tenant_id, moment: datetime) -> date:
    """The day a moment falls on in the organization's time zone (the screen sends UTC: 02:00 IST is the day before)."""
    from zoneinfo import ZoneInfo

    try:
        return moment.astimezone(ZoneInfo(deadlines.org_zone(db, tenant_id) or "UTC")).date()
    except Exception:  # an unknown zone name: the day in UTC
        return moment.date()


def submitted_meaning(country: str, day: date) -> str:
    return (
        f"I recorded that this report was submitted to the authority of {other.name_of(country)} on "
        f"{day.isoformat()}, as attached."
    )


@router.post("/{obligation_id}/attached-submission", dependencies=[Depends(other._on), reports.DECIDERS])
def attached_submission(
    obligation_id: uuid.UUID,
    payload: AttachedSubmission,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record "Submitted" (OC-04, OC-05, OC-19): the report file (scanned) and the date are mandatory, the Report ID or
    "Not issued yet"; the person recording it signs (password and MFA), the file's SHA-256 in the signed material. No
    snapshot, no second person (OC-D3). MDARIX sends nothing."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import fingerprint, signature_hash

    obligation = _attached(db, ctx, obligation_id)
    if obligation.state not in SUBMITTABLE:
        raise reports._error(409, "NOT_SUBMITTABLE", "This report is submitted already: a new file is evidence")
    if payload.submitted_at.tzinfo is None or payload.submitted_at > reports._now():
        raise reports._error(422, "SUBMITTED_TIME", "Give when it was submitted, with its time zone, not in the future")
    report_id = reports._text(payload.report_id, 120)
    if not report_id and not payload.not_issued_yet:
        raise reports._error(422, "REPORT_ID_NEEDED", f"Enter the Report ID, or mark it {NOT_ISSUED.lower()}")
    if payload.file is None:
        raise reports._error(422, "FILE_REQUIRED", "Attach the report you submitted")
    file = reports._file(payload.file)
    note = reports._text(payload.note)
    tenant_id = obligation.tenant_id
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    if (role or "").upper() in {"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"}:
        raise reports._error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign a submission record")
    complaint = db.get(Complaint, obligation.complaint_id)
    ref = complaint_ref(complaint) if complaint is not None else str(obligation.complaint_id)
    obligation_ref = obligation.id

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="ReportObligation",
                entity_id=obligation_ref,
                correlation_id=ctx.correlation_id,
                details={"attempt": "ATTACHED_REPORT_SUBMITTED", "complaint": ref, "country": obligation.country},
            )
        )

    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    now = reports._now()
    obligation = _attached(db, ctx, obligation_id)
    if obligation.state not in SUBMITTABLE:
        raise reports._error(409, "NOT_SUBMITTABLE", "This report was recorded as submitted a moment ago")
    attempt = max((row.attempt for row in reports._submissions(db, obligation)), default=0) + 1
    material = {
        "obligation_id": str(obligation.id),
        "complaint": ref,
        "country": obligation.country,
        "country_name": other.name_of(obligation.country),
        "follow_up": obligation.parent_id is not None,
        "attempt": attempt,
        "submitted_at": payload.submitted_at.isoformat(),
        "report_id": report_id,
        "not_issued_yet": not report_id,
        "file": {"name": file["file_name"], "size": file["size"], "sha256": file["sha256"]},
        "note": note,
        "banner": BANNER,
        "starter_mark": STARTER_MARK,
    }
    content_fingerprint = fingerprint(material)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=obligation.id,
        object_version=str(attempt),
        decision_type=DECISION_TYPE,
        decision="SUBMITTED",
        remarks=f"Report ID: {report_id or NOT_ISSUED}",
        signer_user_id=str(ctx.user_id),
        signer_role=role or "UNKNOWN",
        signature_meaning=submitted_meaning(obligation.country, _local_day(db, tenant_id, payload.submitted_at)),
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, str(ctx.user_id), str(attempt)),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    row = reports.record_submission(
        db,
        obligation,
        str(ctx.user_id),
        ROUTE,
        payload.submitted_at,
        note=note,
        file=file,
        differences=[],
        reference=report_id,
        now=now,
    )
    signed = {"attempt": attempt, "signature_id": str(record.id), "sha256": file["sha256"]}
    _set_entries(obligation, signatures=[*((obligation.entries or {}).get("signatures") or []), signed])
    _audit(
        db,
        ctx,
        "REPORT_ATTACHED_SUBMITTED",
        obligation,
        attempt=row.attempt,
        report_id=report_id or NOT_ISSUED,
        sha256=file["sha256"],
        signature_id=str(record.id),
        fingerprint=content_fingerprint,
    )
    signing_commit.commit(db, control_db, "attached report submission")
    return detail(db, control_db, ctx, obligation)


class ReportIdLater(BaseModel):
    submission_id: uuid.UUID
    report_id: str = Field(max_length=120)


@router.put("/{obligation_id}/attached-report-id", dependencies=[Depends(other._on), reports.DECIDERS])
def report_id_later(
    obligation_id: uuid.UUID,
    payload: ReportIdLater,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A Report ID recorded as "Not issued yet", entered once it is known (OC-05), audited. A Report ID already
    entered is never changed here."""
    obligation = _attached(db, ctx, obligation_id)
    row = next((item for item in reports._submissions(db, obligation) if item.id == payload.submission_id), None)
    if row is None:
        raise reports._error(404, "SUBMISSION_NOT_FOUND", "No such submission of this report")
    report_id = reports._text(payload.report_id, 120)
    if not report_id:
        raise reports._error(422, "REPORT_ID_NEEDED", "Enter the Report ID")
    if row.authority_reference:
        raise reports._error(409, "REPORT_ID_RECORDED", "This submission's Report ID is recorded already")
    row.authority_reference, obligation.updated_at = report_id, reports._now()
    _audit(db, ctx, "REPORT_ID_ENTERED", obligation, {"report_id": None}, {"report_id": report_id}, attempt=row.attempt)
    db.commit()
    return detail(db, control_db, ctx, obligation)


class DueDate(BaseModel):
    due_on: date
    reason: str = Field(max_length=2000)


@router.put("/{obligation_id}/attached-due-date", dependencies=[Depends(other._on), reports.DECIDERS])
def due_date(
    obligation_id: uuid.UUID,
    payload: DueDate,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """With no reporting window naming the country, the person enters the due date (OC-D2, OC-10): shown as "Due date
    entered by the customer", counted as any other in the Overdue and Due-this-week lists, audited with its reason."""
    obligation = _attached(db, ctx, obligation_id)
    reason = reports._text(payload.reason)
    if not reason or len(reason) < rules.REASON_MIN:
        raise reports._error(
            422, "REASON_REQUIRED", f"Say where the date comes from, in at least {rules.REASON_MIN} characters"
        )
    if _due_source(obligation) == WINDOW:
        raise reports._error(409, "WINDOW_DUE_DATE", "Your reporting window for this country sets the due date")
    if obligation.state not in SUBMITTABLE:
        raise reports._error(409, "NOT_SUBMITTABLE", "The due date is set before the report is submitted")
    old = {"due_on": reports._iso(obligation.due_on)}
    obligation.due_on, obligation.updated_at = payload.due_on, reports._now()
    _set_entries(obligation, due_source=CUSTOMER)
    _audit(db, ctx, "REPORT_DUE_DATE_ENTERED", obligation, old, {"due_on": payload.due_on.isoformat()}, reason=reason)
    db.commit()
    return detail(db, control_db, ctx, obligation)


class FollowUp(BaseModel):
    reason: str = Field(max_length=2000)


@router.post("/{obligation_id}/attached-follow-ups", dependencies=[Depends(other._on), reports.DECIDERS])
def follow_up(
    obligation_id: uuid.UUID,
    payload: FollowUp,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A follow-up report (OC-07, OC-08): a child of the first report, with its own file, Report ID and status. Several
    are allowed, in any order the authority asks. The first report reads "Follow-up required"."""
    parent = _attached(db, ctx, obligation_id)
    reason = reports._text(payload.reason)
    if not reason or len(reason) < rules.REASON_MIN:
        raise reports._error(
            422, "REASON_REQUIRED", f"Say what the follow-up is for, in at least {rules.REASON_MIN} characters"
        )
    if parent.parent_id is not None:
        raise reports._error(409, "FOLLOW_UP_OF_FIRST", "A follow-up is created from the first report")
    if parent.state not in CLOSABLE:
        raise reports._error(409, "NOT_SUBMITTED", "A follow-up is created once the first report is submitted")
    now = reports._now()
    child = ReportObligation(
        id=uuid.uuid4(),
        tenant_id=parent.tenant_id,
        complaint_id=parent.complaint_id,
        market=other.OTHER,
        country=parent.country,
        kind="RESPONSE",
        parent_id=parent.id,
        assessment_id=parent.assessment_id,
        form_code=FORM,
        form_version=forms.ATTACHED.version,
        report_type=parent.report_type,
        state=rules.DRAFT,
        note=reason,
        entries={"due_source": None},
        created_by=str(ctx.user_id),
        created_at=now,
        updated_at=now,
    )
    db.add(child)
    db.flush()
    old = {"state": parent.state}
    parent.state, parent.updated_at = rules.FOLLOW_UP, now
    _audit(db, ctx, "REPORT_FOLLOW_UP_CREATED", child, parent_id=str(parent.id), reason=reason)
    _audit(db, ctx, "REPORT_FOLLOW_UP_DUE", parent, old, {"state": rules.FOLLOW_UP}, follow_up=str(child.id))
    db.commit()
    return detail(db, control_db, ctx, child)


def close_problem(db, obligation) -> tuple[int, str, str] | None:
    """Why an Other Regulatory Report cannot be closed (OC-09): never submitted, or a follow-up still open. The reason
    itself is asked by the shared Close route."""
    if obligation.state not in CLOSABLE:
        return 409, "NOT_SUBMITTED", "A report is closed once it is submitted"
    if any(row.state in OPEN_FOLLOW_UP for row in _children(db, obligation)):
        return 409, "FOLLOW_UP_OPEN", "Close every follow-up report first"
    return None
