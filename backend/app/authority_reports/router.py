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
- ``GET /api/v1/reports/{id}/worksheet.pdf`` and ``.docx`` (``snapshot`` for an approved one; an approved US report's
  PDF is FDA's own Form 3500A, filled), ``/emdr.xml`` (an approved US report as FDA's eMDR file), and an evidence file.

MDARIX never submits: no route here sends anything anywhere. Snapshots, attempts and evidence are never edited or
deleted through the API. Reading is open to every signed-in member; changes need regulatory.review or
regulatory.approve. These routes serve a free trial and a pilot alike (T-B1).
"""

from __future__ import annotations

from backend.app.trial.sample_source import is_sample
from backend.app.downloads import attachment
from backend.app import links
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
from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.authority_reports import ReportEvidence, ReportObligation, ReportSnapshot, ReportSubmission
from backend.app.db.models.foundation import Complaint, SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.reportability import assessments, deadlines, markets
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.standards import STARTER_MARK, chips
from backend.app.workflow import approvals
from backend.app.workflow.tasks import run_hook
from backend.app.business_ids import complaint_ref
from object_storage.service import ObjectStorageService

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


def _approved_only(frozen) -> None:
    """A file sent to an authority comes only from the snapshot that is approved now, never from a superseded one."""
    if frozen.state != "APPROVED":
        raise _error(
            409,
            "SNAPSHOT_NOT_APPROVED",
            "This snapshot is not the approved report (superseded by a later version, or cancelled): use the approved one",
        )


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


def new_navigation(control_db, tenant_id) -> bool:
    """Whether the organization is on the new navigation (Release C's switch, ``tenants.navigation``): there a report
    is created when its conclusion is signed, Send for approval waits for every mandatory field, and the PDF comes
    after approval (0.10.75, C3). The classic navigation keeps its rules."""
    from backend.app.db.models.foundation import Tenant

    tenant = control_db.get(Tenant, tenant_id)
    return tenant is not None and tenant.navigation == "new"


def _names(control_db, tenant_id, refs) -> dict[str, str]:
    found = people(control_db, tenant_id, [ref for ref in refs if ref])
    return {**SAMPLE_NAMES, **found}


def _audit(db, ctx, action: str, obligation: ReportObligation, old=None, new=None, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=obligation.tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="ReportObligation",
            entity_id=obligation.id,
            correlation_id=ctx.correlation_id,
            details={"complaint_id": str(obligation.complaint_id), "market": obligation.market, **details},
            old_values=old,
            new_values=new,
        )
    )


def _obligation(db, tenant_id, obligation_id, *, lock: bool = False) -> ReportObligation:
    query = db.query(ReportObligation).filter(
        ReportObligation.tenant_id == tenant_id, ReportObligation.id == obligation_id
    )
    # Fresh values under the lock, not the identity map's copies read before it (code audit 6).
    found = (query.with_for_update().populate_existing() if lock else query).one_or_none()
    if found is None:
        raise _error(404, "REPORT_NOT_FOUND", "No such report in your organization")
    return found


def _form(obligation: ReportObligation) -> forms.Form:
    return forms.FORMS[obligation.form_code]


def _snapshots(db, obligation: ReportObligation, *, fresh: bool = False) -> list[ReportSnapshot]:
    query = db.query(ReportSnapshot).filter(
        ReportSnapshot.tenant_id == obligation.tenant_id, ReportSnapshot.obligation_id == obligation.id
    )
    return (query.populate_existing() if fresh else query).order_by(ReportSnapshot.version).all()


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
    # On the new navigation a mapped code is a suggestion a person confirms (0.10.77, C5).
    context["confirm_codes"] = new_navigation(control_db, obligation.tenant_id)
    # Before approval freezes it, the contact office (G1) is checked as the eMDR file needs it (0.10.92, A5).
    context["check_contact_office"] = obligation.state in rules.EDITABLE
    if is_follow_up(obligation):
        parent = db.get(ReportObligation, obligation.parent_id)
        chain = _follow_ups(db, obligation.tenant_id, parent.id)
        context["follow_up"] = {
            "number": follow_up_number(chain, obligation),
            "report_type": parent.report_type,
            "previous": _chain_values(db, [parent, *chain], obligation),
        }
    return context


# --------------------------------------------------------------------------------------------- US follow-ups (B3)


def is_follow_up(obligation: ReportObligation) -> bool:
    """A US follow-up (0.10.96, B3 group B): a Form 3500A child of an initial report, in its chain (21 CFR 803.56)."""
    return obligation.parent_id is not None and obligation.form_code == forms.FDA_3500A.code


def _follow_ups(db, tenant_id, parent_id) -> list[ReportObligation]:
    return (
        db.query(ReportObligation)
        .filter(
            ReportObligation.tenant_id == tenant_id,
            ReportObligation.parent_id == parent_id,
            ReportObligation.form_code == forms.FDA_3500A.code,
        )
        .order_by(ReportObligation.created_at, ReportObligation.id)
        .all()
    )


def _chain_values(db, chain: list, obligation) -> dict[str, str]:
    """What FDA holds for the chain before this follow-up (B2): the values of the last submitted report's approved
    snapshot (each snapshot keeps every value, so the last is the merged one)."""
    from backend.app.authority_reports import fda_3500a

    mine = (obligation.created_at, str(obligation.id))
    sent = [row for row in chain if (row.created_at, str(row.id)) < mine and row.state in rules.SUBMITTED]
    approved = [row for row in _snapshots(db, sent[-1]) if row.state == "APPROVED"] if sent else []
    return fda_3500a.values((approved[-1].fields or {}).get("sections", [])) if approved else {}


def follow_up_number(chain: list, row) -> int:
    """A follow-up's number: 1 + the follow-ups before it that were submitted. One is open at a time, so the numbers
    run 1, 2, 3 without gaps; a follow-up cancelled before it was sent never takes one."""
    earlier = [item for item in chain if (item.created_at, str(item.id)) < (row.created_at, str(row.id))]
    return 1 + sum(item.state in rules.SUBMITTED for item in earlier)


def state_label(row) -> str:
    """A state's label; a follow-up cancelled before it went out says so (it was never "not reportable")."""
    if row.state == rules.CANCELLED and is_follow_up(row):
        return "Cancelled before it was sent"
    return rules.STATE_LABELS[row.state]


def _h2(value: str) -> str | None:
    """Why an H2 value is not FDA's follow-up types (None: it is)."""
    from backend.app.authority_reports import fda_3500a

    found, other = fda_3500a.choices("H2", value)
    if found and not other:
        return None
    return (
        "Choose FDA's follow-up types: Correction; Additional information; Response to FDA request; Device evaluation"
    )


def _preparers(obligation: ReportObligation, extra: str | None = None) -> set[str]:
    found = {obligation.created_by, *(entry.get("by") for entry in (obligation.entries or {}).values())}
    if extra:
        found.add(extra)
    return {ref for ref in found if ref}


def standing(control_db, ctx, tenant_id, preparers: set[str], signer: str | None, trial: bool) -> dict:
    """Whether this person may approve the snapshot, told before any password (J13, workflow/approvals.py): never the
    preparer, the conclusion's signer or an administrator, except that working alone in a trial one may approve one's
    own practice report ("same person", T-B8); the colleagues who may approve, by name."""
    me = str(ctx.user_id)
    person = current_person(control_db, ctx)
    role = person.role_for(REGULATORY_APPROVE if person.holds(REGULATORY_APPROVE) else REGULATORY_REVIEW)
    if person.holds_any(*approvals.PERMISSIONS):
        problem = rules.approver_problem(me, role, preparers, signer)
        separation = problem is not None and (role or "").upper() not in rules.ADMINISTRATOR_ROLES
    else:
        problem, separation = approvals.NO_RIGHTS, False
    others = [name for _, name in approvals.approvers(control_db, tenant_id, {*preparers, signer, me})]
    return {**approvals.standing(problem, separation, others, trial, role, "report"), "role": role}


def _deadline(obligation: ReportObligation, context: dict, today, org_zone: str | None = None) -> dict:
    """The obligation's deadline: the one it was given (a rejection never moves it); while it is provisional, the
    market assessment's current one."""
    due = obligation.due_on
    provisional = obligation.due_provisional
    if provisional:
        row = context["current"] or context["draft"]
        if row is not None and row.due_on is not None:
            due = row.due_on
            provisional = row.conclusion is None
    return due_fields(
        due, obligation.market, org_zone, today, provisional, obligation.state in rules.MET, obligation.state
    )


def due_fields(
    due: date | None, market: str, org_zone: str | None, now, provisional: bool, met: bool, state: str | None = None
) -> dict:
    """A report's deadline on the wire: its latest day, its end with the time zone, days left, and overdue (never
    once met, never once cancelled), counted by the market's rule (reportability/deadlines.py). A cancelled report's
    deadline state is CANCELLED (0.10.81, F11: it read MET)."""
    cancelled = state == rules.CANCELLED
    if due is None:
        return {
            "due_on": None,
            "provisional": provisional,
            "days_left": None,
            "overdue": False,
            **deadlines.end_fields(None, None, None),
            "due_state": None,
        }
    found = deadlines.end_of(due, market, org_zone)
    clock = deadlines.state(found, now, 1)
    return {
        "due_on": due.isoformat(),
        "provisional": provisional,
        "days_left": deadlines.days_left(found, now),
        "overdue": clock == deadlines.OVERDUE and not met and not cancelled,
        "due_at": found.at.isoformat(),
        "due_zone": found.zone,
        "due_label": found.label,
        "due_state": rules.CANCELLED if cancelled else "MET" if met else clock,
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
        "same_person": bool(row.approved_by)
        and (
            row.approved_by in (row.preparers or []) or row.approved_by == (row.fields or {}).get("conclusion_signer")
        ),
        "sample": is_sample(row.source_system),
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


def _submission_view(
    row: ReportSubmission, evidence: list[ReportEvidence], names: dict, due_on, market=None, org_zone=None
) -> dict:
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
        "follow_up": rules.follow_up(row.submitted_at, due_on, row.route, market, org_zone)
        if row.result == "PENDING"
        else None,
        "recorded_by": names.get(row.recorded_by) or "A colleague",
        "recorded_at": _iso(row.recorded_at),
        "evidence": [_evidence_view(item, names) for item in evidence],
        "receipt_only": row.result == "PENDING" and any(item.outcome == "RECEIPT" for item in evidence),
        "sample": is_sample(row.source_system),
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
    today = deadlines.as_moment(None)
    form = _form(obligation)
    context = _context(db, control_db, obligation)
    snapshots = _snapshots(db, obligation)
    submissions = _submissions(db, obligation)
    evidence = _evidence(db, tenant_id, [row.id for row in submissions])
    names = _names(control_db, tenant_id, _refs(obligation, snapshots, submissions, evidence, context))
    sections = worksheet.build(form, context, obligation.entries or {}, names, obligation.request_text)
    deadline_zone = deadlines.org_zone(db, tenant_id)
    deadline = _deadline(obligation, context, today, deadline_zone)
    due = date.fromisoformat(deadline["due_on"]) if deadline["due_on"] else None
    pending = next((row for row in snapshots if row.state == "PENDING"), None)
    approved = next((row for row in reversed(snapshots) if row.state == "APPROVED"), None)
    mandatory = worksheet.mandatory(sections)
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
            "ref": complaint_ref(record),
            "business_id": record["business_id"],
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
            "starter": form.starter,
            "report_types": list(form.report_types),
            "report_kind": forms.report_kind(form, obligation.entries or {}),
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
        "state_label": state_label(obligation),
        "next_step": rules.next_step(obligation.state, pending is not None),
        "steps": [{"state": step, "label": rules.STATE_LABELS[step]} for step in rules.STEPS],
        # The status path and the mandatory-fields meter (0.10.75, C3).
        **rules.stage_view(obligation.state, len(mandatory["missing"]), pending is not None, state_label(obligation)),
        "mandatory": mandatory,
        "approved_snapshot": _snapshot_view(approved, names) if approved else None,
        "preparers": sorted({names.get(ref) or "A colleague" for ref in _preparers(obligation)}),
        "cancelled_reason": obligation.note if obligation.state == rules.CANCELLED else None,
        "conclusion_changed": conclusion_changed(obligation, context["current"]),
        "deadline": deadline,
        "report_type": obligation.report_type,
        "assessment": _assessment_view(context, names),
        "case": worksheet.SOURCES["case"](context)[0] if context["case"] else None,
        "sections": sections,
        "counts": worksheet.counts(sections),
        "status_labels": worksheet.STATUS_LABELS,
        "editable": obligation.state in rules.EDITABLE,
        "snapshots": [_snapshot_view(row, names) for row in reversed(snapshots)],
        # The approver reads the values as frozen, in the form's order, with each value's source (0.10.83, D2.8).
        "pending_snapshot": {**_snapshot_view(pending, names), "sections": (pending.fields or {}).get("sections")}
        if pending
        else None,
        # Every signature on the report: who, when and what it means (21 CFR 11.50; 0.10.83, D2.8).
        "signatures": signatures(context, pending or approved, names),
        "cannot_approve": sorted({names.get(ref) or "A colleague" for ref in (*_preparers(obligation), signer) if ref}),
        # Who approves, before anyone types a password: for the waiting snapshot, else for the one this person asks.
        "approval": standing(
            control_db,
            ctx,
            tenant_id,
            set(pending.preparers or []) | _preparers(obligation)
            if pending
            else _preparers(obligation, str(ctx.user_id)),
            ((pending.fields or {}).get("conclusion_signer") if pending else None) or signer,
            trial,
        )
        if obligation.state in rules.EDITABLE
        else None,
        "submissions": [
            _submission_view(row, evidence.get(row.id, []), names, due, obligation.market, deadline_zone)
            for row in reversed(submissions)
        ],
        "request": (
            {"text": obligation.request_text, "received_on": _iso(obligation.request_received_on)}
            if obligation.kind == "RESPONSE"
            else None
        ),
        # FDA requests recorded on this open follow-up after it was started (owner decision 1 after B3 run 4).
        "fda_requests": ((obligation.entries or {}).get("FDA_REQUESTS") or {}).get("items") or [],
        "parent_id": str(obligation.parent_id) if obligation.parent_id else None,
        # A US follow-up's number in its chain (0.10.96, B3): "Follow-up #n".
        "follow_up": (context.get("follow_up") or {}).get("number"),
        "responses": [
            {
                "id": str(row.id),
                "state": row.state,
                "state_label": state_label(row),
                "due_on": _iso(row.due_on),
                "request_text": row.request_text,
                "received_on": _iso(row.request_received_on),
                "follow_up": follow_up_number([c for c in children if is_follow_up(c)], row)
                if is_follow_up(row)
                else None,
            }
            for row in children
        ],
        "note": obligation.note,
        "follow_up_due_on": _iso(obligation.follow_up_due_on),
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
        # A mapped code is a suggestion a person confirms or changes (the new navigation, 0.10.77).
        "codes_confirmed": context["confirm_codes"],
        "never_submits": rules.NEVER_SUBMITS,
        "sample": is_sample(obligation.source_system),
        # What the eMDR file still needs, and what it leaves out, read from the approved report (or the draft); on a
        # draft also whether FDA's schema takes the file (0.10.96: Send for approval refuses otherwise).
        "emdr": _emdr_check(
            (approved.fields or {}).get("sections") if approved else sections,
            context,
            _emdr_kind(obligation),
            frozen=bool(approved and "emdr_xml" in (approved.fields or {})),
        )
        if form.code == forms.FDA_3500A.code
        else None,
    }


def _emdr_kind(obligation: ReportObligation) -> str:
    """The eMDR report type: a manufacturer's initial report, or a follow-up in its chain."""
    return "M-I" if obligation.kind == "INITIAL" else "M-F"


def _emdr_check(sections, context, kind: str = "M-I", frozen: bool = False) -> dict:
    from backend.app.authority_reports import emdr

    previous = (context.get("follow_up") or {}).get("previous")
    found = emdr.prepare(
        sections or [], context["parties"], kind=kind, sender="-", now=_now(), practice=False, previous=previous
    )
    return {
        # An approved file is frozen and signed: today's Settings never block its download (review B3-Z 7).
        "missing": [] if frozen else found["missing"],
        "left_out": found["left_out"],
        "schema_errors": [] if frozen else found["errors"],
        "changed": found["changed"],  # a follow-up: what its file sends, new or changed since the last one sent
    }


def _emdr_gate(found: dict) -> None:
    """Send for approval refuses a US report whose eMDR file FDA would refuse, naming each block (0.10.96, A2)."""
    if found["missing"]:
        raise _error(
            422,
            "EMDR_MISSING",
            "Before sending for approval, the eMDR file needs: " + "; ".join(found["missing"]),
            missing=found["missing"],
        )
    if found["errors"]:
        raise _error(
            422,
            "EMDR_INVALID",
            "The eMDR file does not validate against FDA's schema: " + "; ".join(found["errors"][:3]),
            errors=found["errors"][:10],
        )


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
    today = deadlines.as_moment(None)
    org_zone = deadlines.org_zone(db, tenant_id)
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
    paths = _list_paths(db, control_db, ctx, tenant_id, [row for row in obligations if row.complaint_id in complaints])
    # The EU, GB and Canada worksheets are the new navigation's (0.10.76); the classic one keeps the US and India.
    fresh = new_navigation(control_db, tenant_id)

    def base(complaint, market):
        return {
            "complaint_id": str(complaint.id),
            "complaint_ref": complaint_ref(complaint),
            "complaint_identifier": complaint.complaint_identifier,
            "description": complaint.description,
            "market": market,
            "market_label": markets.MARKET_LABELS.get(market, market),
            "sample": is_sample(complaint.source_system),
        }

    for row in candidates:
        complaint = complaints.get(row.complaint_id)
        if complaint is None or (row.complaint_id, row.market) in started:
            continue
        form = forms.form_for(row.market, fresh)
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
                **due_fields(row.due_on, row.market, org_zone, today, row.conclusion is None, bool(row.filed_on)),
                "assessment": markets.CONCLUSION_LABELS.get(row.conclusion or row.suggested_conclusion),
                "can_start": bool(form) and not row.filed_on,
                "stage": None,
                "views": [],
            }
        )
    chains: dict = {}
    for row in sorted(obligations, key=lambda item: (item.created_at, str(item.id))):
        if is_follow_up(row):
            chains.setdefault(row.parent_id, []).append(row)
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
                # "Follow-up #n" in the list (0.10.96, B3 B1).
                "follow_up": follow_up_number(chains[row.parent_id], row) if is_follow_up(row) else None,
                "form_title": forms.FORMS[row.form_code].title,
                "form_version": row.form_version,
                "state": row.state,
                "state_label": state_label(row),
                "next_step": rules.next_step(row.state),
                **due_fields(due, row.market, org_zone, today, row.due_provisional, row.state in rules.MET, row.state),
                "assessment": None,
                "can_start": False,
                **paths[row.id],
            }
        )
    items.sort(key=lambda item: (item["state"] in rules.CLOSED, item["due_at"] or "9999", item["complaint_ref"] or ""))
    return {
        "items": items,
        "forms": [
            {"market": market, "title": form.title, "version": form.version, "starter": form.starter}
            for market, form in forms.BY_MARKET.items()
            if forms.form_for(market, fresh)
        ],
        "never_submits": rules.NEVER_SUBMITS,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if _trial(control_db, tenant_id) else None,
    }


