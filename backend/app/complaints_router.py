"""The organization's complaints, across every product: search, filter by product, status, product version, lot,
problem code, country and source, page through."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
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
    """What the list's filters offer: the problem codes, countries, product versions and sources the complaints
    record. The sources tell a free trial's own imported complaints from the sample's (DEV-017)."""

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
        "sources": distinct(Complaint.source_system),
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
    # The new navigation's list (0.10.68): each complaint's owner, stage, deadlines and markets, as its page shows them.
    work: bool = Query(False),
    # A list view of the new navigation (0.10.74, C2): open, due-week, legal-week, reportability, waiting-reporter,
    # my-approval or signed-month (backend/app/oversight/router.py LIST_VIEWS).
    view: str = Query("", max_length=40),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
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
                # The customer's own references for the same complaint (0.10.85, D3.11): its service ticket, serial
                # number and UDI.
                func.lower(Complaint.service_reference).like(pattern, escape="\\"),
                func.lower(Complaint.serial_number).like(pattern, escape="\\"),
                func.lower(Complaint.udi).like(pattern, escape="\\"),
            )
        )
    default = [RECEIVED_AT.desc().nullslast()]
    reads = None
    if view:
        from backend.app.oversight import closure
        from backend.app.oversight import service as oversight
        from backend.app.oversight.router import LIST_VIEWS, dated_reads, list_view, urgency

        if view not in LIST_VIEWS:
            raise HTTPException(status_code=422, detail={"code": "UNKNOWN_LIST_VIEW", "message": "No such list view"})
        # The dates every view, its order and its work columns read, read once (0.10.85, D3.13).
        reads = dated_reads(db, control_db, tenant_id, oversight.now_utc())
        places = urgency(reads)
        if view == "open":
            query = query.filter(
                or_(Complaint.status.is_(None), func.lower(Complaint.status).notin_(closure.CLOSED_STATUSES))
            )
            ranked = list(places)
        else:
            moments = list_view(db, control_db, tenant_id, view, str(ctx.user_id), reads)
            query = query.filter(Complaint.id.in_([uuid.UUID(key) for key in moments] or [None]))
            # The view's own moment breaks a tie (the newest signature first for "signed-month").
            ranked = sorted(moments, key=lambda key: moments[key] or "~", reverse=view == "signed-month")
        # Every view, the most urgent first (0.10.85, D3.1): overdue, then the nearest legal deadline, then the
        # nearest other date; the undated after, newest first.
        ranked.sort(key=lambda key: places.get(key, (2, "~", "~")))
        if ranked:
            rank = case({uuid.UUID(key): index for index, key in enumerate(ranked)}, value=Complaint.id)
            default = [rank.asc().nullslast(), *default]
    total = query.count()
    # Newest first (a list view: its own order) unless a column heading asks for another order across every page.
    ordered = order_query(query, sort, order, _sorts(), default=default, tiebreak=[Complaint.id])
    rows = ordered.offset((page - 1) * page_size).limit(page_size).all()
    ids = [complaint.id for complaint, *_ in rows]
    if work:
        from backend.app.oversight.router import complaint_work

        worked = complaint_work(db, control_db, tenant_id, [complaint for complaint, *_ in rows], reads)
    else:
        worked = {}
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
                **({"work": worked[str(complaint.id)]} if work else {}),
            }
            for complaint, product_identifier, product_name, version, product_business_id in rows
        ],
    }
