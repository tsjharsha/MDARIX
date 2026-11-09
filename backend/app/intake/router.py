"""The first contact, urgent intake and triage, duplicates and import history (T-G32, T-G19, T-G20; MVP G32, G19, G20).

- ``GET /api/v1/intake/guide``: the starter first-contact guide, its outcomes table and the starter word lists;
- ``GET /api/v1/intake``, ``POST /api/v1/intake``: the logged contacts and urgent intakes; log one. A contact's
  awareness is the time of the contact; an urgent intake creates a triage item at once and its QMS-complaint task;
- ``GET /api/v1/intake/{id}``: one event with its check's versions, tasks, links and possible duplicates;
- ``PUT /api/v1/intake/{id}/check``: save the answers (the suggestion and the triage flag follow at once, before any
  signature); ``POST .../check/sign``: the coordinator signs the classification (password and authenticator code);
  ``POST .../check/review``: the QA review of a "service only" (agree, or reclassify as a complaint);
- ``POST /api/v1/intake/{id}/follow-up``: close the follow-up with the reporter (answered, or unresolved after
  attempts); ``POST /api/v1/intake/{id}/qms``: enter the QMS complaint ID (awaiting import confirmation), or record
  that none is needed, with a reason;
- ``POST /api/v1/intake/from-complaint/{id}``: the first-contact check of an imported service record (the second look);
- ``GET /api/v1/intake/duplicates``, ``POST /api/v1/intake/links``, ``POST /api/v1/intake/links/{id}/undo``: possible
  duplicates; link or dismiss with a reason; undo a link with a reason;
- ``GET /api/v1/intake/changes``: the field changes a re-upload made;
- ``GET /api/v1/triage``, ``POST /api/v1/triage/escalate``, ``POST /api/v1/triage/{kind}/{id}/record``: the triage
  list before every queue; a manual escalation from any queue; the triage record.

Reading is open to every signed-in member; writing needs the second look's permissions (triage, opening cases or
quality review); administrators never sign. MDARIX never answers, never signs and never submits. These routes serve a
free trial and a pilot alike: they are not part of mvp-1.0's ``_PILOT_API`` gate (T-B1).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.trial.sample_source import is_sample
from backend.app.access.permissions import INVESTIGATION_CREATE, QUALITY_REVIEW, SIGNAL_TRIAGE
from backend.app.complaint_classification import rules as coding
from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Complaint, LotBatch, Product, SignedApprovalRecord
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, RecordLink, TriageRecord
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person, require_any_permission
from backend.app.intake import case_rules, rules, service
from backend.app.paging import open_first
from backend.app.reportability import markets
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training.router import is_trial
from backend.app.standards import STARTER_MARK

logger = logging.getLogger("mdarix.intake")
router = APIRouter(prefix="/api/v1", tags=["First contact and triage"])

OBJECT_TYPE = "FirstContactCheck"
DECISION_TYPE = "FIRST_CONTACT_CHECK"
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})
WRITERS = Depends(require_any_permission(SIGNAL_TRIAGE, INVESTIGATION_CREATE, QUALITY_REVIEW))
# Clock skew allowed for a time entered as "now".
_SKEW = timedelta(minutes=5)


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _tenant(ctx) -> uuid.UUID:
    return uuid.UUID(ctx.tenant_id)


class AnswerIn(BaseModel):
    answer: str | None = Field(default=None, max_length=20)
    note: str = Field(default="", max_length=rules.TEXT_MAX)


class IntakeIn(BaseModel):
    kind: str = Field(default="CONTACT", max_length=20)
    reporter_words: str = Field(min_length=1, max_length=rules.WORDS_MAX)
    reporter_type: str = Field(default="", max_length=40)
    reporter_site: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=80)
    product_id: uuid.UUID | None = None
    lot: str = Field(default="", max_length=120)
    serial_number: str = Field(default="", max_length=120)
    requested: str = Field(default="NONE", max_length=30)
    use_environment: str = Field(default="UNKNOWN", max_length=30)
    user_type: str = Field(default="UNKNOWN", max_length=30)
    event_at: datetime | None = None
    event_zone: str = Field(default="", max_length=60)
    first_knowledge_at: datetime | None = None
    first_knowledge_zone: str = Field(default="", max_length=60)
    first_knowledge_party: str = Field(default="", max_length=30)
    first_knowledge_basis: str = Field(default="", max_length=30)
    received_at: datetime | None = None
    received_zone: str = Field(default="", max_length=60)
    awareness_at: datetime | None = None
    awareness_zone: str = Field(default="", max_length=60)
    service_ticket: str = Field(default="", max_length=120)
    answers: dict[str, AnswerIn] = Field(default_factory=dict, max_length=12)
    unknowns: str = Field(default="", max_length=rules.TEXT_MAX)
    # 0.10.93 (B2): ID-1 and S-3 identifiers with their status and source, S-1 category, idempotent create (A4).
    udi: str = Field(default="", max_length=120)
    software_version: str = Field(default="", max_length=60)
    hardware_revision: str = Field(default="", max_length=60)
    firmware_version: str = Field(default="", max_length=60)
    identifiers: dict[str, dict] = Field(default_factory=dict, max_length=8)
    issue_category: str = Field(default="", max_length=20)
    request_key: str = Field(default="", max_length=80)


class CheckIn(BaseModel):
    answers: dict[str, AnswerIn] = Field(default_factory=dict, max_length=12)
    unknowns: str = Field(default="", max_length=rules.TEXT_MAX)
    seen_version: int = Field(default=0, ge=0)


class SignIn(BaseModel):
    classification: str = Field(max_length=30)
    override_reason: str = Field(default="", max_length=rules.TEXT_MAX)
    reason: str = Field(default="", max_length=rules.TEXT_MAX)
    service_ticket: str = Field(default="", max_length=120)
    seen_version: int = Field(ge=1)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


class ReviewIn(BaseModel):
    outcome: str = Field(max_length=20)
    note: str = Field(default="", max_length=rules.TEXT_MAX)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)
    # S-2: what was done for the customer; required before a service-only Case is closed.
    resolution_summary: str = Field(default="", max_length=rules.TEXT_MAX)


class FollowUpIn(BaseModel):
    outcome: str = Field(max_length=20)
    note: str = Field(default="", max_length=rules.TEXT_MAX)


class QmsIn(BaseModel):
    qms_ref: str = Field(default="", max_length=120)
    not_needed_reason: str = Field(default="", max_length=rules.TEXT_MAX)


class LinkIn(BaseModel):
    left_kind: str = Field(max_length=20)
    left_id: uuid.UUID
    right_kind: str = Field(max_length=20)
    right_id: uuid.UUID
    decision: str = Field(max_length=20)
    reason: str = Field(default="", max_length=rules.TEXT_MAX)


class UndoIn(BaseModel):
    reason: str = Field(default="", max_length=rules.TEXT_MAX)


class EscalateIn(BaseModel):
    kind: str = Field(max_length=20)
    id: uuid.UUID
    reason: str = Field(default="", max_length=rules.TEXT_MAX)


class TriageIn(BaseModel):
    severity: str = Field(max_length=20)
    public_health_threat: bool = False
    remedial_action: bool = False
    event_owner: str = Field(max_length=64)
    triage_owner: str = Field(max_length=64)
    backup_owner: str = Field(default="", max_length=64)
    immediate_action: str = Field(default="", max_length=rules.TEXT_MAX)
    no_action_reason: str = Field(default="", max_length=rules.TEXT_MAX)
    awareness_confirmed_at: datetime | None = None
    awareness_note: str = Field(default="", max_length=rules.TEXT_MAX)


# --------------------------------------------------------------------------------------------- reading


@router.get("/intake/guide")
def guide(_ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """The starter first-contact guide (starter text, T-B6), its outcomes table, the starter word lists and the time
    zones a call's times are entered in."""
    from backend.app.oversight.rules import LEGACY_ZONES, zone_names

    return {
        "version": case_rules.GUIDE_VERSION,
        "questions": [
            {
                "id": question,
                "text": text,
                "not_stated": question in rules.HARM_QUESTIONS,
                "free_text": question == "Q10",
            }
            for question, text in rules.QUESTIONS
        ],
        "answers": [{"code": code, "label": rules.ANSWER_LABELS[code]} for code in rules.ANSWERS],
        "note": rules.GUIDE_NOTE,
        "outcomes": [{"code": code, "label": case_rules.OUTCOME_LABELS[code]} for code in case_rules.OUTCOMES],
        "states": [{"code": code, "label": case_rules.STATE_LABELS[code]} for code in case_rules.STATES],
        "issue_categories": [{"code": code, "label": label} for code, label in case_rules.ISSUE_CATEGORIES.items()],
        "identifiers": {
            "keys": [{"code": key, "label": case_rules.IDENTIFIER_LABELS[key]} for key in case_rules.IDENTIFIERS],
            "not_sure": list(case_rules.NOT_SURE_ALLOWED),
            "sources": [{"code": code, "label": label} for code, label in case_rules.SOURCE_LABELS.items()],
        },
        "table": [{"row": row, "answers": answers, "outcome": result} for row, answers, result in rules.OUTCOME_TABLE],
        "requests": [{"code": code, "label": rules.REQUEST_LABELS[code]} for code in rules.REQUESTS],
        "use_environments": [{"code": c, "label": label} for c, label in coding.USE_ENVIRONMENT_LABELS.items()],
        "user_types": [{"code": c, "label": label} for c, label in coding.USER_TYPE_LABELS.items()],
        "harm_words": {"version": rules.HARM_WORDS_VERSION, "words": list(rules.HARM_WORDS)},
        "fault_words": {"version": rules.FAULT_WORDS_VERSION, "words": list(rules.FAULT_WORDS)},
        "levels": [{"code": level, "label": markets.LEVEL_LABELS[level]} for level in markets.LEVELS],
        "zones": list(zone_names()),
        # Old names a browser may report ("Asia/Calcutta"), each with its current one, so the form preselects it.
        "zone_aliases": LEGACY_ZONES,
        "starter_mark": STARTER_MARK,
    }


