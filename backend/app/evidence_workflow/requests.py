"""Evidence requests: asking a colleague, a role or a supplier for evidence a case needs, and turning the answer into
evidence of the case.

Requests to a colleague or a role (``request_kind`` INTERNAL) and to suppliers (SUPPLIER) share the
``supplier_evidence_requests`` table. A supplier request is created by the existing supplier flow
(backend/app/stage3_workflow_router.py: delivery, rate limits and its task hooks unchanged) and then given the case's
unknown, priority and due date.

- ``POST /api/v1/investigations/{id}/evidence-requests`` (``evidence.request``)
- ``GET  /api/v1/evidence-requests`` (``box`` sent | received | all), ``GET /api/v1/evidence-requests/{id}``
- ``POST /api/v1/evidence-requests/{id}/acknowledge | respond | cannot-provide`` (the recipient: the person asked or
  anyone holding the role asked), ``/cancel`` (the requester or ``investigation.assign``), ``/review`` (the requester
  or ``evidence.review``), ``/attachments`` (upload: requester or recipient; download: requester, recipient or
  ``investigation.work``).

Every change locks the request row, is limited to the signed-in organization (another organization's request is "not
found"), is audited (EVIDENCE_REQUEST_*), and moves workflow tasks through never-blocking hooks (hooks.py).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import String, cast, false, func, or_, select
from sqlalchemy import case as sql_case
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from backend.app.downloads import attachment
from backend.app.access.permissions import (
    EVIDENCE_REQUEST,
    EVIDENCE_REVIEW,
    INVESTIGATION_ASSIGN,
    INVESTIGATION_WORK,
    require_permission,
)
from backend.app.business_ids import as_uuid
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import (
    AuditEvent,
    Evidence,
    Investigation,
    InvestigationEvidence,
    Supplier,
    Unknown,
)
from backend.app.db.models.stage3 import EvidenceAttachment, SupplierEvidenceRequest
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.sorting import order_query
from backend.app.sorting_lookup import lookup_order, person_names
from backend.app.evidence_workflow import hooks
from backend.app.evidence_workflow.inventory import (
    error,
    inventory_items,
    load_case,
    now_utc,
    refuse_closed,
    review_event,
)
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.evidence_workflow.rules import (
    ANSWERABLE_STATUSES,
    ANSWERED_STATUSES,
    BOXES,
    DEFAULT_EVIDENCE_TYPE,
    EVIDENCE_SOURCE_SYSTEM,
    FINISHED_STATUSES,
    KIND_INTERNAL,
    KIND_SUPPLIER,
    UNREVIEWED,
    WAITING_STATUSES,
    EvidenceRequestPayload,
    ReasonPayload,
    RequestReviewPayload,
    RespondPayload,
    is_overdue,
    request_actions,
    request_kind,
    status_label,
)
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import is_platform_admin_role, role_code
from backend.app.stage3_workflow_router import _DeclaredSizeLimitedRoute

logger = logging.getLogger("mdarix.evidence_workflow")
router = APIRouter(tags=["Evidence Requests"])
BASE = "/api/v1/evidence-requests"
ENTITY = "EvidenceRequest"


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _not_found():
    return error(404, "EVIDENCE_REQUEST_NOT_FOUND", "Evidence request is not available")


def _load(db: Session, tenant_id, request_id, *, lock: bool = False) -> SupplierEvidenceRequest:
    query = db.query(SupplierEvidenceRequest).filter(
        SupplierEvidenceRequest.id == request_id, SupplierEvidenceRequest.tenant_id == tenant_id
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise _not_found()
    return row


def is_requester(person: Person, row: SupplierEvidenceRequest) -> bool:
    return person.is_user(row.requested_by)


def is_recipient(person: Person, row: SupplierEvidenceRequest) -> bool:
    """The person asked, or anyone holding the role asked (requests to colleagues only)."""
    if request_kind(row.request_kind) != KIND_INTERNAL:
        return False
    if row.recipient_user_id is not None and person.is_user(row.recipient_user_id):
        return True
    return bool(row.recipient_role) and role_code(row.recipient_role) in person.role_codes


def actions_for(person: Person, row: SupplierEvidenceRequest) -> dict[str, bool]:
    return request_actions(
        kind=row.request_kind,
        status=row.status,
        is_requester=is_requester(person, row),
        is_recipient=is_recipient(person, row),
        can_assign=person.holds(INVESTIGATION_ASSIGN),
        can_review_evidence=person.holds(EVIDENCE_REVIEW),
    )


def _document(row: SupplierEvidenceRequest) -> dict:
    return dict(row.requested_items or {}) if isinstance(row.requested_items, dict) else {}


def _supplier_replies(row: SupplierEvidenceRequest) -> list[dict]:
    replies = _document(row).get("replies") or []
    return [reply for reply in replies if isinstance(reply, dict)]


def _answer(row: SupplierEvidenceRequest) -> tuple[str | None, str | None]:
    """The answer text and when it came: the colleague's note, or the supplier's recorded replies."""
    if request_kind(row.request_kind) == KIND_INTERNAL:
        return row.response_note, _iso(row.responded_at)
    replies = _supplier_replies(row)
    if not replies:
        return row.response_note, _iso(row.responded_at)
    note = "\n\n".join(str(reply.get("note") or "").strip() for reply in replies if reply.get("note"))
    return (row.response_note or note or None), (_iso(row.responded_at) or replies[-1].get("recorded_at"))


def serialize(
    db: Session, control_db: Session, tenant_id, person: Person, rows: list[SupplierEvidenceRequest]
) -> list[dict]:
    """The EvidenceRequest JSON of each row, with names and business ids read in bulk."""
    from backend.app.workflow.labels import role_label
    from backend.app.workflow.people import names_by_id

    if not rows:
        return []
    now = now_utc()
    names = names_by_id(
        control_db,
        tenant_id,
        [ref for row in rows for ref in (row.requested_by, row.recipient_user_id, row.reviewed_by)],
    )

    def lookup(model, columns, ids):
        wanted = {item for item in ids if item is not None}
        if not wanted:
            return {}
        return {
            values[0]: values
            for values in db.query(model.id, *columns).filter(model.tenant_id == tenant_id, model.id.in_(list(wanted)))
        }

    suppliers = lookup(Supplier, (Supplier.business_id, Supplier.name), (row.supplier_id for row in rows))
    cases = lookup(Investigation, (Investigation.business_id,), (row.investigation_id for row in rows))
    unknowns = lookup(Unknown, (Unknown.business_id, Unknown.description), (row.unknown_id for row in rows))
    evidence = lookup(Evidence, (Evidence.business_id,), (row.resolved_evidence_id for row in rows))
    counts = dict(
        db.query(EvidenceAttachment.request_id, func.count(EvidenceAttachment.id))
        .filter(EvidenceAttachment.tenant_id == tenant_id, EvidenceAttachment.request_id.in_([row.id for row in rows]))
        .group_by(EvidenceAttachment.request_id)
        .all()
    )

    def name(ref) -> str | None:
        key = as_uuid(ref)
        return names.get(str(key)) if key is not None else None

    items = []
    for row in rows:
        kind = request_kind(row.request_kind)
        document = _document(row)
        note, responded_at = _answer(row)
        supplier = suppliers.get(row.supplier_id)
        case = cases.get(row.investigation_id)
        unknown = unknowns.get(row.unknown_id)
        snapshot = document.get("unknown") if isinstance(document.get("unknown"), dict) else None
        resolved = evidence.get(row.resolved_evidence_id)
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "kind": kind,
                "title": row.title,
                "requested_items": [str(item) for item in (document.get("items") or [])],
                "rationale": document.get("rationale"),
                "status": row.status,
                "status_label": status_label(row.status),
                "priority": row.priority or "MEDIUM",
                "due_at": _iso(row.due_at),
                "overdue": is_overdue(row.status, row.due_at, now),
                "investigation": {"id": str(case[0]), "business_id": case[1]} if case else None,
                "unknown": (
                    {"id": str(unknown[0]), "business_id": unknown[1], "description": unknown[2]}
                    if unknown
                    else (
                        {
                            "id": snapshot.get("id"),
                            "business_id": snapshot.get("business_id"),
                            "description": snapshot.get("description"),
                        }
                        if snapshot
                        else None
                    )
                ),
                "requester": {"id": str(row.requested_by), "name": name(row.requested_by)},
                "recipient": {
                    "user": (
                        {"id": str(row.recipient_user_id), "name": name(row.recipient_user_id)}
                        if row.recipient_user_id
                        else None
                    ),
                    "role": row.recipient_role,
                    "role_label": role_label(row.recipient_role),
                    "supplier": (
                        {"id": str(supplier[0]), "business_id": supplier[1], "name": supplier[2]} if supplier else None
                    ),
                    "email": row.recipient if kind == KIND_SUPPLIER else None,
                },
                "response_note": note,
                "responded_at": responded_at,
                "acknowledged_at": _iso(row.acknowledged_at),
                "cannot_provide_reason": row.cannot_provide_reason,
                "review": document.get("review"),
                "reviewed_by_name": name(row.reviewed_by),
                "reviewed_at": _iso(row.reviewed_at),
                "resolved_evidence": {"id": str(resolved[0]), "business_id": resolved[1]} if resolved else None,
                "attachments_count": int(counts.get(row.id, 0)),
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
                "actions": actions_for(person, row),
            }
        )
    return items


def _one(db: Session, control_db: Session, tenant_id, person: Person, row) -> dict:
    return serialize(db, control_db, tenant_id, person, [row])[0]


def _audit(db: Session, ctx, person: Person, row, action: str, now, *, reason=None, details=None, entity_id=None):
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=person.user_id,
            action=action,
            entity_type=ENTITY if entity_id is None else "EvidenceAttachment",
            entity_id=entity_id or row.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={
                "request_kind": request_kind(row.request_kind),
                "investigation_id": str(row.investigation_id) if row.investigation_id else None,
                "status": row.status,
                **dict(details or {}),
            },
            created_at=now,
        )
    )


def _case_of(db: Session, tenant_id, row) -> Investigation | None:
    if row.investigation_id is None:
        return None
    return (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.id == row.investigation_id)
        .first()
    )


def _refuse_closed_case(db: Session, tenant_id, row) -> None:
    case = _case_of(db, tenant_id, row)
    if case is not None:
        refuse_closed(case)


def resolve_unknown(db: Session, tenant_id, case: Investigation, unknown_id) -> tuple[uuid.UUID | None, dict | None]:
    """The unknown a request should resolve: a recorded unknown of the case (``unknowns`` row), or an unknown of the
    case's latest unknown set (GET .../unknowns ``unknown_set.unknowns[].unknown_id``). An unknown of the set is mapped
    to its recorded row when there is one (same statement); otherwise its id is kept with a snapshot of its statement.
    404 when the case has no such unknown."""
    if unknown_id is None:
        return None, None
    row = (
        db.query(Unknown.id)
        .filter(Unknown.tenant_id == tenant_id, Unknown.id == unknown_id, Unknown.investigation_id == case.id)
        .first()
    )
    if row is not None:
        return row[0], None

    def from_latest_set():
        from failure_chain.service import UnknownsFailureChainService
        from unknowns.engine import ORCHESTRATION_VERSION, PROVIDER
        from unknowns.schemas import UnknownSet

        latest = UnknownsFailureChainService().latest(
            db, tenant_id, case.id, PROVIDER, ORCHESTRATION_VERSION, UnknownSet
        )
        if not latest:
            return None
        return next((item for item in latest[0].unknowns if str(item.unknown_id) == str(unknown_id)), None)

    item = None
    try:
        with db.begin_nested():
            item = from_latest_set()
    except Exception:
        logger.warning("The unknown set of case %s could not be read", case.id, exc_info=True)
    if item is None:
        raise error(404, "UNKNOWN_NOT_FOUND", "Choose an unknown of this investigation")
    recorded = (
        db.query(Unknown.id, Unknown.business_id)
        .filter(
            Unknown.tenant_id == tenant_id,
            Unknown.investigation_id == case.id,
            Unknown.description == item.statement,
        )
        .first()
    )
    if recorded is not None:
        return recorded[0], None
    return as_uuid(unknown_id), {
        "id": str(unknown_id),
        "business_id": getattr(item, "business_id", None),
        "description": item.statement,
    }


def _conflict(message: str):
    return error(409, "EVIDENCE_REQUEST_STATE_CONFLICT", message)


# ---------------------------------------------------------------------------------------------------------- create


@router.post(
    "/api/v1/investigations/{investigation_id}/evidence-requests",
    status_code=201,
    dependencies=[Depends(require_permission(EVIDENCE_REQUEST))],
)
def create_evidence_request(
    investigation_id: uuid.UUID,
    payload: EvidenceRequestPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    case = load_case(db, tenant_id, investigation_id)
    refuse_closed(case)
    unknown_id, unknown_snapshot = resolve_unknown(db, tenant_id, case, payload.unknown_id)
    payload = payload.model_copy(update={"unknown_id": unknown_id})
    if payload.kind == KIND_SUPPLIER:
        return _create_supplier_request(db, control_db, ctx, person, case, payload, unknown_snapshot)

    from backend.app.access.permissions import permissions_for_roles
    from backend.app.workflow.labels import known_role
    from backend.app.workflow.people import find_user

    recipient = None
    if payload.recipient_user_id is not None:
        recipient = find_user(control_db, tenant_id, payload.recipient_user_id)
        if recipient is None or is_platform_admin_role(recipient.role):
            raise error(422, "RECIPIENT_NOT_ELIGIBLE", "Ask an active colleague in your organization")
    role = None
    if payload.recipient_role:
        role = role_code(payload.recipient_role)
        # The role's queue must be one its holders can see: the role grants the task's permission.
        if not known_role(role) or EVIDENCE_REQUEST not in (permissions_for_roles([role]) or ()):
            raise error(422, "ROLE_NOT_ELIGIBLE", "That role does not answer evidence requests")
    now = now_utc()
    row = SupplierEvidenceRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        supplier_id=None,
        requested_by=person.user_id,
        recipient=None,
        title=payload.title,
        requested_items={
            "items": payload.requested_items,
            "rationale": payload.rationale,
            **({"unknown": unknown_snapshot} if unknown_snapshot else {}),
        },
        status="OPEN",
        request_kind=KIND_INTERNAL,
        recipient_user_id=recipient.id if recipient is not None else None,
        recipient_role=role,
        unknown_id=payload.unknown_id,
        priority=payload.priority,
        due_at=payload.due_at,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUESTED",
        now,
        details={
            "recipient_user_id": str(row.recipient_user_id) if row.recipient_user_id else None,
            "recipient_role": role,
            "unknown_id": str(payload.unknown_id) if payload.unknown_id else None,
            "priority": payload.priority,
            "due_at": _iso(payload.due_at),
            "item_count": len(payload.requested_items),
            "actor_role": person.role_for(EVIDENCE_REQUEST),
        },
    )
    db.commit()
    # The recipient's task to answer and the requester's waiting task. Saved after the request; never undo it.
    hooks.on_internal_request_created(db, control_db, row, actor_user_id=person.user_id)
    return _one(db, control_db, tenant_id, person, row)


def _create_supplier_request(
    db, control_db, ctx, person: Person, case: Investigation, payload, unknown_snapshot: dict | None = None
) -> dict:
    """The existing supplier flow sends the email, applies its limits and creates its tasks; the request then takes
    the case's unknown, priority, due date and rationale."""
    from backend.app.stage3_workflow_router import SupplierEvidenceRequestPayload, request_supplier_evidence

    try:
        supplier_payload = SupplierEvidenceRequestPayload(
            recipient=payload.recipient,
            title=payload.title,
            requested_items=payload.requested_items,
            supplier_id=payload.supplier_id,
            investigation_id=case.id,
        )
    except ValidationError as exc:
        problems = exc.errors()
        message = str(problems[0].get("msg")) if problems else "The supplier request is not valid"
        raise error(422, "INVALID_SUPPLIER_REQUEST", message.removeprefix("Value error, ")) from exc
    created = request_supplier_evidence(payload=supplier_payload, db=db, ctx=ctx, control_db=control_db)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    row = _load(db, tenant_id, uuid.UUID(created["id"]), lock=True)
    now = now_utc()
    document = _document(row)
    document["rationale"] = payload.rationale
    if unknown_snapshot:
        document["unknown"] = unknown_snapshot
    row.requested_items = document
    flag_modified(row, "requested_items")
    row.request_kind = KIND_SUPPLIER
    row.unknown_id = payload.unknown_id
    row.priority = payload.priority
    row.due_at = payload.due_at
    row.updated_at = now
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUESTED",
        now,
        details={
            "supplier_id": str(row.supplier_id) if row.supplier_id else None,
            "email_delivery": created.get("email_delivery"),
            "unknown_id": str(payload.unknown_id) if payload.unknown_id else None,
            "priority": payload.priority,
            "due_at": _iso(payload.due_at),
            "item_count": len(payload.requested_items),
            "actor_role": person.role_for(EVIDENCE_REQUEST),
        },
    )
    db.commit()
    hooks.on_supplier_request_scheduled(db, row)
    return {**_one(db, control_db, tenant_id, person, row), "email_delivery": created.get("email_delivery")}


