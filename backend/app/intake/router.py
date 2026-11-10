"""The first contact, urgent intake and triage, duplicates and import history (T-G32, T-G19, T-G20; MVP G32, G19, G20).

- ``GET /api/v1/intake/guide``: the starter first-contact guide, its outcomes table and the starter word lists;
- ``GET /api/v1/intake`` (bounded; the screens read ``GET /api/v1/intake/cases``), ``POST /api/v1/intake``: the logged
  contacts and urgent intakes; log one. A contact's
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
from types import SimpleNamespace
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.trial.sample_source import is_sample
from backend.app.access.permissions import (
    ALL as ALL_PERMISSIONS,
    CASE_CLASSIFY,
    CASE_LOG,
    COMPLAINT_TRIAGE,
    QUALITY_REVIEW,
    effective_permissions,
)
from backend.app.complaint_classification import rules as coding
from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion, SignedApprovalRecord
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, RecordLink, TriageRecord
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import current_person
from backend.app.intake import case_import, case_rules, cases_list, rules, service, triage_rules
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


def _refused(control_db, ctx, what: str, needs, **details) -> None:
    """Audit a refused action (B2 step 4: deny by default, and every refusal is on the record)."""
    control_db.add(
        make_audit_event(
            tenant_id=_tenant(ctx),
            actor_ref=ctx.user_id,
            action="ACTION_REFUSED",
            entity_type="Permission",
            correlation_id=ctx.correlation_id,
            details={"action": what, "needs": list(needs), **details},
        )
    )
    control_db.commit()


def require_any_permission_audited(*permissions: str):
    """Deny by default, decided on the server from the person's roles (never from the request): the person holds one
    of ``permissions``, else 403 and the refusal is audited. A direct API call gets no more than the screens do."""
    unknown = [permission for permission in permissions if permission not in ALL_PERMISSIONS]
    if not permissions or unknown:
        raise ValueError(f"Unknown permission {unknown}")

    def dependency(
        request: Request,
        ctx: AuthenticatedRequestContext = Depends(get_request_context),
        control_db: Session = Depends(get_db),
    ) -> None:
        if any(permission in effective_permissions(control_db, ctx) for permission in permissions):
            return
        _refused(control_db, ctx, f"{request.method} {request.url.path}", permissions)
        raise _error(
            403, "PERMISSION_DENIED", "Your role does not allow this action", permission=" or ".join(permissions)
        )

    return Depends(dependency)


# Who may do what (spec 6.1 and 6.3, OD-4): log a Case (case.log), save the answers and sign the Case check
# (case.classify), the QA review, withdraw and "QMS complaint not expected" (quality.review), triage
# (complaint.triage). Any workspace role (every role but a viewer) may log an urgent Case and escalate to triage.
ANY_ROLE = require_any_permission_audited(*sorted(ALL_PERMISSIONS))
LOGGERS = require_any_permission_audited(CASE_LOG)
CLASSIFIERS = require_any_permission_audited(CASE_CLASSIFY)
REVIEWERS = require_any_permission_audited(QUALITY_REVIEW)
TRIAGERS = require_any_permission_audited(COMPLAINT_TRIAGE)
LINKERS = require_any_permission_audited(CASE_LOG, COMPLAINT_TRIAGE)
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
    # Spec 4.2: a product not in the organization's products is typed and kept as typed, flagged.
    product_text: str = Field(default="", max_length=200)
    # Spec 4.2: how it came in, the patients involved, what happened to them and what was tried on the call.
    channel: str = Field(default="", max_length=40)
    channel_ref: str = Field(default="", max_length=200)
    patients: str = Field(default="", max_length=12)
    harm_text: str = Field(default="", max_length=rules.TEXT_MAX)
    troubleshooting: str = Field(default="", max_length=rules.TEXT_MAX)


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
    # B2 (spec 2.4, 3.3 step 2): the duplicate choice at escalation when a likely match exists.
    attach_to: uuid.UUID | None = None
    create_new: bool = False


class SignedEscalateIn(BaseModel):
    """Spec 9.3: the duplicate choice for a Case signed a complaint before 0.10.93 and never escalated."""

    attach_to: uuid.UUID | None = None
    create_new: bool = False


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
    # 0.10.93 (B2): potential harm, the threat answer, containment, versions, and the signature a one-person trial
    # gives for a downgrade or a later awareness.
    potential_severity: str = Field(default="", max_length=20)
    threat_reason: str = Field(default="", max_length=rules.TEXT_MAX)
    remedial_reason: str = Field(default="", max_length=rules.TEXT_MAX)
    containment: list[str] = Field(default_factory=list, max_length=6)
    change_reason: str = Field(default="", max_length=rules.TEXT_MAX)
    seen_version: int = Field(default=0, ge=0)
    password: str = Field(default="", max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


class SeenIn(BaseModel):
    seen_version: int = Field(default=0, ge=0)


class SignedReasonIn(BaseModel):
    reason: str = Field(default="", max_length=rules.TEXT_MAX)
    decision: str = Field(default="APPROVE", max_length=10)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


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
        "channels": [{"code": code, "label": label} for code, label in FORM_CHANNELS.items()],
        "patients": [{"code": code, "label": label} for code, label in case_rules.PATIENTS.items()],
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
    # RT-30: an imported Case known of long before its import: no check due (no overdue alarm), with a note.
    backlog = case_import.is_backlog(event, service.backlog_settings(db, tenant_id)[0])
    check_due = (
        service.working_day_end(rules.utc(event.created_at), 0, service.calendar(db, event.tenant_id))
        if signed is None and not backlog
        else None
    )
    product = db.get(Product, event.product_id) if event.product_id else None
    lot = db.get(LotBatch, event.lot_batch_id) if event.lot_batch_id else None
    complaint = db.get(Complaint, event.complaint_id) if event.complaint_id else None
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
        # B7 step 12 (IN-15): the words may not be English: the harm words may miss something; add a translation.
        "language_note": "May not be English: the harm-word check reads English only. Add a translation addendum."
        if rules.may_not_be_english(event.reporter_words)
        else None,
        "reporter_type": event.reporter_type,
        "reporter_site": event.reporter_site,
        "country": event.country,
        "product_id": str(event.product_id) if event.product_id else None,
        "product_name": product.name if product else event.product_text,
        "product_from_lot": ((event.identifiers or {}).get("product") or {}).get("source") == "LOT",
        "lot": lot.lot_identifier if lot else event.lot_text,
        # Spec 4.2/4.3: typed, not in the organization's products or lots (kept as typed and flagged).
        "not_in_master": [key for key, typed in (("product", event.product_text), ("lot", event.lot_text)) if typed],
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
        "channel": event.channel,
        "channel_label": case_rules.CHANNELS.get(event.channel or ""),
        "channel_ref": event.channel_ref,
        "patients": event.patients,
        "harm_text": event.harm_text,
        "troubleshooting": event.troubleshooting,
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
        "complaint_ref": complaint.complaint_identifier if complaint else None,
        "escalation": event.escalation,
        "escalated_at": service._iso(event.escalated_at),
        "identifiers": event.identifiers or {},
        "issue_category": event.issue_category,
        "issue_category_label": case_rules.ISSUE_CATEGORIES.get(event.issue_category or ""),
        "resolution_summary": event.resolution_summary,
        "missing": case_rules.missing_information(event.identifiers or {}, answers),
        # A3: owner, next action, due, reason, missing information and escalation state, as the Cases list shows it.
        "header": cases_list.header(
            event,
            signed,
            answers,
            tasks,
            name(event.owner_id),
            complaint.complaint_identifier if complaint else None,
            record,
            check_due,
            now,
        ),
        "backlog_note": case_import.BACKLOG_NOTE if backlog else None,
        "draft": bool(latest and latest.signed_at is None),
        "signed": _check_view(signed, name) if signed else None,
        "check_due_at": service._iso(check_due) if latest and check_due else None,
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
        found["addenda"] = _addenda_view(db, tenant_id, event.id, name)
        found["fault_words"] = rules.fault_words(event.reporter_words)
        found["harm_words"] = rules.harm_words(event.reporter_words)
        # Spec 4.4/4.5: the six classifications with their disabled reasons, the provisional clock chip, and the
        # complaints the escalation panel offers to attach to (one product's newest, bounded).
        found["choices"] = (
            case_rules.choices(suggestion, no_deficiency_confirmed=_no_deficiency(tasks)) if v2 and latest else None
        )
        open_case = event.status not in (case_rules.ESCALATED, case_rules.VOIDED)
        found["clock"] = (
            _case_clock(db, tenant_id, event, bool(flags), awareness["at"], now, record) if open_case else None
        )
        found["likely_complaints"] = (
            service.likely_complaints(db, tenant_id, event)
            if open_case and service.linked_complaint(db, tenant_id, event) is None
            else []
        )
        found["escalate_signed"] = signed_unescalated(db, tenant_id, event, signed)
    return found


def _case_clock(db, tenant_id, event, flagged: bool, aware_at, now, record=None) -> dict | None:
    """The Case check's clock chip (spec 4.4, 5.2): the provisional clock of the Case's market from its awareness;
    without a country, the shortest of the enabled markets. Until its triage is completed, the market's earliest
    possible report (check 3a), as the triage list shows it."""
    from backend.app.reportability import deadlines

    found = rules.provisional_deadlines(
        aware_at,
        service.enabled_markets(db, tenant_id),
        rules.tier(flagged, bool(record and record.public_health_threat)),
        now,
        bool(record and record.remedial_action),
        own=markets.market_of(event.country),
        org_zone=deadlines.org_zone(db, tenant_id),
        answered=bool(record and record.completed_at),
    )
    # provisional_deadlines sorts the own market first, then the earliest due.
    return found[0] if found else None


def _addenda_view(db, tenant_id, event_id, name) -> list[dict]:
    """What was said later, oldest first, each with who said it and when (IN-17)."""
    from backend.app.db.models.intake import CaseAddendum

    rows = (
        db.query(CaseAddendum)
        .filter(CaseAddendum.tenant_id == tenant_id, CaseAddendum.intake_event_id == event_id)
        .order_by(CaseAddendum.created_at)
        .limit(service.READ_LIMIT)
    )
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "said_by_role": row.said_by_role,
            "said_at": service._iso(row.said_at),
            "text": row.text,
            "masked": bool(row.masked),
            "added_by": name(row.created_by),
            "added_at": service._iso(row.created_at),
        }
        for row in rows
    ]


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
    decide_by = (task.details or {}).get("decide_by")
    if state == "OPEN" and decide_by and datetime.fromisoformat(decide_by) <= now:
        state = "DECIDE"  # Connect, 10 working days without the QMS ID (spec 5.4, L3)
    labels = {
        "OPEN": "QMS complaint to create or link",
        "DECIDE": "Link the QMS complaint by hand, or sign QMS complaint not expected",
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
    """The logged contacts and urgent intakes, newest first, with what each waits for. Kept for API clients; the
    screens read ``GET /intake/cases`` (paged on the server, A5). Bounded (B2): at most READ_LIMIT Cases are read,
    the waiting ones first; ``truncated`` says when more exist."""
    if show not in SHOWS:
        raise _error(422, "UNKNOWN_SHOW", f"Show one of {', '.join(SHOWS)}")
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    # Every contact still waiting (to sign, pending, the QA review of "service only"), however old; then the newest
    # 500 finished ones (0.10.86: the newest 500 were read before the waiting ones were picked out).
    mine = db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)
    order = [IntakeEvent.created_at.desc(), IntakeEvent.id.desc()]
    events = open_first(mine, IntakeEvent.id, _waiting(), order, 500, cap=service.READ_LIMIT + 1)
    truncated = len(events) > service.READ_LIMIT
    events = events[: service.READ_LIMIT]
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
    return {
        "items": shown,
        "summary": summary,
        "duplicates": len(service.duplicates(db, tenant_id)),
        "truncated": truncated,
        "cases_path": "/api/v1/intake/cases",
    }


@router.get("/intake/cases")
def cases(
    view: str = Query("all", max_length=30),
    q: str = Query("", max_length=80),
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(25, ge=1, le=cases_list.PAGE_MAX),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The Cases list (A5, spec 4.3): one page, filtered and searched on the server, each row with its header (A3)."""
    if view not in cases_list.VIEWS:
        raise _error(422, "UNKNOWN_VIEW", f"Show one of {', '.join(cases_list.VIEWS)}")
    return cases_list.cases_page(db, control_db, _tenant(ctx), str(ctx.user_id), view, q, page, size)


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