def _event_view(db, control_db, tenant_id, event: IntakeEvent, versions, tasks, now, record=None, detail=False):
    latest = versions[-1] if versions else None
    signed = service.current_signed(versions)
    unresolved = any(t.task_type == service.FOLLOW_UP and t.completion_outcome == "UNRESOLVED" for t in tasks)
    answers = latest.answers if latest else {}
    v2 = bool(latest and latest.guide_version == case_rules.GUIDE_VERSION)
    suggestion = (
        (case_rules.case_outcome(answers, event.requested, unresolved) if v2 else rules.outcome(answers, unresolved))
        if latest
        else None
    )
    flags = rules.intake_flags(event.kind, event.reporter_words, answers)
    awareness = service.event_awareness(event, record)
    product = db.get(Product, event.product_id) if event.product_id else None
    lot = db.get(LotBatch, event.lot_batch_id) if event.lot_batch_id else None
    people = service.names_of(
        control_db,
        tenant_id,
        {
            event.created_by,
            event.owner_id,
            *(row.signed_by for row in versions),
            *(row.reviewed_by for row in versions),
        },
    )

    def name(ref):
        return (people.get(ref) or "A colleague") if ref else None

    found = {
        "id": str(event.id),
        "reference": event.reference,
        "kind": event.kind,
        "kind_label": rules.KIND_LABELS[event.kind],
        "reporter_words": event.reporter_words,
        "reporter_type": event.reporter_type,
        "reporter_site": event.reporter_site,
        "country": event.country,
        "product_id": str(event.product_id) if event.product_id else None,
        "product_name": product.name if product else None,
        "lot": lot.lot_identifier if lot else None,
        "serial_number": event.serial_number,
        "requested": event.requested,
        "requested_label": rules.REQUEST_LABELS.get(event.requested or "", None),
        "use_environment": event.use_environment,
        "user_type": event.user_type,
        "times": {
            "event": {"at": service._iso(event.event_at), "zone": event.event_zone},
            "first_knowledge": {
                "at": service._iso(event.first_knowledge_at),
                "zone": event.first_knowledge_zone,
                "party": event.first_knowledge_party,
                "basis": event.first_knowledge_basis,
            },
            "received": {"at": service._iso(event.received_at), "zone": event.received_zone},
            "awareness": {"at": service._iso(event.awareness_at), "zone": event.awareness_zone},
            "available": {"at": service._iso(event.created_at), "zone": "UTC"},
        },
        "awareness": {
            "at": awareness["at"].isoformat(),
            "source": awareness["source"],
            "source_label": rules.AWARENESS_LABELS.get(awareness["source"]),
            "unresolved": awareness["unresolved"],
            "label": rules.UNRESOLVED_LABEL if awareness["unresolved"] else None,
        },
        "flags": flags,
        "flagged": bool(flags),
        "qms_ref": event.qms_ref,
        "service_ticket": event.service_ticket,
        "sample": is_sample(event.source_system),
        "created_by": name(event.created_by),
        "created_at": event.created_at.isoformat(),
        "version": latest.version if latest else 0,
        "answers": answers,
        "unknowns": latest.unknowns if latest else None,
        "suggestion": suggestion,
        "suggestion_label": case_rules.OUTCOME_LABELS.get(suggestion or "", None),
        "outcome_row": rules.outcome_row(answers) if latest and suggestion != case_rules.UNANSWERED else None,
        "unanswered": case_rules.unanswered(answers) if latest else [],
        # 0.10.93 (B2): the Case's state, owner, Complaint, identifiers (ID-1, S-3), category (S-1), resolution (S-2)
        # and what it still needs (A3).
        "status": event.status,
        "status_label": case_rules.STATE_LABELS.get(event.status),
        "row_version": event.version,
        "owner": name(event.owner_id),
        "complaint_id": str(event.complaint_id) if event.complaint_id else None,
        "escalation": event.escalation,
        "escalated_at": service._iso(event.escalated_at),
        "identifiers": event.identifiers or {},
        "issue_category": event.issue_category,
        "issue_category_label": case_rules.ISSUE_CATEGORIES.get(event.issue_category or ""),
        "resolution_summary": event.resolution_summary,
        "missing": case_rules.missing_information(event.identifiers or {}, answers),
        "draft": bool(latest and latest.signed_at is None),
        "signed": _check_view(signed, name) if signed else None,
        "check_due_at": service._iso(
            service.working_day_end(rules.utc(event.created_at), 0, service.calendar(db, event.tenant_id))
        )
        if latest and signed is None
        else None,
        "tasks": [service.task_view(task, now) for task in tasks],
        "qms_task": _qms_state(tasks, now),
    }
    if detail:
        found["history"] = [_check_view(row, name) for row in versions if row.signed_at is not None]
        found["links"] = _links_view(db, tenant_id, service.INTAKE, event.id, control_db)
        found["duplicates"] = [
            item
            for item in service.duplicates(db, tenant_id)
            if str(event.id) in (item["left"]["id"], item["right"]["id"])
        ]
        found["fault_words"] = rules.fault_words(event.reporter_words)
        found["harm_words"] = rules.harm_words(event.reporter_words)
    return found


def _check_view(row: FirstContactCheck, name) -> dict:
    return {
        "id": str(row.id),
        "version": row.version,
        "guide_version": row.guide_version,
        "suggestion": row.suggestion,
        "classification": row.classification,
        "classification_label": case_rules.OUTCOME_LABELS.get(row.classification or "", None),
        "override_reason": row.override_reason,
        "reason": row.reason,
        "signed_by": name(row.signed_by),
        "signed_at": service._iso(row.signed_at),
        "superseded": row.superseded_by is not None,
        "review_outcome": row.review_outcome,
        "reviewed_by": name(row.reviewed_by),
        "reviewed_at": service._iso(row.reviewed_at),
        "review_note": row.review_note,
        "same_person": bool(row.reviewed_by and row.reviewed_by == row.signed_by),
    }


def _qms_state(tasks, now) -> dict | None:
    task = next((t for t in reversed(tasks) if t.task_type == service.QMS), None)
    if task is None:
        return None
    view = service.task_view(task, now)
    state = (
        "AWAITING_IMPORT"
        if task.status == "WAITING"
        else "OPEN"
        if view["open"]
        else ("NOT_NEEDED" if task.completion_outcome == "NOT_NEEDED" else "CLOSED")
    )
    labels = {
        "OPEN": "QMS complaint to create or link",
        "AWAITING_IMPORT": service.AWAITING_IMPORT,
        "CLOSED": "QMS complaint linked",
        "NOT_NEEDED": "No QMS complaint needed",
    }
    return {**view, "state": state, "label": labels[state]}


