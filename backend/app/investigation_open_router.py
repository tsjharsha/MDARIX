"""Opening an investigation: the first step of the quality workflow for a tenant's own products and complaints.

Investigators (and anyone who may change records) open a case for one of their products, with the question it
must answer and, optionally, the complaints that prompted it. Everything is checked against the signed-in tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.permissions import RECORDS_WRITE, permissions_for_roles, require_permission, roles_of_user
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Complaint,
    Decision,
    Investigation,
    InvestigationComplaint,
    Product,
)
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations", tags=["Investigations"])
assignees_router = APIRouter(prefix="/api/v1/investigation-assignees", tags=["Investigations"])
# A decision still waiting for its human review keeps the case open.
DECISIONS_AWAITING_REVIEW = ("REQUIRES_REVIEW",)


class OpenInvestigationRequest(BaseModel):
    product_id: uuid.UUID
    investigation_question: str = Field(min_length=10, max_length=2000)
    complaint_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    investigation_identifier: str | None = Field(
        default=None, min_length=3, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
    )
    assign_to_me: bool = True


@router.post("", status_code=201, dependencies=[Depends(require_permission(RECORDS_WRITE))])
def open_investigation(
    payload: OpenInvestigationRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    owner = None
    if payload.assign_to_me:
        user = control_db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(ctx.user_id)).first()
        owner = user[0] if user else None
    investigation, product, complaint_ids = open_case(
        db,
        tenant_id,
        actor_ref=ctx.user_id,
        product_id=payload.product_id,
        investigation_question=payload.investigation_question,
        complaint_ids=payload.complaint_ids,
        investigation_identifier=payload.investigation_identifier,
        owner_ref=owner,
    )
    db.commit()
    result = {
        "id": str(investigation.id),
        "business_id": investigation.business_id,
        "investigation_identifier": investigation.investigation_identifier,
        "product_id": str(product.id),
        "product_business_id": product.business_id,
        "status": investigation.status,
        "owner_ref": owner,
        "complaints_linked": len(complaint_ids),
    }
    # The case's first task: the opener's (accepted) when they own it, else the investigators' queue. Saved after the
    # case; a failure is logged and never undoes it (backend/app/workflow/hooks.py).
    from backend.app.workflow.hooks import on_investigation_opened

    on_investigation_opened(
        db, control_db, investigation, actor_user_id=ctx.user_id, owner_user_id=ctx.user_id if owner else None
    )
    return result


def open_case(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    actor_ref: str,
    product_id,
    investigation_question: str,
    complaint_ids,
    investigation_identifier: str | None = None,
    owner_ref: str | None = None,
) -> tuple[Investigation, Product, list]:
    """Open a case for one of the tenant's products: checks the product and the complaints (all of that product),
    the identifier (generated when none is given; refused when taken), then writes the investigation, its complaint
    links and the INVESTIGATION_OPENED audit event. Shared by ``POST /api/v1/investigations`` and opening a case from
    a signal (backend/app/signals/router.py). Raises HTTPException when a check fails. Does not commit."""
    product = db.query(Product).filter(Product.id == product_id, Product.tenant_id == tenant_id).first()
    if product is None:
        raise HTTPException(404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Not found in your organization"})
    complaint_ids = list(dict.fromkeys(complaint_ids or []))
    if complaint_ids:
        found = {
            row[0]
            for row in db.query(Complaint.id).filter(
                Complaint.tenant_id == tenant_id,
                Complaint.product_id == product.id,
                Complaint.id.in_(complaint_ids),
            )
        }
        if len(found) != len(complaint_ids):
            raise HTTPException(
                422,
                detail={
                    "code": "COMPLAINT_NOT_FOR_PRODUCT",
                    "message": "Every complaint must belong to this product in your organization",
                },
            )
    now = datetime.now(timezone.utc)
    identifier = investigation_identifier or f"INV-{now:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    taken = (
        db.query(Investigation.id)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == identifier)
        .first()
    )
    if taken is not None:
        raise HTTPException(
            409, detail={"code": "INVESTIGATION_EXISTS", "message": f"An investigation {identifier} already exists"}
        )
    investigation = Investigation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        product_id=product.id,
        investigation_identifier=identifier,
        investigation_question=investigation_question.strip(),
        status="open",
        opened_at=now,
        owner_ref=owner_ref,
        source_system="MDARIX",
        source_identifier=identifier,
        source_timestamp=now,
        effective_timestamp=now,
        recorded_timestamp=now,
        ingestion_timestamp=now,
        created_at=now,
        updated_at=now,
    )
    db.add(investigation)
    db.flush()
    for complaint_id in complaint_ids:
        db.add(
            InvestigationComplaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                investigation_id=investigation.id,
                complaint_id=complaint_id,
                created_at=now,
            )
        )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="INVESTIGATION_OPENED",
            entity_type="Investigation",
            entity_id=investigation.id,
            details={"identifier": identifier, "product": product.product_identifier, "complaints": len(complaint_ids)},
            created_at=now,
        )
    )
    return investigation, product, complaint_ids


def _can_work_cases(db: Session, user: AuthUser) -> bool:
    return RECORDS_WRITE in permissions_for_roles(roles_of_user(db, user))


@assignees_router.get("")
def list_assignees(
    control_db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    """Colleagues a case can be assigned to: active people in this organization whose role may work on cases.
    Names only (and the internal id to choose by), no contact details."""
    people = (
        control_db.query(AuthUser)
        .filter(AuthUser.tenant_id == uuid.UUID(ctx.tenant_id), AuthUser.status == "ACTIVE")
        .order_by(AuthUser.display_name)
        .all()
    )
    from backend.app.access.authz import _is_platform_role

    return [
        {"id": str(person.id), "business_id": person.business_id, "display_name": person.display_name}
        for person in people
        if not _is_platform_role(person.role) and _can_work_cases(control_db, person)
    ]


class ManageInvestigationRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    investigation_question: str | None = Field(default=None, min_length=10, max_length=2000)
    assignee_id: uuid.UUID | None = None
    unassign: bool = False
    status: str | None = Field(default=None, pattern="^(open|closed)$")


@router.patch("/{investigation_id}", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def manage_investigation(
    investigation_id: uuid.UUID,
    payload: ManageInvestigationRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Edit the question, assign or unassign, close or reopen a case. Every change needs a reason and is audited.

    A closed case can only be reopened; it cannot be closed while one of its decisions still awaits review.
    """
    tenant_id = uuid.UUID(ctx.tenant_id)
    case = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if case is None:
        raise HTTPException(404, detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Investigation not found"})
    current = str(case.status or "").lower()
    closed = current == "closed"
    changes_content = payload.investigation_question is not None or payload.assignee_id is not None or payload.unassign
    if closed and (changes_content or payload.status != "open"):
        raise HTTPException(
            409, detail={"code": "INVESTIGATION_CLOSED", "message": "This investigation is closed; reopen it first"}
        )
    if payload.assignee_id is not None and payload.unassign:
        raise HTTPException(422, detail={"code": "ASSIGNMENT_CONFLICT", "message": "Assign or unassign, not both"})
    if not changes_content and payload.status in (None, current):
        raise HTTPException(422, detail={"code": "NOTHING_TO_CHANGE", "message": "Nothing to change"})
    before = {"question": case.investigation_question, "owner": case.owner_ref, "status": case.status}
    now = datetime.now(timezone.utc)
    if payload.investigation_question is not None:
        case.investigation_question = payload.investigation_question.strip()
    if payload.assignee_id is not None:
        person = (
            control_db.query(AuthUser)
            .filter(AuthUser.id == payload.assignee_id, AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE")
            .first()
        )
        from backend.app.access.authz import _is_platform_role

        if person is None or _is_platform_role(person.role) or not _can_work_cases(control_db, person):
            raise HTTPException(
                422,
                detail={
                    "code": "ASSIGNEE_NOT_ELIGIBLE",
                    "message": "Assign the case to an active colleague whose role may work on cases",
                },
            )
        case.owner_ref = person.username
    if payload.unassign:
        case.owner_ref = None
    if payload.status == "closed" and not closed:
        waiting = (
            db.query(Decision.id)
            .filter(
                Decision.tenant_id == tenant_id,
                Decision.investigation_id == case.id,
                Decision.decision_status.in_(DECISIONS_AWAITING_REVIEW),
            )
            .first()
        )
        if waiting is not None:
            raise HTTPException(
                409,
                detail={
                    "code": "DECISIONS_AWAITING_REVIEW",
                    "message": "A decision on this case still awaits its human review; finish it before closing",
                },
            )
        case.status = "closed"
        case.closed_at = now
    elif payload.status == "open" and closed:
        case.status = "open"
        case.closed_at = None
    case.updated_at = now
    after = {"question": case.investigation_question, "owner": case.owner_ref, "status": case.status}
    action = (
        "INVESTIGATION_CLOSED"
        if after["status"] != before["status"] and after["status"] == "closed"
        else "INVESTIGATION_REOPENED"
        if after["status"] != before["status"]
        else "INVESTIGATION_UPDATED"
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Investigation",
            entity_id=case.id,
            reason=payload.reason,
            old_values={key: value for key, value in before.items() if before[key] != after[key]},
            new_values={key: value for key, value in after.items() if before[key] != after[key]},
            created_at=now,
        )
    )
    db.commit()
    if case.owner_ref and case.owner_ref != before["owner"]:
        # Tell the new owner (not someone who assigned themselves). Queued after the change is saved, on the control
        # database where the outbox lives; a queueing failure is logged and never undoes the assignment.
        from backend.app.governance_router import _notify

        if _notify(
            "notify_assignment",
            control_db,
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            assignee_ref=case.owner_ref,
            assigned_by_user_id=str(ctx.user_id),
            reference=case.business_id,
            investigation_business_id=case.business_id,
        ):
            control_db.commit()
    result = {
        "id": str(case.id),
        "business_id": case.business_id,
        "investigation_identifier": case.investigation_identifier,
        "investigation_question": case.investigation_question,
        "owner_ref": case.owner_ref,
        "status": case.status,
        "closed_at": case.closed_at.isoformat() if case.closed_at else None,
    }
    # The case's tasks follow it: a new owner (or none) replaces its open task, closing cancels every open task,
    # reopening adds one. Saved after the change; a failure is logged and never undoes it.
    from backend.app.workflow.hooks import on_investigation_managed

    on_investigation_managed(
        db,
        control_db,
        case,
        actor_user_id=ctx.user_id,
        before_owner=before["owner"],
        before_status=before["status"],
        assignee_user_id=payload.assignee_id,
    )
    # Signals the case was opened for follow it: closed when all their cases are closed, open again when it reopens.
    # Saved after the change; a failure is logged and never undoes it (backend/app/signals/hooks.py).
    from backend.app.signals.hooks import on_investigation_status_changed

    on_investigation_status_changed(db, control_db, case, actor_user_id=ctx.user_id, before_status=before["status"])
    return result