@router.get("/intake/shipped-to")
def shipped_to(
    site: str = Query("", max_length=120),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """ID-2: the products and lots shipped to the caller's hospital, for Log a case's quick picker. No match is an
    empty list, never an error: the free picker stays."""
    return service.shipped_to(db, _tenant(ctx), site)


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
    view = _event_view(
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
    view["contact"] = contact_view(db, control_db, ctx, event)
    return view


# --------------------------------------------------------------------------------------------- logging a contact


# "Imported service record" is set only by the 0.10.93 data script: a person never picks it (owner Q2, 10 Nov).
FORM_CHANNELS = {code: label for code, label in case_rules.CHANNELS.items() if code != "SERVICE_RECORD_IMPORT"}


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
    """The loaded lot of that number and its version's product id, or (None, None): a lot not in the organization's
    lots is kept as typed (spec 4.2). PV-1 F2: a lot whose version belongs to another product than the chosen one is
    refused; a lot with an unknown version stays allowed."""
    text = rules.clean(value, 120)
    if not text:
        return None, None
    lot = db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier == text).first()
    if lot is None or lot.product_version_id is None:
        return lot, None
    lot_product = (
        db.query(ProductVersion.product_id)
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id == lot.product_version_id)
        .scalar()
    )
    if product_id is not None and lot_product != product_id:
        raise _error(
            422, "LOT_NOT_FOR_PRODUCT", f"Lot {text} belongs to another product: choose its product, or check the lot"
        )
    return lot, lot_product


@router.post("/intake", dependencies=[ANY_ROLE])
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
    if kind == "CONTACT" and CASE_LOG not in effective_permissions(control_db, ctx):
        _refused(control_db, ctx, "POST /api/v1/intake (CONTACT)", [CASE_LOG])
        raise _error(403, "PERMISSION_DENIED", "Your role may log an urgent case only", permission=CASE_LOG)
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
    lot, lot_product = _resolve_lot(db, tenant_id, payload.product_id, payload.lot)
    # PV-1 F2: no product chosen but a known lot: the product is the lot's, shown "from the lot".
    product_from_lot = product is None and lot_product is not None
    if product_from_lot:
        product = db.get(Product, lot_product)
    lot_text = None if lot is not None else (rules.clean(payload.lot, 120) or None)
    product_text = None if product is not None else (rules.clean(payload.product_text, 200) or None)
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
        "product": product is not None or bool(product_text),
        "version": bool(lot and lot.product_version_id),
        "lot": lot is not None or bool(lot_text),
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
        identifiers=case_rules.clean_identifiers(payload.identifiers, given)
        | (
            {"product": {"not_sure": False, "status": case_rules.UNCONFIRMED, "source": "LOT"}}
            if product_from_lot
            else {}
        ),
        issue_category=case_rules.issue_category(payload.issue_category),
        product_text=product_text,
        lot_text=lot_text,
        channel=_choice(payload.channel, FORM_CHANNELS),
        channel_ref=rules.clean(payload.channel_ref, 200) or None,
        patients=_choice(payload.patients, case_rules.PATIENTS),
        harm_text=_masked_text(rules.clean(payload.harm_text))[0] or None,
        troubleshooting=_masked_text(rules.clean(payload.troubleshooting))[0] or None,
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
        # Urgent Case: a complaint by definition. B2: it becomes the Complaint at once and is triaged on the fast track;
        # a Connect organization gets the task to enter its QMS complaint ID (escalate_case).
        owner, flow = service.case_setup(db, tenant_id, is_trial(control_db, tenant_id))
        service.escalate_case(
            db,
            control_db,
            tenant_id,
            event,
            None,
            ctx.user_id,
            now,
            record_owner=owner,
            flow=flow,
            correlation_id=ctx.correlation_id,
        )
        from backend.app.oversight import urgent_alert

        urgent_alert.queue(
            db,
            control_db,
            tenant_id,
            reference=event.reference,
            subject_id=event.id,
            received_at=event.received_at,
            actor=ctx.user_id,
            correlation_id=ctx.correlation_id,
        )
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


@router.put("/intake/{event_id}/check", dependencies=[CLASSIFIERS])
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
    db.flush()
    # T-D7: re-answered with a death, a serious injury or a higher floor, a finished triage reopens on the fast track.
    service.reopen_raised(db, control_db, tenant_id, ctx.user_id, now, ctx.correlation_id, "Case check re-answered")
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
    role = person.role_for(CASE_CLASSIFY) or person.role_for(QUALITY_REVIEW) or person.role_for(COMPLAINT_TRIAGE)
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        raise _error(403, "ADMINISTRATOR_CANNOT_SIGN", "Administrators cannot sign a first-contact check")
    return role


