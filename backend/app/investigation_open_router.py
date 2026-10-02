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

from backend.app.access.permissions import RECORDS_WRITE, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Complaint,
    Investigation,
    InvestigationComplaint,
    Product,
)
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations", tags=["Investigations"])


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
    product = db.query(Product).filter(Product.id == payload.product_id, Product.tenant_id == tenant_id).first()
    if product is None:
        raise HTTPException(404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Not found in your organization"})
    complaint_ids = list(dict.fromkeys(payload.complaint_ids))
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
    identifier = payload.investigation_identifier or f"INV-{now:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    taken = (
        db.query(Investigation.id)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == identifier)
        .first()
    )
    if taken is not None:
        raise HTTPException(
            409, detail={"code": "INVESTIGATION_EXISTS", "message": f"An investigation {identifier} already exists"}
        )
    owner = None
    if payload.assign_to_me:
        user = control_db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(ctx.user_id)).first()
        owner = user[0] if user else None
    investigation = Investigation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        product_id=product.id,
        investigation_identifier=identifier,
        investigation_question=payload.investigation_question.strip(),
        status="open",
        opened_at=now,
        owner_ref=owner,
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
            actor_ref=ctx.user_id,
            action="INVESTIGATION_OPENED",
            entity_type="Investigation",
            entity_id=investigation.id,
            details={"identifier": identifier, "product": product.product_identifier, "complaints": len(complaint_ids)},
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(investigation.id),
        "investigation_identifier": identifier,
        "product_id": str(product.id),
        "status": investigation.status,
        "owner_ref": owner,
        "complaints_linked": len(complaint_ids),
    }