# The Reports tab's list views (0.10.75, C3), each a filter of the one list: still owed, waiting for this person's
# approval (in a trial one's own too, as practice; as Complaints' "Waiting for my approval"), submitted this month.
REPORT_VIEWS = ("open", "my-approval", "submitted-month")


def _list_paths(db, control_db, ctx, tenant_id, obligations: list[ReportObligation]) -> dict:
    """Each started report's place on the status path, its mandatory-fields meter, its latest submission and the list
    views it belongs to. shortcut: reads each report's worksheet (a few queries a report), fine for a trial's or a
    pilot's tens of reports; batch the reads if an organization keeps hundreds open."""
    from zoneinfo import ZoneInfo

    if not obligations:
        return {}
    ids = [row.id for row in obligations]
    pending = {
        row.obligation_id: row
        for row in db.query(ReportSnapshot).filter(
            ReportSnapshot.tenant_id == tenant_id,
            ReportSnapshot.obligation_id.in_(ids),
            ReportSnapshot.state == "PENDING",
        )
    }
    latest: dict = {}
    for row in db.query(ReportSubmission).filter(
        ReportSubmission.tenant_id == tenant_id, ReportSubmission.obligation_id.in_(ids)
    ):
        if row.obligation_id not in latest or row.submitted_at > latest[row.obligation_id]:
            latest[row.obligation_id] = row.submitted_at
    try:
        zone = ZoneInfo(deadlines.org_zone(db, tenant_id) or "UTC")
    except Exception:  # an unknown zone name: count the month in UTC
        zone = timezone.utc
    month = _now().astimezone(zone).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    practice = _trial(control_db, tenant_id)
    out = {}
    for row in obligations:
        try:
            context = _context(db, control_db, row)
        except HTTPException:
            context = None
        meter = (
            worksheet.mandatory(worksheet.build(_form(row), context, row.entries or {}, {}, row.request_text))
            if context is not None
            else {"total": 0, "filled": 0, "missing": []}
        )
        waiting = pending.get(row.id)
        path = rules.stage_view(row.state, len(meter["missing"]), waiting is not None, state_label(row))
        signer = context["current"].signed_by if context is not None and context["current"] else None
        mine = (
            waiting is not None
            and (
                standing(
                    control_db,
                    ctx,
                    tenant_id,
                    set(waiting.preparers or []) | _preparers(row),
                    (waiting.fields or {}).get("conclusion_signer") or signer,
                    practice,
                )["may_approve"]
            )
        )
        views = [
            name
            for name, holds in (
                ("open", row.state not in rules.CLOSED),
                ("my-approval", mine),
                # Submitted, and still so: a report sent back for correction is not (0.10.81).
                ("submitted-month", row.state in rules.SUBMITTED and row.id in latest and latest[row.id] >= month),
            )
            if holds
        ]
        out[row.id] = {
            "stage": path["stage"],
            "stage_label": path["stage_label"],
            "mandatory": {"total": meter["total"], "filled": meter["filled"]},
            "submitted_at": _iso(latest.get(row.id)),
            "views": views,
        }
    return out