def _links_view(db, tenant_id, kind, record_id, control_db) -> list[dict]:
    rows = (
        db.query(RecordLink)
        .filter(
            RecordLink.tenant_id == tenant_id,
            ((RecordLink.left_kind == kind) & (RecordLink.left_id == record_id))
            | ((RecordLink.right_kind == kind) & (RecordLink.right_id == record_id)),
        )
        .order_by(RecordLink.decided_at)
        .all()
    )
    names = service.names_of(control_db, tenant_id, {ref for row in rows for ref in (row.decided_by, row.undone_by)})
    found = []
    for row in rows:
        other_kind, other_id = (
            (row.right_kind, row.right_id)
            if (row.left_kind, row.left_id) == (kind, record_id)
            else (row.left_kind, row.left_id)
        )
        found.append(
            {
                "id": str(row.id),
                "state": row.state,
                "other": _ref_of(db, tenant_id, other_kind, other_id),
                "reason": row.reason,
                "decided_by": names.get(row.decided_by) or "A colleague",
                "decided_at": row.decided_at.isoformat(),
                "awareness_before": service._iso(row.awareness_before),
                "awareness_after": service._iso(row.awareness_after),
                "conflict": row.conflict,
                "undo_reason": row.undo_reason,
                "undone_by": (names.get(row.undone_by) or "A colleague") if row.undone_by else None,
                "undone_at": service._iso(row.undone_at),
            }
        )
    return found


def _ref_of(db, tenant_id, kind, record_id) -> dict:
    if kind == service.INTAKE:
        event = db.get(IntakeEvent, record_id)
        ref = event.reference if event is not None and event.tenant_id == tenant_id else "Removed record"
    else:
        complaint = db.get(Complaint, record_id)
        ref = (
            (complaint.business_id or complaint.complaint_identifier)
            if complaint is not None and complaint.tenant_id == tenant_id
            else "Removed record"
        )
    return {"kind": kind, "id": str(record_id), "ref": ref}


def _event_or_404(db, tenant_id, event_id, lock: bool = False) -> IntakeEvent:
    query = db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.id == event_id)
    if lock:
        query = query.with_for_update()
    event = query.first()
    if event is None:
        raise _error(404, "INTAKE_NOT_FOUND", "No such contact or urgent intake in your organization")
    return event


SHOWS = ("all", "to_sign", "pending", "service_only", "review", "complaint")


def _waiting():
    """In SQL, the contacts ``intake_list``'s ``state`` reads as to_sign, pending or review: not an urgent intake, and
    no current signed check that ends it (a complaint, both, or service only once its QA review is done)."""
    check = FirstContactCheck
    done = exists().where(
        check.tenant_id == IntakeEvent.tenant_id,
        check.intake_event_id == IntakeEvent.id,
        check.signed_at.isnot(None),
        check.superseded_by.is_(None),
        check.classification.notin_(list(rules.PENDING_OUTCOMES)),
        ~((check.classification == rules.SERVICE_ONLY) & check.review_outcome.is_(None)),
    )
    return (IntakeEvent.kind != "URGENT") & ~done


@router.get("/intake")
def intake_list(
    show: str = Query("all", max_length=20),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The logged contacts and urgent intakes, newest first, with what each waits for."""
    if show not in SHOWS:
        raise _error(422, "UNKNOWN_SHOW", f"Show one of {', '.join(SHOWS)}")
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    # Every contact still waiting (to sign, pending, the QA review of "service only"), however old; then the newest
    # 500 finished ones (0.10.86: the newest 500 were read before the waiting ones were picked out).
    mine = db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)
    events = open_first(mine, IntakeEvent.id, _waiting(), [IntakeEvent.created_at.desc(), IntakeEvent.id.desc()], 500)
    ids = [event.id for event in events]
    checks = service.checks_of(db, tenant_id, ids)
    tasks = service.tasks_of(db, tenant_id, ids)
    records = service.triage_records(db, tenant_id)
    items = [
        _event_view(
            db,
            control_db,
            tenant_id,
            event,
            checks.get(event.id, []),
            tasks.get(event.id, []),
            now,
            records.get((service.INTAKE, event.id)),
        )
        for event in events
    ]

    def state(item) -> str:
        signed = item["signed"]
        if item["kind"] == "URGENT":
            return "complaint"
        if signed is None:
            return "to_sign"
        if signed["classification"] in rules.PENDING_OUTCOMES:
            return "pending"
        if signed["classification"] == rules.SERVICE_ONLY:
            return "review" if signed["review_outcome"] is None else "service_only"
        return "complaint"

    for item in items:
        item["state"] = state(item)
    summary = {name: sum(1 for item in items if item["state"] == name) for name in SHOWS[1:]}
    # Every contact and urgent intake, the finished ones not listed included.
    summary["all"] = mine.order_by(None).count()
    summary["flagged"] = sum(1 for item in items if item["flagged"])
    summary["service_only"] += summary["review"]
    shown = [
        item
        for item in items
        if show == "all" or item["state"] == show or (show == "service_only" and item["state"] == "review")
    ]
    return {"items": shown, "summary": summary, "duplicates": len(service.duplicates(db, tenant_id))}


@router.get("/intake/duplicates")
def duplicate_list(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    tenant_id = _tenant(ctx)
    links = service.links_of(db, tenant_id)
    return {
        "items": service.duplicates(db, tenant_id),
        "window_days": rules.DUPLICATE_DAYS,
        "links": [
            {
                "id": str(row.id),
                "state": row.state,
                "left": _ref_of(db, tenant_id, row.left_kind, row.left_id),
                "right": _ref_of(db, tenant_id, row.right_kind, row.right_id),
                "reason": row.reason,
                "decided_at": row.decided_at.isoformat(),
                "awareness_before": service._iso(row.awareness_before),
                "awareness_after": service._iso(row.awareness_after),
                "conflict": row.conflict,
                "undo_reason": row.undo_reason,
                "undone_at": service._iso(row.undone_at),
            }
            for row in reversed(links)
        ],
    }


@router.get("/intake/changes")
def field_changes(
    import_ref: uuid.UUID | None = None,
    record_id: uuid.UUID | None = None,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The field changes re-uploads made: of one import run, or of one record."""
    if import_ref is None and record_id is None:
        raise _error(422, "NAME_A_RUN_OR_RECORD", "Name the import run or the record")
    return {"items": service.changes_of(db, _tenant(ctx), import_ref=import_ref, record_id=record_id)}


@router.get("/intake/{event_id}")
def intake_detail(
    event_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id)
    records = service.triage_records(db, tenant_id)
    return _event_view(
        db,
        control_db,
        tenant_id,
        event,
        service.checks_of(db, tenant_id, [event.id]).get(event.id, []),
        service.tasks_of(db, tenant_id, [event.id]).get(event.id, []),
        service.now_utc(),
        records.get((service.INTAKE, event.id)),
        detail=True,
    )


# --------------------------------------------------------------------------------------------- logging a contact


def _choice(value: str, allowed, default: str | None = None) -> str | None:
    code = rules.clean(value, 40).upper()
    return code if code in allowed else default


def _zone(value: str, fallback: str = "UTC") -> str:
    """A call's time zone, by its current name, from the list (J28); refused when it is not a time zone."""
    from backend.app.oversight.rules import canonical_zone, zone_names

    zone = canonical_zone(rules.clean(value, 60)) or fallback
    if zone not in zone_names():
        raise _error(422, "TIME_ZONE_UNKNOWN", "Choose the call's time zone from the list")
    return zone


def _at(value: datetime | None, zone: str) -> datetime | None:
    """A time as entered: a time without an offset is the wall-clock time in ``zone`` (Chicago 09:00 is 15:00 UTC in
    November, J28); one with an offset is kept."""
    from backend.app.oversight.rules import zone_info

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone_info(zone))
    return rules.utc(value)


def _resolve_lot(db, tenant_id, product_id, value: str):
    text = rules.clean(value, 120)
    if not text:
        return None
    lot = db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier == text).first()
    if lot is None:
        raise _error(422, "LOT_NOT_FOUND", f"No lot {text} in your organization: leave it blank, or name a loaded lot")
    return lot


