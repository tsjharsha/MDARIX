"""The organization's complaints, across every product: search, filter by product and status, page through."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Complaint, InvestigationComplaint, Product, ProductVersion
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.sorting import order_query

router = APIRouter(prefix="/api/v1/complaints", tags=["Complaints"])


def _like(text: str) -> str:
    """A LIKE pattern that matches the text literally (the user's % and _ are not wildcards)."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


RECEIVED_AT = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp)


def _sorts() -> dict:
    """What each column of the complaint list sorts on (``sort``/``order``)."""
    cases = (
        select(func.count(InvestigationComplaint.id))
        .where(
            InvestigationComplaint.tenant_id == Complaint.tenant_id,
            InvestigationComplaint.complaint_id == Complaint.id,
        )
        .scalar_subquery()
    )
    return {
        "business_id": [func.coalesce(Complaint.business_id, Complaint.complaint_identifier)],
        "complaint_identifier": [Complaint.complaint_identifier],
        "product": [Product.name, ProductVersion.version_identifier],
        "description": [Complaint.description],
        "received": [RECEIVED_AT],
        "severity": [Complaint.severity],
        "status": [Complaint.status],
        "cases": [cases],
    }


@router.get("")
def list_complaints(
    q: str = Query("", max_length=120),
    product_id: uuid.UUID | None = None,
    status: str = Query("", max_length=40),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(50, ge=1, le=200),
    sort: str | None = Query(None, max_length=60),
    order: str | None = Query(None, max_length=10),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    query = (
        db.query(
            Complaint, Product.product_identifier, Product.name, ProductVersion.version_identifier, Product.business_id
        )
        .join(Product, (Product.id == Complaint.product_id) & (Product.tenant_id == Complaint.tenant_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.id == Complaint.product_version_id) & (ProductVersion.tenant_id == Complaint.tenant_id),
        )
        .filter(Complaint.tenant_id == tenant_id)
    )
    if product_id:
        query = query.filter(Complaint.product_id == product_id)
    if status.strip():
        query = query.filter(func.lower(Complaint.status) == status.strip().lower())
    if q.strip():
        pattern = _like(q.strip())
        query = query.filter(
            or_(
                func.lower(Complaint.complaint_identifier).like(pattern, escape="\\"),
                func.lower(Complaint.business_id).like(pattern, escape="\\"),
                func.lower(Complaint.description).like(pattern, escape="\\"),
            )
        )
    total = query.count()
    # Newest first unless a column heading asks for another order (``sort``/``order``) across every page.
    ordered = order_query(
        query, sort, order, _sorts(), default=[RECEIVED_AT.desc().nullslast()], tiebreak=[Complaint.id]
    )
    rows = ordered.offset((page - 1) * page_size).limit(page_size).all()
    ids = [complaint.id for complaint, *_ in rows]
    linked = (
        dict(
            db.query(InvestigationComplaint.complaint_id, func.count(InvestigationComplaint.id))
            .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id.in_(ids))
            .group_by(InvestigationComplaint.complaint_id)
            .all()
        )
        if ids
        else {}
    )
    statuses = [
        row[0]
        for row in db.query(func.lower(Complaint.status))
        .filter(Complaint.tenant_id == tenant_id, Complaint.status.is_not(None))
        .distinct()
        .order_by(func.lower(Complaint.status))
    ]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "statuses": statuses,
        "items": [
            {
                "id": str(complaint.id),
                "business_id": complaint.business_id,
                "complaint_identifier": complaint.complaint_identifier,
                "product_id": str(complaint.product_id),
                "product_business_id": product_business_id,
                "product_identifier": product_identifier,
                "product_name": product_name,
                "version": version,
                "status": complaint.status,
                "description": complaint.description,
                "event_date": complaint.event_timestamp.isoformat() if complaint.event_timestamp else None,
                "received_date": complaint.complaint_timestamp.isoformat() if complaint.complaint_timestamp else None,
                "source_system": complaint.source_system,
                "investigations": int(linked.get(complaint.id, 0)),
                # Regulatory details recorded by the quality system (offered in the list's column chooser).
                "severity": complaint.severity,
                "country": complaint.country,
                "complaint_type": complaint.complaint_type,
                "problem_code": complaint.problem_code,
                "serial_number": complaint.serial_number,
                "udi": complaint.udi,
                "awareness_date": complaint.awareness_timestamp.isoformat() if complaint.awareness_timestamp else None,
                "device_returned": complaint.device_returned,
                "patient_involved": complaint.patient_involved,
                "serious_injury": complaint.serious_injury,
                "death": complaint.death,
                "malfunction": complaint.malfunction,
            }
            for complaint, product_identifier, product_name, version, product_business_id in rows
        ],
    }
