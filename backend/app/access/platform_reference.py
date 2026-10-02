"""Platform administration: product configuration, canonical model, mapping impact, AI models and security controls."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    ConnectorConfiguration,
    MasterMapping,
    Product,
    ProductVersion,
    Tenant,
    TenantMappingVersion,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import (
    PlatformProductRequest,
    PlatformProductUpdateRequest,
    PlatformProductVersionRequest,
)
from backend.app.access.authz import _require_platform_admin
from backend.app.access.common import _audit_configuration, _safe_connector_summary

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.get("/platform-admin/api-contract")
def api_contract(request: Request, db: Session = Depends(get_db)):
    """The API contract (OpenAPI) for the platform's API registry.

    The public /openapi.json is switched off in production-like environments; platform administrators still
    need the contract, so it is served here behind the platform-admin check.
    """
    _require_platform_admin(request, db)
    return request.app.openapi()


@router.get("/platform-admin/ai/models")
def get_platform_ai_models(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    from genai.provider import GenAIProvider

    health = GenAIProvider().health()
    return {
        "models": [
            {
                "provider": health.get("provider"),
                "model": health.get("model"),
                "configured": health.get("configured", False),
                "configuration_version": health.get("configuration_version", "genai-config-1"),
                "human_review_required": True,
                "hidden_chain_of_thought_persisted": False,
            }
        ],
        # Free providers used in order when the one before is limited or down (keys are never returned).
        "fallbacks": health.get("fallbacks", []),
        # Named in the setting but unusable (for example a retired service), with the reason.
        "skipped_fallbacks": health.get("skipped_fallbacks", {}),
        "scope": {"secrets_redacted": True},
    }


@router.get("/platform-admin/security/controls")
def get_platform_security_controls(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    return {
        "controls": [
            {"code": "TENANT_AUTHORIZATION", "status": "ENFORCED"},
            {"code": "FIELD_POLICY_FILTERING", "status": "ENFORCED"},
            {"code": "AUDIT_APPEND_ONLY", "status": "ENFORCED"},
            {"code": "SESSION_REVOCATION", "status": "ENFORCED"},
            {"code": "MFA_CRITICAL_OPERATIONS", "status": "ENVIRONMENT_DEPENDENT"},
        ],
        "production_validation": "PENDING",
        "scope": {"platform_authorized": True},
    }


@router.get("/platform-admin/canonical-model")
def get_canonical_model(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    entities = [
        "Product",
        "ProductVersion",
        "Component",
        "Material",
        "Supplier",
        "Site",
        "Lot",
        "Batch",
        "Complaint",
        "QualityEvent",
        "Investigation",
        "Evidence",
        "Observation",
        "Hypothesis",
        "Contradiction",
        "Unknown",
        "Risk",
        "FailureMode",
        "Control",
        "CAPA",
        "FieldAction",
        "Recall",
        "Change",
        "Decision",
        "Approval",
        "Signature",
        "SourceRecord",
        "Provenance",
        "AuditEvent",
    ]
    return {
        "entities": [{"name": name, "governed": True, "raw_schema_editable": False} for name in entities],
        "future_entities_supported": True,
    }


@router.get("/platform-admin/mapping-impact")
def get_mapping_impact(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    mappings = db.query(MasterMapping).order_by(MasterMapping.code).all()
    return {
        "mappings": [
            {
                "id": str(m.id),
                "code": m.code,
                "source_system": m.source_system,
                "target_entity": m.target_entity,
                "status": m.status,
                "released_immutable": m.status == "RELEASED",
            }
            for m in mappings
        ],
        "release_rule": "REVIEW -> VALIDATION -> APPROVAL -> ACTIVATION",
        "silent_propagation": False,
    }


@router.get("/platform/product-configuration/{tenant_id}")
def platform_product_configuration(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Platform-only product, version, connector and mapping configuration view.

    Secrets are never returned; tenant_id is selected only after platform authorization.
    """
    _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer is not available"})
    products = db.query(Product).filter(Product.tenant_id == tenant_id).order_by(Product.name).all()
    versions = (
        db.query(ProductVersion)
        .filter(ProductVersion.tenant_id == tenant_id)
        .order_by(ProductVersion.version_identifier)
        .all()
    )
    connectors = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.tenant_id == tenant_id)
        .order_by(ConnectorConfiguration.code)
        .all()
    )
    mappings = (
        db.query(TenantMappingVersion)
        .filter(TenantMappingVersion.tenant_id == tenant_id)
        .order_by(TenantMappingVersion.created_at.desc())
        .all()
    )
    return {
        "tenant": {"id": str(tenant.id), "tenant_key": tenant.tenant_key, "name": tenant.name, "status": tenant.status},
        "products": [
            {
                "id": str(item.id),
                "identifier": item.product_identifier,
                "name": item.name,
                "status": item.lifecycle_status,
                "family": item.product_family,
                "description": item.description,
                "manufacturer": item.manufacturer_context,
            }
            for item in products
        ],
        "versions": [
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "identifier": item.version_identifier,
                "status": item.lifecycle_status,
                "release_timestamp": item.release_timestamp.isoformat() if item.release_timestamp else None,
            }
            for item in versions
        ],
        "connectors": [_safe_connector_summary(item) for item in connectors],
        "mapping_versions": [
            {
                "id": str(item.id),
                "master_mapping_id": str(item.master_mapping_id),
                "version": item.version,
                "status": item.status,
                "rules": item.rules,
            }
            for item in mappings
        ],
    }


