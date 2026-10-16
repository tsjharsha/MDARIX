"""The organization's complaints, across every product: search, filter by product, status, product version, lot,
problem code, country and source, page through."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Complaint, InvestigationComplaint, LotBatch, Product, ProductVersion
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.sorting import order_query

router = APIRouter(prefix="/api/v1/complaints", tags=["Complaints"])


def _like(text: str) -> str:
    """A LIKE pattern that matches the text literally (the user's % and _ are not wildcards)."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


RECEIVED_AT = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp)
# The most values each filter's list offers (the problem codes, countries and versions recorded on complaints).
FACET_MAX = 200


def _uuid(text: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def _facets(db: Session, tenant_id: uuid.UUID) -> dict:
    """What the list's filters offer: the problem codes, countries and product versions the complaints record."""

    def distinct(column) -> list[str]:
        return [
            row[0]
            for row in db.query(column)
            .filter(Complaint.tenant_id == tenant_id, column.is_not(None), column != "")
            .distinct()
            .order_by(column)
            .limit(FACET_MAX)
        ]

    has_complaint = exists().where(
        Complaint.tenant_id == ProductVersion.tenant_id, Complaint.product_version_id == ProductVersion.id
    )
    versions = (
        db.query(
            ProductVersion.id, ProductVersion.business_id, ProductVersion.version_identifier, Product.id, Product.name
        )
        .join(Product, (Product.id == ProductVersion.product_id) & (Product.tenant_id == ProductVersion.tenant_id))
        .filter(ProductVersion.tenant_id == tenant_id, has_complaint)
        .order_by(Product.name, ProductVersion.version_identifier)
        .limit(FACET_MAX)
        .all()
    )
    return {
        "problem_codes": distinct(Complaint.problem_code),
        "countries": distinct(Complaint.country),
        "versions": [
            {
                "id": str(version_id),
                "business_id": business_id,
                "product_id": str(product_id),
                "label": f"{product_name} {identifier}",
            }
            for version_id, business_id, identifier, product_id, product_name in versions
        ],
    }


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
    # A product version by its MDARIX ID (or its id), a lot by its number (or MDARIX ID), a problem code and a country
    # as recorded (any case), and the system the complaints came from (Getting started's insights read one source).
    version: str = Query("", max_length=120),
    lot: str = Query("", max_length=120),
    problem_code: str = Query("", max_length=120),
    country: str = Query("", max_length=80),
    source_system: str = Query("", max_length=120),
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
    if version.strip():
        # The joined version is the tenant's own (the join matches on tenant), so another tenant's never matches.
        value = version.strip()
        version_id = _uuid(value)
        query = query.filter(
            or_(ProductVersion.business_id == value, ProductVersion.id == version_id)
            if version_id
            else ProductVersion.business_id == value
        )
    if lot.strip():
        value = lot.strip()
        lots = select(LotBatch.id).where(
            LotBatch.tenant_id == tenant_id,
            or_(func.lower(LotBatch.lot_identifier) == value.lower(), LotBatch.business_id == value),
        )
        query = query.filter(Complaint.lot_batch_id.in_(lots))
    if problem_code.strip():
        query = query.filter(func.lower(Complaint.problem_code) == problem_code.strip().lower())
    if country.strip():
        query = query.filter(func.lower(Complaint.country) == country.strip().lower())
    if source_system.strip():
        query = query.filter(Complaint.source_system == source_system.strip())
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
    lot_ids = {complaint.lot_batch_id for complaint, *_ in rows if complaint.lot_batch_id}
    lot_numbers = (
        dict(
            db.query(LotBatch.id, LotBatch.lot_identifier)
            .filter(LotBatch.tenant_id == tenant_id, LotBatch.id.in_(lot_ids))
            .all()
        )
        if lot_ids
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
        **_facets(db, tenant_id),
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
                "lot": lot_numbers.get(complaint.lot_batch_id),
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