@router.post("/intake", dependencies=[WRITERS])
def log_intake(
    payload: IntakeIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Log a contact (the reporter's words verbatim, the times, what was asked for and the guide's answers so far) or
    an urgent intake. The suggestion and the triage flag follow at once; nothing is signed here."""
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    kind = _choice(payload.kind, ("CONTACT", "URGENT"))
    if kind is None:
        raise _error(422, "UNKNOWN_KIND", "Log a contact or an urgent intake")
    words = payload.reporter_words.strip()
    if len(words) < rules.REASON_MIN:
        raise _error(422, "WORDS_NEEDED", "Write down the reporter's words, as they said them")
    # A4: a retried request with the same key returns the Case it created, never a second one.
    request_key = rules.clean(payload.request_key, 80) or None
    if request_key:
        known = _by_request_key(db, tenant_id, request_key)
        if known is not None:
            return intake_detail(known, db, control_db, ctx)
    product = None
    if payload.product_id is not None:
        product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == payload.product_id).first()
        if product is None:
            raise _error(422, "PRODUCT_NOT_FOUND", "No such product in your organization")
    lot = _resolve_lot(db, tenant_id, payload.product_id, payload.lot)
    zone = _zone(payload.received_zone)
    received = _at(payload.received_at, zone) or now
    if received > now + _SKEW:
        raise _error(422, "TIME_IN_FUTURE", "The contact cannot be received in the future")
    first_at = _at(payload.first_knowledge_at, _zone(payload.first_knowledge_zone, zone))
    basis = _choice(payload.first_knowledge_basis, rules.FIRST_KNOWLEDGE_BASES)
    # H1 (B2): a Case's awareness is the earliest of its receipt and a first knowledge that counts.
    awareness = (
        case_rules.case_awareness(received, first_at, basis)
        if kind == "CONTACT"
        else _at(payload.awareness_at, _zone(payload.awareness_zone, zone))
    )
    requested = _choice(payload.requested, rules.REQUESTS, "NONE")
    serial = rules.clean(payload.serial_number, 120) or None
    values = {
        "udi": rules.clean(payload.udi, 120) or None,
        "software_version": rules.clean(payload.software_version, 60) or None,
        "hardware_revision": rules.clean(payload.hardware_revision, 60) or None,
        "firmware_version": rules.clean(payload.firmware_version, 60) or None,
    }
    given = {
        "product": product is not None,
        "version": bool(lot and lot.product_version_id),
        "lot": lot is not None,
        "serial": bool(serial),
        **{key: bool(value) for key, value in values.items()},
    }
    event = IntakeEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        reference=service.make_reference(db, tenant_id, kind),
        kind=kind,
        reporter_words=words,
        reporter_type=rules.clean(payload.reporter_type, 40) or None,
        reporter_site=rules.clean(payload.reporter_site, 120) or None,
        country=rules.clean(payload.country, 80) or None,
        product_id=product.id if product else None,
        product_version_id=lot.product_version_id if lot else None,
        lot_batch_id=lot.id if lot else None,
        serial_number=serial,
        requested=requested,
        use_environment=_choice(payload.use_environment, coding.USE_ENVIRONMENT_LABELS, "UNKNOWN"),
        user_type=_choice(payload.user_type, coding.USER_TYPE_LABELS, "UNKNOWN"),
        event_at=_at(payload.event_at, _zone(payload.event_zone, zone)),
        event_zone=_zone(payload.event_zone, zone) if payload.event_at else None,
        first_knowledge_at=first_at,
        first_knowledge_zone=_zone(payload.first_knowledge_zone, zone) if payload.first_knowledge_at else None,
        first_knowledge_party=_choice(payload.first_knowledge_party, rules.FIRST_KNOWLEDGE_PARTIES),
        first_knowledge_basis=basis,
        received_at=received,
        received_zone=zone,
        awareness_at=awareness,
        awareness_zone=(
            _zone(payload.first_knowledge_zone, zone)
            if kind == "CONTACT" and awareness != received
            else _zone(payload.awareness_zone, zone)
        )
        if awareness
        else None,
        service_ticket=rules.clean(payload.service_ticket, 120) or None,
        created_by=str(ctx.user_id),
        created_at=now,
        updated_at=now,
        owner_id=str(ctx.user_id),
        request_key=request_key,
        identifiers=case_rules.clean_identifiers(payload.identifiers, given),
        issue_category=case_rules.issue_category(payload.issue_category),
        **values,
    )
    db.add(event)
    db.flush()
    answers = case_rules.clean_answers({key: value.model_dump() for key, value in payload.answers.items()})
    suggestion = case_rules.case_outcome(answers, requested) if kind == "CONTACT" else None
    if kind == "CONTACT":
        db.add(
            FirstContactCheck(
                tenant_id=tenant_id,
                intake_event_id=event.id,
                version=1,
                guide_version=case_rules.GUIDE_VERSION,
                answers=answers,
                unknowns=rules.clean(payload.unknowns) or None,
                suggestion=suggestion,
                history=[case_rules.recalculation(None, answers, None, suggestion, ctx.user_id, now)],
                created_by=str(ctx.user_id),
                created_at=now,
                updated_at=now,
            )
        )
        service.ensure_follow_up(db, tenant_id, event, answers, suggestion, ctx.user_id, now)
    else:
        # Urgent intake: a complaint by definition; triaged at once, its QMS complaint to create or link (G20).
        service.ensure_qms_task(db, tenant_id, event, ctx.user_id, now)
    flags = rules.intake_flags(kind, words, answers)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="INTAKE_LOGGED",
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            details={
                "reference": event.reference,
                "kind": kind,
                "flags": [item["code"] for item in flags],
                "suggestion": suggestion,
                "awareness_at": service._iso(awareness),
                "issue_category": event.issue_category,
                "identifiers": event.identifiers,
            },
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # The same request key raced in at the same moment: return the Case the other request created.
        db.rollback()
        known = _by_request_key(db, tenant_id, request_key) if request_key else None
        if known is None:
            raise
        return intake_detail(known, db, control_db, ctx)
    return intake_detail(event.id, db, control_db, ctx)


def _by_request_key(db, tenant_id, request_key: str):
    row = (
        db.query(IntakeEvent.id)
        .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.request_key == request_key)
        .first()
    )
    return row.id if row else None


@router.put("/intake/{event_id}/check", dependencies=[WRITERS])
def save_check(
    event_id: uuid.UUID,
    payload: CheckIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Save the answers. An unsigned draft is updated; after a signature a new version starts (a reclassification),
    and the contact keeps its awareness time."""
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    if event.kind == "URGENT":
        raise _error(409, "URGENT_HAS_NO_CHECK", "An urgent intake is a complaint by definition: it has no check")
    now = service.now_utc()
    versions = service.checks_of(db, tenant_id, [event.id]).get(event.id, [])
    latest = versions[-1] if versions else None
    if (latest.version if latest else 0) != payload.seen_version:
        raise _error(409, "CHANGED_MEANWHILE", "A colleague changed this check a moment ago; reload to see it")
    answers = case_rules.clean_answers({key: value.model_dump() for key, value in payload.answers.items()})
    tasks = service.tasks_of(db, tenant_id, [event.id]).get(event.id, [])
    unresolved = any(t.task_type == service.FOLLOW_UP and t.completion_outcome == "UNRESOLVED" for t in tasks)
    suggestion = case_rules.case_outcome(answers, event.requested, unresolved)
    # X1: every recalculation is kept (which answers changed, the suggestion before and after).
    entry = case_rules.recalculation(
        latest.answers if latest else None, answers, latest.suggestion if latest else None, suggestion, ctx.user_id, now
    )
    if latest is not None and latest.signed_at is None:
        latest.answers, latest.suggestion, latest.guide_version = answers, suggestion, case_rules.GUIDE_VERSION
        latest.history = [*(latest.history or []), entry]
        latest.unknowns = rules.clean(payload.unknowns) or None
        latest.updated_at = now
    else:
        db.add(
            FirstContactCheck(
                tenant_id=tenant_id,
                intake_event_id=event.id,
                version=(latest.version if latest else 0) + 1,
                guide_version=case_rules.GUIDE_VERSION,
                answers=answers,
                unknowns=rules.clean(payload.unknowns) or None,
                suggestion=suggestion,
                history=[entry],
                created_by=str(ctx.user_id),
                created_at=now,
                updated_at=now,
            )
        )
    service.ensure_follow_up(db, tenant_id, event, answers, suggestion, ctx.user_id, now)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="FIRST_CONTACT_ANSWERS_SAVED",
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            details={
                "reference": event.reference,
                "suggestion": suggestion,
                "flags": [item["code"] for item in rules.intake_flags(event.kind, event.reporter_words, answers)],
            },
            created_at=now,
        )
    )
    db.commit()
    return intake_detail(event.id, db, control_db, ctx)


def _signer_role(control_db, ctx) -> str | None:
    person = current_person(control_db, ctx)
    role = person.role_for(QUALITY_REVIEW) or person.role_for(SIGNAL_TRIAGE) or person.role_for(INVESTIGATION_CREATE)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign a first-contact check")
    return role


