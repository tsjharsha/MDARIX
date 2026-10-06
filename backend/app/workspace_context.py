from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Investigation, Product, ProductVersion
from backend.app.db.models.stage2 import MDARIXCaseContext
from backend.app.db.session import get_db
from backend.app.db.data_plane import get_data_plane_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/workspace/context", tags=["Workspace Context"])


class ContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID | None = None
    product_version_id: UUID | None = None
    signal_id: UUID | None = None
    complaint_cluster_id: UUID | None = None
    investigation_id: UUID | None = None
    temporal_mode: str = "CURRENT"
    temporal_cutoff: datetime | None = None
    decision_brief_id: UUID | None = None
    decision_id: UUID | None = None
    last_page: str | None = None


def _row(db, ctx):
    row = (
        db.query(MDARIXCaseContext)
        .filter(MDARIXCaseContext.tenant_id == ctx.tenant_id, MDARIXCaseContext.user_id == ctx.user_id)
        .first()
    )
    if row is None:
        now = datetime.now(timezone.utc)
        row = MDARIXCaseContext(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            membership_id=ctx.membership_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
    return row


def _validate(db, ctx, data):
    """Every record the context names exists in the tenant, and they agree with each other: the version belongs to
    the product and the investigation to the product. When the investigation and the product disagree, the
    investigation wins (the product becomes the investigation's) and a version of another product is cleared."""
    investigation = None
    if data.investigation_id:
        investigation = (
            db.query(Investigation.id, Investigation.product_id)
            .filter(Investigation.id == data.investigation_id, Investigation.tenant_id == ctx.tenant_id)
            .first()
        )
        if investigation is None:
            raise HTTPException(
                404,
                detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Investigation is not available for this tenant"},
            )
        if data.product_id != investigation.product_id:
            data.product_id = investigation.product_id
    if (
        data.product_id
        and not db.query(Product.id).filter(Product.id == data.product_id, Product.tenant_id == ctx.tenant_id).first()
    ):
        raise HTTPException(
            404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product is not available for this tenant"}
        )
    if data.product_version_id:
        version = (
            db.query(ProductVersion.id, ProductVersion.product_id)
            .filter(ProductVersion.id == data.product_version_id, ProductVersion.tenant_id == ctx.tenant_id)
            .first()
        )
        if version is not None and version.product_id != data.product_id and investigation is not None:
            # A version of another product than the case's: the case decides, so the version is dropped.
            data.product_version_id = None
        elif version is None or version.product_id != data.product_id:
            raise HTTPException(
                404,
                detail={
                    "code": "PRODUCT_VERSION_NOT_FOUND",
                    "message": "ProductVersion is not available for this tenant",
                },
            )
    if data.temporal_mode not in {"CURRENT", "EVENT_AS_OF", "KNOWN_AS_OF"}:
        raise HTTPException(422, detail={"code": "INVALID_TEMPORAL_MODE", "message": "Unsupported temporal mode"})


def _business_ids(db, ctx, row) -> dict:
    """The product's and the investigation's numbers as people see them (PRD000003, INV000147), from the data plane."""
    product = (
        db.query(Product.business_id).filter(Product.id == row.product_id, Product.tenant_id == ctx.tenant_id).first()
        if row.product_id
        else None
    )
    investigation = (
        db.query(Investigation.business_id)
        .filter(Investigation.id == row.investigation_id, Investigation.tenant_id == ctx.tenant_id)
        .first()
        if row.investigation_id
        else None
    )
    return {
        "product_business_id": product[0] if product else None,
        "investigation_business_id": investigation[0] if investigation else None,
    }


def _out(row):
    return {
        k: (str(v) if v is not None and k.endswith("_id") else v)
        for k in (
            "id",
            "tenant_id",
            "user_id",
            "membership_id",
            "product_id",
            "product_version_id",
            "signal_id",
            "complaint_cluster_id",
            "investigation_id",
            "temporal_mode",
            "temporal_cutoff",
            "decision_brief_id",
            "decision_id",
            "context_version",
            "last_page",
            "updated_at",
        )
        for v in [getattr(row, k)]
    }


@router.get("")
def get_context(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    return _out(_row(db, ctx))


@router.put("")
def put_context(
    data: ContextUpdate,
    db: Session = Depends(get_db),
    business: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    # The product, version and case live in the tenant's data plane; the saved context in the control plane.
    _validate(business, ctx, data)
    row = _row(db, ctx)
    if data.product_id != row.product_id:
        row.product_version_id = row.signal_id = row.investigation_id = None
    if data.product_version_id != row.product_version_id:
        row.signal_id = row.investigation_id = None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    row.context_version += 1
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {**_out(row), **_business_ids(business, ctx, row)}


@router.get("/resolve")
def resolve_investigation(
    investigation: str = Query(min_length=1, max_length=120),
    business: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The investigation a deep link names (/app/<view>?case=INV000147), by its business id or the customer's own
    identifier, with its product: what the workspace context needs to open it. Only the signed-in tenant's cases."""
    value = investigation.strip()
    match = None
    if value:
        query = business.query(Investigation).filter(Investigation.tenant_id == ctx.tenant_id)
        # Business ids are stored in upper case (INV000147); a link may carry them in any case.
        match = query.filter(Investigation.business_id == value.upper()).first()
        if match is None:
            match = query.filter(Investigation.investigation_identifier == value).first()
    if match is None:
        raise HTTPException(
            404, detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Investigation is not available for this tenant"}
        )
    product = (
        business.query(Product.business_id)
        .filter(Product.id == match.product_id, Product.tenant_id == ctx.tenant_id)
        .first()
    )
    return {
        "investigation_id": str(match.id),
        "investigation_business_id": match.business_id,
        "product_id": str(match.product_id),
        "product_business_id": product[0] if product else None,
    }


@router.post("/reset")
def reset_context(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    row = _row(db, ctx)
    for k in (
        "product_id",
        "product_version_id",
        "signal_id",
        "complaint_cluster_id",
        "investigation_id",
        "temporal_cutoff",
        "decision_brief_id",
        "decision_id",
        "last_page",
    ):
        setattr(row, k, None)
    row.temporal_mode = "CURRENT"
    row.context_version += 1
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _out(row)
