"""Governance configuration: approval authorities, segregation-of-duties policies, entitlements."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    ApprovalAuthority,
    FeatureEntitlement,
    PlanDefinition,
    SegregationOfDutiesPolicy,
    TenantPlanAssignment,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import AuthorityRequest, SodRequest, StatusRequest
from backend.app.access.authz import _admin_tenant
from backend.app.access.common import _audit_configuration
from backend.app.role_codes import is_administrator_role

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


def _refuse_administrator_authority(role_name: str | None) -> None:
    """Administrators manage people and settings; they never approve (separation of duties). Signing refuses them
    whatever authority exists (governance_router.approval_denial); this keeps such an authority from being made."""
    if is_administrator_role(role_name):
        raise HTTPException(
            422,
            detail={"code": "ROLE_CANNOT_APPROVE", "message": "Administrator roles cannot hold approval authority"},
        )


@router.post("/admin/governance/approval-authorities")
def create_authority(payload: AuthorityRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    _refuse_administrator_authority(payload.role_name)
    now = datetime.now(timezone.utc)
    row = ApprovalAuthority(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        role_name=payload.role_name,
        object_type=payload.object_type,
        decision_type=payload.decision_type,
        scope={},
        authority=payload.authority,
        version=payload.version,
        status="DRAFT",
        effective_from=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "APPROVAL_AUTHORITY_CREATED", "ApprovalAuthority", row.id, row.version)
    db.commit()
    return {"authority_id": str(row.id), "tenant_id": str(admin.tenant_id), "status": row.status}


@router.post("/admin/governance/sod-policies")
def create_sod(payload: SodRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    now = datetime.now(timezone.utc)
    row = SegregationOfDutiesPolicy(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        name=payload.name,
        object_type=payload.object_type,
        decision_type=payload.decision_type,
        creator_cannot_approve=payload.creator_cannot_approve,
        last_material_editor_cannot_approve=payload.last_material_editor_cannot_approve,
        version=payload.version,
        status="DRAFT",
        effective_from=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit_configuration(db, admin, "SOD_POLICY_CREATED", "SegregationOfDutiesPolicy", row.id, row.version)
    db.commit()
    return {"policy_id": str(row.id), "tenant_id": str(admin.tenant_id), "status": row.status}


@router.get("/admin/governance/policies")
def governance_policies(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    authorities = db.query(ApprovalAuthority).filter(ApprovalAuthority.tenant_id == admin.tenant_id).all()
    sod = db.query(SegregationOfDutiesPolicy).filter(SegregationOfDutiesPolicy.tenant_id == admin.tenant_id).all()
    return {
        "approval_authorities": [
            {
                "id": str(row.id),
                "role_name": row.role_name,
                "object_type": row.object_type,
                "decision_type": row.decision_type,
                "authority": row.authority,
                "version": row.version,
                "status": row.status,
            }
            for row in authorities
        ],
        "sod_policies": [
            {
                "id": str(row.id),
                "name": row.name,
                "object_type": row.object_type,
                "decision_type": row.decision_type,
                "creator_cannot_approve": row.creator_cannot_approve,
                "last_material_editor_cannot_approve": row.last_material_editor_cannot_approve,
                "version": row.version,
                "status": row.status,
            }
            for row in sod
        ],
    }


@router.get("/admin/governance/entitlements")
def tenant_entitlements(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(FeatureEntitlement)
        .join(PlanDefinition, PlanDefinition.id == FeatureEntitlement.plan_id)
        .join(TenantPlanAssignment, TenantPlanAssignment.plan_id == PlanDefinition.id)
        .filter(TenantPlanAssignment.tenant_id == admin.tenant_id)
        .all()
    )
    return [
        {
            "feature": row.feature_code,
            "enabled": row.enabled,
            "limits": row.limits or {},
            "plan_id": str(row.plan_id),
            "status": row.status,
        }
        for row in rows
    ]


@router.patch("/admin/governance/policies/{policy_type}/{policy_id}/status")
def activate_policy(
    policy_type: str, policy_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    model, entity = (
        {
            "authority": (ApprovalAuthority, "ApprovalAuthority"),
            "sod": (SegregationOfDutiesPolicy, "SegregationOfDutiesPolicy"),
        }
    ).get(policy_type, (None, None))
    if model is None:
        raise HTTPException(
            422, detail={"code": "POLICY_TYPE_INVALID", "message": "Policy type must be authority or sod"}
        )
    row = db.query(model).filter(model.id == policy_id, model.tenant_id == admin.tenant_id).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "POLICY_NOT_FOUND", "message": "Policy is not available for this tenant"}
        )
    if model is ApprovalAuthority and str(payload.status).upper() == "ACTIVE":
        _refuse_administrator_authority(row.role_name)
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "GOVERNANCE_POLICY_STATUS_CHANGED", entity, row.id, row.version)
    db.commit()
    return {"id": str(row.id), "policy_type": policy_type, "status": row.status, "version": row.version}