def _verify(control_db, ctx, event, password, mfa_code, attempt: str) -> None:
    from backend.app.governance_router import verify_signing_credentials

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=_tenant(ctx),
                actor_ref=ctx.user_id,
                action=action,
                entity_type="IntakeEvent",
                entity_id=event.id,
                correlation_id=ctx.correlation_id,
                details={"attempt": attempt, "reference": event.reference},
            )
        )

    verify_signing_credentials(control_db, ctx, password=password, mfa_code=mfa_code, record_refusal=refused)


def _signature(control_db, ctx, tenant_id, check_id, version, decision, remarks, role, material, now, meaning):
    from backend.app.human_decision.rules import fingerprint, signature_hash

    content = fingerprint(material)
    record_id = uuid.uuid4()
    control_db.add(
        SignedApprovalRecord(
            id=record_id,
            tenant_id=tenant_id,
            object_type=OBJECT_TYPE,
            object_id=check_id,
            object_version=str(version),
            decision_type=DECISION_TYPE,
            decision=decision,
            remarks=remarks[:2000],
            signer_user_id=str(ctx.user_id),
            signer_role=role or "UNKNOWN",
            signature_meaning=meaning,
            content_fingerprint=content,
            signature_hash=signature_hash(content, str(ctx.user_id), str(version)),
            status="SIGNED",
            signed_at=now,
            created_at=now,
        )
    )
    return record_id, content


def _commit(db, control_db) -> None:
    signing_commit.commit(db, control_db, "first-contact check")


def _after_classification(db, tenant_id, event, check, previous, actor, now) -> None:
    """What a signed classification starts: the QMS-complaint task (complaint, both), the QA review (service only),
    the follow-up (pending); a complaint after "service only" reopens triage from the reclassification (G19)."""
    if check.classification in rules.COMPLAINT_OUTCOMES:
        linked = any(
            link.state == "LINKED" and service.COMPLAINT in (link.left_kind, link.right_kind)
            for link in service.links_of(db, tenant_id)
            if event.id in (link.left_id, link.right_id)
        )
        if not linked:
            service.ensure_qms_task(db, tenant_id, event, actor, now)
    elif check.classification in case_rules.REVIEWED_OUTCOMES:
        service.ensure_review_task(db, tenant_id, event, check, actor, now)
    else:
        service.ensure_follow_up(db, tenant_id, event, check.answers, check.classification, actor, now)
    if (
        previous is not None
        and previous.classification in case_rules.REVIEWED_OUTCOMES
        and check.classification not in case_rules.REVIEWED_OUTCOMES
    ):
        record = (
            db.query(TriageRecord)
            .filter(
                TriageRecord.tenant_id == tenant_id,
                TriageRecord.subject_kind == service.INTAKE,
                TriageRecord.subject_id == event.id,
            )
            .first()
        )
        if record is not None:
            record.opened_at, record.completed_at, record.completed_by, record.updated_at = now, None, None, now


def _second_look(db, tenant_id, event, check, actor, now) -> None:
    """An imported service record's check is its second-look decision: complaint or both confirms it; "service only"
    dismisses it, with the written reason (one decision path)."""
    if event.kind != "SERVICE_RECORD":
        return
    link = next(
        (
            row
            for row in service.links_of(db, tenant_id)
            if row.state == "LINKED" and event.id in (row.left_id, row.right_id)
        ),
        None,
    )
    if link is None:
        return
    complaint_id = link.right_id if link.left_id == event.id else link.left_id
    if check.classification in rules.PENDING_OUTCOMES:
        return
    decision = "DISMISSED" if check.classification == rules.SERVICE_ONLY else "CONFIRMED"
    reason = check.reason or check.override_reason or f"First-contact check {event.reference}: {check.classification}"
    existing = (
        db.query(ComplaintSecondLook)
        .filter(ComplaintSecondLook.tenant_id == tenant_id, ComplaintSecondLook.complaint_id == complaint_id)
        .first()
    )
    if existing is None:
        db.add(
            ComplaintSecondLook(
                tenant_id=tenant_id,
                complaint_id=complaint_id,
                decision=decision,
                reason=reason[:2000],
                flagged={"first_contact": event.reference},
                decided_by=str(actor),
                decided_at=now,
            )
        )
    else:
        existing.decision, existing.reason, existing.decided_by, existing.decided_at = (
            decision,
            reason[:2000],
            str(actor),
            now,
        )