# ---------------------------------------------------------------------------------------------------------- read

# A priority column sorted ascending reads from low to critical.
_REQUEST_PRIORITY = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _people_and_roles(query, control_db: Session, tenant_id) -> tuple[dict[str, str], dict[str, str]]:
    """The names of the people (requesters and recipients) and role queues the requests in ``query`` name."""
    from backend.app.workflow.labels import role_label

    refs = query.with_entities(
        SupplierEvidenceRequest.requested_by,
        SupplierEvidenceRequest.recipient_user_id,
        SupplierEvidenceRequest.recipient_role,
    ).distinct()
    people: set = set()
    roles: set = set()
    for requested_by, recipient_user_id, recipient_role in refs:
        people.update(ref for ref in (requested_by, recipient_user_id) if ref is not None)
        if recipient_role:
            roles.add(recipient_role)
    names = {str(key): value for key, value in person_names(control_db, tenant_id, people).items()}
    return names, {role: role_label(role) or role for role in roles}


def _searched(query, q: str | None, names: dict[str, str], roles: dict[str, str]):
    """Requests whose ID, title, recipient e-mail, case, supplier, requester, recipient or role queue holds ``q``."""
    text = " ".join(str(q or "").split())
    if not text:
        return query
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    needle = text.casefold()
    people = [ref for ref, name in names.items() if needle in name.casefold()]
    held = [role for role, label in roles.items() if needle in label.casefold() or needle in role.casefold()]
    case_ids = select(Investigation.id).where(
        Investigation.tenant_id == SupplierEvidenceRequest.tenant_id,
        Investigation.business_id.ilike(pattern, escape="\\"),
    )
    supplier_ids = select(Supplier.id).where(
        Supplier.tenant_id == SupplierEvidenceRequest.tenant_id,
        or_(Supplier.name.ilike(pattern, escape="\\"), Supplier.business_id.ilike(pattern, escape="\\")),
    )
    conditions = [
        SupplierEvidenceRequest.business_id.ilike(pattern, escape="\\"),
        SupplierEvidenceRequest.title.ilike(pattern, escape="\\"),
        SupplierEvidenceRequest.recipient.ilike(pattern, escape="\\"),
        SupplierEvidenceRequest.investigation_id.in_(case_ids),
        SupplierEvidenceRequest.supplier_id.in_(supplier_ids),
    ]
    if people:
        conditions.append(SupplierEvidenceRequest.requested_by.in_(people))
        conditions.append(cast(SupplierEvidenceRequest.recipient_user_id, String).in_(people))
    if held:
        conditions.append(SupplierEvidenceRequest.recipient_role.in_(held))
    return query.filter(or_(*conditions))