class StartRequest(BaseModel):
    complaint_id: uuid.UUID
    market: str = Field(max_length=10)


def start(
    db,
    tenant_id,
    complaint_id,
    market: str,
    actor: str,
    now: datetime,
    source_system: str | None = None,
    candidate: ComplaintMarketAssessment | None = None,
):
    """A new initial obligation for the complaint and market, from its market assessment (shared with the sample and
    with the signing of a reportable conclusion, which passes its signed version as ``candidate``)."""
    form = forms.BY_MARKET.get(market)
    if form is None:
        raise _error(
            409, "NO_WORKSHEET", "This market's worksheet comes later: record the filing on its signed conclusion"
        )
    if candidate is None:
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
    if market in forms.BY_MARKET and forms.form_for(market, new_navigation(control_db, tenant_id)) is None:
        raise _error(
            409, "NO_WORKSHEET", "This market's worksheet comes later: record the filing on its signed conclusion"
        )
    try:
        obligation = start(db, tenant_id, payload.complaint_id, market, str(ctx.user_id), _now())
        _audit(db, ctx, "REPORT_WORKSHEET_STARTED", obligation, form=obligation.form_code)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "REPORT_EXISTS", "This market's report is already started: open it from the list") from exc
    return detail(db, control_db, ctx, obligation)


def follow_conclusion(db, ctx, tenant_id, complaint_id, market: str, signed, now: datetime) -> list:
    """What a signed market conclusion does to the market's report on the new navigation (0.10.75, C3), in the
    signing's own transaction. Reportable: the report is created from the signed version (one per market per complaint;
    a cancelled one is reopened). Not reportable: a report not yet submitted is cancelled, its reason kept and audited
    (a submitted one stays as recorded). A draft conclusion never comes here. Returns the pending snapshots whose
    approval tasks end once the signing is saved."""
    if market not in forms.BY_MARKET:
        return []
    existing = (
        db.query(ReportObligation)
        .filter(
            ReportObligation.tenant_id == tenant_id,
            ReportObligation.complaint_id == complaint_id,
            ReportObligation.market == market,
            ReportObligation.kind == "INITIAL",
        )
        .with_for_update()
        .one_or_none()
    )
    label = markets.MARKET_LABELS.get(market, market)
    if signed.conclusion == markets.REPORTABLE:
        if existing is None:
            obligation = start(db, tenant_id, complaint_id, market, str(ctx.user_id), now, candidate=signed)
            _audit(
                db, ctx, "REPORT_CREATED_FROM_CONCLUSION", obligation, form=obligation.form_code, version=signed.version
            )
        elif existing.state == rules.CANCELLED:
            # The cancellation's note leaves the report and stays in the audit trail (0.10.81, F11).
            old = {"state": existing.state, "note": existing.note}
            existing.state, existing.assessment_id, existing.report_type = rules.DRAFT, signed.id, signed.report_type
            existing.due_on, existing.due_provisional, existing.updated_at = signed.due_on, False, now
            existing.note = None
            _audit(
                db,
                ctx,
                "REPORT_REOPENED_BY_CONCLUSION",
                existing,
                old,
                {"state": rules.DRAFT, "note": None},
                version=signed.version,
            )
        return []
    if signed.conclusion != markets.NOT_REPORTABLE or existing is None or existing.state not in rules.CANCELLABLE:
        return []
    reason = (
        f"The {label} conclusion signed on {now.date().isoformat()} (version {signed.version}) says not reportable"
        + (f": {signed.override_reason}" if signed.override_reason else ".")
    )
    pending = []
    for row in _snapshots(db, existing):
        if row.state in ("PENDING", "APPROVED"):
            if row.state == "PENDING":
                pending.append(row.id)
            row.state = "SUPERSEDED"
    before = existing.state
    old = {"state": before, "note": existing.note}
    existing.state, existing.note, existing.updated_at = rules.CANCELLED, reason, now
    _audit(
        db,
        ctx,
        "REPORT_CANCELLED",
        existing,
        old,
        {"state": rules.CANCELLED, "note": reason},
        reason=reason,
        state_before=before,
        version=signed.version,
    )
    return pending


def follow_signed(db, ctx, obligation: ReportObligation, signed, now: datetime) -> list:
    """An open report follows its market's latest signed reportable conclusion (0.10.81, F1): its report type, its due
    date and its provisional flag, audited with before and after. A pending or approved snapshot of another report type,
    or of an earlier signed version of the conclusion, is superseded (it was approved as another report, or on the old
    conclusion's content) and an approved report is a draft again. A report already
    submitted is never changed: the change is audited and the report page flags it, so a follow-up report can be
    considered (``conclusion_changed``). Returns the pending snapshots whose approval tasks end."""
    before = {
        "report_type": obligation.report_type,
        "due_on": _iso(obligation.due_on),
        "provisional": obligation.due_provisional,
    }
    after = {"report_type": signed.report_type, "due_on": _iso(signed.due_on), "provisional": False}
    if is_follow_up(obligation):
        after = before  # a follow-up keeps its own clock (803.56); only a re-sign supersedes its approval
    if obligation.state in rules.SUBMITTED:
        if (before["report_type"], before["due_on"]) != (after["report_type"], after["due_on"]):
            _audit(
                db, ctx, "REPORT_CONCLUSION_CHANGED_AFTER_SUBMISSION", obligation, before, after, version=signed.version
            )
        return []
    if obligation.state not in rules.CANCELLABLE:
        return []
    # A conclusion signed again (a new version) also ends the snapshots of the old one, even with the same report
    # type: their content and signer are the old conclusion's (code audit 4).
    resigned = obligation.assessment_id is not None and obligation.assessment_id != signed.id
    obligation.assessment_id = signed.id
    if before == after and not resigned:
        return []
    pending, superseded = [], []
    if before["report_type"] != after["report_type"] or resigned:
        for row in _snapshots(db, obligation):
            if row.state in ("PENDING", "APPROVED"):
                if row.state == "PENDING":
                    pending.append(row.id)
                superseded.append(row.version)
                row.state = "SUPERSEDED"
        if obligation.state == rules.APPROVED:
            obligation.state = rules.DRAFT
    if not is_follow_up(obligation):
        obligation.report_type, obligation.due_on, obligation.due_provisional = signed.report_type, signed.due_on, False
    obligation.updated_at = now
    action = "REPORT_RETYPED_BY_CONCLUSION" if before != after else "REPORT_RESIGNED_BY_CONCLUSION"
    _audit(db, ctx, action, obligation, before, after, version=signed.version, superseded=superseded)
    return pending


def conclusion_changed(obligation: ReportObligation, current) -> str | None:
    """A submitted report whose market's latest signed conclusion now says otherwise (0.10.81, F1; F13): what to
    consider. It never changes the report."""
    if obligation.kind != "INITIAL" or obligation.state not in rules.SUBMITTED or current is None:
        return None
    label = markets.MARKET_LABELS.get(obligation.market, obligation.market)
    signed = f"The {label} conclusion signed later (version {current.version})"
    if current.conclusion == markets.NOT_REPORTABLE:
        return f"{signed} says not reportable. This report stays as submitted: consider a final report that says so."
    if current.conclusion == markets.REPORTABLE and current.report_type != obligation.report_type:
        kind = markets.REPORT_TYPES.get(current.report_type or "")
        was = markets.REPORT_TYPES.get(obligation.report_type or "")
        return (
            f"{signed} says {kind.label if kind else 'another report type'}; this report was submitted as "
            f"{was.label if was else 'another report type'}. It stays as submitted: consider a follow-up report."
        )
    return None