@router.post("/intake/{event_id}/check/sign", dependencies=[WRITERS])
def sign_check(
    event_id: uuid.UUID,
    payload: SignIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The coordinator signs the classification: the guide's suggestion, or another outcome with a reason. "Service
    only", "Inquiry" and "Not a complaint" need a written reason and are offered only when the answers give them. A
    complaint is escalated in the same transaction (D1): the Case becomes, or joins, the Complaint."""
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id)
    versions = service.checks_of(db, tenant_id, [event.id]).get(event.id, [])
    latest = versions[-1] if versions else None
    if latest is None or latest.signed_at is not None:
        raise _error(409, "NOTHING_TO_SIGN", "Save the answers first: there is no unsigned check")
    if latest.version != payload.seen_version:
        raise _error(409, "CHANGED_MEANWHILE", "A colleague changed this check a moment ago; reload to see it")
    problem = rules.answers_problem(latest.answers)
    tasks = service.tasks_of(db, tenant_id, [event.id]).get(event.id, [])
    unresolved = any(t.task_type == service.FOLLOW_UP and t.completion_outcome == "UNRESOLVED" for t in tasks)
    classification = rules.clean(payload.classification, 30).upper()
    override = rules.clean(payload.override_reason)
    reason = rules.clean(payload.reason)
    # A version saved under the Case check v2 is signed by its rules; an older draft keeps the guide it was saved with.
    if latest.guide_version == case_rules.GUIDE_VERSION:
        suggestion = case_rules.case_outcome(latest.answers, event.requested, unresolved)
        problem = problem or case_rules.classification_problem(
            suggestion, classification, override, reason, no_deficiency_confirmed=_no_deficiency(tasks)
        )
    else:
        suggestion = rules.outcome(latest.answers, unresolved)
        problem = problem or rules.classification_problem(suggestion, classification, override, reason)
    if problem:
        raise _error(422, "CHECK_INCOMPLETE", problem)
    target = case_rules.state_after(classification)
    _move_allowed(control_db, ctx, event, target)
    role = _signer_role(control_db, ctx)
    _verify(control_db, ctx, event, payload.password, payload.mfa_code, "FIRST_CONTACT_SIGN")
    now = service.now_utc()
    trial = is_trial(control_db, tenant_id)
    previous = service.current_signed(versions)
    material = {
        "event": event.reference,
        "version": latest.version,
        "guide_version": latest.guide_version,
        "answers": latest.answers,
        "suggestion": suggestion,
        "classification": classification,
        "override_reason": override or None,
        "reason": reason or None,
        "awareness_at": service._iso(service.event_awareness(event)["at"]),
        "flags": [item["code"] for item in rules.intake_flags(event.kind, event.reporter_words, latest.answers)],
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL if trial else None,
    }
    record_id, content = _signature(
        control_db,
        ctx,
        tenant_id,
        latest.id,
        latest.version,
        classification,
        reason or override or case_rules.OUTCOME_LABELS[classification],
        role,
        material,
        now,
        f"I have checked case {event.reference} with guide {latest.guide_version} and classify it: "
        f"{case_rules.OUTCOME_LABELS[classification].lower()}."
        + (" It becomes a complaint in MDARIX now." if target == case_rules.ESCALATED else ""),
    )
    latest.suggestion, latest.classification = suggestion, classification
    latest.override_reason, latest.reason = override or None, reason or None
    latest.signed_record_id, latest.content_fingerprint = record_id, content
    latest.signed_by, latest.signed_at, latest.updated_at = str(ctx.user_id), now, now
    if payload.service_ticket.strip():
        event.service_ticket = rules.clean(payload.service_ticket, 120)
    if previous is not None:
        previous.superseded_by = latest.id
    db.flush()
    complaint = _move(db, control_db, ctx, event, latest, target, now)
    _after_classification(db, tenant_id, event, latest, previous, ctx.user_id, now)
    _second_look(db, tenant_id, event, latest, ctx.user_id, now)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="FIRST_CONTACT_SIGNED",
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            reason=override or reason or None,
            details={
                "reference": event.reference,
                "version": latest.version,
                "suggestion": suggestion,
                "classification": classification,
                "reclassified_from": previous.classification if previous else None,
                "signature_id": str(record_id),
                "signer_role": role,
                "case_state": event.status,
                "complaint_id": str(complaint.id) if complaint else None,
            },
            created_at=now,
        )
    )
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


def _no_deficiency(tasks) -> bool:
    """The reporter's "confirm no deficiency" follow-up closed answered (Not a complaint may then be signed)."""
    return any(
        task.task_type == service.FOLLOW_UP
        and task.completion_outcome == "ANSWERED"
        and (task.details or {}).get("questions") == ["NO_DEFICIENCY"]
        for task in tasks
    )


def _move_allowed(control_db, ctx, event, target: str) -> None:
    """Refuse, before anything is signed, a move the Case's states do not allow; the refusal is audited (B2-08)."""
    current = event.status or case_rules.OPEN
    problem = None if current == target else case_rules.transition_problem(current, target)
    if problem:
        service._audit(
            control_db,
            _tenant(ctx),
            ctx.user_id,
            "CASE_STATE_REFUSED",
            event,
            service.now_utc(),
            ctx.correlation_id,
            **{"from": current, "to": target, "problem": problem},
        )
        control_db.commit()
        raise _error(409, "CASE_STATE_REFUSED", problem)


def _move(db, control_db, ctx, event, check, target: str, now):
    """Move the Case after a signed classification: a complaint escalates it (create or attach); any other outcome
    sets its state. Returns the Complaint when it escalated."""
    tenant_id = _tenant(ctx)
    if target != case_rules.ESCALATED:
        service.set_case_status(db, control_db, tenant_id, event, target, ctx.user_id, now, ctx.correlation_id)
        return None
    owner, flow = service.case_setup(db, tenant_id, is_trial(control_db, tenant_id))
    return service.escalate_case(
        db,
        control_db,
        tenant_id,
        event,
        check,
        ctx.user_id,
        now,
        record_owner=owner,
        flow=flow,
        correlation_id=ctx.correlation_id,
    )


@router.post("/intake/{event_id}/check/review", dependencies=[WRITERS])
def review_check(
    event_id: uuid.UUID,
    payload: ReviewIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The QA review of a signed "service only": agree, or reclassify it as a complaint, which keeps the contact's
    awareness time (a new signed version). In the trial the reviewer may be the signer; the record says so (T-B8)."""
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id)
    versions = service.checks_of(db, tenant_id, [event.id]).get(event.id, [])
    signed = service.current_signed(versions)
    if signed is None or signed.classification not in case_rules.REVIEWED_OUTCOMES or signed.review_outcome is not None:
        raise _error(
            409, "NOTHING_TO_REVIEW", 'Only an unreviewed "service only", "inquiry" or "not a complaint" is reviewed'
        )
    outcome = rules.clean(payload.outcome, 20).upper()
    note = rules.clean(payload.note)
    if outcome not in ("AGREED", "RECLASSIFIED"):
        raise _error(422, "UNKNOWN_OUTCOME", "Agree, or reclassify it as a complaint")
    if len(note) < rules.REASON_MIN:
        raise _error(422, "NOTE_NEEDED", f"Say in at least {rules.REASON_MIN} characters what you checked")
    if rules.clean(payload.resolution_summary):
        event.resolution_summary = rules.clean(payload.resolution_summary)
    # Cases signed before 0.10.93 keep their state until the data script sets it: only an IN_REVIEW Case closes.
    closes = outcome == "AGREED" and event.status == case_rules.IN_REVIEW
    if closes:
        problem = case_rules.close_problem(signed.classification, event.resolution_summary)
        if problem:
            raise _error(422, "RESOLUTION_SUMMARY_NEEDED", problem)
    _move_allowed(control_db, ctx, event, case_rules.CLOSED if closes else event.status)
    role = _signer_role(control_db, ctx)
    _verify(control_db, ctx, event, payload.password, payload.mfa_code, "FIRST_CONTACT_REVIEW")
    now = service.now_utc()
    signed.review_outcome, signed.reviewed_by, signed.reviewed_at, signed.review_note = (
        outcome,
        str(ctx.user_id),
        now,
        note,
    )
    signed.updated_at = now
    from backend.app.workflow.tasks import complete_tasks

    complete_tasks(
        db,
        tenant_id,
        source_type=service.SOURCE_TYPE,
        source_id=event.id,
        task_types=[service.REVIEW],
        outcome=outcome,
        actor_ref=ctx.user_id,
    )
    new = None
    if outcome == "RECLASSIFIED":
        new = FirstContactCheck(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            intake_event_id=event.id,
            version=max(row.version for row in versions) + 1,
            guide_version=signed.guide_version,
            answers=signed.answers,
            unknowns=signed.unknowns,
            suggestion=signed.suggestion,
            classification=rules.COMPLAINT,
            override_reason=f"QA review: {note}",
            created_by=str(ctx.user_id),
            created_at=now,
            updated_at=now,
        )
        material = {
            "event": event.reference,
            "version": new.version,
            "review_of": signed.version,
            "classification": rules.COMPLAINT,
            "review_note": note,
            "awareness_at": service._iso(service.event_awareness(event)["at"]),
        }
        record_id, content = _signature(
            control_db,
            ctx,
            tenant_id,
            new.id,
            new.version,
            rules.COMPLAINT,
            note,
            role,
            material,
            now,
            f"I have reviewed first contact {event.reference} and reclassify it: complaint.",
        )
        new.signed_record_id, new.content_fingerprint, new.signed_by, new.signed_at = (
            record_id,
            content,
            str(ctx.user_id),
            now,
        )
        db.add(new)
        db.flush()
        signed.superseded_by = new.id
        _move(db, control_db, ctx, event, new, case_rules.ESCALATED, now)
        _after_classification(db, tenant_id, event, new, signed, ctx.user_id, now)
    elif closes:
        service.set_case_status(
            db,
            control_db,
            tenant_id,
            event,
            case_rules.CLOSED,
            ctx.user_id,
            now,
            ctx.correlation_id,
            classification=signed.classification,
        )
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="FIRST_CONTACT_REVIEWED",
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            reason=note,
            details={
                "reference": event.reference,
                "outcome": outcome,
                "same_person": signed.signed_by == str(ctx.user_id),
                "new_version": new.version if new else None,
            },
            created_at=now,
        )
    )
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/{event_id}/follow-up", dependencies=[WRITERS])
def close_follow_up(
    event_id: uuid.UUID,
    payload: FollowUpIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Close the follow-up with the reporter: answered (then update the answers), or unresolved after attempts (a
    "confirm no deficiency" contact then ends as a complaint: an unconfirmed contact is never assumed fault-free)."""
    from backend.app.workflow.tasks import complete_tasks

    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id)
    outcome = rules.clean(payload.outcome, 20).upper()
    note = rules.clean(payload.note)
    if outcome not in ("ANSWERED", "UNRESOLVED"):
        raise _error(422, "UNKNOWN_OUTCOME", "Answered, or unresolved after attempts")
    if len(note) < rules.REASON_MIN:
        raise _error(
            422, "NOTE_NEEDED", f"Say in at least {rules.REASON_MIN} characters what the reporter said or tried"
        )
    done = complete_tasks(
        db,
        tenant_id,
        source_type=service.SOURCE_TYPE,
        source_id=event.id,
        task_types=[service.FOLLOW_UP],
        outcome=outcome,
        actor_ref=ctx.user_id,
        reason=note,
    )
    if not done:
        raise _error(409, "NO_OPEN_FOLLOW_UP", "This contact has no open follow-up")
    from backend.app.communications.service import close_for_intake

    close_for_intake(db, tenant_id, event.id, outcome, note, str(ctx.user_id), service.now_utc())
    if event.status == case_rules.PENDING:
        service.set_case_status(
            db, db, tenant_id, event, case_rules.OPEN, ctx.user_id, service.now_utc(), ctx.correlation_id
        )
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="FIRST_CONTACT_FOLLOW_UP_CLOSED",
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            reason=note,
            details={"reference": event.reference, "outcome": outcome},
            created_at=service.now_utc(),
        )
    )
    db.commit()
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/{event_id}/qms", dependencies=[WRITERS])
def qms_complaint(
    event_id: uuid.UUID,
    payload: QmsIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The QMS-complaint task: the complaint ID entered by hand ("awaiting import confirmation" until an upload brings
    it), or a recorded reason that none is needed (confirmed by the event owner; in the trial the person who enters
    it). Reporting never waits for it."""
    from backend.app.workflow.tasks import complete_tasks

    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    tasks = service.tasks_of(db, tenant_id, [event.id]).get(event.id, [])
    task = service.open_task(tasks, service.QMS)
    if task is None:
        raise _error(409, "NO_OPEN_QMS_TASK", "This event has no open QMS-complaint task")
    now = service.now_utc()
    ref = rules.clean(payload.qms_ref, 120)
    reason = rules.clean(payload.not_needed_reason)
    if ref:
        event.qms_ref, event.updated_at = ref, now
        task.status, task.updated_at = "WAITING", now
        task.details = {**(task.details or {}), "qms_ref": ref, "by_hand": True}
        db.flush()
        service.confirm_by_import(db, tenant_id, [ref], str(ctx.user_id), now)
        action = "QMS_COMPLAINT_ENTERED"
    elif len(reason) >= rules.REASON_MIN:
        complete_tasks(
            db,
            tenant_id,
            source_type=service.SOURCE_TYPE,
            source_id=event.id,
            task_types=[service.QMS],
            outcome="NOT_NEEDED",
            actor_ref=ctx.user_id,
            reason=reason,
        )
        action = "QMS_COMPLAINT_NOT_NEEDED"
    else:
        raise _error(
            422,
            "QMS_REF_OR_REASON",
            f"Enter the QMS complaint ID, or say in at least {rules.REASON_MIN} characters why none is needed",
        )
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            reason=reason or None,
            details={"reference": event.reference, "qms_ref": ref or None},
            created_at=now,
        )
    )
    db.commit()
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/from-complaint/{complaint_id}", dependencies=[WRITERS])
def check_service_record(
    complaint_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The same first-contact check for an imported service record (from the second look): an intake event with the
    record's words and times, linked to it. Its signed check is the second-look decision. Once per record."""
    tenant_id = _tenant(ctx)
    complaint = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id).first()
    if complaint is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    for link in service.links_of(db, tenant_id):
        if link.state == "LINKED" and complaint.id in (link.left_id, link.right_id):
            other = link.left_id if link.right_id == complaint.id else link.right_id
            event = db.get(IntakeEvent, other)
            if event is not None and event.kind == "SERVICE_RECORD":
                return intake_detail(event.id, db, control_db, ctx)
    now = service.now_utc()
    aware = service.complaint_awareness(complaint)
    event = IntakeEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        reference=service.make_reference(db, tenant_id, "SERVICE_RECORD"),
        kind="SERVICE_RECORD",
        reporter_words=complaint.description,
        reporter_type=complaint.reporter_type,
        country=complaint.country,
        product_id=complaint.product_id,
        product_version_id=complaint.product_version_id,
        lot_batch_id=complaint.lot_batch_id,
        serial_number=complaint.serial_number,
        requested="NONE",
        event_at=complaint.event_timestamp,
        received_at=complaint.complaint_timestamp,
        awareness_at=aware["at"],
        awareness_zone="UTC",
        created_by=str(ctx.user_id),
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.flush()
    db.add(
        FirstContactCheck(
            tenant_id=tenant_id,
            intake_event_id=event.id,
            version=1,
            guide_version=case_rules.GUIDE_VERSION,
            answers=case_rules.clean_answers({}),
            suggestion=case_rules.UNANSWERED,
            created_by=str(ctx.user_id),
            created_at=now,
            updated_at=now,
        )
    )
    service.add_link(
        db,
        tenant_id,
        (service.INTAKE, event.id),
        (service.COMPLAINT, complaint.id),
        str(ctx.user_id),
        now,
        "First-contact check of an imported service record (second look)",
    )
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="INTAKE_LOGGED",
            entity_type="IntakeEvent",
            entity_id=event.id,
            correlation_id=ctx.correlation_id,
            details={
                "reference": event.reference,
                "kind": "SERVICE_RECORD",
                "complaint": complaint.complaint_identifier,
            },
            created_at=now,
        )
    )
    db.commit()
    return intake_detail(event.id, db, control_db, ctx)


