import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.service import _verify
from backend.app.db.models.foundation import (
    ApprovalAuthority,
    AuthUser,
    Decision,
    FeatureEntitlement,
    PlanDefinition,
    SegregationOfDutiesPolicy,
    SignedApprovalRecord,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.db.models.stage3 import ContextSnapshot
from backend.app.db.session import get_db
from backend.app.db.data_plane import get_data_plane_db
from backend.app.enterprise_audit import change_diff
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.access.permissions import RECORDS_WRITE, require_permission

router = APIRouter(prefix="/api/v1/governance", tags=["Enterprise Governance"])
FEATURE = "DECISION_CENTER_SIGNATURES"
ASK_FEATURE = "ASK_MDARIX"
NOW = lambda: datetime.now(timezone.utc)


class SignatureRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    remarks: str = Field(min_length=1, max_length=4000)
    password: str = Field(min_length=1, max_length=128)
    object_version: str
    mfa_code: str | None = Field(default=None, min_length=6, max_length=12)


class MaterialChangeRequest(BaseModel):
    change_summary: str = Field(min_length=1, max_length=2000)
    expected_updated_at: str


def audit(
    db, tenant, actor, action, entity_id, details=None, request=None, reason=None, old_values=None, new_values=None
):
    from backend.app.enterprise_audit import make_audit_event

    db.add(
        make_audit_event(
            tenant_id=tenant.id,
            actor_ref=actor,
            action=action,
            entity_type="Decision",
            entity_id=entity_id,
            details=details or {},
            request=request,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
        )
    )


# The demo bootstrap grants decision approval to this role only. Read-only roles never receive it by default.
DEFAULT_APPROVER_ROLE = "Approver"
# Roles that may approve and sign investigation decisions in every tenant unless the tenant changes its rules.
DEFAULT_APPROVAL_ROLES = ("APPROVER", "LEADER")


def approval_denial(db, tenant_id, role_name: str, decision, user_id: str) -> tuple[str, str] | None:
    """Why this user may not approve this decision, or None when they may.

    Shared by signing and by review approval so both enforce the same rules:
    an ACTIVE approval authority for the user's role, and segregation of duties (no self-approval).
    """
    from backend.app.access.permissions import normalize_role

    # Role names are compared the way permissions are ('Approver' == 'APPROVER'), so a rule written in any case
    # matches the role stored on the account.
    wanted = normalize_role(role_name)
    authority = next(
        (
            row
            for row in db.query(ApprovalAuthority).filter_by(
                tenant_id=tenant_id,
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                authority="AUTHORIZED",
                status="ACTIVE",
            )
            if wanted and normalize_role(row.role_name) == wanted
        ),
        None,
    )
    if not authority:
        return "APPROVAL_AUTHORITY_DENIED", "Active role lacks approval authority"
    sod = (
        db.query(SegregationOfDutiesPolicy)
        .filter_by(tenant_id=tenant_id, object_type="Decision", decision_type="INVESTIGATION_REVIEW", status="ACTIVE")
        .first()
    )
    if sod and sod.creator_cannot_approve and str(decision.authorized_by_ref) == str(user_id):
        return "SOD_DENIED", "Approval by another authorized user is required"
    return None


def ensure_governance_defaults(db, tenant) -> None:
    """Every tenant's starting rules for decisions: Approvers and Leaders may approve and sign, and nobody may
    approve their own decision. Only what is missing is added, so a tenant's own changes are kept."""
    now = NOW()
    from backend.app.access.permissions import normalize_role

    existing = {
        normalize_role(row.role_name)
        for row in db.query(ApprovalAuthority).filter_by(
            tenant_id=tenant.id, object_type="Decision", decision_type="INVESTIGATION_REVIEW"
        )
    }
    changed = False
    for role in DEFAULT_APPROVAL_ROLES:
        if role not in existing:
            db.add(
                ApprovalAuthority(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    role_name=role,
                    object_type="Decision",
                    decision_type="INVESTIGATION_REVIEW",
                    scope={},
                    authority="AUTHORIZED",
                    version="v1",
                    status="ACTIVE",
                    effective_from=now,
                    effective_to=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            changed = True
    if (
        not db.query(SegregationOfDutiesPolicy)
        .filter_by(tenant_id=tenant.id, object_type="Decision", decision_type="INVESTIGATION_REVIEW")
        .first()
    ):
        db.add(
            SegregationOfDutiesPolicy(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Decision creator separation",
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                creator_cannot_approve=True,
                last_material_editor_cannot_approve=True,
                version="v1",
                status="ACTIVE",
                effective_from=now,
                effective_to=None,
                created_at=now,
                updated_at=now,
            )
        )
        changed = True
    if changed:
        db.commit()


def bootstrap(db, tenant):
    plan = db.query(PlanDefinition).filter_by(code="R1_GOVERNANCE_DEMO").first()
    now = NOW()
    changed = False
    if not plan:
        plan = PlanDefinition(
            id=uuid.uuid4(),
            code="R1_GOVERNANCE_DEMO",
            name="R1 Governance Demo",
            description="Synthetic non-commercial Day 23 entitlement configuration",
            version="v1",
            status="ACTIVE",
            effective_from=now,
            effective_to=None,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.flush()
        changed = True
    for feature in (FEATURE, ASK_FEATURE):
        if not db.query(FeatureEntitlement).filter_by(plan_id=plan.id, feature_code=feature).first():
            db.add(
                FeatureEntitlement(
                    id=uuid.uuid4(),
                    plan_id=plan.id,
                    feature_code=feature,
                    enabled=True,
                    limits={},
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                )
            )
            changed = True
    if not db.query(TenantPlanAssignment).filter_by(tenant_id=tenant.id, plan_id=plan.id).first():
        db.add(
            TenantPlanAssignment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="ACTIVE",
                effective_from=now,
                effective_to=None,
                reason="Day 23 synthetic demo",
                created_at=now,
                updated_at=now,
            )
        )
        changed = True
    if (
        not db.query(ApprovalAuthority)
        .filter_by(
            tenant_id=tenant.id,
            role_name=DEFAULT_APPROVER_ROLE,
            object_type="Decision",
            decision_type="INVESTIGATION_REVIEW",
        )
        .first()
    ):
        db.add(
            ApprovalAuthority(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                role_name=DEFAULT_APPROVER_ROLE,
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                scope={},
                authority="AUTHORIZED",
                version="v1",
                status="ACTIVE",
                effective_from=now,
                effective_to=None,
                created_at=now,
                updated_at=now,
            )
        )
        changed = True
    if (
        not db.query(SegregationOfDutiesPolicy)
        .filter_by(tenant_id=tenant.id, object_type="Decision", decision_type="INVESTIGATION_REVIEW")
        .first()
    ):
        db.add(
            SegregationOfDutiesPolicy(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Decision creator separation",
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                creator_cannot_approve=True,
                last_material_editor_cannot_approve=True,
                version="v1",
                status="ACTIVE",
                effective_from=now,
                effective_to=None,
                created_at=now,
                updated_at=now,
            )
        )
        changed = True
    if changed:
        db.commit()
    return plan


def tenant(db, actor):
    try:
        tenant_id = uuid.UUID(actor["tenant_id"])
    except (ValueError, TypeError):
        raise HTTPException(
            403, detail={"code": "TENANT_CONTEXT_INVALID", "message": "Authenticated tenant context is invalid"}
        )
    item = db.query(Tenant).filter(Tenant.id == tenant_id, Tenant.status.in_(("active", "ACTIVE"))).first()
    if not item:
        raise HTTPException(403, detail={"code": "TENANT_INACTIVE", "message": "Active tenant required"})
    # Default decision rules only. The synthetic demo plan (bootstrap) is assigned by the demo and fixture scripts,
    # never as a side effect of a real tenant's request.
    ensure_governance_defaults(db, item)
    return item


def entitled(db, t):
    """Controlled signatures are part of every active plan unless the plan switches them off."""
    from backend.app.access.plan_features import plan_includes

    return plan_includes(db, t.id, FEATURE)


def _signer(db, ctx: AuthenticatedRequestContext):
    try:
        return (
            db.query(AuthUser)
            .filter(AuthUser.id == uuid.UUID(ctx.user_id), AuthUser.tenant_id == ctx.tenant_id)
            .first()
        )
    except (ValueError, TypeError):
        return None


def session_actor(db, ctx: AuthenticatedRequestContext):
    try:
        user = (
            db.query(AuthUser)
            .filter(AuthUser.id == uuid.UUID(ctx.user_id), AuthUser.tenant_id == ctx.tenant_id)
            .first()
        )
    except (ValueError, TypeError):
        user = None
    if user is None:
        return {
            "tenant_id": ctx.tenant_id,
            "user_id": ctx.user_id,
            "active_role": ctx.active_role_id or "Viewer",
            "display_name": ctx.user_id,
            "session_id": ctx.session_id,
        }
    from backend.app.access.permissions import role_of_user

    return {
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user_id,
        "active_role": role_of_user(db, user) or "Viewer",
        "display_name": user.display_name or ctx.user_id,
        "session_id": ctx.session_id,
    }


@router.get("/effective-access")
def effective_access(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    return {
        "feature": FEATURE,
        "entitled": entitled(db, t),
        "user_id": actor["user_id"],
        "active_role": actor["active_role"],
    }


@router.post("/decisions/{decision_id}/sign")
def sign(
    decision_id: uuid.UUID,
    payload: SignatureRequest,
    request: Request,
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    audit(db, t, actor["user_id"], "APPROVAL_REQUESTED", decision_id)
    if not entitled(db, t):
        audit(db, t, actor["user_id"], "ENTITLEMENT_ACCESS_DENIED", decision_id)
        db.commit()
        raise HTTPException(
            403, detail={"code": "DENIED_NOT_ENTITLED", "message": "Tenant is not entitled to controlled signatures"}
        )
    item = data.query(Decision).filter(Decision.id == decision_id, Decision.tenant_id == t.id).first()
    if not item:
        raise HTTPException(
            404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
        )
    version = item.updated_at.isoformat()
    if payload.object_version != version:
        raise HTTPException(
            409, detail={"code": "STALE_OBJECT_VERSION", "message": "Decision changed; re-review the current version"}
        )
    denial = approval_denial(db, t.id, actor["active_role"], item, actor["user_id"])
    if denial:
        code, message = denial
        audit(db, t, actor["user_id"], code, decision_id)
        db.commit()
        raise HTTPException(403, detail={"code": code, "message": message})
    if not payload.remarks.strip():
        raise HTTPException(400, detail={"code": "REMARKS_REQUIRED", "message": "Remarks are required"})
    from backend.app import mfa

    signer = _signer(db, ctx)
    if signer is not None:
        # Wrong passwords and wrong codes at signing count together; 5 lock signing for 15 minutes. Sign-in has its
        # own lock, so signing cannot be used to guess passwords around it.
        mfa.ensure_not_locked(db, signer, scope="sign")
    try:
        user = (
            db.query(AuthUser)
            .filter(AuthUser.id == uuid.UUID(ctx.user_id), AuthUser.tenant_id == ctx.tenant_id)
            .first()
        )
        password_ok = user is not None and bool(user.password_hash) and _verify(payload.password, user.password_hash)
    except (ValueError, TypeError):
        password_ok = False
    if not password_ok:
        audit(db, t, actor["user_id"], "SIGNATURE_REAUTHENTICATION_FAILED", decision_id)
        if signer is not None:
            mfa.record_failure(db, signer, scope="sign")
        db.commit()
        raise HTTPException(
            403, detail={"code": "INVALID_REAUTHENTICATION", "message": "Current password was not verified"}
        )
    if mfa.signatures_require_mfa():
        if signer is None or not mfa.is_enrolled(signer):
            audit(db, t, actor["user_id"], "MFA_REQUIRED_FOR_SIGNATURE", decision_id)
            db.commit()
            raise HTTPException(
                403,
                detail={
                    "code": "MFA_ENROLLMENT_REQUIRED",
                    "message": "Set up an authenticator app (My Account > Security) before signing decisions",
                },
            )
        if not payload.mfa_code or not mfa.check_code(signer, payload.mfa_code, allow_recovery=False):
            audit(db, t, actor["user_id"], "SIGNATURE_MFA_FAILED", decision_id)
            mfa.record_failure(db, signer, scope="sign")
            db.commit()
            raise HTTPException(
                403,
                detail={"code": "MFA_REQUIRED", "message": "Enter the current code from your authenticator app"},
            )
    if signer is not None:
        mfa.record_success(db, signer, scope="sign")
    material = {
        "decision_id": str(item.id),
        "version": version,
        "type": "INVESTIGATION_REVIEW",
        "decision": payload.decision,
        "remarks": payload.remarks.strip(),
    }
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    existing = (
        db.query(SignedApprovalRecord)
        .filter_by(
            tenant_id=t.id,
            object_type="Decision",
            object_id=item.id,
            object_version=version,
            decision_type="INVESTIGATION_REVIEW",
        )
        .first()
    )
    if existing:
        signed_status = "APPROVED" if existing.decision == "APPROVE" else "REJECTED"
        if item.decision_status != signed_status:
            # The signature was recorded but the decision's status update did not reach the tenant data plane.
            item.decision_status = signed_status
            data.commit()
        raise HTTPException(
            409, detail={"code": "DUPLICATE_SIGNATURE", "message": "This decision version is already signed"}
        )
    meaning = f"I have reviewed this record and {payload.decision.lower()} this decision."
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=t.id,
        object_type="Decision",
        object_id=item.id,
        object_version=version,
        decision_type="INVESTIGATION_REVIEW",
        decision=payload.decision,
        remarks=payload.remarks.strip(),
        signer_user_id=actor["user_id"],
        signer_role=actor["active_role"],
        signature_meaning=meaning,
        content_fingerprint=fingerprint,
        signature_hash=hashlib.sha256((fingerprint + actor["user_id"] + version).encode()).hexdigest(),
        status="SIGNED",
        signed_at=NOW(),
        created_at=NOW(),
    )
    db.add(record)
    signed_status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    if payload.decision == "APPROVE":
        db.add(
            ContextSnapshot(
                id=uuid.uuid4(),
                tenant_id=t.id,
                decision_id=item.id,
                decision_version=version,
                snapshot={
                    "decision_id": str(item.id),
                    "investigation_id": str(item.investigation_id),
                    "product_id": str(item.product_id) if item.product_id else None,
                    "product_version_id": str(item.product_version_id) if item.product_version_id else None,
                    "selected_action": item.selected_action,
                    "rationale": item.rationale,
                    "approval": payload.remarks,
                },
                created_by=actor["user_id"],
                created_at=NOW(),
            )
        )
    audit(
        db,
        t,
        actor["user_id"],
        "SIGNED_APPROVAL_CREATED" if payload.decision == "APPROVE" else "SIGNED_REJECTION_CREATED",
        item.id,
        {"signature_id": str(record.id), "fingerprint": fingerprint},
        request=request,
        reason=payload.remarks,
    )
    # The signature and audit trail (control plane) are committed first; the decision lives in the tenant data plane.
    db.commit()
    item.decision_status = signed_status
    data.commit()
    return {
        "signature_id": record.id,
        "status": item.decision_status,
        "fingerprint": fingerprint,
        "signer": actor["display_name"],
        "role": actor["active_role"],
        "signed_at": record.signed_at,
    }


@router.post("/decisions/{decision_id}/material-change", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def material_change(
    decision_id: uuid.UUID,
    payload: MaterialChangeRequest,
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    item = data.query(Decision).filter(Decision.id == decision_id, Decision.tenant_id == t.id).first()
    if not item:
        raise HTTPException(
            404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
        )
    current = item.updated_at.isoformat()
    if payload.expected_updated_at != current:
        raise HTTPException(409, detail={"code": "STALE_OBJECT_VERSION", "message": "Record changed since review"})
    previous = {"decision_status": item.decision_status, "updated_at": current}
    item.updated_at = NOW()
    item.decision_status = "REQUIRES_REVIEW"
    changed_old, changed_new = change_diff(
        previous, {"decision_status": item.decision_status, "updated_at": item.updated_at.isoformat()}
    )
    audit(
        db,
        t,
        actor["user_id"],
        "RE_REVIEW_REQUIRED",
        item.id,
        {
            "change_summary": payload.change_summary,
            "previous_version": current,
            "new_version": item.updated_at.isoformat(),
            "old_values": changed_old,
            "new_values": changed_new,
        },
    )
    audit(db, t, actor["user_id"], "RE_SIGNATURE_REQUIRED", item.id)
    db.commit()
    data.commit()
    return {"status": "RE_REVIEW_REQUIRED", "previous_version": current, "current_version": item.updated_at}


@router.get("/decisions/{decision_id}/signature-history")
def signature_history(
    decision_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    rows = (
        db.query(SignedApprovalRecord)
        .filter_by(tenant_id=t.id, object_type="Decision", object_id=decision_id)
        .order_by(SignedApprovalRecord.signed_at)
        .all()
    )
    return [
        {
            "signature_id": r.id,
            "object_version": r.object_version,
            "decision": r.decision,
            "status": r.status,
            "signer_user_id": r.signer_user_id,
            "signer_role": r.signer_role,
            "signed_at": r.signed_at,
            "fingerprint": r.content_fingerprint,
            "signature_meaning": r.signature_meaning,
        }
        for r in rows
    ]


@router.get("/decisions/{decision_id}/signature-verification")
def signature_verification(
    decision_id: uuid.UUID,
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Return server-side verification evidence without exposing secrets or signing material."""
    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    item = data.query(Decision).filter(Decision.id == decision_id, Decision.tenant_id == t.id).first()
    if not item:
        raise HTTPException(
            404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
        )
    rows = (
        db.query(SignedApprovalRecord)
        .filter_by(tenant_id=t.id, object_type="Decision", object_id=decision_id)
        .order_by(SignedApprovalRecord.signed_at)
        .all()
    )
    result = []
    for r in rows:
        material = {
            "decision_id": str(item.id),
            "version": r.object_version,
            "type": r.decision_type,
            "decision": r.decision,
            "remarks": r.remarks,
        }
        fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        expected = hashlib.sha256((fingerprint + r.signer_user_id + r.object_version).encode()).hexdigest()
        result.append(
            {
                "signature_id": str(r.id),
                "valid": fingerprint == r.content_fingerprint and expected == r.signature_hash and r.status == "SIGNED",
                "decision": r.decision,
                "signer_user_id": r.signer_user_id,
                "signer_role": r.signer_role,
                "object_version": r.object_version,
                "signed_at": r.signed_at,
                "meaning": r.signature_meaning,
            }
        )
    return {
        "decision_id": str(decision_id),
        "tenant_id": str(t.id),
        "verification_status": "VALID" if all(x["valid"] for x in result) and result else "NOT_SIGNED",
        "signatures": result,
    }
