"""Tenant catalog: products, product versions, master mappings, mapping versions and overrides."""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.business_ids import business_id_map
from backend.app.db.models.foundation import (
    MasterMapping,
    Product,
    ProductVersion,
    TenantMappingOverride,
    TenantMappingVersion,
)
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.paging import Page
from backend.app.request_context import get_request_context
from backend.app.access.schemas import (
    AdminUpdateRequest,
    LifecycleRequest,
    MappingOverrideRequest,
    MappingVersionRequest,
    MasterMappingRequest,
    ProductRequest,
    ProductVersionRequest,
    StatusRequest,
)
from backend.app.access.authz import _admin_tenant, _require_platform_admin
from backend.app.access.common import _audit_configuration

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@contextmanager
def _tenant_business(request: Request, db: Session):
    """The signed-in tenant's business data (its data plane, or the control database for a shared plane)."""
    sessions = get_data_plane_db(get_request_context(request, db), db)
    business = next(sessions)
    try:
        yield business
    finally:
        sessions.close()


def _commit(business: Session, db: Session) -> None:
    if business is not db:
        business.commit()
    db.commit()


@router.post("/admin/catalog/products")
def create_product(payload: ProductRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    with _tenant_business(request, db) as business:
        now = datetime.now(timezone.utc)
        if (
            business.query(Product)
            .filter(Product.tenant_id == admin.tenant_id, Product.product_identifier == payload.product_identifier)
            .first()
        ):
            raise HTTPException(
                409, detail={"code": "PRODUCT_EXISTS", "message": "Product identifier already exists for this tenant"}
            )
        row = Product(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            product_identifier=payload.product_identifier,
            name=payload.name,
            description=payload.description,
            product_family=payload.product_family,
            manufacturer_context=payload.manufacturer_context,
            lifecycle_status="active",
            created_at=now,
            updated_at=now,
        )
        business.add(row)
        _audit_configuration(db, admin, "PRODUCT_CREATED", "Product", row.id, "v1")
        _commit(business, db)
        return {
            "id": str(row.id),
            "business_id": row.business_id,
            "product_identifier": row.product_identifier,
            "name": row.name,
            "tenant_id": str(row.tenant_id),
        }


@router.get("/admin/catalog/products")
def list_products(request: Request, response: Response, page: Page = Depends(), db: Session = Depends(get_db)):
    """Return the authenticated tenant's master product catalog and version counts (paged: backend/app/paging.py)."""
    admin = _admin_tenant(request, db)
    with _tenant_business(request, db) as business:
        query = business.query(Product).filter(Product.tenant_id == admin.tenant_id).order_by(Product.name.asc())
        rows = page.apply(query, response)
        # One grouped count for the page's products, not one query per product.
        counts = dict(
            business.query(ProductVersion.product_id, func.count(ProductVersion.id))
            .filter(
                ProductVersion.tenant_id == admin.tenant_id, ProductVersion.product_id.in_([row.id for row in rows])
            )
            .group_by(ProductVersion.product_id)
            .all()
        )
        return [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "tenant_id": str(row.tenant_id),
                "product_identifier": row.product_identifier,
                "name": row.name,
                "description": row.description,
                "product_family": row.product_family,
                "manufacturer_context": row.manufacturer_context,
                "lifecycle_status": row.lifecycle_status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "version_count": counts.get(row.id, 0),
            }
            for row in rows
        ]


@router.get("/admin/catalog/product-versions")
def list_product_versions(
    request: Request,
    response: Response,
    product_id: uuid.UUID | None = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
):
    """Return version history, optionally scoped to one tenant-owned product."""
    admin = _admin_tenant(request, db)
    with _tenant_business(request, db) as business:
        query = business.query(ProductVersion).filter(ProductVersion.tenant_id == admin.tenant_id)
        if product_id is not None:
            query = query.filter(ProductVersion.product_id == product_id)
        rows = page.apply(query.order_by(ProductVersion.version_identifier.asc()), response)
        products = business_id_map(business, Product, (row.product_id for row in rows))
        return [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "tenant_id": str(row.tenant_id),
                "product_id": str(row.product_id),
                "product_business_id": products.get(str(row.product_id)),
                "version_identifier": row.version_identifier,
                "description": row.description,
                "lifecycle_status": row.lifecycle_status,
                "release_timestamp": row.release_timestamp.isoformat() if row.release_timestamp else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]