def _column_sorts(box: str, names: dict[str, str], roles: dict[str, str]) -> dict:
    """What each column of the request list sorts on. "To" (sent) is the recipient as the list shows it: the person,
    else the role queue, else the supplier, else the e-mail; "From" (received, all) is the person who asked."""
    case_id = (
        select(Investigation.business_id)
        .where(
            Investigation.tenant_id == SupplierEvidenceRequest.tenant_id,
            Investigation.id == SupplierEvidenceRequest.investigation_id,
        )
        .scalar_subquery()
    )
    supplier_name = (
        select(func.coalesce(Supplier.name, Supplier.business_id))
        .where(
            Supplier.tenant_id == SupplierEvidenceRequest.tenant_id, Supplier.id == SupplierEvidenceRequest.supplier_id
        )
        .scalar_subquery()
    )
    files = (
        select(func.count(EvidenceAttachment.id))
        .where(
            EvidenceAttachment.tenant_id == SupplierEvidenceRequest.tenant_id,
            EvidenceAttachment.request_id == SupplierEvidenceRequest.id,
        )
        .scalar_subquery()
    )
    recipient = func.coalesce(
        lookup_order(cast(SupplierEvidenceRequest.recipient_user_id, String), names),
        lookup_order(SupplierEvidenceRequest.recipient_role, roles),
        supplier_name,
        SupplierEvidenceRequest.recipient,
    )
    requester = lookup_order(SupplierEvidenceRequest.requested_by, names)
    return {
        "business_id": [SupplierEvidenceRequest.business_id],
        "title": [SupplierEvidenceRequest.title],
        "investigation": [case_id],
        "party": [recipient if box == "sent" else requester],
        "status": [SupplierEvidenceRequest.status],
        "priority": [sql_case(_REQUEST_PRIORITY, value=SupplierEvidenceRequest.priority, else_=None)],
        "due_at": [SupplierEvidenceRequest.due_at],
        "attachments_count": [files],
    }