def end_cancelled_approvals(db, ctx, tenant_id, pending: list, outcome: str = "Cancelled: not reportable") -> None:
    """The approval tasks of the snapshots a cancelled (or retyped) report no longer needs, after the signing is
    saved."""
    for snapshot_id in pending:
        run_hook(
            db,
            "report snapshot approval task",
            approvals.finish,
            tenant_id,
            source_type=OBJECT_TYPE,
            source_id=snapshot_id,
            outcome=outcome,
            actor=str(ctx.user_id),
            approved=False,
        )


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
    # IMDRF codes chosen in the code picker (0.10.77), for a code field: the server writes the field's text.
    codes: list[str] | None = Field(default=None, max_length=5)


def _code_entry(db, control_db, obligation, field, payload: FieldRequest, actor: str) -> dict:
    """A code field's entry (0.10.77): the suggestion confirmed, or the codes chosen in the picker (CHANGED when the
    mapping suggested others, else ENTERED), each code checked against the newest loaded IMDRF release and written
    with its term (and its FDA code on the FDA's form). The entry keeps what was suggested."""
    from backend.app import regulatory_reference as reference

    context = _context(db, control_db, obligation)
    found = worksheet.SOURCES[field.source](context)
    suggestion = found[0] if found else None
    entry = {"by": actor, "at": _iso(_now()), "suggested": suggestion}
    if payload.codes:
        release = reference.newest_release(control_db)
        if not release:
            raise _error(409, "NO_IMDRF_RELEASE", "No IMDRF release is loaded yet")
        codes = [code.strip().upper() for code in payload.codes if code and code.strip()]
        items = reference.chosen_codes(control_db, release, field.source[-1], list(dict.fromkeys(codes)))
        fda = reference.fda_codes(control_db, [item.code for item in items]) if obligation.market == "US" else {}
        value = "; ".join(reference.code_text(item.code, item.term, fda.get(item.code)) for item in items)
        state = worksheet.CONFIRMED if value == suggestion else worksheet.CHANGED if suggestion else None
        return {
            **entry,
            "value": value,
            "codes": [item.code for item in items],
            "release": release,
            "code_state": state,
        }
    if not suggestion:
        raise _error(422, "NOTHING_SUGGESTED", "No code is suggested here: choose one in the code picker")
    return {**entry, "value": suggestion, "code_state": worksheet.CONFIRMED}


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
    follow = is_follow_up(obligation)
    if field.missing == forms.NOT_USED and not (follow and field_id == "H2"):
        raise _error(422, "FIELD_NOT_USED", "This field is not used in this report")
    if follow and field_id == "MFR_REPORT":
        raise _error(422, "FOLLOWS_INITIAL", "A follow-up carries its initial report's number")
    if follow and field_id == "G6":
        raise _error(422, "FOLLOWS_CHAIN", "A follow-up's G6 is its clock and its number in the chain")
    entries = dict(obligation.entries or {})
    before = entries.get(field_id)
    coded = bool(field.source and field.source.startswith("imdrf_"))
    if payload.codes and not coded:
        raise _error(422, "NOT_A_CODE_FIELD", "Only an IMDRF code field takes codes")
    value = None if payload.clear else _text(payload.value, worksheet.VALUE_MAX)
    if value and field.options and value not in field.options:
        raise _error(422, "NOT_A_CHOICE", f"Choose one of: {'; '.join(field.options)}", choices=list(field.options))
    if value and field.source == "front_page":
        raise _error(
            422, "FOLLOWS_FRONT_PAGE", "This field follows the front page's manufacturer report number: change it there"
        )
    if value and field.source == "sent_day":
        raise _error(422, "FILLED_AT_SEND", "This date is filled in with the day the report is sent for approval")
    problem = forms.value_problem(field, value)
    if problem:
        raise _error(422, f"NOT_A_{field.kind}", problem)
    if value and field_id == "G6" and obligation.form_code == forms.FDA_3500A.code:
        from backend.app.authority_reports.emdr import FOLLOW_UP

        if FOLLOW_UP.search(value):  # an initial report is never a follow-up: those are made in the chain
            raise _error(422, "NOT_A_FOLLOW_UP", "A follow-up is started from the submitted report, not typed in G6")
    if value and field_id == "H2" and _h2(value):
        raise _error(422, "NOT_A_CHOICE", _h2(value))
    if value and field.kind == forms.LIST_CODE:
        from backend.app import regulatory_reference as reference

        value = value.upper()
        name = forms.LIST_CODES[field.source][0]
        if name:
            reference._known(control_db, name, value, "CODE_UNKNOWN", f"is not in the loaded {name.replace('_', ' ')}")
    code_state = None
    if payload.clear:
        entries.pop(field_id, None)
    elif coded and (payload.codes or (payload.confirmed and not value)):
        entries[field_id] = _code_entry(db, control_db, obligation, field, payload, str(ctx.user_id))
        code_state = entries[field_id]["code_state"] or worksheet.ENTERED
    elif value:
        entries[field_id] = {"value": value, "by": str(ctx.user_id), "at": _iso(_now())}
    elif payload.confirmed:
        entries[field_id] = {"confirmed": True, "by": str(ctx.user_id), "at": _iso(_now())}
    else:
        raise _error(422, "NOTHING_TO_SAVE", "Enter a value, or confirm the record's value")
    obligation.entries, obligation.updated_at = entries, _now()
    _audit(
        db,
        ctx,
        "REPORT_FIELD_SET",
        obligation,
        # The field's entry before and after (0.10.81, F7): an overwritten value stays in the audit trail.
        _entry_values(field_id, before),
        _entry_values(field_id, entries.get(field_id)),
        field=field_id,
        cleared=payload.clear,
        confirmed=payload.confirmed,
        **({"code_state": code_state, "codes": entries[field_id].get("codes")} if code_state else {}),
    )
    db.commit()
    return detail(db, control_db, ctx, obligation)