def _verify(control_db, ctx, event, password, mfa_code, attempt: str) -> None:
    from backend.app.governance_router import verify_signing_credentials

    def refused(action: str) -> None:
        # A refused signature changes nothing but its audit: drop what the request staged (on the shared trial plane
        # the data session is this one, so a triage record created before the check would be committed with it).
        control_db.rollback()
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


def _signature(
    control_db,
    ctx,
    tenant_id,
    check_id,
    version,
    decision,
    remarks,
    role,
    material,
    now,
    meaning,
    object_type=OBJECT_TYPE,
    decision_type=DECISION_TYPE,
):
    from backend.app.human_decision.rules import fingerprint, signature_hash

    content = fingerprint(material)
    record_id = uuid.uuid4()
    control_db.add(
        SignedApprovalRecord(
            id=record_id,
            tenant_id=tenant_id,
            object_type=object_type,
            object_id=check_id,
            object_version=str(version),
            decision_type=decision_type,
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
    dismisses it, as do inquiry and "not a complaint" (outcomes v2), with the written reason (one decision path)."""
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
    decision = "DISMISSED" if check.classification in case_rules.REVIEWED_OUTCOMES else "CONFIRMED"
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


@router.post("/intake/{event_id}/check/sign", dependencies=[CLASSIFIERS])
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
    attach = _duplicate_choice(db, tenant_id, event, payload) if target == case_rules.ESCALATED else None
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
    complaint = _move(db, control_db, ctx, event, latest, target, now, attach)
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


def _likely_complaints(db, tenant_id, event) -> list[dict]:
    """The complaints the duplicate check pairs with this Case (same product and lot or serial, near dates, ...):
    one product's newest complaints, bounded (service.DUPLICATE_SCAN), not the whole organization's scan."""
    return service.likely_complaints(db, tenant_id, event)


def _duplicate_choice(db, tenant_id, event, payload) -> Complaint | None:
    """Escalation never silently duplicates: a Case not linked yet, with a likely duplicate, needs "attach to ..." or
    "create new" (spec 2.4). Returns the complaint to attach to, or None to create one."""
    if service.linked_complaint(db, tenant_id, event) is not None:
        return None
    if payload.attach_to is not None:
        complaint = (
            db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == payload.attach_to).first()
        )
        if complaint is None:
            raise _error(404, "RECORD_NOT_FOUND", "No such complaint in your organization")
        return complaint
    likely = [] if payload.create_new else _likely_complaints(db, tenant_id, event)
    if likely:
        raise _error(
            422,
            "DUPLICATE_CHOICE_NEEDED",
            "A likely duplicate exists: attach this case to it, or create a new complaint",
            candidates=likely,
        )
    return None


def _move(db, control_db, ctx, event, check, target: str, now, attach_to=None):
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
        attach_to=attach_to,
        correlation_id=ctx.correlation_id,
    )


def signed_unescalated(db, tenant_id, event, signed) -> bool:
    """Spec 9.3: a Case signed "complaint" or "complaint and service" before 0.10.93 (signing escalates since) that
    never became or joined a complaint: it offers "Signed before 0.10.93: escalate"."""
    return (
        signed is not None
        and signed.classification in rules.COMPLAINT_OUTCOMES
        and event.status not in (case_rules.ESCALATED, case_rules.VOIDED)
        and event.complaint_id is None
        and service.linked_complaint(db, tenant_id, event) is None
    )


@router.post("/intake/{event_id}/escalate", dependencies=[CLASSIFIERS])
def escalate_signed(
    event_id: uuid.UUID,
    payload: SignedEscalateIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """ "Signed before 0.10.93: escalate" (spec 9.3): the signed classification is carried out now, with the duplicate
    choice (attach or create new). Nothing is signed again: the signed check is the decision. Its old "Awaiting
    import" task is completed (Complete: owned in MDARIX; Connect: the escalation's QMS-ID task replaces it)."""
    from backend.app.workflow.tasks import complete_tasks

    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    signed = service.current_signed(service.checks_of(db, tenant_id, [event.id]).get(event.id, []))
    if not signed_unescalated(db, tenant_id, event, signed):
        raise _error(
            409, "NOTHING_TO_ESCALATE", "Only a case signed a complaint and not yet escalated is escalated here"
        )
    _move_allowed(control_db, ctx, event, case_rules.ESCALATED)
    attach = _duplicate_choice(db, tenant_id, event, payload)
    now = service.now_utc()
    owner, _ = service.case_setup(db, tenant_id, is_trial(control_db, tenant_id))
    complete_tasks(
        db,
        tenant_id,
        source_type=service.SOURCE_TYPE,
        source_id=event.id,
        task_types=[service.QMS],
        outcome="NOT_NEEDED",
        actor_ref=ctx.user_id,
        reason="Not needed: owned in MDARIX"
        if owner == "MDARIX"
        else "Replaced by the QMS complaint ID task of the escalation",
        correlation_id=ctx.correlation_id,
    )
    complaint = _move(db, control_db, ctx, event, signed, case_rules.ESCALATED, now, attach)
    service._audit(
        control_db,
        tenant_id,
        ctx.user_id,
        "CASE_ESCALATED_SIGNED_BEFORE",
        event,
        now,
        ctx.correlation_id,
        complaint_id=str(complaint.id),
        check_version=signed.version,
        signed_at=service._iso(signed.signed_at),
        escalation=event.escalation,
    )
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/{event_id}/check/review", dependencies=[REVIEWERS])
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
    if signed.signed_by == str(ctx.user_id) and not is_trial(control_db, tenant_id):
        _refused(control_db, ctx, "QA review", [QUALITY_REVIEW], why="REVIEWER_IS_SIGNER", case=event.reference)
        raise _error(403, "REVIEWER_IS_SIGNER", "The QA review is done by someone other than the person who signed")
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


@router.post("/intake/{event_id}/follow-up", dependencies=[LOGGERS])
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


@router.post("/intake/{event_id}/qms", dependencies=[require_any_permission_audited(CASE_LOG, QUALITY_REVIEW)])
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
        if QUALITY_REVIEW not in effective_permissions(control_db, ctx):
            _refused(control_db, ctx, "QMS complaint not expected", [QUALITY_REVIEW], case=event.reference)
            raise _error(403, "PERMISSION_DENIED", "A quality reviewer records that no QMS complaint is expected")
        signer = service.current_signed(service.checks_of(db, tenant_id, [event.id]).get(event.id, []))
        if signer is not None and signer.signed_by == str(ctx.user_id) and not is_trial(control_db, tenant_id):
            _refused(
                control_db, ctx, "QMS complaint not expected", [QUALITY_REVIEW], why="SIGNER", case=event.reference
            )
            raise _error(
                403, "SAME_PERSON", "Someone other than the Case's signer records that no QMS complaint is expected"
            )
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


@router.post("/intake/from-complaint/{complaint_id}", dependencies=[CLASSIFIERS])
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
        channel="SERVICE_RECORD_IMPORT",
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


@router.post("/intake/links", dependencies=[LINKERS])
def decide_link(
    payload: LinkIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
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
    if decision == "LINKED":
        db.flush()
        # T-D8: triage belongs to the event; the record joining it inherits a finished triage.
        for source, target in ((left, right), (right, left)):
            service.inherit_triage(db, db, tenant_id, source, target, str(ctx.user_id), now, ctx.correlation_id)
        # T-D7: a link that brings more harm reopens a finished triage on the fast track.
        service.reopen_raised(db, control_db, tenant_id, ctx.user_id, now, ctx.correlation_id, "Records linked")
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


@router.post("/intake/links/{link_id}/undo", dependencies=[LINKERS])
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


@router.get("/triage/backlog")
def imported_backlog(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The "Imported backlog" view (OD-12, TR-21): old imported complaints, routine, with their own target."""
    return service.imported_backlog(db, _tenant(ctx), page=page, page_size=page_size)


def _subject_exists(db, tenant_id, kind: str, record_id: uuid.UUID) -> bool:
    if kind == service.QUARANTINE:
        return (
            db.query(ImportQuarantineRow.id)
            .filter(ImportQuarantineRow.tenant_id == tenant_id, ImportQuarantineRow.id == record_id)
            .first()
            is not None
        )
    return _record_exists(db, tenant_id, kind, record_id)


def _record_for(db, tenant_id, kind, record_id, actor, now, opened=None) -> TriageRecord:
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
            opened_at=opened or now,
            target_hours=rules.TRIAGE_TARGET_HOURS,
            created_by=str(actor),
            created_at=now,
            updated_at=now,
        )
        db.add(record)
    return record


@router.post("/triage/escalate", dependencies=[ANY_ROLE])
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


@router.post("/triage/{kind}/{record_id}/record", dependencies=[TRIAGERS])
def complete_triage(
    kind: str,
    record_id: uuid.UUID,
    payload: TriageIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The triage record of an event (every record linked into it), at its speed (B2, spec 3.4): the harm now ("Not
    known yet" or a level, never below the floor), the harm if it happened again (whenever a malfunction is alleged),
    the owners (a backup on the fast track when two or more people are active), the containment, the immediate action
    or why none is needed, and the awareness confirmed. Every save is a new version; an update needs a reason.
    Lowering a fast-track triage, or a later awareness, needs a second person outside the trial (A6, T-H4)."""
    return _save_triage(db, control_db, ctx, kind, record_id, payload)


def _subject_or_404(db, tenant_id, kind: str, record_id) -> str:
    kind = kind.upper()
    if kind not in (service.INTAKE, service.COMPLAINT, service.QUARANTINE) or not _subject_exists(
        db, tenant_id, kind, record_id
    ):
        raise _error(404, "RECORD_NOT_FOUND", "No such record in your organization")
    return kind


def _triage_item(db, control_db, tenant_id, kind, record_id, now) -> dict | None:
    found = service.triage(db, control_db, tenant_id, "all", now)
    return next((entry for entry in found["items"] if f"{kind}:{record_id}" in entry["members"]), None)


def _members(item, kind, record_id) -> list[tuple[str, uuid.UUID]]:
    keys = item["members"] if item else [f"{kind}:{record_id}"]
    return [(key.split(":")[0], uuid.UUID(key.split(":")[1])) for key in keys]


def _opened(item, now) -> datetime:
    return datetime.fromisoformat(item["triage_clock"]["from"]) if item else now


def _subject_ref(item, record_id) -> SimpleNamespace:
    """What a refused signature is audited against (``_verify``): the triage subject."""
    return SimpleNamespace(id=record_id, reference=item["ref"] if item else str(record_id))


def _triage_audit(db, ctx, action, entity_id, now, reason=None, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=_tenant(ctx),
            actor_ref=ctx.user_id,
            action=action,
            entity_type="TriageRecord",
            entity_id=entity_id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details=details,
            created_at=now,
        )
    )


def _save_triage(db, control_db, ctx, kind, record_id, payload: TriageIn, *, approval=None, action="TRIAGE_RECORDED"):
    tenant_id = _tenant(ctx)
    kind = _subject_or_404(db, tenant_id, kind, record_id)
    now = service.now_utc()
    item = _triage_item(db, control_db, tenant_id, kind, record_id, now)
    members = _members(item, kind, record_id)
    facts = {**(item["facts"] if item else triage_rules.facts([])), "threat": payload.public_health_threat}
    least = item["severity_floor"] if item else None
    record = _record_for(db, tenant_id, kind, record_id, ctx.user_id, now, _opened(item, now))
    saved = bool(record.flags_at_completion)
    # T-D9: saving the full form on a QMS triage still to confirm is its confirmation (TR-14, TR-38).
    qms_confirm = record.source_system == "QMS" and record.completed_at is None
    if qms_confirm:
        action = "TRIAGE_QMS_CONFIRMED"
    if saved and payload.seen_version != record.version:
        raise _error(409, "TRIAGE_CHANGED", "A colleague changed this triage a moment ago; reload to see it")
    severity = rules.clean(payload.severity, 20).upper()
    potential = rules.clean(payload.potential_severity, 20).upper() or None
    reason = rules.clean(payload.change_reason)
    # Below the level the QMS gave needs a reason, as lowering a saved one does (spec 3.4, severity rules).
    problem = triage_rules.severity_problem(severity, least, record.severity if saved or qms_confirm else None, reason)
    if problem:
        raise _error(422, *problem)
    if potential and potential not in triage_rules.SCALE:
        raise _error(422, "POTENTIAL_UNKNOWN", "Choose the harm if it happened again on the harm scale")
    if facts["malfunction"] and not potential:
        raise _error(
            422,
            "POTENTIAL_NEEDED",
            "Harm if it happened again: asked whenever a malfunction is alleged (worst credible)",
        )
    if (
        facts["death"]
        and not payload.public_health_threat
        and len(rules.clean(payload.threat_reason)) < rules.REASON_MIN
    ):
        raise _error(
            422,
            "THREAT_ANSWER_NEEDED",
            "A death is recorded: answer 'Possible serious public health threat' with a reason",
        )
    people = {entry["id"] for entry in service.colleagues(control_db, tenant_id)}
    if payload.event_owner not in people or payload.triage_owner not in people:
        raise _error(422, "OWNERS_NEEDED", "Name the event owner and the triage owner from your team")
    if payload.backup_owner and payload.backup_owner not in people:
        raise _error(422, "BACKUP_UNKNOWN", "Name the backup from your team")
    reopened = record.reopened_at is not None and record.completed_at is None
    pace = triage_rules.speed(facts, potential, severity, reopened)
    backup = triage_rules.backup_problem(pace, len(people), payload.backup_owner)
    if backup:
        raise _error(422, "BACKUP_NEEDED", backup)
    action_text, no_action = rules.clean(payload.immediate_action), rules.clean(payload.no_action_reason)
    if len(action_text) < rules.REASON_MIN and len(no_action) < rules.REASON_MIN:
        raise _error(
            422,
            "ACTION_OR_REASON",
            f"Record the immediate action, or why none is needed (at least {rules.REASON_MIN} characters)",
        )
    choices = triage_rules.containment(payload.containment)
    if not choices:
        # A form that sends only the text (before the B2 screens): the choice follows from it, "Other" for an action.
        choices = ["OTHER"] if len(action_text) >= rules.REASON_MIN else ["NONE_NEEDED"]
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
    later = bool(confirmed is not None and item and confirmed > datetime.fromisoformat(item["awareness"]["at"]))
    if later and len(rules.clean(payload.awareness_note)) < rules.REASON_MIN:
        raise _error(
            422, "AWARENESS_REASON", "A later awareness than the earliest known needs a reason (who knew, and for whom)"
        )
    if record.remedial_action and not payload.remedial_action and len(rules.clean(payload.remedial_reason)) < 10:
        raise _error(422, "REMEDIAL_REASON", "Say why remedial action is no longer thought to be needed")
    if saved and record.completed_at is not None and len(reason) < rules.REASON_MIN:
        raise _error(
            422, "CHANGE_REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why the triage changes"
        )
    rows = [
        record
        if (k, i) == (kind, record_id)
        else _record_for(db, tenant_id, k, i, ctx.user_id, now, _opened(item, now))
        for k, i in members
    ]
    if any(row.public_health_threat and not payload.public_health_threat for row in rows):
        raise _error(
            409,
            "THREAT_NOT_EXCLUDED_HERE",
            "A possible public health threat stays until a signed triage decision excludes it",
        )
    downgrade = saved and triage_rules.is_downgrade(
        {"speed": record.speed, "severity": record.severity, "potential_severity": record.potential_severity},
        {"speed": pace, "severity": severity, "potential_severity": potential},
    )
    signed_id, one_person = (approval or {}).get("signed"), False
    if (downgrade or later) and approval is None:
        what = "a later awareness" if later and not downgrade else "lowering a fast-track triage"
        if not is_trial(control_db, tenant_id):
            from backend.app.workflow.tasks import create_task

            task = create_task(
                db,
                tenant_id,
                task_type=triage_rules.DOWNGRADE_TASK,
                title=f"Approve {what} for {item['ref'] if item else record_id}",
                source_type="TriageRecord",
                source_id=record.id,
                assigned_role=service_role_for_downgrade(db, tenant_id),
                due_at=now + timedelta(hours=service.fast_hours(db, tenant_id)),
                created_by=ctx.user_id,
            )
            task.details = {
                "payload": payload.model_dump(mode="json", exclude={"password", "mfa_code"}),
                "kind": kind,
                "record_id": str(record_id),
                "requested_by": str(ctx.user_id),
                "ref": item["ref"] if item else None,
                "what": what,
            }
            _triage_audit(
                db,
                ctx,
                "TRIAGE_DOWNGRADE_REFUSED",
                record.id,
                now,
                reason or None,
                why="SECOND_PERSON",
                task=str(task.id),
            )
            db.commit()
            raise _error(
                409,
                "SECOND_PERSON_NEEDED",
                f"{what[0].upper()}{what[1:]} needs the approval of a second person: a request is open",
                task_id=str(task.id),
            )
        # A one-person trial may do it, signed with the password; the record says "one person" (spec 6.4).
        if not payload.password:
            raise _error(422, "SIGNATURE_NEEDED", f"Sign {what} with your password")
        role = _signer_role(control_db, ctx)
        _verify(control_db, ctx, _subject_ref(item, record_id), payload.password, payload.mfa_code, "TRIAGE_DOWNGRADE")
        db.flush()  # a first save's record gets its id (server default) for the signature
        signed_id, _ = _signature(
            control_db,
            ctx,
            tenant_id,
            record.id,
            record.version,
            "LATER_AWARE" if later and not downgrade else "DOWNGRADE",
            reason or rules.clean(payload.awareness_note),
            role,
            {"severity": severity, "potential": potential, "awareness": service._iso(confirmed), "speed": pace},
            now,
            f"I approve {what} for {item['ref'] if item else record_id} (one person, trial).",
            object_type="TriageRecord",
            decision_type="TRIAGE_DOWNGRADE",
        )
        one_person = True
    target = datetime.fromisoformat(item["triage_clock"]["due_at"]) if item else now
    codes = [flag["code"] for flag in item["flags"]] if item else []
    changed: dict = {}
    for row in rows:
        before = service.triage_snapshot(row) if row.flags_at_completion else None
        row.severity, row.potential_severity, row.speed, row.due_at = severity, potential, pace, target
        row.public_health_threat = payload.public_health_threat
        row.remedial_action = payload.remedial_action
        row.event_owner, row.triage_owner = payload.event_owner, payload.triage_owner
        row.backup_owner = payload.backup_owner or None
        row.immediate_action, row.no_action_reason = action_text or None, no_action or None
        row.severity_floor, row.floor_reasons = least, [item["floor_note"]] if item and item["floor_note"] else []
        row.flags_at_completion = {"facts": facts, "codes": codes}
        row.containment = {"choices": choices, "text": action_text or no_action}
        row.change_reason = reason or None
        if confirmed is not None:
            row.awareness_confirmed_at = confirmed
            row.awareness_note = rules.clean(payload.awareness_note) or None
            if later:
                row.awareness_signed_record_id = signed_id
        if row.acknowledged_at is None or rules.utc(row.acknowledged_at) < rules.utc(row.opened_at):
            row.acknowledged_at, row.acknowledged_by = now, str(ctx.user_id)  # saving the triage acknowledges it
        row.completed_by, row.completed_at, row.updated_at = str(ctx.user_id), now, now
        if row is record and qms_confirm:
            row.confirmed_by, row.confirmed_at = str(ctx.user_id), now
        db.flush()
        found = service.add_triage_version(db, tenant_id, row, before, ctx.user_id, now, reason or None, signed_id)
        if row is record:
            changed = found
        if confirmed is not None and row.subject_kind == service.COMPLAINT:
            # A complaint with no awareness or received date keeps the confirmed time as its awareness, so the
            # watch and the market assessment count from it and do not ask again (0.10.81, F4).
            complaint = (
                db.query(Complaint)
                .filter(Complaint.tenant_id == tenant_id, Complaint.id == row.subject_id)
                .one_or_none()
            )
            if (
                complaint is not None
                and complaint.awareness_timestamp is None
                and complaint.complaint_timestamp is None
            ):
                complaint.awareness_timestamp, complaint.updated_at = confirmed, now
    _triage_tasks(db, ctx, record, item, severity, choices, payload.triage_owner, now)
    _triage_audit(
        db,
        ctx,
        action,
        record.id,
        now,
        reason or None,
        members=["%s:%s" % member for member in members],
        severity=severity,
        potential_severity=potential,
        speed=pace,
        public_health_threat=payload.public_health_threat,
        threat_reason=rules.clean(payload.threat_reason) or None,
        awareness_confirmed_at=service._iso(confirmed),
        deadlines=[(d["market"], d["due_date"]) for d in (item["deadlines"] if item else [])],
        changed=changed,
        owners={"event": payload.event_owner, "triage": payload.triage_owner, "backup": payload.backup_owner or None},
        containment=choices,
        version=record.version,
        one_person=one_person,
        approved_by=(approval or {}).get("by"),
        requested_by=(approval or {}).get("requested_by"),
        signature_id=str(signed_id) if signed_id else None,
    )
    if signed_id:
        signing_commit.commit(db, control_db, "triage")
    else:
        db.commit()
    return service.triage(db, control_db, tenant_id, "all")


def service_role_for_downgrade(db, tenant_id) -> str:
    """The queue a downgrade request goes to: the organization's escalation role (Leader by default)."""
    from backend.app.oversight.service import settings_row

    row = settings_row(db, tenant_id)
    return row.escalation_role if row is not None else "LEADER"


def _triage_tasks(db, ctx, record, item, severity, choices, owner, now) -> None:
    """The tasks a triage save opens: the follow-up of a "Not known yet" harm (1 working day, TR-01) and the
    containment tasks (Hold the lot, Consider a field action; T-D11)."""
    from backend.app.workflow.tasks import create_task

    tenant_id = _tenant(ctx)
    ref = item["ref"] if item else str(record.subject_id)
    due = service.working_day_end(now, 1, service.calendar(db, tenant_id))
    wanted = [(code, title) for choice, (code, title) in triage_rules.CONTAINMENT_TASKS.items() if choice in choices]
    if severity == triage_rules.NOT_KNOWN:
        wanted.insert(0, (triage_rules.FOLLOW_UP_TASK, "Find out the harm for {ref}: triage said Not known yet"))
    for code, title in wanted:
        task = create_task(
            db,
            tenant_id,
            task_type=code,
            title=title.format(ref=ref),
            source_type="TriageRecord",
            source_id=record.id,
            assigned_user_id=owner,
            due_at=due,
            created_by=ctx.user_id,
            details={"reference": ref, "triage_record": str(record.id)},
        )
        if code != triage_rules.FOLLOW_UP_TASK:
            _triage_audit(db, ctx, "CONTAINMENT_TASK_OPENED", record.id, now, task=str(task.id), type=code)


@router.post("/triage/{kind}/{record_id}/confirm", dependencies=[TRIAGERS])
def confirm_routine(
    kind: str,
    record_id: uuid.UUID,
    payload: SeenIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Routine triage in one click (TR-25): the three pre-filled facts (owner: the Case's signer; harm now: no health
    consequence; immediate action: none needed). Anything else is the full form ("Change something")."""
    tenant_id = _tenant(ctx)
    kind = _subject_or_404(db, tenant_id, kind, record_id)
    item = _triage_item(db, control_db, tenant_id, kind, record_id, service.now_utc())
    # An imported-backlog complaint (OD-12) is routine but not on the triage list: the same one click, owned by you.
    backlog = (
        item is None
        and kind == service.COMPLAINT
        and service.imported_backlog(db, tenant_id, complaint_id=record_id)["items"]
    )
    if not backlog and (item is None or item["speed"] != triage_rules.ROUTINE or not item["routine_prefill"]):
        raise _error(409, "NOT_ROUTINE", "Only a routine triage is confirmed in one click: use the full form")
    prefill = item["routine_prefill"] if item else {**triage_rules.ROUTINE_PREFILL, "triage_owner": None}
    people = {entry["id"] for entry in service.colleagues(control_db, tenant_id)}
    owner = prefill["triage_owner"] if prefill["triage_owner"] in people else str(ctx.user_id)
    body = TriageIn(
        severity=prefill["severity"],
        event_owner=owner,
        triage_owner=owner,
        no_action_reason=prefill["no_action_reason"],
        containment=prefill["containment"],
        seen_version=payload.seen_version,
        change_reason="Routine triage confirmed",
    )
    return _save_triage(db, control_db, ctx, kind, record_id, body, action="TRIAGE_ROUTINE_CONFIRMED")


@router.post("/triage/{kind}/{record_id}/confirm-qms", dependencies=[TRIAGERS])
def confirm_qms_triage(
    kind: str,
    record_id: uuid.UUID,
    payload: TriageIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Confirm QMS triage (T-D9; TR-14, TR-38): a person checks the triage imported from the QMS on a flagged
    complaint and saves the full form; the record keeps who confirmed it and when. One record at a time: there is no
    bulk confirmation."""
    tenant_id = _tenant(ctx)
    kind = _subject_or_404(db, tenant_id, kind, record_id)
    record = (
        db.query(TriageRecord)
        .filter(
            TriageRecord.tenant_id == tenant_id, TriageRecord.subject_kind == kind, TriageRecord.subject_id == record_id
        )
        .first()
    )
    if record is None or record.source_system != "QMS" or record.completed_at is not None:
        raise _error(409, "NOT_QMS_TO_CONFIRM", "There is no triage from your QMS waiting for confirmation here")
    return _save_triage(db, control_db, ctx, kind, record_id, payload)


@router.post("/triage/{kind}/{record_id}/acknowledge", dependencies=[TRIAGERS])
def acknowledge_triage(
    kind: str,
    record_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A1: a named owner acknowledges a fast-track triage before its acknowledgement is due; the person who
    acknowledges becomes its triage owner when it has none. Unacknowledged, the alert sweep escalates it."""
    tenant_id = _tenant(ctx)
    kind = _subject_or_404(db, tenant_id, kind, record_id)
    now = service.now_utc()
    item = _triage_item(db, control_db, tenant_id, kind, record_id, now)
    if item is None or item["speed"] != triage_rules.FAST:
        raise _error(409, "NOT_FAST", "Only a fast-track triage is acknowledged")
    if not item["acknowledgement"]["done"]:
        for member_kind, member_id in _members(item, kind, record_id):
            row = _record_for(db, tenant_id, member_kind, member_id, ctx.user_id, now, _opened(item, now))
            row.acknowledged_at, row.acknowledged_by = now, str(ctx.user_id)
            row.acknowledge_due_at = datetime.fromisoformat(item["acknowledgement"]["due_at"])
            row.triage_owner = row.triage_owner or str(ctx.user_id)
            row.speed, row.updated_at = triage_rules.FAST, now
        db.flush()
        _triage_audit(
            db,
            ctx,
            "TRIAGE_ACKNOWLEDGED",
            row.id,
            now,
            ref=item["ref"],
            due_at=item["acknowledgement"]["due_at"],
            late=item["acknowledgement"]["overdue"],
        )
        db.commit()
    return service.triage(db, control_db, tenant_id, "all")


def _ticked_by(db, tenant_id, record) -> str | None:
    """Who marked the threat: the first version that holds it."""
    for version in service.triage_versions(db, tenant_id, record.id):
        if (version.snapshot or {}).get("public_health_threat"):
            return version.changed_by
    return record.completed_by


@router.post("/triage/{kind}/{record_id}/exclude-threat", dependencies=[TRIAGERS])
def exclude_threat(
    kind: str,
    record_id: uuid.UUID,
    payload: SignedReasonIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Exclude a possible public health threat (TR-06, T-H3): a reason, password and code; outside the trial a person
    other than the one who marked it. The history keeps the threat and its exclusion."""
    tenant_id = _tenant(ctx)
    kind = _subject_or_404(db, tenant_id, kind, record_id)
    now = service.now_utc()
    item = _triage_item(db, control_db, tenant_id, kind, record_id, now)
    rows = [
        row
        for row in (
            db.query(TriageRecord)
            .filter(
                TriageRecord.tenant_id == tenant_id,
                TriageRecord.subject_id.in_([i for _, i in _members(item, kind, record_id)]),
            )
            .with_for_update()
            .all()
        )
        if row.public_health_threat
    ]
    if not rows:
        raise _error(409, "NO_THREAT", "No possible public health threat is marked on this triage")
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why it is not a threat")
    ticked = _ticked_by(db, tenant_id, rows[0])
    if ticked == str(ctx.user_id) and not is_trial(control_db, tenant_id):
        _triage_audit(db, ctx, "TRIAGE_THREAT_EXCLUSION_REFUSED", rows[0].id, now, reason, why="SAME_PERSON")
        db.commit()
        raise _error(403, "SAME_PERSON", "The person who marked the threat cannot exclude it: a second person signs")
    role = _signer_role(control_db, ctx)
    _verify(control_db, ctx, _subject_ref(item, record_id), payload.password, payload.mfa_code, "TRIAGE_THREAT")
    signed_id, _ = _signature(
        control_db,
        ctx,
        tenant_id,
        rows[0].id,
        rows[0].version,
        "EXCLUDED",
        reason,
        role,
        {"ref": item["ref"] if item else None, "reason": reason, "marked_by": ticked},
        now,
        f"I exclude the possible public health threat for {item['ref'] if item else record_id}.",
        object_type="TriageRecord",
        decision_type="TRIAGE_THREAT_EXCLUSION",
    )
    for row in rows:
        before = service.triage_snapshot(row)
        row.public_health_threat = False
        row.threat_excluded_at, row.threat_excluded_by, row.threat_exclusion_reason = now, str(ctx.user_id), reason
        row.threat_signed_record_id, row.updated_at = signed_id, now
        service.add_triage_version(db, tenant_id, row, before, ctx.user_id, now, reason, signed_id)
    _triage_audit(
        db,
        ctx,
        "TRIAGE_THREAT_EXCLUDED",
        rows[0].id,
        now,
        reason,
        signature_id=str(signed_id),
        marked_by=ticked,
        same_person=ticked == str(ctx.user_id),
    )
    signing_commit.commit(db, control_db, "triage")
    return service.triage(db, control_db, tenant_id, "all")


@router.post("/triage/downgrades/{task_id}", dependencies=[TRIAGERS])
def decide_downgrade(
    task_id: uuid.UUID,
    payload: SignedReasonIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A6: the second person approves or rejects a requested downgrade of a fast-track triage (or a later awareness),
    signed. The person who asked can never approve it; a refused attempt is audited."""
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
    from backend.app.workflow.tasks import complete_tasks

    tenant_id = _tenant(ctx)
    task = (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.id == task_id,
            WorkflowTask.task_type == triage_rules.DOWNGRADE_TASK,
        )
        .with_for_update()
        .first()
    )
    if task is None or task.status not in OPEN_TASK_STATUSES:
        raise _error(404, "NO_REQUEST", "No open downgrade request with this id")
    details = task.details or {}
    decision = rules.clean(payload.decision, 10).upper()
    if decision not in ("APPROVE", "REJECT"):
        raise _error(422, "UNKNOWN_DECISION", "Approve or reject the request")
    now = service.now_utc()
    if details.get("requested_by") == str(ctx.user_id):
        _triage_audit(
            db, ctx, "TRIAGE_DOWNGRADE_REFUSED", task.source_entity_id, now, None, why="SAME_PERSON", task=str(task.id)
        )
        db.commit()
        raise _error(403, "SAME_PERSON", "The person who asked for the downgrade cannot approve it")
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters what you checked")
    role = _signer_role(control_db, ctx)
    subject = SimpleNamespace(id=task.source_entity_id, reference=details.get("ref") or str(task.source_entity_id))
    _verify(control_db, ctx, subject, payload.password, payload.mfa_code, "TRIAGE_DOWNGRADE")
    signed_id, _ = _signature(
        control_db,
        ctx,
        tenant_id,
        task.source_entity_id,
        (details.get("payload") or {}).get("seen_version", 0),
        decision,
        reason,
        role,
        {"request": details, "decision": decision, "reason": reason},
        now,
        f"I {decision.lower()} {details.get('what', 'the downgrade')} for {subject.reference}.",
        object_type="TriageRecord",
        decision_type="TRIAGE_DOWNGRADE",
    )
    complete_tasks(
        db,
        tenant_id,
        source_type="TriageRecord",
        source_id=task.source_entity_id,
        task_types=[triage_rules.DOWNGRADE_TASK],
        outcome=decision,
        actor_ref=ctx.user_id,
        reason=reason,
    )
    if decision == "REJECT":
        _triage_audit(db, ctx, "TRIAGE_DOWNGRADE_REJECTED", task.source_entity_id, now, reason, task=str(task.id))
        signing_commit.commit(db, control_db, "triage")
        return service.triage(db, control_db, tenant_id, "all")
    return _save_triage(
        db,
        control_db,
        ctx,
        details["kind"],
        uuid.UUID(details["record_id"]),
        TriageIn(**details["payload"]),
        approval={"by": str(ctx.user_id), "signed": signed_id, "requested_by": details.get("requested_by")},
    )


@router.get("/triage/{kind}/{record_id}/versions")
def triage_versions(
    kind: str,
    record_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every version of a triage record: who changed what, old -> new, and why (spec 4.7 "Versions")."""
    tenant_id = _tenant(ctx)
    kind = _subject_or_404(db, tenant_id, kind, record_id)
    record = (
        db.query(TriageRecord)
        .filter(
            TriageRecord.tenant_id == tenant_id, TriageRecord.subject_kind == kind, TriageRecord.subject_id == record_id
        )
        .first()
    )
    rows = service.triage_versions(db, tenant_id, record.id) if record is not None else []
    names = service.names_of(control_db, tenant_id, {row.changed_by for row in rows})
    return {
        "items": [
            {
                "version": row.version,
                "changed_by": names.get(row.changed_by) or "A colleague",
                "changed_at": service._iso(row.changed_at),
                "change_reason": row.change_reason,
                "changed_fields": row.changed_fields,
                "signed": row.signed_record_id is not None,
            }
            for row in rows
        ]
    }


# --------------------------------------------------------------------------------------------- Case actions (B2 step 4)


class VoidIn(BaseModel):
    reason: str = Field(default="", max_length=rules.TEXT_MAX)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


class WaitingIn(BaseModel):
    waiting: bool = True
    reason: str = Field(default="", max_length=rules.TEXT_MAX)


class ContactIn(BaseModel):
    organisation: str = Field(default="", max_length=200)
    contact_role: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=254)
    preferred_channel: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=200)
    no_contact_reason: str = Field(default="", max_length=rules.TEXT_MAX)


CONTACT_CHANNELS = ("PHONE", "EMAIL", "LETTER", "DISTRIBUTOR")
# OD-1: who sees the contact itself; everyone else reads "Contact held".
CONTACT_READERS = frozenset({"SERVICE_DESK", "TRIAGE_LEAD", "REVIEWER", "REGULATORY_REVIEWER", "LEADER"})


@router.post("/intake/{event_id}/void", dependencies=[REVIEWERS])
def void_case(
    event_id: uuid.UUID,
    payload: VoidIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Withdraw a Case entered in error (spec 2.5, 3.2): only before it became a complaint, signed with a reason;
    outside the trial by someone other than the person who logged it (spec 6.4)."""
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why it was entered in error")
    if event.created_by == str(ctx.user_id) and not is_trial(control_db, tenant_id):
        _refused(control_db, ctx, "Withdraw a case", [QUALITY_REVIEW], why="LOGGER", case=event.reference)
        raise _error(403, "SAME_PERSON", "Someone other than the person who logged the case withdraws it")
    if event.status == case_rules.VOIDED:
        raise _error(409, "CASE_STATE_REFUSED", "This case is withdrawn already")
    _move_allowed(control_db, ctx, event, case_rules.VOIDED)
    role = _signer_role(control_db, ctx)
    _verify(control_db, ctx, event, payload.password, payload.mfa_code, "CASE_VOID")
    now = service.now_utc()
    signed_id, _ = _signature(
        control_db,
        ctx,
        tenant_id,
        event.id,
        event.version or 1,
        "VOIDED",
        reason,
        role,
        {"case": event.reference, "reason": reason, "status": event.status},
        now,
        f"I withdraw case {event.reference}: entered in error.",
        object_type="IntakeEvent",
        decision_type="CASE_VOID",
    )
    event.voided_at, event.voided_by, event.void_reason = now, str(ctx.user_id), reason
    event.void_signed_record_id = signed_id
    service.set_case_status(
        db, control_db, tenant_id, event, case_rules.VOIDED, ctx.user_id, now, ctx.correlation_id, reason
    )
    service._audit(
        control_db,
        tenant_id,
        ctx.user_id,
        "CASE_VOIDED",
        event,
        now,
        ctx.correlation_id,
        reason=reason,
        signature_id=str(signed_id),
        same_person=event.created_by == str(ctx.user_id),
    )
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/{event_id}/waiting", dependencies=[LOGGERS])
def wait_internal(
    event_id: uuid.UUID,
    payload: WaitingIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """S-2: send a Case to the internal team (engineering, technical support), or take it back when they answered:
    back to the QA review or the reporter's follow-up its signed outcome started, else To check."""
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters what the team is asked")
    if payload.waiting:
        target = case_rules.WAITING_INTERNAL
    elif event.status != case_rules.WAITING_INTERNAL:
        raise _error(409, "NOT_WAITING", "This case is not waiting for the internal team")
    else:
        signed = service.current_signed(service.checks_of(db, tenant_id, [event.id]).get(event.id, []))
        after = case_rules.state_after(signed.classification) if signed is not None else case_rules.OPEN
        target = after if after in (case_rules.PENDING, case_rules.IN_REVIEW) else case_rules.OPEN
    _move_allowed(control_db, ctx, event, target)
    now = service.now_utc()
    service.set_case_status(db, control_db, tenant_id, event, target, ctx.user_id, now, ctx.correlation_id, reason)
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


def _reporter(db, tenant_id, event_id):
    from backend.app.db.models.guides_communications import ExternalParty

    return (
        db.query(ExternalParty)
        .filter(
            ExternalParty.tenant_id == tenant_id,
            ExternalParty.intake_event_id == event_id,
            ExternalParty.party_type == "REPORTER",
        )
        .first()
    )


def contact_view(db, control_db, ctx, event) -> dict:
    """OD-1: the contact for those who need it (Service Desk, Complaint Handler, Quality Reviewer, Regulatory
    Reviewer, Leader); everyone else reads "Contact held". Plain views are not audited (too frequent to be useful)."""
    from backend.app.access.permissions import effective_roles
    from backend.app.role_codes import role_code

    party = _reporter(db, _tenant(ctx), event.id)
    held = party is not None and party.contact_erased_at is None
    base = {
        "held": held,
        "erased": bool(party is not None and party.contact_erased_at),
        "no_contact_reason": event.no_contact_reason,
    }
    if not held or not {role_code(role) for role in effective_roles(control_db, ctx)} & CONTACT_READERS:
        return {**base, "label": "Contact held" if held else "No contact held"}
    return {
        **base,
        "label": "Contact held",
        "organisation": party.name,
        "contact_role": party.contact_role,
        "name": party.primary_name,
        "phone": party.contact_phone,
        "email": party.contact_email,
        "preferred_channel": party.preferred_channel,
    }


@router.put("/intake/{event_id}/contact", dependencies=[LOGGERS])
def set_contact(
    event_id: uuid.UUID,
    payload: ContactIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """OD-1: the Case's customer contact, structured (organisation, job role, phone, e-mail, preferred way to reply),
    or "No contact" with why. The trial holds an organisation contact only, never a personal name. A Connect
    organization keeps the contact in its QMS. Every edit is audited by field name, never by value."""
    from backend.app.db.models.guides_communications import ExternalParty

    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    trial = is_trial(control_db, tenant_id)
    owner, _ = service.case_setup(db, tenant_id, trial)
    if owner == "EXTERNAL":
        raise _error(409, "CONTACT_IN_QMS", "Contact: in your QMS. MDARIX holds no contact for this organization")
    if trial and rules.clean(payload.name):
        raise _error(422, "NO_PERSONAL_NAME", "The trial holds an organisation contact only: no personal name")
    values = {
        "name": rules.clean(payload.organisation, 200),
        "contact_role": rules.clean(payload.contact_role, 120),
        "primary_name": rules.clean(payload.name, 200),
        "contact_phone": rules.clean(payload.phone, 40),
        "contact_email": rules.clean(payload.email, 254),
        "preferred_channel": _choice(payload.preferred_channel, CONTACT_CHANNELS) if payload.preferred_channel else "",
    }
    if values["preferred_channel"] is None:
        raise _error(422, "UNKNOWN_CHANNEL", "Reply by phone, e-mail, letter or through the distributor")
    if values["contact_email"] and "@" not in values["contact_email"]:
        raise _error(422, "EMAIL_INVALID", "Enter an e-mail address, or leave it empty")
    no_contact = rules.clean(payload.no_contact_reason)
    if not any(values.values()) and len(no_contact) < rules.REASON_MIN:
        raise _error(422, "CONTACT_OR_REASON", "Enter the contact, or say why there is none (anonymous or refused)")
    now = service.now_utc()
    party = _reporter(db, tenant_id, event.id)
    if party is None:
        party = ExternalParty(
            tenant_id=tenant_id,
            party_type="REPORTER",
            name=values["name"] or event.reporter_site or "Reporter",
            intake_event_id=event.id,
            complaint_id=event.complaint_id,
            source_system="MDARIX_CASE",
            created_by=str(ctx.user_id),
            created_at=now,
            updated_by=str(ctx.user_id),
            updated_at=now,
        )
        db.add(party)
    changed = sorted(field for field, value in values.items() if (getattr(party, field) or "") != value)
    for field, value in values.items():
        if field != "name" or value:
            setattr(party, field, value or None)
    party.contact_erased_at = party.contact_erased_by = party.contact_erase_reason = None
    party.updated_by, party.updated_at = str(ctx.user_id), now
    event.no_contact_reason, event.updated_at = no_contact or None, now
    service._audit(
        control_db, tenant_id, ctx.user_id, "CASE_CONTACT_SET", event, now, ctx.correlation_id, fields=changed
    )
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/{event_id}/contact/erase", dependencies=[REVIEWERS])
def erase_contact(
    event_id: uuid.UUID,
    payload: UndoIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """OD-1: erase the contact on a data-subject request, with a reason; the Case then says "contact erased on
    request". The record of the complaint itself stays."""
    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say in at least {rules.REASON_MIN} characters why it is erased")
    party = _reporter(db, tenant_id, event.id)
    if party is None or party.contact_erased_at is not None:
        raise _error(404, "NO_CONTACT", "No contact is held on this case")
    now = service.now_utc()
    party.contact_role = party.contact_phone = party.contact_email = party.preferred_channel = None
    party.primary_name, party.primary_details = None, None
    party.contact_erased_at, party.contact_erased_by, party.contact_erase_reason = now, str(ctx.user_id), reason
    party.updated_by, party.updated_at = str(ctx.user_id), now
    service._audit(
        control_db, tenant_id, ctx.user_id, "CASE_CONTACT_ERASED", event, now, ctx.correlation_id, reason=reason
    )
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


# --------------------------------------------------------------------------------------------- B2: addenda, facts, bulk

SAID_BY = ("REPORTER", "TECHNICIAN", "DISTRIBUTOR", "OUR_STAFF")
# Facts a person may correct (spec 2.5), with their stored length; the reporter's words are never edited.
CORRECTABLE = {
    "serial_number": 120,
    "lot_text": 120,
    "product_text": 200,
    "udi": 120,
    "software_version": 60,
    "hardware_revision": 60,
    "firmware_version": 60,
    "reporter_site": 120,
    "country_text": 80,
    "harm_text": rules.TEXT_MAX,
    "troubleshooting": rules.TEXT_MAX,
}
MASKED_FACTS = ("harm_text", "troubleshooting", "reporter_site")
BULK_MAX = 200


class AddendumIn(BaseModel):
    kind: str = Field(max_length=30)
    said_by_role: str = Field(max_length=30)
    said_at: datetime | None = None
    said_zone: str = Field(default="", max_length=60)
    text: str = Field(max_length=rules.TEXT_MAX)


class CorrectIn(BaseModel):
    field: str = Field(max_length=60)
    value: str = Field(default="", max_length=rules.TEXT_MAX)
    reason: str = Field(max_length=rules.TEXT_MAX)
    seen_version: int | None = None


class BulkAssignIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX)
    owner_id: str = Field(max_length=64)


def _masked_text(value: str) -> tuple[str, dict | None]:
    """Free text masked on save with the import's masking (spec 2.5); what was masked is counted, never kept."""
    from backend.app.trial.imports import _mask

    masked = _mask(value)
    return masked, ({"personal_data": 1} if masked != value else None)


def _new_information(db, control_db, ctx, event, words: str, now, why: str) -> None:
    """New information on a Case (T-D7, spec 3.1): a closed Case with a harm or fault word reopens, and a finished
    triage whose facts it raises reopens on the fast track (the sweep then alerts the escalation role)."""
    if event.status == case_rules.CLOSED and (rules.harm_words(words) or rules.fault_words(words)):
        service.set_case_status(
            db, control_db, event.tenant_id, event, case_rules.OPEN, ctx.user_id, now, ctx.correlation_id, why
        )
    db.flush()
    service.reopen_raised(db, control_db, event.tenant_id, ctx.user_id, now, ctx.correlation_id, why)


@router.post("/intake/bulk-assign", dependencies=[LOGGERS])
def bulk_assign(
    payload: BulkAssignIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """CI-36: set the owner of up to 200 Cases at once. Assignment only: there is no bulk signature."""
    from backend.app.enterprise_audit import make_audit_event

    tenant_id = _tenant(ctx)
    if payload.owner_id not in {entry["id"] for entry in service.colleagues(control_db, tenant_id)}:
        raise _error(422, "OWNER_UNKNOWN", "Name the owner from your team")
    ids = list(dict.fromkeys(payload.ids))
    events = (
        db.query(IntakeEvent)
        .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.id.in_(ids))
        .order_by(IntakeEvent.id)
        .with_for_update()
        .all()
    )
    if len(events) != len(ids):
        raise _error(404, "INTAKE_NOT_FOUND", "One or more cases are not in your organization")
    now = service.now_utc()
    changed = [event for event in events if event.owner_id != payload.owner_id]
    for event in changed:
        event.owner_id, event.version, event.updated_at = payload.owner_id, event.version + 1, now
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="CASE_BULK_ASSIGNED",
            entity_type="IntakeEvent",
            entity_id=None,
            correlation_id=ctx.correlation_id,
            details={"ids": [str(event.id) for event in changed], "count": len(changed), "owner": payload.owner_id},
            created_at=now,
        )
    )
    _commit(db, control_db)
    return {"assigned": len(changed), "unchanged": len(events) - len(changed)}


@router.post("/intake/{event_id}/addenda", dependencies=[LOGGERS])
def add_addendum(
    event_id: uuid.UUID,
    payload: AddendumIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """What was said later and by whom (IN-17, IN-18): a new row, the reporter's first words never edited. A
    withdrawal is an addendum only: an escalated Complaint stands."""
    from backend.app.db.models.intake import ADDENDUM_KINDS, CaseAddendum

    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    if event.status == case_rules.VOIDED:
        raise _error(409, "CASE_VOIDED", "This case was withdrawn: entered in error")
    # EMAIL addenda are made from a message in "E-mail to check" (B7b), never typed here.
    kind = _choice(payload.kind.upper(), tuple(k for k in ADDENDUM_KINDS if k != "EMAIL"))
    said_by = _choice(payload.said_by_role.upper(), SAID_BY)
    if kind is None or said_by is None:
        raise _error(422, "ADDENDUM_INCOMPLETE", "Choose what kind of addendum it is and who said it")
    text = rules.clean(payload.text)
    if len(text) < rules.REASON_MIN:
        raise _error(422, "WORDS_NEEDED", f"Write what was said, in at least {rules.REASON_MIN} characters")
    now = service.now_utc()
    zone = _zone(payload.said_zone)
    said_at = _at(payload.said_at, zone) or now
    if said_at > now + _SKEW:
        raise _error(422, "TIME_IN_FUTURE", "It cannot have been said in the future")
    text, masked = _masked_text(text)
    row = CaseAddendum(
        tenant_id=tenant_id,
        intake_event_id=event.id,
        kind=kind,
        said_by_role=said_by,
        said_at=said_at,
        said_zone=zone,
        text=text,
        masked=masked,
        source_system="MDARIX",
        created_by=str(ctx.user_id),
        created_at=now,
    )
    db.add(row)
    db.flush()
    service._audit(
        control_db,
        tenant_id,
        ctx.user_id,
        "CASE_ADDENDUM_ADDED",
        event,
        now,
        ctx.correlation_id,
        addendum=str(row.id),
        kind=kind,
        said_by=said_by,
    )
    _new_information(db, control_db, ctx, event, text, now, f"Addendum added ({kind.lower()})")
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


@router.post("/intake/{event_id}/correct", dependencies=[LOGGERS])
def correct_fact(
    event_id: uuid.UUID,
    payload: CorrectIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Correct or add a fact (spec 2.5): the new value, a field-change row (source CORRECTION) with the reason, and
    the audit (field, old, new, reason). The reporter's words are never edited."""
    from backend.app.db.models.intake import RecordFieldChange

    tenant_id = _tenant(ctx)
    event = _event_or_404(db, tenant_id, event_id, lock=True)
    field = payload.field.strip().lower()
    if field not in CORRECTABLE:
        raise _error(422, "FIELD_NOT_CORRECTABLE", "This fact cannot be corrected here", fields=sorted(CORRECTABLE))
    if event.status == case_rules.VOIDED:
        raise _error(409, "CASE_VOIDED", "This case was withdrawn: entered in error")
    if payload.seen_version is not None and payload.seen_version != event.version:
        raise _error(409, "CASE_CHANGED", "A colleague changed this case a moment ago; reload to see it")
    reason = rules.clean(payload.reason)
    if len(reason) < rules.REASON_MIN:
        raise _error(422, "REASON_NEEDED", f"Say why, in at least {rules.REASON_MIN} characters")
    value = rules.clean(payload.value, CORRECTABLE[field]) or None
    if value and field in MASKED_FACTS:
        value, _ = _masked_text(value)
    before = getattr(event, field)
    if value == before:
        raise _error(422, "NO_CHANGE", "The value is the same as recorded")
    now = service.now_utc()
    setattr(event, field, value)
    event.version, event.updated_at = event.version + 1, now
    db.add(
        RecordFieldChange(
            tenant_id=tenant_id,
            entity="IntakeEvent",
            record_id=event.id,
            record_key=event.reference,
            field=field,
            before=before,
            after=value,
            source="CORRECTION",
            changed_at=now,
        )
    )
    service._audit(
        control_db,
        tenant_id,
        ctx.user_id,
        "CASE_FACT_CORRECTED",
        event,
        now,
        ctx.correlation_id,
        reason=reason,
        field=field,
        old=before,
        new=value,
    )
    _new_information(db, control_db, ctx, event, value or "", now, f"Fact corrected ({field})")
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)