@router.get(BASE)
def list_evidence_requests(
    investigation_id: uuid.UUID | None = None,
    box: str = Query(default="all", pattern="^(" + "|".join(BOXES) + ")$"),
    status: str | None = Query(default=None, max_length=40),
    q: str | None = Query(default=None, max_length=200),
    sort: str | None = Query(default=None, max_length=60),
    order: str | None = Query(default=None, max_length=10),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of the organization's evidence requests, newest first: those I sent, those asked of me or of a role I
    hold (received), or all of them; optionally of one case and in one status. ``q`` searches every page (request
    ID, title, case, recipient, requester, supplier); ``sort`` (a column: business_id, title, investigation, party,
    status, priority, due_at, attachments_count) with ``order`` (asc or desc) orders every page by that column."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    query = db.query(SupplierEvidenceRequest).filter(SupplierEvidenceRequest.tenant_id == tenant_id)
    if investigation_id is not None:
        query = query.filter(SupplierEvidenceRequest.investigation_id == investigation_id)
    if box == "sent":
        query = query.filter(SupplierEvidenceRequest.requested_by == person.user_id)
    elif box == "received":
        mine = (
            SupplierEvidenceRequest.recipient_user_id == person.user_uuid if person.user_uuid is not None else false()
        )
        roles = sorted(person.role_codes)
        held = SupplierEvidenceRequest.recipient_role.in_(roles) if roles else false()
        query = query.filter(SupplierEvidenceRequest.request_kind == KIND_INTERNAL, or_(mine, held))
    if status:
        query = query.filter(SupplierEvidenceRequest.status == status.strip().upper())
    columns: dict = {}
    if (q and q.strip()) or sort:
        names, roles = _people_and_roles(query, control_db, tenant_id)
        query = _searched(query, q, names, roles)
        columns = _column_sorts(box, names, roles) if sort else {}
    total = query.count()
    ordered = order_query(
        query,
        sort,
        order,
        columns,
        default=[SupplierEvidenceRequest.created_at.desc()],
        tiebreak=[SupplierEvidenceRequest.id],
    )
    rows = ordered.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": serialize(db, control_db, tenant_id, person, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _attachments(db: Session, tenant_id, row) -> list[EvidenceAttachment]:
    return (
        db.query(EvidenceAttachment)
        .filter(EvidenceAttachment.tenant_id == tenant_id, EvidenceAttachment.request_id == row.id)
        .order_by(EvidenceAttachment.created_at, EvidenceAttachment.id)
        .all()
    )


@router.get(BASE + "/{request_id}")
def get_evidence_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The request with its attachments, the supplier's replies (supplier requests) and its history."""
    from backend.app.workflow.people import names_by_id

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _load(db, tenant_id, request_id)
    attachments = _attachments(db, tenant_id, row)
    events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id.in_([row.id, *[item.id for item in attachments]]),
        )
        .order_by(AuditEvent.created_at, AuditEvent.id)
        .limit(500)
        .all()
    )
    names = names_by_id(
        control_db, tenant_id, [event.actor_ref for event in events] + [item.uploaded_by for item in attachments]
    )

    def name(ref) -> str | None:
        key = as_uuid(ref)
        return names.get(str(key)) if key is not None else None

    return {
        **_one(db, control_db, tenant_id, person, row),
        "attachments": [
            {
                "id": str(item.id),
                "filename": item.filename,
                "content_type": item.content_type,
                "size": item.size,
                "checksum": item.checksum,
                "uploaded_by_name": name(item.uploaded_by),
                "created_at": _iso(item.created_at),
                "download_path": f"{BASE}/{row.id}/attachments/{item.id}",
            }
            for item in attachments
        ],
        "replies": [
            {
                "id": reply.get("id"),
                "note": reply.get("note"),
                "attachment_id": reply.get("attachment_id"),
                "recorded_by_name": name(reply.get("recorded_by")),
                "recorded_at": reply.get("recorded_at"),
            }
            for reply in _supplier_replies(row)
        ],
        "history": [
            {
                "action": event.action,
                "actor_name": name(event.actor_ref),
                "reason": event.reason,
                "status": (event.details or {}).get("status") if isinstance(event.details, dict) else None,
                "created_at": _iso(event.created_at),
            }
            for event in events
        ],
    }