@router.post("/{obligation_id}/codes/confirm", dependencies=[DECIDERS])
def confirm_all_codes(
    obligation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Confirm all codes (0.10.96, D8): every code field whose suggested code waits for a person is confirmed as
    suggested, each through the same step as its own Confirm and with its own audit event. A code a person chose, and
    a field with no suggestion, stay as they are (a draft only; suggestions wait only on the new navigation)."""
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    if obligation.state not in rules.EDITABLE:
        raise _error(409, "NOT_A_DRAFT", "Only a draft is changed: reopen it first")
    form = _form(obligation)
    sections = worksheet.build(
        form, _context(db, control_db, obligation), obligation.entries or {}, {}, obligation.request_text
    )
    waiting = [item["id"] for part in sections for item in part["fields"] if item["status"] == worksheet.SUGGESTED]
    if not waiting:
        raise _error(422, "NOTHING_SUGGESTED", "No suggested code waits for confirmation")
    fields = {item.id: item for item in form.fields()}
    entries = dict(obligation.entries or {})
    for field_id in waiting:
        before = entries.get(field_id)
        entries[field_id] = _code_entry(
            db, control_db, obligation, fields[field_id], FieldRequest(confirmed=True), str(ctx.user_id)
        )
        _audit(
            db,
            ctx,
            "REPORT_FIELD_SET",
            obligation,
            _entry_values(field_id, before),
            _entry_values(field_id, entries[field_id]),
            field=field_id,
            cleared=False,
            confirmed=True,
            code_state=worksheet.CONFIRMED,
            codes=None,
            all_codes=True,
        )
    obligation.entries, obligation.updated_at = entries, _now()
    db.commit()
    return detail(db, control_db, ctx, obligation)


class OnceRequest(BaseModel):
    # A product's or the organization's facts, by field id (the US product code and its 510(k) number go together).
    values: dict[str, str] = Field(default_factory=dict, max_length=10)
    # The US contact office's e-mail (G1), added to the responsible party the eMDR file reads it from (0.10.92, A5).
    contact_email: str = Field(default="", max_length=254)


_PARTY_MARKET = {"US": "US", "EU_NI": "EU", "GB": "GB", "IN": "IN", "CA": "CA"}
_US_TYPES = (("DEN", "DE_NOVO"), ("P", "PMA"), ("K", "510K"))


@router.put("/{obligation_id}/once", dependencies=[DECIDERS])
def enter_once(
    obligation_id: uuid.UUID,
    payload: OnceRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Enter a product's or the organization's fact once, for every report (0.10.83, D2.7; usability U-10): it is saved
    on the product (its identity or its registration) or as the market's responsible party, with an audit record,
    and every report of that product reads it from there. A fact the product already holds is never overwritten."""
    from backend.app import regulatory_reference as reference

    tenant_id = _tenant(ctx)
    obligation = _obligation(db, tenant_id, obligation_id, lock=True)
    if obligation.state not in rules.EDITABLE:
        raise _error(409, "NOT_A_DRAFT", "Only a draft is changed: reopen it first")
    fields = {item.id: item for item in _form(obligation).fields()}
    values = {key: _text(value, 200) for key, value in payload.values.items() if _text(value, 200)}
    email = _text(payload.contact_email, 254)
    if not values and not email:
        raise _error(422, "NOTHING_TO_SAVE", "Enter the value")
    if email and len(email) > 50:
        raise _error(422, "EMAIL_TOO_LONG", "FDA's eMDR takes a contact e-mail of up to 50 characters")
    sources = {}
    for field_id in values:
        field = fields.get(field_id)
        if field is None or not worksheet.once_of(field.source):
            raise _error(422, "NOT_ENTERED_ONCE", f"Field {field_id} is entered on this report, not once")
        sources[field.source] = values[field_id]
    context = _context(db, control_db, obligation)
    product = context["product"]
    market = _PARTY_MARKET.get(obligation.market, obligation.market)
    done: list[dict] = []
    identity = {worksheet.ONCE_IDENTITY[key]: value for key, value in sources.items() if key in worksheet.ONCE_IDENTITY}
    registration = {
        worksheet.ONCE_REGISTRATION[key][1]: value
        for key, value in sources.items()
        if key in worksheet.ONCE_REGISTRATION
    }
    parties = {worksheet.ONCE_PARTY[key]: value for key, value in sources.items() if key in worksheet.ONCE_PARTY}
    if (identity or registration) and product is None:
        raise _error(409, "NO_PRODUCT", "This complaint names no product: enter the value on this report")
    if identity:
        held = {column: getattr(product, column) for column in reference.IDENTITY_COLUMNS}
        clash = [column for column, value in identity.items() if held.get(column) and held[column] != value]
        if clash:
            raise _error(409, "PRODUCT_HOLDS_A_VALUE", "The product already holds this value: change it in Products")
        reference.set_identity(db, tenant_id, product.id, {**held, **identity}, control_db)
        done.append({"product": product.product_identifier, **identity})
    if registration:
        number = registration.get("registration_number")
        kind = {"IN": "CDSCO_LICENCE", "GB": "UKCA", "CA": "MDL"}.get(market)
        if market == "US":
            if not (number and registration.get("product_code")):
                raise _error(422, "BOTH_NEEDED", "Give both the FDA product code and the 510(k), PMA or De Novo number")
            kind = next((code for prefix, code in _US_TYPES if number.upper().startswith(prefix)), "EXEMPT")
        reference.add_registration(
            db, tenant_id, product.id, {"market": market, "registration_type": kind, **registration}, control_db
        )
        done.append(
            {"product": product.product_identifier, "market": market, "registration_type": kind, **registration}
        )
    for role, organisation in parties.items():
        held = next(
            (
                item
                for item in reference.responsible_parties(db, tenant_id)
                if item["market"] == market and item["role"] == role
            ),
            None,
        )
        if held is not None:
            raise _error(
                409, "PARTY_EXISTS", "Your organization's details for this market are set: change them in Settings"
            )
        reference.set_party(db, tenant_id, {"market": market, "role": role, "organisation": organisation})
        done.append({"market": market, "role": role, "organisation": organisation})
    if email:
        # G1 reads the US manufacturer, else the importer (worksheet us_contact_office): the e-mail goes there, never
        # over one already given.
        held = next(
            (
                item
                for role in ("MANUFACTURER", "IMPORTER")
                for item in reference.responsible_parties(db, tenant_id)
                if market == "US" and item["market"] == market and item["role"] == role
            ),
            None,
        )
        if held is None:
            raise _error(409, "NO_CONTACT_OFFICE", "Set your US responsible party first, in Settings › Products")
        if held["contact_email"]:
            raise _error(409, "PARTY_EXISTS", "The contact office has an e-mail: change it in Settings › Products")
        reference.set_party(db, tenant_id, {**held, "contact_email": email})
        done.append({"market": market, "role": held["role"], "contact_email": email})
    _audit(db, ctx, "REPORT_FACT_ENTERED_ONCE", obligation, None, {"saved": done}, fields=sorted(values))
    db.commit()
    return detail(db, control_db, ctx, obligation)


def _entry_values(field_id: str, entry: dict | None) -> dict:
    """A worksheet entry as the audit keeps it: its value, codes and whether it was a confirmation."""
    entry = entry or {}
    return {
        field_id: {key: entry[key] for key in ("value", "codes", "code_state", "confirmed") if entry.get(key)} or None
    }


def _conclusion(context: dict, market: str, any_signed: bool = False):
    """The market's signed conclusion a snapshot is approved on: reportable, or for a US follow-up any signed one (a
    follow-up may be sent after a later "not reportable", 0.10.96)."""
    current = context["current"]
    if current is None or (current.conclusion != markets.REPORTABLE and not any_signed):
        raise _error(
            409,
            "CONCLUSION_NOT_SIGNED",
            f"Sign the {markets.MARKET_LABELS.get(market, market)} conclusion as reportable first: a snapshot is "
            "approved on a signed conclusion",
        )
    return current


NUMBER_LOCK = "mdarix-us-report-number:"
NUMBER_AUDIT = (("report_number", "value"), ("number_assigned", "assigned"))


def assign_number(db, control_db, obligation: ReportObligation, actor: str, now: datetime) -> None:
    """The US report number at Send for approval (0.10.96, D5): a blank number becomes the organization's next
    (emdr.next_number), a typed one is kept. Either is unique across every US report of the organization, cancelled
    ones included, so a number is never reused; a follow-up shares its initial report's. Numbers are read under an
    advisory lock held until the transaction ends, so two reports sent at once get different numbers."""
    from sqlalchemy import text

    from backend.app.authority_reports import emdr
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    if is_follow_up(obligation):  # a follow-up carries its initial report's number, never its own
        held = (db.get(ReportObligation, obligation.parent_id).entries or {}).get("MFR_REPORT") or {}
        entries = dict(obligation.entries or {})
        entries["MFR_REPORT"] = {"value": held.get("value"), "by": actor, "at": _iso(now), "follows_initial": True}
        obligation.entries = entries
        return
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"{NUMBER_LOCK}{obligation.tenant_id}"})
    value = ReportObligation.entries["MFR_REPORT"]["value"].astext
    chain = {obligation.id, obligation.parent_id} - {None}
    rows = [
        (number, source == SAMPLE_SOURCE)
        for row_id, parent_id, number, source in db.query(
            ReportObligation.id, ReportObligation.parent_id, value, ReportObligation.source_system
        )
        .filter(
            ReportObligation.tenant_id == obligation.tenant_id,
            ReportObligation.form_code == forms.FDA_3500A.code,
            value.isnot(None),
        )
        .order_by(ReportObligation.created_at, ReportObligation.id)
        if row_id not in chain and parent_id not in chain
    ]
    # A trial's sample report holds a practice number (0.10.96, A9): it is never reused, but never the organization's
    # first number either, so the person still types their own once. Sample numbers go first: the CFN is the last own.
    used = [number for number, sample in sorted(rows, key=lambda row: not row[1])]
    entries = dict(obligation.entries or {})
    typed = (entries.get("MFR_REPORT") or {}).get("value")
    if typed:
        if typed in used:
            raise _error(
                409, "REPORT_NUMBER_IN_USE", f"Report number {typed} is already used by another US report: clear it"
            )
        return
    year = _org_day(db, obligation.tenant_id, now).year
    own = any(not sample and emdr.REPORT_NUMBER.match(number) for number, sample in rows)
    number = emdr.next_number(used, year, _trial(control_db, obligation.tenant_id)) if own else None
    if number is None:
        return  # the organization's first number: a person types it once (FIRST_NUMBER, after the mandatory fields)
    entries["MFR_REPORT"] = {"value": number, "by": actor, "at": _iso(now), "assigned": True}
    obligation.entries = entries


def _first_number(obligation: ReportObligation) -> None:
    if not ((obligation.entries or {}).get("MFR_REPORT") or {}).get("value"):
        raise _error(
            422,
            "REPORT_NUMBER_FIRST",
            "Type your first manufacturer report number once (your CFN or FEI, the year and a 5-digit number, "
            "1234567-2026-00001): MDARIX numbers every later report from it",
        )


def _org_day(db, tenant_id, now: datetime) -> date:
    """The organization's own day of ``now`` (its working calendar's time zone)."""
    from backend.app.oversight.rules import zone_info

    return now.astimezone(zone_info(deadlines.org_zone(db, tenant_id)) or timezone.utc).date()


def frozen_emdr(xml: bytes, parties, sections: list[dict], left: list[str] = ()) -> dict:
    """What a US snapshot keeps of its eMDR file (0.10.96, D6): the file's text, its SHA-256, and the G1 contact
    office and D3 manufacturer it was built from, in parts (the official form reads them, never Settings later); and,
    for the PDF's record page, the approved values the file leaves out as they read at Send."""
    from backend.app.authority_reports import emdr, fda_3500a

    values = fda_3500a.values(sections)
    return {
        "emdr_xml": xml.decode("utf-8"),
        "emdr_sha256": hashlib.sha256(xml).hexdigest(),
        "emdr_parties": {
            "G1": emdr.office(parties, emdr.OFFICE_ROLES, values.get("G1")),
            "D3": emdr.office(parties, emdr.MAKER_ROLES, values.get("D3")),
        },
        "emdr_left_out": list(left),
    }


def snapshot_material(obligation, complaint: str, conclusion_id, sections: list[dict], frozen_file: dict) -> dict:
    """What a snapshot's fingerprint (and so its approval signature) covers: the report, its form, the conclusion,
    the sections and, for a US report, the eMDR file's SHA-256 and the parties it was built from (0.10.96, D6)."""
    return {
        "obligation": str(obligation.id),
        "form": obligation.form_code,
        "form_version": obligation.form_version,
        "complaint": complaint,
        "market": obligation.market,
        "conclusion": str(conclusion_id),
        "sections": sections,
        **{key: frozen_file[key] for key in ("emdr_sha256", "emdr_parties") if key in frozen_file},
    }