# --------------------------------------------------------------------------------------------- duplicates and links


def _record_exists(db, tenant_id, kind: str, record_id: uuid.UUID) -> bool:
    model = IntakeEvent if kind == service.INTAKE else Complaint if kind == service.COMPLAINT else None
    if model is None:
        return False
    return db.query(model.id).filter(model.tenant_id == tenant_id, model.id == record_id).first() is not None


@router.post("/intake/links", dependencies=[WRITERS])
def decide_link(
    payload: LinkIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Link two records into one event, or dismiss the warning, with a reason. Sources are kept. A link to an imported
    complaint closes the intake's QMS-complaint task; an earlier awareness raises "awareness conflict" on the triage
    list, and every deadline counted from awareness is recomputed from it."""
    tenant_id = _tenant(ctx)
    left = (rules.clean(payload.left_kind, 20).upper(), payload.left_id)
    right = (rules.clean(payload.right_kind, 20).upper(), payload.right_id)
    decision = rules.clean(payload.decision, 20).upper()
    reason = rules.clean(payload.reason)
    if decision not in ("LINKED", "DISMISSED"):
        raise _error(422, "UNKNOWN_DECISION", "Link the records, or dismiss the warning")
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why")
    if left == right or not all(_record_exists(db, tenant_id, *side) for side in (left, right)):
        raise _error(404, "RECORD_NOT_FOUND", "Name two records of your organization")
    existing = [
        link
        for link in service.links_of(db, tenant_id)
        if {(link.left_kind, link.left_id), (link.right_kind, link.right_id)} == {left, right}
        and link.state in ("LINKED", "DISMISSED")
    ]
    if existing:
        raise _error(409, "DECIDED_ALREADY", "Someone decided on these two records already; reload to see it")
    now = service.now_utc()
    if decision == "LINKED":
        link = service.add_link(db, tenant_id, left, right, str(ctx.user_id), now, reason)
        from backend.app.workflow.tasks import complete_tasks

        for kind, record_id in (left, right):
            other = right if (kind, record_id) == left else left
            if kind == service.INTAKE and other[0] == service.COMPLAINT:
                complete_tasks(
                    db,
                    tenant_id,
                    source_type=service.SOURCE_TYPE,
                    source_id=record_id,
                    task_types=[service.QMS],
                    outcome="LINKED_TO_IMPORTED",
                    actor_ref=ctx.user_id,
                    reason=reason,
                )
    else:
        link = RecordLink(
            tenant_id=tenant_id,
            left_kind=left[0],
            left_id=left[1],
            right_kind=right[0],
            right_id=right[1],
            state="DISMISSED",
            reason=reason,
            decided_by=str(ctx.user_id),
            decided_at=now,
            created_at=now,
        )
        db.add(link)
        db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="RECORDS_LINKED" if decision == "LINKED" else "DUPLICATE_DISMISSED",
            entity_type="RecordLink",
            entity_id=link.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={
                "left": f"{left[0]}:{left[1]}",
                "right": f"{right[0]}:{right[1]}",
                "awareness_before": service._iso(link.awareness_before),
                "awareness_after": service._iso(link.awareness_after),
                "conflict": link.conflict,
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(link.id),
        "state": link.state,
        "conflict": link.conflict,
        "awareness_before": service._iso(link.awareness_before),
        "awareness_after": service._iso(link.awareness_after),
    }


def _signed_since(db, tenant_id, link: RecordLink) -> list[str]:
    """Signed work on a linked complaint since the link: undoing such a link is MVP set 5's part, not the trial's yet."""
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment

    found = []
    for kind, record_id in ((link.left_kind, link.left_id), (link.right_kind, link.right_id)):
        if kind != service.COMPLAINT:
            continue
        for model, label in (
            (ComplaintMarketAssessment, "a signed market assessment"),
            (ComplaintDisposition, "a signed disposition"),
        ):
            if (
                db.query(model.id)
                .filter(
                    model.tenant_id == tenant_id, model.complaint_id == record_id, model.signed_at > link.decided_at
                )
                .first()
                is not None
            ):
                found.append(label)
    return found


@router.post("/intake/links/{link_id}/undo", dependencies=[WRITERS])
def undo_link(
    link_id: uuid.UUID,
    payload: UndoIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Undo a link, with a reason. The link and its audit history are kept (state UNLINKED); each record is its own
    event again. A link with signed work since it was made is not undone in the trial yet (G20 set 5)."""
    tenant_id = _tenant(ctx)
    link = (
        db.query(RecordLink)
        .filter(RecordLink.tenant_id == tenant_id, RecordLink.id == link_id)
        .with_for_update()
        .first()
    )
    if link is None:
        raise _error(404, "LINK_NOT_FOUND", "No such link in your organization")
    if link.state != "LINKED":
        raise _error(409, "NOT_LINKED", "Only a link in force can be undone")
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why the link is undone")
    signed = _signed_since(db, tenant_id, link)
    if signed:
        raise _error(
            409,
            "LINK_HAS_SIGNED_WORK",
            "This link has " + " and ".join(signed) + " since it was made. Undoing it after signed work comes later "
            "(it reopens triage and reviews each obligation).",
        )
    now = service.now_utc()
    link.state, link.undo_reason, link.undone_by, link.undone_at = "UNLINKED", reason, str(ctx.user_id), now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="RECORD_LINK_UNDONE",
            entity_type="RecordLink",
            entity_id=link.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={"left": f"{link.left_kind}:{link.left_id}", "right": f"{link.right_kind}:{link.right_id}"},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(link.id), "state": link.state}