# ---------------------------------------------------------------------------------------------------- the answer


def _for_recipient(db: Session, tenant_id, person: Person, request_id, *, statuses, message: str):
    row = _load(db, tenant_id, request_id, lock=True)
    if request_kind(row.request_kind) != KIND_INTERNAL:
        raise error(409, "SUPPLIER_REQUEST", "A supplier answers by email; record the reply on the supplier request")
    if not is_recipient(person, row):
        raise error(403, "NOT_RECIPIENT", "Only the person or role asked can do this")
    if row.status not in statuses:
        raise _conflict(message)
    _refuse_closed_case(db, tenant_id, row)
    return row


@router.post(BASE + "/{request_id}/acknowledge")
def acknowledge_evidence_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _for_recipient(
        db, tenant_id, person, request_id, statuses={"OPEN"}, message="Only an open request can be acknowledged"
    )
    now = now_utc()
    previous = row.status
    row.status = "ACKNOWLEDGED"
    row.acknowledged_at = now
    row.updated_at = now
    _audit(db, ctx, person, row, "EVIDENCE_REQUEST_ACKNOWLEDGED", now, details={"previous_status": previous})
    db.commit()
    hooks.on_request_acknowledged(db, control_db, row, actor_user_id=person.user_id)
    return _one(db, control_db, tenant_id, person, row)