@router.post("/platform/product-configuration/products")
def platform_create_product(payload: PlatformProductRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer is not available"})
    if (
        db.query(Product)
        .filter(Product.tenant_id == payload.tenant_id, Product.product_identifier == payload.product_identifier)
        .first()
    ):
        raise HTTPException(
            409, detail={"code": "PRODUCT_EXISTS", "message": "Product identifier already exists for this tenant"}
        )
    now = datetime.now(timezone.utc)
    row = Product(
        id=uuid.uuid4(),
        tenant_id=payload.tenant_id,
        product_identifier=payload.product_identifier,
        name=payload.name,
        description=payload.description,
        product_family=payload.product_family,
        manufacturer_context=payload.manufacturer_context,
        lifecycle_status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "PLATFORM_PRODUCT_CREATED", "Product", row.id, "v1")
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(payload.tenant_id),
        "product_identifier": row.product_identifier,
        "name": row.name,
        "status": row.lifecycle_status,
    }


@router.patch("/platform/product-configuration/{tenant_id}/products/{product_id}")
def platform_update_product(
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: PlatformProductUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Edit a tenant's product: name, description, family, manufacturer or lifecycle (identifier is fixed)."""
    admin = _require_platform_admin(request, db)
    row = db.query(Product).filter(Product.id == product_id, Product.tenant_id == tenant_id).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product is not available for this tenant"}
        )
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, detail={"code": "NOTHING_TO_CHANGE", "message": "No change was given"})
    before = {field: getattr(row, field) for field in changes}
    for field, value in changes.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(
        db, admin, "PLATFORM_PRODUCT_UPDATED", "Product", row.id, "v1", request=request, before=before, after=changes
    )
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(tenant_id),
        "product_identifier": row.product_identifier,
        "name": row.name,
        "status": row.lifecycle_status,
    }


@router.post("/platform/product-configuration/product-versions")
def platform_create_product_version(
    payload: PlatformProductVersionRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    product = db.query(Product).filter(Product.id == payload.product_id, Product.tenant_id == payload.tenant_id).first()
    if product is None:
        raise HTTPException(
            404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Product is not available for this tenant"}
        )
    if (
        db.query(ProductVersion)
        .filter(
            ProductVersion.tenant_id == payload.tenant_id,
            ProductVersion.product_id == product.id,
            ProductVersion.version_identifier == payload.version_identifier,
        )
        .first()
    ):
        raise HTTPException(409, detail={"code": "PRODUCT_VERSION_EXISTS", "message": "ProductVersion already exists"})
    now = datetime.now(timezone.utc)
    release = (
        datetime.fromisoformat(payload.release_timestamp.replace("Z", "+00:00")) if payload.release_timestamp else None
    )
    row = ProductVersion(
        id=uuid.uuid4(),
        tenant_id=payload.tenant_id,
        product_id=product.id,
        version_identifier=payload.version_identifier,
        description=payload.description,
        lifecycle_status="active",
        release_timestamp=release,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "PLATFORM_PRODUCT_VERSION_CREATED", "ProductVersion", row.id, "v1")
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(payload.tenant_id),
        "product_id": str(row.product_id),
        "version_identifier": row.version_identifier,
        "status": row.lifecycle_status,
    }