def request_snapshot(
    db,
    control_db,
    obligation: ReportObligation,
    actor: str,
    now: datetime,
    source_system=None,
    *,
    strict=False,
    parties=None,
):
    """Freeze the worksheet as the next snapshot, pending approval (shared with the sample). ``strict``: a US report
    whose eMDR file FDA would refuse is refused (Send for approval, 0.10.96)."""
    from backend.app.human_decision.rules import fingerprint

    context = _context(db, control_db, obligation)
    if parties is not None:  # the trial sample's own US manufacturer, never stored (0.10.96, A9)
        context["parties"] = parties
    current = _conclusion(context, obligation.market, any_signed=is_follow_up(obligation))
    if not is_follow_up(obligation):  # FDA's follow-up leaves B4 out (its "Manufacturer Follow-up" example)
        context["sent_day"] = _org_day(db, obligation.tenant_id, now).isoformat()  # B4 (0.10.96, Q3)
    names = _names(control_db, obligation.tenant_id, _preparers(obligation))
    frozen_file: dict = {}
    sections = worksheet.frozen(
        worksheet.build(_form(obligation), context, obligation.entries or {}, names, obligation.request_text)
    )
    if obligation.form_code == forms.FDA_3500A.code:
        from backend.app.authority_reports import emdr
        from backend.app.stage3_workflow_router import _organization_name

        found = emdr.prepare(
            sections,
            context["parties"],
            kind=_emdr_kind(obligation),
            sender=_organization_name(control_db, obligation.tenant_id) or "-",
            now=now,
            practice=_trial(control_db, obligation.tenant_id),
            previous=(context.get("follow_up") or {}).get("previous"),  # a follow-up sends what changed (B2)
        )
        if strict:
            _emdr_gate(found)
        if found["xml"] and not found["errors"]:
            frozen_file = frozen_emdr(found["xml"], context["parties"], sections, found["left_out"])
    if is_follow_up(obligation):
        obligation.assessment_id = current.id  # a later re-sign supersedes its approval (audit fix 4, the chain)
    if obligation.kind == "INITIAL":
        obligation.assessment_id, obligation.report_type = current.id, current.report_type
        if obligation.due_provisional:
            obligation.due_on, obligation.due_provisional = current.due_on, False
    snapshots = _snapshots(db, obligation)
    for row in snapshots:
        if row.state == "PENDING":
            row.state = "SUPERSEDED"
    material = snapshot_material(
        obligation,
        context["record"]["business_id"] or context["record"]["complaint_identifier"],
        current.id,
        sections,
        frozen_file,
    )
    snapshot = ReportSnapshot(
        id=uuid.uuid4(),
        tenant_id=obligation.tenant_id,
        obligation_id=obligation.id,
        version=max((row.version for row in snapshots), default=0) + 1,
        form_version=obligation.form_version,
        fields={
            "sections": sections,
            "complaint": material["complaint"],
            "conclusion_signer": current.signed_by,
            **frozen_file,
        },
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
    if obligation.form_code == forms.FDA_3500A.code:
        assign_number(db, control_db, obligation, str(ctx.user_id), _now())
    if new_navigation(control_db, obligation.tenant_id):
        sections = worksheet.build(
            _form(obligation),
            _context(db, control_db, obligation),
            obligation.entries or {},
            {},
            obligation.request_text,
        )
        missing = worksheet.mandatory(sections)["missing"]
        if missing:
            labels = {
                item["id"]: f"{item['number']} {item['label']}".strip() for part in sections for item in part["fields"]
            }
            raise _error(
                422,
                "MANDATORY_FIELDS_MISSING",
                f"Fill every mandatory field before sending for approval: {len(missing)} still empty ("
                + "; ".join(labels[field] for field in missing)
                + ")",
                missing=missing,
            )
    if obligation.form_code == forms.FDA_3500A.code:
        _first_number(obligation)
    if is_follow_up(obligation) and _h2(((obligation.entries or {}).get("H2") or {}).get("value") or ""):
        raise _error(
            422, "H2_REQUIRED", "Tick at least one H2 follow-up type before sending the follow-up for approval"
        )
    replaced = [row.id for row in _snapshots(db, obligation) if row.state == "PENDING"]
    snapshot = request_snapshot(db, control_db, obligation, str(ctx.user_id), _now(), strict=True)
    _audit(
        db,
        ctx,
        "REPORT_SNAPSHOT_REQUESTED",
        obligation,
        version=snapshot.version,
        fingerprint=snapshot.content_fingerprint,
        # The US report number, and whether MDARIX assigned it at this send (0.10.96, D5).
        **(
            {key: (obligation.entries.get("MFR_REPORT") or {}).get(name) for key, name in NUMBER_AUDIT}
            if obligation.form_code == forms.FDA_3500A.code
            else {}
        ),
    )
    db.commit()
    run_hook(db, "report snapshot approval task", _approval_tasks, control_db, ctx, obligation, snapshot, replaced)
    return detail(db, control_db, ctx, obligation)


def _approval_tasks(db, control_db, ctx, obligation: ReportObligation, snapshot: ReportSnapshot, replaced) -> None:
    """The approver's task in My Work (J13): for each colleague who may approve the snapshot, due at the end of the
    next working day or at the report's deadline when sooner; a replaced snapshot's tasks are cancelled."""
    from backend.app.oversight.service import calendar_of

    actor = str(ctx.user_id)
    for old in replaced:
        approvals.finish(
            db,
            obligation.tenant_id,
            source_type=OBJECT_TYPE,
            source_id=old,
            outcome="Replaced",
            actor=actor,
            approved=False,
        )
    calendar = calendar_of(db, obligation.tenant_id)
    due = calendar.working_day_end(snapshot.requested_at, 1)
    if obligation.due_on:
        due = min(due, rules.deadline_end(obligation.due_on, obligation.market, calendar.zone))
    ref = (snapshot.fields or {}).get("complaint") or str(obligation.complaint_id)
    approvals.ask(
        db,
        control_db,
        obligation.tenant_id,
        source_type=OBJECT_TYPE,
        source_id=snapshot.id,
        # One task per approver, in plain words (0.10.83, D2.8; usability U-09): no "snapshot", the customer's reference.
        title=_task_title(db, control_db, obligation, snapshot),
        due_at=due,
        excluded={*(snapshot.preparers or []), (snapshot.fields or {}).get("conclusion_signer")},
        requester=actor,
        trial=_trial(control_db, obligation.tenant_id),
        details={
            "complaint_id": str(obligation.complaint_id),
            "complaint_business_id": ref,
            "obligation_id": str(obligation.id),
            "market": obligation.market,
            "category": "OBLIGATION",
            "opens": links.target("Complaints", "Reports", record=("report", obligation.id)),
        },
    )


def _task_title(db, control_db, obligation: ReportObligation, snapshot: ReportSnapshot) -> str:
    """ "Approve the India report for SAMPLE-RV-10 (prepared by Asha Quality)"."""
    complaint = db.get(Complaint, obligation.complaint_id)
    ref = complaint_ref(complaint) if complaint is not None else (snapshot.fields or {}).get("complaint")
    market = markets.MARKET_LABELS.get(obligation.market, obligation.market).split(" (")[0]
    preparer = _names(control_db, obligation.tenant_id, [snapshot.requested_by]).get(snapshot.requested_by)
    return f"Approve the {market} report for {ref}" + (f" (prepared by {preparer})" if preparer else "")


class ApproveRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


def signature_meaning(form_title: str, version: int, ref: str) -> str:
    return (
        f"I approve version {version} of the {form_title.replace(' worksheet', '')} for {ref} as the content to "
        "submit. MDARIX does not submit it."
    )


def signatures(context: dict, snapshot: ReportSnapshot | None, names: dict) -> list[dict]:
    """The report's signatures in order, each with the signer's full name, the moment and its meaning: the market
    conclusion it rests on, the preparation sent for approval, and the approval (a practice approval says so)."""
    found = []
    current = context["current"]
    if current is not None and current.signed_at:
        found.append(
            {
                "name": names.get(current.signed_by) or "A colleague",
                "at": _iso(current.signed_at),
                "meaning": f"signed {markets.CONCLUSION_LABELS.get(current.conclusion, '').lower()}",
            }
        )
    if snapshot is not None:
        found.append(
            {
                "name": names.get(snapshot.requested_by) or "A colleague",
                "at": _iso(snapshot.requested_at),
                "meaning": "prepared",
            }
        )
        if snapshot.approved_by:
            practice = snapshot.approved_by in (snapshot.preparers or []) or snapshot.approved_by == (
                snapshot.fields or {}
            ).get("conclusion_signer")
            found.append(
                {
                    "name": names.get(snapshot.approved_by) or "A colleague",
                    "at": _iso(snapshot.approved_at),
                    "meaning": "practice approval (the preparer, working alone in the trial)"
                    if practice
                    else "approved for submission",
                }
            )
    return found


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
    allowed = standing(
        control_db,
        ctx,
        tenant_id,
        set(snapshot.preparers or []) | _preparers(obligation),
        (snapshot.fields or {}).get("conclusion_signer"),
        _trial(control_db, tenant_id),
    )
    role, same_person = allowed["role"], allowed["same_person"]
    if not allowed["may_approve"]:
        problem = allowed["message"]
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
    snapshot = next((row for row in _snapshots(db, obligation, fresh=True) if row.id == snapshot_id), None)
    if snapshot is None or snapshot.state != "PENDING" or obligation.state not in rules.EDITABLE:
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
        remarks=f"{obligation.form_version}, snapshot {snapshot.version}"
        + (", same person (trial practice: prepared and approved by one person)" if same_person else ""),
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
                "same_person": same_person,
            },
            created_at=now,
        )
    )
    snapshot.state, snapshot.approved_by, snapshot.approved_at = "APPROVED", me, now
    snapshot.signed_record_id = record.id
    obligation.state, obligation.updated_at = rules.APPROVED, now
    signing_commit.commit(db, control_db, "report snapshot")
    run_hook(
        db,
        "report snapshot approval task",
        approvals.finish,
        tenant_id,
        source_type=OBJECT_TYPE,
        source_id=snapshot.id,
        outcome="Approved",
        actor=me,
        approved=True,
    )
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
    content_type = _text(payload.content_type, 120) or "application/octet-stream"
    if not ObjectStorageService().scan(data, content_type):
        raise _error(422, "MALWARE_SCAN_REJECTED", "The file failed the malware safety scan")
    return {
        "file_name": _text(payload.name, 200) or "evidence",
        "content_type": content_type,
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
        late=bool(
            obligation.due_on
            and submitted_at
            > rules.deadline_end(obligation.due_on, obligation.market, deadlines.org_zone(db, obligation.tenant_id))
        ),
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
        headers={"Content-Disposition": attachment(f"{row.file_name or 'evidence'}")},
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


class FollowUpCreate(BaseModel):
    received_on: date  # the day the new information arrived (prefilled with today on the page)
    what_is_new: str = Field(max_length=rules.NOTE_MAX * 2)
    h2: list[str] = Field(default_factory=list, max_length=4)
    narrative: str | None = Field(default=None, max_length=worksheet.VALUE_MAX)


FOLLOW_UP_OWN = frozenset({"MFR_REPORT", "B4", "B5", "H11", "H2", "G8", "G6"})


def follow_up_due(received_on: date) -> date:
    """A US follow-up is due 30 calendar days after the information arrived (21 CFR 803.56)."""
    return deadlines.count(received_on, 30, "CALENDAR", markets.US, None).day


def create_follow_up(db, ctx, initial: ReportObligation, received_on: date, text: str, h2: list[str], narrative, due):
    """Follow-up #n of a submitted US initial report (0.10.96, B3 B1), with the initial row locked and read fresh
    (audit fix 6): one open follow-up per chain, FDA's H2 types, and the new narrative (B5) as typed."""
    if not (initial.kind == "INITIAL" and initial.form_code == forms.FDA_3500A.code):
        raise _error(409, "NOT_A_US_INITIAL", "A follow-up is made on a US initial report (Form FDA 3500A)")
    if initial.state not in rules.VALID_SUBMISSION:
        raise _error(409, "NOT_SUBMITTED", "A follow-up follows the initial report once it is submitted and accepted")
    chain = _follow_ups(db, initial.tenant_id, initial.id)
    # Accepted (or cancelled) before the next: one still pending may yet be rejected and come back (review B3-Z 1).
    if any(row.state not in (*rules.VALID_SUBMISSION, rules.CANCELLED) for row in chain):
        raise _error(
            409, "FOLLOW_UP_OPEN", "The last follow-up must be accepted (or cancelled) first: FDA takes them in order"
        )
    ticks = "; ".join(dict.fromkeys(item.strip() for item in h2 if item and item.strip()))
    if ticks and _h2(ticks):
        raise _error(422, "NOT_A_CHOICE", _h2(ticks))
    now, actor = _now(), str(ctx.user_id)
    number = ((initial.entries or {}).get("MFR_REPORT") or {}).get("value")
    # The follow-up starts from what the initial report holds (its file sends only what changes, B2); its narrative
    # (B5, H11) is only what is new, and its number, B4 and H2 are its own.
    entries = {key: value for key, value in (initial.entries or {}).items() if key not in FOLLOW_UP_OWN}
    entries["MFR_REPORT"] = {"value": number, "by": actor, "at": _iso(now), "follows_initial": True}
    if ticks:
        entries["H2"] = {"value": ticks, "by": actor, "at": _iso(now)}
    told = _text(narrative, worksheet.VALUE_MAX) if narrative else None
    if told:
        entries["B5"] = {"value": told, "by": actor, "at": _iso(now)}
    child = ReportObligation(
        id=uuid.uuid4(),
        tenant_id=initial.tenant_id,
        complaint_id=initial.complaint_id,
        market=initial.market,
        kind="RESPONSE",
        parent_id=initial.id,
        assessment_id=initial.assessment_id,
        form_code=initial.form_code,
        form_version=initial.form_version,
        report_type=initial.report_type,
        due_on=due,
        due_provisional=False,
        state=rules.DRAFT,
        entries=entries,
        request_text=text,
        request_received_on=received_on,
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    db.add(child)
    db.flush()
    _audit(
        db,
        ctx,
        "REPORT_FOLLOW_UP_CREATED",
        initial,
        follow_up=str(child.id),
        number=follow_up_number([*chain, child], child),
        due_on=_iso(due),
    )
    return child


@router.post("/{obligation_id}/follow-ups", dependencies=[DECIDERS])
def start_follow_up(
    obligation_id: uuid.UUID,
    payload: FollowUpCreate,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Create follow-up #n of a submitted US report: what is new, the day it arrived, H2 and the new narrative."""
    initial = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    text = _text(payload.what_is_new)
    if not text or len(text) < rules.REASON_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say what is new, in at least {rules.REASON_MIN} characters")
    child = create_follow_up(
        db, ctx, initial, payload.received_on, text, payload.h2, payload.narrative, follow_up_due(payload.received_on)
    )
    db.commit()
    return detail(db, control_db, ctx, child)


@router.post("/{obligation_id}/cancel", dependencies=[DECIDERS])
def cancel_follow_up(
    obligation_id: uuid.UUID,
    payload: ReasonRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Cancel a US follow-up that was never sent (0.10.96), with a reason, audited: its approval ends and the chain is
    free for the next follow-up, which takes its number (numbers count only the follow-ups sent). The initial report
    (it follows its signed conclusion) and a submitted follow-up are never cancelled here."""
    obligation = _obligation(db, _tenant(ctx), obligation_id, lock=True)
    reason = _text(payload.reason)
    if not reason or len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say why, in at least {rules.REASON_MIN} characters")
    if not is_follow_up(obligation):
        raise _error(409, "NOT_A_FOLLOW_UP", "Only a US follow-up is cancelled here: a report follows its conclusion")
    if obligation.state not in rules.CANCELLABLE:
        raise _error(409, "ALREADY_SENT", "This follow-up was submitted (or cancelled): it stays as recorded")
    pending = []
    for row in _snapshots(db, obligation):
        if row.state in ("PENDING", "APPROVED"):
            if row.state == "PENDING":
                pending.append(row.id)
            row.state = "SUPERSEDED"
    before = obligation.state
    old = {"state": before, "note": obligation.note}
    obligation.state, obligation.note, obligation.updated_at = rules.CANCELLED, reason, _now()
    _audit(
        db,
        ctx,
        "REPORT_CANCELLED",
        obligation,
        old,
        {"state": rules.CANCELLED, "note": reason},
        reason=reason,
        state_before=before,
    )
    db.commit()
    end_cancelled_approvals(db, ctx, obligation.tenant_id, pending, "Cancelled: the follow-up was not sent")
    return detail(db, control_db, ctx, obligation)


RESPONSE_TO_FDA = "Response to FDA request"


def attach_request(db, ctx, follow: ReportObligation, text: str, received_on: date, due_on: date) -> ReportObligation:
    """An FDA request that arrives while follow-up ``follow`` is open is kept on it, with its dates (owner decision 1
    after B3 run 4). A draft gets H2 "Response to FDA request" ticked; one not yet sent is due by the earlier date.
    An approved or sent follow-up keeps its file as it is: the page says to reopen it or answer in the next one.
    ``follow`` is locked and read fresh by the caller."""
    entries = dict(follow.entries or {})
    now, actor = _now(), str(ctx.user_id)
    ticks = [item.strip() for item in str((entries.get("H2") or {}).get("value") or "").split(";") if item.strip()]
    tick = follow.state in rules.EDITABLE and RESPONSE_TO_FDA not in ticks
    old = {"H2": "; ".join(ticks) or None, "due_on": _iso(follow.due_on)}
    if tick:
        entries["H2"] = {"value": "; ".join([*ticks, RESPONSE_TO_FDA]), "by": actor, "at": _iso(now)}
    if follow.state in rules.CANCELLABLE and (follow.due_on is None or due_on < follow.due_on):
        follow.due_on = due_on
    # Kept beside the fields (no "by" at the top: recording a request alone does not make a preparer).
    held = (entries.get("FDA_REQUESTS") or {}).get("items") or []
    request = {"text": text, "received_on": _iso(received_on), "due_on": _iso(due_on), "by": actor, "at": _iso(now)}
    entries["FDA_REQUESTS"] = {"items": [*held, {**request, "h2_ticked": RESPONSE_TO_FDA in ticks or tick}]}
    follow.entries, follow.updated_at = entries, now
    new = {"H2": (entries.get("H2") or {}).get("value"), "due_on": _iso(follow.due_on)}
    _audit(db, ctx, "REPORT_REQUEST_ATTACHED", follow, old, new, request_text=text, received_on=_iso(received_on),
           due_on=_iso(due_on), state=follow.state)  # fmt: skip
    return follow


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
    if parent.kind == "INITIAL" and parent.form_code == forms.FDA_3500A.code:
        # A US request for information is answered by a follow-up, H2 "Response to FDA request" (0.10.96, spec 3.3);
        # one arriving while a follow-up is open is recorded on that one (owner decision 1 after B3 run 4).
        def is_open(row) -> bool:
            return row.state not in (*rules.VALID_SUBMISSION, rules.CANCELLED)

        open_one = next((row for row in _follow_ups(db, parent.tenant_id, parent.id) if is_open(row)), None)
        if open_one is not None:  # read again under its lock: it may have been accepted or cancelled meanwhile
            open_one = _obligation(db, parent.tenant_id, open_one.id, lock=True)
            open_one = open_one if is_open(open_one) else None
        if open_one is not None:
            child = attach_request(db, ctx, open_one, text, payload.received_on, payload.due_on)
        else:
            child = create_follow_up(
                db, ctx, parent, payload.received_on, text, [RESPONSE_TO_FDA], None, payload.due_on
            )
        _audit(
            db,
            ctx,
            "REPORT_INFORMATION_REQUESTED",
            parent,
            response=str(child.id),
            due_on=_iso(payload.due_on),
            attached=open_one is not None,
        )
        db.commit()
        return detail(db, control_db, ctx, child)
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
    form: str | None = Query(default=None),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The worksheet as a PDF or DOCX: the approved snapshot exactly as frozen (the record copy) or, before approval,
    the draft as it is now or the snapshot awaiting approval, marked DRAFT - NOT APPROVED (D7). Never a superseded
    snapshot or a cancelled report. "MDARIX never submits", with its form version, the starter-text mark and, in a
    trial, the practice label.

    A US report's PDF (0.10.96, D1 and D2) is its eMDR file laid out as Form FDA 3500A (emdr_pdf: the file frozen at
    Send for approval; for the draft, the file as it builds now); form=official gives FDA's own fillable form, filled
    from the approved snapshot and the parties frozen with it."""
    from backend.app.authority_reports import render
    from backend.app.stage3_workflow_router import _organization_name

    kind = kind.lower()
    if kind not in MEDIA:
        raise _error(404, "FORMAT_NOT_SUPPORTED", "Download the PDF or the DOCX")
    tenant_id = _tenant(ctx)
    obligation = _obligation(db, tenant_id, obligation_id)
    us_pdf = kind == "pdf" and obligation.form_code == forms.FDA_3500A.code
    # B9: an India report's official MvPI form (form=official) and ADRMS entry sheet (form=adrms).
    india_pdf = kind == "pdf" and obligation.form_code == forms.MVPI_MDAE.code and _b9_india()
    if (
        form is not None
        and not (form == "official" and (us_pdf or india_pdf))
        and not (form in INDIA_FILES and india_pdf)
    ):
        raise _error(404, "FORMAT_NOT_SUPPORTED", "The official form is a US or India report's PDF")
    view = detail(db, control_db, ctx, obligation)
    frozen = None
    if snapshot is not None:
        frozen = next((row for row in _snapshots(db, obligation) if row.id == snapshot), None)
        if frozen is None:
            raise _error(404, "SNAPSHOT_NOT_FOUND", "No such snapshot of this report")
        if frozen.state != "PENDING":  # D7: a snapshot awaiting approval previews as DRAFT; a superseded one never
            _approved_only(frozen)
    elif obligation.state == rules.CANCELLED:
        raise _error(409, "REPORT_CANCELLED", "This report was cancelled: there is no draft to preview")
    if frozen is not None:
        signature = None
        if frozen.signed_record_id:
            record = control_db.get(SignedApprovalRecord, frozen.signed_record_id)
            if record is not None:
                signature = {
                    "signer_name": _names(control_db, tenant_id, [record.signer_user_id]).get(record.signer_user_id)
                    or "A colleague",
                    "signer_role": (record.signer_role or "").replace("_", " ").title(),
                    "signed_at": record.signed_at.isoformat(timespec="seconds") if record.signed_at else None,
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
    organization = _organization_name(control_db, tenant_id)
    body = None
    if india_pdf and form is not None:
        if not view.get("signature"):
            raise _error(409, "APPROVE_FIRST", "The official form is filled once the report is approved")
        body = INDIA_FILES[form](view, organization)
    elif us_pdf and form == "official":
        if not view.get("signature"):
            raise _error(409, "APPROVE_FIRST", "FDA's official form is filled once the report is approved")
        body = _official_form(db, control_db, obligation, frozen, view, organization)
    elif us_pdf:
        from backend.app.authority_reports import emdr_pdf

        found = _file_for_pdf(db, control_db, obligation, frozen, view, organization)
        if found:
            body = emdr_pdf.render(found[0], view, organization, found[1], note=found[2])
        elif view.get("signature"):  # approved before 0.10.96, and no file builds from it: today's form, as before
            body = _official_form(db, control_db, obligation, frozen, view, organization)
    if body is None:
        body = render.render(view, kind, organization=organization)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="REPORT_WORKSHEET_DOWNLOADED",
            entity_type="ReportObligation",
            entity_id=obligation.id,
            correlation_id=ctx.correlation_id,
            details={"format": kind.upper(), "snapshot": frozen.version if frozen else None, "form": form or "default"},
        )
    )
    db.commit()
    stem = f"mdarix-{obligation.form_code.lower().replace('_', '-')}-{view['complaint']['ref']}"
    stem += f"-snapshot-{frozen.version}" if frozen else "-draft"
    stem += "-official-form" if form else ""
    return Response(
        content=body,
        media_type=MEDIA[kind],
        headers={"Content-Disposition": attachment(f"{stem}.{kind}")},
    )


def _b9_india() -> bool:
    from backend.app import feature_set

    return feature_set.switched_on("MDARIX_B9_INDIA")


def _mvpi_form(view: dict, organization: str | None) -> bytes:
    from backend.app.authority_reports import mvpi_mdae

    return mvpi_mdae.render(view, organization)


INDIA_FILES = {"official": _mvpi_form}


def snapshot_file(frozen: ReportSnapshot, parties, organization: str | None, practice: bool):
    """A snapshot's eMDR file, its left-out values and how it was made: the file frozen at Send for approval and
    signed with it (0.10.96, D6), the same bytes whatever changed since; for a snapshot approved before 0.10.96, which
    keeps no file, built now from the snapshot and today's parties. Refused (409) rather than a file FDA would refuse."""
    from backend.app.authority_reports import emdr

    stored = (frozen.fields or {}).get("emdr_xml")
    if stored is not None:
        body = stored.encode("utf-8")
        if hashlib.sha256(body).hexdigest() != frozen.fields.get("emdr_sha256"):
            logger.error("eMDR file of snapshot %s does not match its approval", frozen.id)
            raise _error(409, "EMDR_CHANGED", "The stored eMDR file does not match the approved one")
        note = "The file frozen at Send for approval: the approval signature covers it."
        return body, frozen.fields.get("emdr_left_out") or [], note
    sections = frozen.fields["sections"]
    missing, left = emdr.check(sections, parties)
    if missing:
        raise _error(409, "EMDR_MISSING", "Before the eMDR file: " + "; ".join(missing), missing=missing)
    body = emdr.build(sections, parties, sender=organization or "-", now=_now(), practice=practice)
    errors = emdr.validate(body)
    if errors:  # never a file FDA's schema refuses
        logger.error("eMDR file of snapshot %s does not validate: %s", frozen.id, errors[:3])
        raise _error(409, "EMDR_INVALID", "The eMDR file did not validate against FDA's schema", errors=errors[:10])
    return body, left, "Built at download from the approved snapshot and your Settings today (approved before 0.10.96)."


def _file_for_pdf(db, control_db, obligation, frozen, view, organization):
    """The eMDR file the US PDF lays out, its left-out values and how it was made; None when there is none to read (a
    draft or a pending snapshot whose file does not build, or an older approval whose file cannot be built)."""
    from backend.app.authority_reports import emdr

    context = _context(db, control_db, obligation)
    parties = context["parties"]
    practice = _trial(control_db, obligation.tenant_id)
    if frozen is None:  # the working draft, as its file builds now (D7: a preview, marked DRAFT)
        found = emdr.prepare(
            view["sections"],
            parties,
            kind=_emdr_kind(obligation),
            sender=organization or "-",
            now=_now(),
            practice=practice,
            previous=(context.get("follow_up") or {}).get("previous"),  # a follow-up's draft: what it will send
        )
        if not found["xml"] or found["errors"]:
            return None
        return found["xml"], found["left_out"], "Built from the working draft: Send for approval freezes the file."
    if "emdr_xml" not in (frozen.fields or {}) and frozen.state == "PENDING":
        return None
    try:
        return snapshot_file(frozen, parties, organization, practice)
    except HTTPException as refused:
        if refused.detail["code"] == "EMDR_CHANGED":
            raise
        return None


def _official_form(db, control_db, obligation, frozen, view, organization) -> bytes:
    """FDA's own Form 3500A (09/2025), filled from the approved snapshot, with MDARIX's record page last (D2). The G1
    boxes read the contact office frozen with the file; an approval before 0.10.96 reads today's Settings."""
    from backend.app.authority_reports import emdr, fda_3500a

    fields = (frozen.fields if frozen is not None else None) or {}
    if "emdr_parties" in fields:
        contact = fields["emdr_parties"]["G1"]
    else:
        g1 = fda_3500a.values(view["sections"]).get("G1")
        contact = emdr.office(_context(db, control_db, obligation)["parties"], emdr.OFFICE_ROLES, g1)
    return fda_3500a.render(view, organization, contact)


@router.get("/{obligation_id}/emdr.xml", dependencies=[Depends(require_permission(DATA_EXPORT))])
def emdr_file(
    obligation_id: uuid.UUID,
    snapshot: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """An approved US report as FDA's eMDR file (HL7 ICSR XML), validated against FDA's published schema. Refused,
    naming each block, while anything FDA requires is missing. MDARIX never submits: the customer sends the file
    through their own ESG account or eSubmitter, and records the submission here."""
    from backend.app.stage3_workflow_router import _organization_name

    tenant_id = _tenant(ctx)
    obligation = _obligation(db, tenant_id, obligation_id)
    if obligation.form_code != forms.FDA_3500A.code:
        raise _error(404, "NOT_A_US_REPORT", "The eMDR file is for a US report (Form FDA 3500A)")
    frozen = next((row for row in _snapshots(db, obligation) if row.id == snapshot), None)
    if frozen is None:
        raise _error(404, "SNAPSHOT_NOT_FOUND", "No such snapshot of this report")
    if not frozen.signed_record_id:
        raise _error(409, "APPROVE_FIRST", "The eMDR file is made once the report is approved")
    _approved_only(frozen)
    context = _context(db, control_db, obligation)
    organization = _organization_name(control_db, tenant_id)
    body, _, _ = snapshot_file(frozen, context["parties"], organization, _trial(control_db, tenant_id))
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="REPORT_EMDR_DOWNLOADED",
            entity_type="ReportObligation",
            entity_id=obligation.id,
            correlation_id=ctx.correlation_id,
            details={"snapshot": frozen.version},
        )
    )
    db.commit()
    ref = complaint_ref(context["record"])
    return Response(
        content=body,
        media_type="application/xml",
        headers={"Content-Disposition": attachment(f"mdarix-emdr-{ref}-snapshot-{frozen.version}.xml")},
    )