@router.post(BASE + "/{request_id}/respond")
def respond_to_evidence_request(
    request_id: uuid.UUID,
    payload: RespondPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Answer the request (upload files to it first). The requester is then asked to review the answer."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _for_recipient(
        db,
        tenant_id,
        person,
        request_id,
        statuses=ANSWERABLE_STATUSES,
        message="This request is no longer waiting for an answer",
    )
    now = now_utc()
    previous = row.status
    row.status = "RECEIVED"
    row.response_note = payload.note
    row.responded_at = now
    row.updated_at = now
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUEST_RESPONDED",
        now,
        details={"previous_status": previous, "note_length": len(payload.note)},
    )
    db.commit()
    hooks.on_request_responded(db, control_db, row, actor_user_id=person.user_id)
    return _one(db, control_db, tenant_id, person, row)


@router.post(BASE + "/{request_id}/cannot-provide")
def cannot_provide_evidence(
    request_id: uuid.UUID,
    payload: ReasonPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Say why the evidence cannot be provided. The requester gets a follow-up task."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _for_recipient(
        db,
        tenant_id,
        person,
        request_id,
        statuses=ANSWERABLE_STATUSES,
        message="This request is no longer waiting for an answer",
    )
    now = now_utc()
    previous = row.status
    row.status = "CANNOT_PROVIDE"
    row.cannot_provide_reason = payload.reason
    row.responded_at = now
    row.updated_at = now
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUEST_CANNOT_PROVIDE",
        now,
        reason=payload.reason,
        details={"previous_status": previous},
    )
    db.commit()
    hooks.on_request_cannot_provide(db, control_db, row, actor_user_id=person.user_id)
    return _one(db, control_db, tenant_id, person, row)


@router.post(BASE + "/{request_id}/cancel")
def cancel_evidence_request(
    request_id: uuid.UUID,
    payload: ReasonPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Withdraw a request still waiting for its answer (its requester, or whoever assigns work). Its open tasks are
    cancelled. A supplier is not notified; the request simply stops waiting."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _load(db, tenant_id, request_id, lock=True)
    if not (is_requester(person, row) or person.holds(INVESTIGATION_ASSIGN)):
        raise error(403, "NOT_REQUESTER", "Only the requester or someone who assigns work can cancel a request")
    if row.status not in WAITING_STATUSES:
        raise _conflict("Only a request still waiting for its answer can be cancelled")
    now = now_utc()
    previous = row.status
    row.status = "CANCELLED"
    row.updated_at = now
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUEST_CANCELLED",
        now,
        reason=payload.reason,
        details={"previous_status": previous},
    )
    db.commit()
    hooks.on_request_cancelled(db, control_db, row, actor_user_id=person.user_id, reason=payload.reason)
    return _one(db, control_db, tenant_id, person, row)


# ----------------------------------------------------------------------------------------------------- attachments