# --------------------------------------------------------------------------------------------- triage


@router.get("/triage")
def triage_list(
    show: str = Query("open", pattern="^(open|done|all)$"),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return service.triage(db, control_db, _tenant(ctx), show)


def _subject_exists(db, tenant_id, kind: str, record_id: uuid.UUID) -> bool:
    if kind == service.QUARANTINE:
        return (
            db.query(ImportQuarantineRow.id)
            .filter(ImportQuarantineRow.tenant_id == tenant_id, ImportQuarantineRow.id == record_id)
            .first()
            is not None
        )
    return _record_exists(db, tenant_id, kind, record_id)


def _record_for(db, tenant_id, kind, record_id, actor, now) -> TriageRecord:
    record = (
        db.query(TriageRecord)
        .filter(
            TriageRecord.tenant_id == tenant_id, TriageRecord.subject_kind == kind, TriageRecord.subject_id == record_id
        )
        .with_for_update()
        .first()
    )
    if record is None:
        record = TriageRecord(
            tenant_id=tenant_id,
            subject_kind=kind,
            subject_id=record_id,
            opened_at=now,
            target_hours=rules.TRIAGE_TARGET_HOURS,
            created_by=str(actor),
            created_at=now,
            updated_at=now,
        )
        db.add(record)
    return record


@router.post("/triage/escalate", dependencies=[WRITERS])
def escalate(
    payload: EscalateIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Escalate a record to triage by hand, from any queue, whatever the automatic flag says (G19). A record triaged
    before is reopened: its triage target counts from now."""
    tenant_id = _tenant(ctx)
    kind = rules.clean(payload.kind, 20).upper()
    reason = rules.clean(payload.reason)
    if kind not in (service.INTAKE, service.COMPLAINT, service.QUARANTINE):
        raise _error(422, "UNKNOWN_KIND", "Escalate a contact, a complaint or a set-aside row")
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why it needs triage")
    if not _subject_exists(db, tenant_id, kind, payload.id):
        raise _error(404, "RECORD_NOT_FOUND", "No such record in your organization")
    now = service.now_utc()
    record = _record_for(db, tenant_id, kind, payload.id, ctx.user_id, now)
    record.escalated_by, record.escalated_at, record.escalation_reason = str(ctx.user_id), now, reason
    if record.completed_at is not None:
        record.opened_at, record.completed_at, record.completed_by = now, None, None
    record.updated_at = now
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="TRIAGE_ESCALATED",
            entity_type="TriageRecord",
            entity_id=record.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={"subject": f"{kind}:{payload.id}"},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(record.id), "subject_kind": kind, "subject_id": str(payload.id), "escalated_at": now.isoformat()}


@router.post("/triage/{kind}/{record_id}/record", dependencies=[WRITERS])
def complete_triage(
    kind: str,
    record_id: uuid.UUID,
    payload: TriageIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The triage record of an event (every record linked into it): the severity, the event owner and triage owner
    (with a backup where there is a second person), the immediate action or why none is needed, and the awareness
    time confirmed. A possible public health threat, once marked, is not excluded here (a signed triage decision does
    that in the MVP)."""
    tenant_id = _tenant(ctx)
    kind = kind.upper()
    if kind not in (service.INTAKE, service.COMPLAINT, service.QUARANTINE) or not _subject_exists(
        db, tenant_id, kind, record_id
    ):
        raise _error(404, "RECORD_NOT_FOUND", "No such record in your organization")
    severity = rules.clean(payload.severity, 20).upper()
    if severity not in markets.LEVELS:
        raise _error(422, "SEVERITY_NEEDED", "Assess the severity on the harm-severity scale")
    people = {item["id"] for item in service.colleagues(control_db, tenant_id)}
    if payload.event_owner not in people or payload.triage_owner not in people:
        raise _error(422, "OWNERS_NEEDED", "Name the event owner and the triage owner from your team")
    if payload.backup_owner and payload.backup_owner not in people:
        raise _error(422, "BACKUP_UNKNOWN", "Name the backup from your team")
    action, no_action = rules.clean(payload.immediate_action), rules.clean(payload.no_action_reason)
    if len(action) < rules.REASON_MIN and len(no_action) < rules.REASON_MIN:
        raise _error(
            422,
            "ACTION_OR_REASON",
            f"Record the immediate action, or why none is needed (at least {rules.REASON_MIN} characters)",
        )
    now = service.now_utc()
    found = service.triage(db, control_db, tenant_id, "all", now)
    item = next((entry for entry in found["items"] if f"{kind}:{record_id}" in entry["members"]), None)
    members = [tuple(key.split(":")) for key in (item["members"] if item else [f"{kind}:{record_id}"])]
    needs_awareness = bool(item and (item["awareness"]["unresolved"] or item["conflict"]))
    confirmed = rules.utc(payload.awareness_confirmed_at)
    if needs_awareness and confirmed is None:
        raise _error(
            422,
            "AWARENESS_NEEDED",
            "Confirm the awareness time: it is unresolved, or a linked source has an earlier one",
        )
    if confirmed is not None and confirmed > now + _SKEW:
        raise _error(422, "TIME_IN_FUTURE", "Awareness cannot be in the future")
    if (
        confirmed is not None
        and item
        and confirmed > datetime.fromisoformat(item["awareness"]["at"])
        and len(rules.clean(payload.awareness_note)) < rules.REASON_MIN
    ):
        raise _error(
            422, "AWARENESS_REASON", "A later awareness than the earliest known needs a reason (who knew, and for whom)"
        )
    for member_kind, member_id in members:
        record = _record_for(db, tenant_id, member_kind, uuid.UUID(member_id), ctx.user_id, now)
        if record.public_health_threat and not payload.public_health_threat:
            raise _error(
                409,
                "THREAT_NOT_EXCLUDED_HERE",
                "A possible public health threat stays until a signed triage decision excludes it",
            )
        record.severity = severity
        record.public_health_threat = payload.public_health_threat
        record.remedial_action = payload.remedial_action
        record.event_owner, record.triage_owner = payload.event_owner, payload.triage_owner
        record.backup_owner = payload.backup_owner or None
        record.immediate_action, record.no_action_reason = action or None, no_action or None
        if confirmed is not None:
            record.awareness_confirmed_at = confirmed
            record.awareness_note = rules.clean(payload.awareness_note) or None
        record.completed_by, record.completed_at, record.updated_at = str(ctx.user_id), now, now
        if confirmed is not None and member_kind == service.COMPLAINT:
            # A complaint with no awareness or received date keeps the confirmed time as its awareness, so the
            # watch and the market assessment count from it and do not ask again (0.10.81, F4).
            complaint = (
                db.query(Complaint)
                .filter(Complaint.tenant_id == tenant_id, Complaint.id == uuid.UUID(member_id))
                .one_or_none()
            )
            if (
                complaint is not None
                and complaint.awareness_timestamp is None
                and complaint.complaint_timestamp is None
            ):
                complaint.awareness_timestamp, complaint.updated_at = confirmed, now
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="TRIAGE_RECORDED",
            entity_type="TriageRecord",
            entity_id=record_id,
            correlation_id=ctx.correlation_id,
            details={
                "members": ["%s:%s" % member for member in members],
                "severity": severity,
                "public_health_threat": payload.public_health_threat,
                "awareness_confirmed_at": service._iso(confirmed),
                "deadlines": [(d["market"], d["due_date"]) for d in (item["deadlines"] if item else [])],
            },
            created_at=now,
        )
    )
    db.commit()
    return service.triage(db, control_db, tenant_id, "all")