@router.post("/admin/catalog/product-versions")
def create_product_version(payload: ProductVersionRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    with _tenant_business(request, db) as business:
        now = datetime.now(timezone.utc)
        product = (
            business.query(Product)
            .filter(Product.id == payload.product_id, Product.tenant_id == admin.tenant_id)
            .first()
        )
        if product is None:
            raise HTTPException(
                404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product is not available for this tenant"}
            )
        if (
            business.query(ProductVersion)
            .filter(
                ProductVersion.tenant_id == admin.tenant_id,
                ProductVersion.product_id == product.id,
                ProductVersion.version_identifier == payload.version_identifier,
            )
            .first()
        ):
            raise HTTPException(
                409, detail={"code": "PRODUCT_VERSION_EXISTS", "message": "ProductVersion already exists"}
            )
        release_timestamp = (
            datetime.fromisoformat(payload.release_timestamp.replace("Z", "+00:00"))
            if payload.release_timestamp
            else None
        )
        row = ProductVersion(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            product_id=product.id,
            version_identifier=payload.version_identifier,
            description=payload.description,
            lifecycle_status="active",
            release_timestamp=release_timestamp,
            created_at=now,
            updated_at=now,
        )
        business.add(row)
        _audit_configuration(db, admin, "PRODUCT_VERSION_CREATED", "ProductVersion", row.id, "v1")
        _commit(business, db)
        return {
            "id": str(row.id),
            "business_id": row.business_id,
            "product_id": str(row.product_id),
            "product_business_id": product.business_id,
            "version_identifier": row.version_identifier,
            "tenant_id": str(row.tenant_id),
        }


@router.patch("/admin/catalog/products/{product_id}")
def update_product(product_id: uuid.UUID, payload: AdminUpdateRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    with _tenant_business(request, db) as business:
        allowed = {
            "product_identifier",
            "name",
            "description",
            "product_family",
            "manufacturer_context",
            "lifecycle_status",
        }
        if set(payload.values) - allowed:
            raise HTTPException(422, detail={"code": "FIELD_NOT_ALLOWED", "message": "Product field cannot be edited"})
        row = business.query(Product).filter(Product.id == product_id, Product.tenant_id == admin.tenant_id).first()
        if row is None:
            raise HTTPException(
                404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product is not available for this tenant"}
            )
        for field, value in payload.values.items():
            setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        _audit_configuration(db, admin, "PRODUCT_UPDATED", "Product", row.id, "v1")
        _commit(business, db)
        return {"id": str(row.id), "business_id": row.business_id, "status": row.lifecycle_status}


@router.patch("/admin/catalog/product-versions/{version_id}")
def update_product_version(
    version_id: uuid.UUID, payload: AdminUpdateRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    with _tenant_business(request, db) as business:
        allowed = {"version_identifier", "description", "lifecycle_status", "release_timestamp"}
        if set(payload.values) - allowed:
            raise HTTPException(
                422, detail={"code": "FIELD_NOT_ALLOWED", "message": "ProductVersion field cannot be edited"}
            )
        row = (
            business.query(ProductVersion)
            .filter(ProductVersion.id == version_id, ProductVersion.tenant_id == admin.tenant_id)
            .first()
        )
        if row is None:
            raise HTTPException(
                404,
                detail={
                    "code": "PRODUCT_VERSION_NOT_FOUND",
                    "message": "ProductVersion is not available for this tenant",
                },
            )
        if payload.values.get("release_timestamp"):
            payload.values["release_timestamp"] = datetime.fromisoformat(
                str(payload.values["release_timestamp"]).replace("Z", "+00:00")
            )
        for field, value in payload.values.items():
            setattr(row, field, value)
        row.updated_at = datetime.now(timezone.utc)
        _audit_configuration(db, admin, "PRODUCT_VERSION_UPDATED", "ProductVersion", row.id, "v1")
        _commit(business, db)
        return {"id": str(row.id), "business_id": row.business_id, "status": row.lifecycle_status}


@router.patch("/admin/catalog/products/{product_id}/lifecycle")
def update_product_lifecycle(
    product_id: uuid.UUID, payload: LifecycleRequest, request: Request, db: Session = Depends(get_db)
):
    return update_product(
        product_id, AdminUpdateRequest(values={"lifecycle_status": payload.lifecycle_status}), request, db
    )


@router.patch("/admin/catalog/product-versions/{version_id}/lifecycle")
def update_product_version_lifecycle(
    version_id: uuid.UUID, payload: LifecycleRequest, request: Request, db: Session = Depends(get_db)
):
    return update_product_version(
        version_id, AdminUpdateRequest(values={"lifecycle_status": payload.lifecycle_status}), request, db
    )


@router.post("/admin/catalog/master-mappings")
def create_master_mapping(payload: MasterMappingRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    if db.query(MasterMapping).filter(MasterMapping.code == payload.code).first():
        raise HTTPException(
            409, detail={"code": "MASTER_MAPPING_EXISTS", "message": "Master mapping code already exists"}
        )
    now = datetime.now(timezone.utc)
    row = MasterMapping(
        id=uuid.uuid4(),
        code=payload.code,
        source_system=payload.source_system,
        target_entity=payload.target_entity,
        definition=payload.definition,
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "MASTER_MAPPING_CREATED", "MasterMapping", row.id, "v1")
    db.commit()
    return {
        "id": str(row.id),
        "code": row.code,
        "source_system": row.source_system,
        "target_entity": row.target_entity,
        "status": row.status,
    }


@router.get("/admin/catalog/master-mappings")
def list_master_mappings(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    rows = db.query(MasterMapping).filter(MasterMapping.status != "RETIRED").order_by(MasterMapping.code).all()
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "source_system": row.source_system,
            "target_entity": row.target_entity,
            "definition": row.definition,
            "status": row.status,
        }
        for row in rows
    ]


@router.post("/admin/catalog/mapping-versions")
def create_mapping_version(payload: MappingVersionRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    master = (
        db.query(MasterMapping)
        .filter(MasterMapping.id == payload.master_mapping_id, MasterMapping.status.in_(["ACTIVE", "RELEASED"]))
        .first()
    )
    if master is None:
        raise HTTPException(
            404, detail={"code": "MASTER_MAPPING_NOT_FOUND", "message": "Master mapping is not available"}
        )
    if (
        db.query(TenantMappingVersion)
        .filter_by(tenant_id=admin.tenant_id, master_mapping_id=master.id, version=payload.version)
        .first()
    ):
        raise HTTPException(409, detail={"code": "MAPPING_VERSION_EXISTS", "message": "Mapping version already exists"})
    now = datetime.now(timezone.utc)
    effective = datetime.fromisoformat(payload.effective_from.replace("Z", "+00:00")) if payload.effective_from else now
    row = TenantMappingVersion(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        master_mapping_id=master.id,
        version=payload.version,
        rules=payload.rules,
        status="DRAFT",
        effective_from=effective,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "TENANT_MAPPING_VERSION_CREATED", "TenantMappingVersion", row.id, row.version)
    db.commit()
    return {
        "id": str(row.id),
        "master_mapping_id": str(row.master_mapping_id),
        "version": row.version,
        "status": row.status,
    }


@router.post("/admin/catalog/mapping-overrides")
def create_mapping_override(payload: MappingOverrideRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    version = (
        db.query(TenantMappingVersion)
        .filter(
            TenantMappingVersion.id == payload.mapping_version_id, TenantMappingVersion.tenant_id == admin.tenant_id
        )
        .first()
    )
    if version is None:
        raise HTTPException(
            404,
            detail={"code": "MAPPING_VERSION_NOT_FOUND", "message": "Mapping version is not available for this tenant"},
        )
    protected = {
        "tenant_id",
        "id",
        "created_by",
        "audit_id",
        "provenance_id",
        "mapping_version_id",
        "authorization_metadata",
        "source_identity",
        "external_id",
    }
    if payload.field_name in protected or payload.override_rule.get("override_policy") == "PLATFORM_ONLY":
        raise HTTPException(
            403,
            detail={
                "code": "PLATFORM_ONLY_FIELD",
                "message": "Protected mapping fields cannot be overridden by a tenant",
            },
        )
    row = TenantMappingOverride(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        mapping_version_id=version.id,
        field_name=payload.field_name,
        override_rule=payload.override_rule,
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    _audit_configuration(db, admin, "TENANT_MAPPING_OVERRIDE_CREATED", "TenantMappingOverride", row.id, version.version)
    db.commit()
    return {
        "id": str(row.id),
        "mapping_version_id": str(row.mapping_version_id),
        "field_name": row.field_name,
        "status": row.status,
    }


@router.get("/admin/catalog/mapping-versions")
def list_mapping_versions(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(TenantMappingVersion)
        .filter(TenantMappingVersion.tenant_id == admin.tenant_id)
        .order_by(TenantMappingVersion.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(row.id),
            "master_mapping_id": str(row.master_mapping_id),
            "version": row.version,
            "rules": row.rules,
            "status": row.status,
            "effective_from": row.effective_from,
        }
        for row in rows
    ]


@router.get("/admin/catalog/mapping-overrides")
def list_mapping_overrides(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(TenantMappingOverride)
        .filter(TenantMappingOverride.tenant_id == admin.tenant_id)
        .order_by(TenantMappingOverride.updated_at.desc())
        .all()
    )
    return [
        {
            "id": str(row.id),
            "mapping_version_id": str(row.mapping_version_id),
            "field_name": row.field_name,
            "override_rule": row.override_rule,
            "status": row.status,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.patch("/admin/catalog/master-mappings/{mapping_id}/status")
def update_master_mapping_status(
    mapping_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    row = db.query(MasterMapping).filter(MasterMapping.id == mapping_id).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "MASTER_MAPPING_NOT_FOUND", "message": "Master mapping is not available"}
        )
    if row.status in {"RELEASED", "RETIRED"} and payload.status not in {"RETIRED", "SUPERSEDED"}:
        raise HTTPException(
            409,
            detail={
                "code": "IMMUTABLE_MAPPING_VERSION",
                "message": "Released or retired master mappings cannot be reopened",
            },
        )
    if payload.status == "RELEASED" and row.status not in {"APPROVED", "ACTIVE"}:
        raise HTTPException(
            409, detail={"code": "RELEASE_GATE_BLOCKED", "message": "Master mapping must be approved before release"}
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "MASTER_MAPPING_STATUS_CHANGED", "MasterMapping", row.id, "v1")
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.patch("/admin/catalog/mapping-versions/{version_id}/status")
def update_mapping_version_status(
    version_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(TenantMappingVersion)
        .filter(TenantMappingVersion.id == version_id, TenantMappingVersion.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "MAPPING_VERSION_NOT_FOUND", "message": "Mapping version is not available for this tenant"},
        )
    if row.status == "RELEASED" and payload.status not in {"SUPERSEDED", "RETIRED"}:
        raise HTTPException(
            409, detail={"code": "IMMUTABLE_MAPPING_VERSION", "message": "Released mapping versions are immutable"}
        )
    if payload.status in {"APPROVED", "RELEASED"} and not row.rules:
        raise HTTPException(
            409,
            detail={
                "code": "RELEASE_GATE_BLOCKED",
                "message": "A mapping must contain validated rules before approval or release",
            },
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(
        db, admin, "TENANT_MAPPING_VERSION_STATUS_CHANGED", "TenantMappingVersion", row.id, row.version
    )
    db.commit()
    return {"id": str(row.id), "version": row.version, "status": row.status}


@router.patch("/admin/catalog/mapping-overrides/{override_id}")
def update_mapping_override(
    override_id: uuid.UUID, payload: AdminUpdateRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    allowed = {"field_name", "override_rule", "status"}
    unknown = set(payload.values) - allowed
    if unknown:
        raise HTTPException(
            422,
            detail={"code": "FIELD_NOT_ALLOWED", "message": "Only field_name, override_rule, and status can be edited"},
        )
    row = (
        db.query(TenantMappingOverride)
        .filter(TenantMappingOverride.id == override_id, TenantMappingOverride.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                "code": "MAPPING_OVERRIDE_NOT_FOUND",
                "message": "Mapping override is not available for this tenant",
            },
        )
    for field, value in payload.values.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "TENANT_MAPPING_OVERRIDE_UPDATED", "TenantMappingOverride", row.id, "v1")
    db.commit()
    return {"id": str(row.id), "field_name": row.field_name, "status": row.status}