def upload_evidence_request_attachment(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Store one file of a request (its requester, or the person or role asked). The checks are those of supplier
    attachments: permitted type, size, the organization's quota, the malware scan, and content matching its type.
    A plain ``def``: the database, the scan and the storage write all block."""
    from object_storage.service import ObjectStorageService

    from backend.app.stage3_workflow_router import (
        ALLOWED_ATTACHMENT_TYPES,
        MAX_ATTACHMENT_BYTES,
        TENANT_ATTACHMENT_QUOTA_BYTES,
        _content_matches_type,
        safe_filename,
    )

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _load(db, tenant_id, request_id)
    if not (is_requester(person, row) or is_recipient(person, row)):
        raise error(403, "NOT_REQUEST_PARTICIPANT", "Only the requester or the person asked can add files")
    if row.status in FINISHED_STATUSES:
        raise _conflict("Files can no longer be added to this request")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise error(415, "UNSUPPORTED_ATTACHMENT_TYPE", "Attachment type is not permitted")
    content = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise error(413, "ATTACHMENT_TOO_LARGE", "Attachment exceeds the permitted size")
    used = int(
        db.query(func.coalesce(func.sum(EvidenceAttachment.size), 0))
        .filter(EvidenceAttachment.tenant_id == tenant_id)
        .scalar()
        or 0
    )
    if used + len(content) > TENANT_ATTACHMENT_QUOTA_BYTES:
        raise error(413, "TENANT_ATTACHMENT_QUOTA_EXCEEDED", "Tenant attachment storage quota exceeded")
    if not ObjectStorageService().scan(content, content_type):
        raise error(422, "MALWARE_SCAN_REJECTED", "Attachment failed the malware safety scan")
    if not _content_matches_type(content, content_type):
        raise error(415, "ATTACHMENT_CONTENT_MISMATCH", "The file content does not match its type")
    filename = safe_filename(file.filename)
    # The stored key never contains the uploaded name, so a name cannot steer where the file is written.
    metadata = ObjectStorageService().put(str(tenant_id), f"{row.id}-{uuid.uuid4().hex}", content)
    now = now_utc()
    attachment = EvidenceAttachment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        request_id=row.id,
        uploaded_by=person.user_id,
        filename=filename,
        content_type=content_type,
        object_key=metadata["object_key"],
        size=metadata["size"],
        checksum=metadata["checksum"],
        created_at=now,
    )
    db.add(attachment)
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUEST_ATTACHMENT_UPLOADED",
        now,
        entity_id=attachment.id,
        details={
            "request_id": str(row.id),
            "filename": attachment.filename,
            "size": attachment.size,
            "checksum": attachment.checksum,
        },
    )
    db.commit()
    return {
        "id": str(attachment.id),
        "request_id": str(row.id),
        "filename": attachment.filename,
        "content_type": content_type,
        "size": metadata["size"],
        "checksum": metadata["checksum"],
        "created_at": _iso(now),
        "download_path": f"{BASE}/{row.id}/attachments/{attachment.id}",
    }


router.add_api_route(
    BASE + "/{request_id}/attachments",
    upload_evidence_request_attachment,
    methods=["POST"],
    route_class_override=_DeclaredSizeLimitedRoute,
)


@router.get(BASE + "/{request_id}/attachments/{attachment_id}")
def download_evidence_request_attachment(
    request_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Download a file of a request: its requester, the person or role asked, or anyone who works on cases."""
    from object_storage.service import ObjectStorageService

    from backend.app.stage3_workflow_router import safe_filename

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _load(db, tenant_id, request_id)
    stored = (
        db.query(EvidenceAttachment)
        .filter(
            EvidenceAttachment.id == attachment_id,
            EvidenceAttachment.request_id == row.id,
            EvidenceAttachment.tenant_id == tenant_id,
        )
        .first()
    )
    if stored is None:
        raise error(404, "ATTACHMENT_NOT_FOUND", "Attachment is not available")
    if not (is_requester(person, row) or is_recipient(person, row) or person.holds(INVESTIGATION_WORK)):
        raise error(
            403, "PERMISSION_DENIED", "Only the people on this request or on its investigation can open its files"
        )
    try:
        content = ObjectStorageService().get(str(tenant_id), stored.object_key)
    except FileNotFoundError as exc:
        raise error(404, "ATTACHMENT_NOT_FOUND", "Attachment is not available") from exc
    return Response(
        content=content,
        media_type=stored.content_type,
        headers={"Content-Disposition": attachment(safe_filename(stored.filename))},
    )


# ---------------------------------------------------------------------------------------------------------- review


def _evidence_identifier(db: Session, tenant_id, business_id: str) -> str:
    taken = {
        value
        for (value,) in db.query(Evidence.evidence_identifier).filter(
            Evidence.tenant_id == tenant_id, Evidence.evidence_identifier.like(f"{business_id}-%")
        )
    }
    number = 1
    while f"{business_id}-{number}" in taken:
        number += 1
    return f"{business_id}-{number}"


@router.post(BASE + "/{request_id}/review")
def review_evidence_request(
    request_id: uuid.UUID,
    payload: RequestReviewPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Review an answered request. Accepting creates evidence of the case from the answer (its text, and its first
    file as the document), linked with the given review status and relationship. Rejecting creates nothing and needs
    a reason. Either way the request is REVIEWED and the requester's review task completes."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    person = current_person(control_db, ctx)
    row = _load(db, tenant_id, request_id, lock=True)
    if not (is_requester(person, row) or person.holds(EVIDENCE_REVIEW)):
        raise error(403, "PERMISSION_DENIED", "Only the requester or an evidence reviewer can review the answer")
    if row.status not in ANSWERED_STATUSES:
        raise _conflict("Only an answered request can be reviewed")
    now = now_utc()
    note, _ = _answer(row)
    if request_kind(row.request_kind) == KIND_SUPPLIER and row.responded_at is None:
        # The supplier flow records replies on the request; the latest one is when the supplier answered.
        replies = _supplier_replies(row)
        if replies and replies[-1].get("recorded_at"):
            try:
                row.responded_at = datetime.fromisoformat(str(replies[-1]["recorded_at"]))
            except ValueError:
                row.responded_at = None
    ev = None
    link = None
    if payload.accept:
        if row.investigation_id is None:
            raise error(
                409,
                "REQUEST_WITHOUT_CASE",
                "This request belongs to no investigation; its answer cannot become evidence",
            )
        case = load_case(db, tenant_id, row.investigation_id, lock=True)
        refuse_closed(case)
        attachments = _attachments(db, tenant_id, row)
        answered_at = row.responded_at or now
        ev = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=_evidence_identifier(db, tenant_id, row.business_id),
            investigation_id=case.id,
            evidence_type=payload.evidence_type or DEFAULT_EVIDENCE_TYPE,
            title=(payload.title or row.title)[:255],
            source_system=EVIDENCE_SOURCE_SYSTEM,
            source_identifier=row.business_id,
            source_reference=f"Evidence request {row.business_id}",
            source_timestamp=answered_at,
            effective_timestamp=answered_at,
            recorded_timestamp=now,
            ingestion_timestamp=now,
            content=note,
            document_ref=attachments[0].object_key if attachments else None,
            fact_type="source_fact",
            created_at=now,
            updated_at=now,
        )
        db.add(ev)
        db.flush()
        link = InvestigationEvidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case.id,
            evidence_id=ev.id,
            created_at=now,
            review_status=payload.review_status,
            relationship=payload.relationship,
            review_reason=payload.reason,
            limitation=payload.limitation,
            reviewed_by=person.user_id,
            reviewed_at=now,
            linked_by=person.user_id,
        )
        db.add(link)
        db.flush()
        source = {"request_id": str(row.id), "request_business_id": row.business_id}
        review_event(
            db,
            tenant_id=tenant_id,
            case_id=case.id,
            evidence_id=ev.id,
            event_type="LINKED",
            actor=person,
            permission=EVIDENCE_REVIEW,
            to_status=UNREVIEWED,
            to_relationship=UNREVIEWED,
            details=source,
            # Stamped a moment before the review, so the history (ordered by time) always lists the link first.
            now=now - timedelta(microseconds=1),
        )
        review_event(
            db,
            tenant_id=tenant_id,
            case_id=case.id,
            evidence_id=ev.id,
            event_type="REVIEWED",
            actor=person,
            permission=EVIDENCE_REVIEW,
            from_status=UNREVIEWED,
            to_status=payload.review_status,
            from_relationship=UNREVIEWED,
            to_relationship=payload.relationship,
            reason=payload.reason,
            details={**source, **({"limitation": payload.limitation} if payload.limitation else {})},
            now=now,
        )
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=person.user_id,
                action="EVIDENCE_REVIEWED",
                entity_type="InvestigationEvidence",
                entity_id=link.id,
                correlation_id=ctx.correlation_id,
                reason=payload.reason,
                new_values={
                    "review_status": payload.review_status,
                    "relationship": payload.relationship,
                    "review_reason": payload.reason,
                    "limitation": payload.limitation,
                },
                details={
                    "investigation_id": str(case.id),
                    "evidence_id": str(ev.id),
                    "actor_role": person.role_for(EVIDENCE_REVIEW),
                    **source,
                },
                created_at=now,
            )
        )
        row.resolved_evidence_id = ev.id
    previous = row.status
    document = _document(row)
    document["review"] = {
        "accepted": bool(payload.accept),
        "reason": payload.reason,
        "reviewed_by": person.user_id,
        "reviewed_at": _iso(now),
    }
    row.requested_items = document
    flag_modified(row, "requested_items")
    row.status = "REVIEWED"
    row.reviewed_by = person.user_id
    row.reviewed_at = now
    row.updated_at = now
    _audit(
        db,
        ctx,
        person,
        row,
        "EVIDENCE_REQUEST_REVIEWED",
        now,
        reason=payload.reason,
        details={
            "previous_status": previous,
            "accepted": bool(payload.accept),
            "evidence_id": str(ev.id) if ev is not None else None,
            "review_status": payload.review_status if payload.accept else None,
            "relationship": payload.relationship if payload.accept else None,
            "actor_role": person.role_for(EVIDENCE_REVIEW),
        },
    )
    db.commit()
    hooks.on_request_reviewed(db, control_db, row, actor_user_id=person.user_id, accepted=bool(payload.accept))
    if ev is not None:
        # An answer accepted as evidence of a decided case asks for an impact assessment. Never blocks or undoes the
        # review (backend/app/decision_followups/impact.py).
        from backend.app.decision_followups.impact import after_late_evidence

        after_late_evidence(
            db,
            control_db,
            tenant_id,
            row.investigation_id,
            [ev.id],
            trigger="EVIDENCE_REQUEST_ACCEPTED",
            actor_ref=person.user_id,
            correlation_id=ctx.correlation_id,
        )
    result = _one(db, control_db, tenant_id, person, row)
    if ev is not None:
        case = load_case(db, tenant_id, row.investigation_id)
        items = inventory_items(db, control_db, tenant_id, case, evidence_ids=[ev.id])
        result["evidence"] = items[0] if items else None
    else:
        result["evidence"] = None
    return result
