import hashlib
import json
import uuid
from collections.abc import Sequence
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
from backend.app.role_codes import is_administrator_role
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


ADMINISTRATOR_CANNOT_SIGN = (
    "ADMINISTRATOR_CANNOT_SIGN",
    "Administrators do not approve or sign; an approver of your organization must do this",
)


def approval_denial(db, tenant_id, role_name: str | Sequence[str], decision, user_id: str) -> tuple[str, str] | None:
    """Why this user may not approve this decision, or None when they may.

    Shared by signing and by review approval so both enforce the same rules:
    an ACTIVE approval authority for the user's role, and segregation of duties (no self-approval).
    ``role_name`` may also be every role the person holds (``session_actor(...)["roles"]``); see ``approval_check``.
    """
    return approval_check(db, tenant_id, role_name, decision, user_id)[0]


def approval_check(
    db, tenant_id, roles: str | Sequence[str] | None, decision, user_id: str
) -> tuple[tuple[str, str] | None, str | None]:
    """``(denial, role used)``: why this user may not approve this decision (None when they may), and the role whose
    approval authority they approve under (None when they may not).

    A person holding several roles may approve when ANY of them has an ACTIVE approval authority and segregation of
    duties passes; the first such role (the account role before additional roles) is the one used. An administrator
    role among any of them still refuses. With one role this is exactly the single-role rule.
    """
    from backend.app.access.permissions import normalize_role

    held = [roles] if roles is None or isinstance(roles, str) else list(roles)
    # Administrators (customer or platform) never approve or sign, whatever authority rules say: an administrator
    # can write those rules, so an authority naming their own role would let them sign around segregation of duties.
    if any(is_administrator_role(role) for role in held):
        return ADMINISTRATOR_CANNOT_SIGN, None
    # Role names are compared the way permissions are ('Approver' == 'APPROVER'), so a rule written in any case
    # matches the role stored on the account.
    authorized = {
        normalize_role(row.role_name)
        for row in db.query(ApprovalAuthority).filter_by(
            tenant_id=tenant_id,
            object_type="Decision",
            decision_type="INVESTIGATION_REVIEW",
            authority="AUTHORIZED",
            status="ACTIVE",
        )
    }
    role_used = next((role for role in held if normalize_role(role) and normalize_role(role) in authorized), None)
    if role_used is None:
        return ("APPROVAL_AUTHORITY_DENIED", "Active role lacks approval authority"), None
    sod = (
        db.query(SegregationOfDutiesPolicy)
        .filter_by(tenant_id=tenant_id, object_type="Decision", decision_type="INVESTIGATION_REVIEW", status="ACTIVE")
        .first()
    )
    if sod and sod.creator_cannot_approve and str(decision.authorized_by_ref) == str(user_id):
        return ("SOD_DENIED", "Approval by another authorized user is required"), None
    return None, role_used


SELF_REVIEW_DENIED = ("SOD_DENIED", "You recorded this decision; another user must review it")


def is_decision_author(decision, user_id) -> bool:
    """True when this user recorded the decision (its author is the signed-in user who created it)."""
    return str(decision.authorized_by_ref) == str(user_id)


def same_object_version(sent: str | None, current: datetime) -> bool:
    """True when the version a client sent is the decision's current version (its ``updated_at``).

    The server writes the version as ``updated_at.isoformat()``; a client may send that text back, or the same moment
    written another way ('Z' for UTC, another offset). Both are compared as exact instants, to the microsecond, so any
    other moment is still stale. A naive value is read as UTC.
    """
    if not sent:
        return False
    if sent == current.isoformat():
        return True
    try:
        parsed = datetime.fromisoformat(sent.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return parsed == current


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
            "roles": [ctx.active_role_id or "Viewer"],
            "display_name": ctx.user_id,
            "session_id": ctx.session_id,
        }
    from backend.app.access.permissions import role_of_user, roles_of_user

    active_role = role_of_user(db, user) or "Viewer"
    return {
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user_id,
        "active_role": active_role,
        # Every role the person holds (account role first, then additional workflow roles): approval and signing
        # accept any of them (approval_check).
        "roles": roles_of_user(db, user) or [active_role],
        "display_name": user.display_name or ctx.user_id,
        "session_id": ctx.session_id,
    }


def verify_signing_credentials(
    db, ctx: AuthenticatedRequestContext, *, password: str | None, mfa_code: str | None, record_refusal
) -> AuthUser | None:
    """Re-authenticate the signed-in person before an electronic signature or a controlled approval.

    The one check behind every signature-grade action (decision signing here, regulatory document approval in
    regulatory_router.py): the current password, then - when signatures require MFA (``mfa.signatures_require_mfa``)
    - a current authenticator code from an enrolled account. Wrong passwords and wrong codes count together on the
    "sign" throttle (5 lock signing for 15 minutes); sign-in has its own lock, so signing cannot be used to guess
    passwords around it. Each refusal calls ``record_refusal(action)`` (the caller's audit event), is committed, and
    raises 403. Returns the signer (None for a legacy in-process session that has no account).
    """
    from backend.app import mfa

    signer = _signer(db, ctx)
    if signer is not None:
        mfa.ensure_not_locked(db, signer, scope="sign")
    password_ok = (
        signer is not None and bool(signer.password_hash) and bool(password) and _verify(password, signer.password_hash)
    )
    if not password_ok:
        record_refusal("SIGNATURE_REAUTHENTICATION_FAILED")
        if signer is not None:
            mfa.record_failure(db, signer, scope="sign")
        db.commit()
        raise HTTPException(
            403, detail={"code": "INVALID_REAUTHENTICATION", "message": "Current password was not verified"}
        )
    if mfa.signatures_require_mfa():
        if signer is None or not mfa.is_enrolled(signer):
            record_refusal("MFA_REQUIRED_FOR_SIGNATURE")
            db.commit()
            raise HTTPException(
                403,
                detail={
                    "code": "MFA_ENROLLMENT_REQUIRED",
                    "message": "Set up an authenticator app (My Account > Security) before signing decisions",
                },
            )
        if not mfa_code or not mfa.check_code(signer, mfa_code, allow_recovery=False):
            record_refusal("SIGNATURE_MFA_FAILED")
            mfa.record_failure(db, signer, scope="sign")
            db.commit()
            raise HTTPException(
                403,
                detail={"code": "MFA_REQUIRED", "message": "Enter the current code from your authenticator app"},
            )
    if signer is not None:
        mfa.record_success(db, signer, scope="sign")
    return signer


def _notify(helper: str, db, **details) -> bool:
    """Queue a decision notification through backend/app/notifications.py (emails go out from the outbox worker).

    The helpers are optional so a notification can never block a signature: when one is missing (an older build)
    or fails to queue, the caller's audit trail still records the event and the failure is logged."""
    import logging

    from backend.app import notifications

    send = getattr(notifications, helper, None)
    if send is None:
        logging.getLogger("mdarix.governance").warning("Notification helper %s is not available", helper)
        return False
    try:
        send(db, **details)
        return True
    except Exception:
        logging.getLogger("mdarix.governance").exception("Notification %s could not be queued", helper)
        return False


def decision_actions(db, ctx: AuthenticatedRequestContext, decisions) -> dict:
    """What the signed-in user may do with each decision: ``{decision id: {can_review, can_approve, can_sign,
    reason}}``, ``reason`` saying why something is not offered (None when everything is).

    The rules are those of the review and sign endpoints: a review needs permission to change records, may not be of
    the user's own decision and not of a signed decision; approving through a review also needs ``approval_denial``
    to pass (approval authority, segregation of duties, no administrators); signing needs that, the
    DECISION_CENTER_SIGNATURES entitlement and a current version that is not signed yet. Read-only: unlike the
    endpoints it writes no audit event and counts no failed attempt. A screen uses it to offer only what the server
    would accept; the endpoints stay the authority.
    """
    from backend.app.access.permissions import effective_permissions
    from decision_center.service import SIGNED_STATUSES

    decisions = list(decisions)
    if not decisions:
        return {}
    may_write = RECORDS_WRITE in effective_permissions(db, ctx)
    try:
        actor = session_actor(db, ctx)
        t = tenant(db, actor)  # the same tenant check and default decision rules as the endpoints
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        reason = detail.get("message") or "Decisions cannot be reviewed or signed in this organization"
        return {
            item.id: {"can_review": False, "can_approve": False, "can_sign": False, "reason": reason}
            for item in decisions
        }
    administrator = any(is_administrator_role(role) for role in actor["roles"])
    signatures_enabled = entitled(db, t)
    signed_versions = {
        (row.object_id, row.object_version)
        for row in db.query(SignedApprovalRecord.object_id, SignedApprovalRecord.object_version).filter(
            SignedApprovalRecord.tenant_id == t.id,
            SignedApprovalRecord.object_type == "Decision",
            SignedApprovalRecord.decision_type == "INVESTIGATION_REVIEW",
            SignedApprovalRecord.object_id.in_([item.id for item in decisions]),
        )
    }
    result = {}
    for item in decisions:
        locked = str(item.decision_status or "").upper() in SIGNED_STATUSES
        own = is_decision_author(item, ctx.user_id)
        denial = approval_denial(db, t.id, actor["roles"], item, actor["user_id"])
        version_signed = item.updated_at is not None and (item.id, item.updated_at.isoformat()) in signed_versions
        can_review = may_write and not own and not locked
        can_approve = can_review and denial is None
        can_sign = not locked and not version_signed and not administrator and signatures_enabled and denial is None
        reasons = [
            "This decision is signed and closed; record a new decision to change it" if locked else None,
            "This version of the decision is already signed" if version_signed else None,
            SELF_REVIEW_DENIED[1] if own else None,
            ADMINISTRATOR_CANNOT_SIGN[1] if administrator else None,
            None if may_write else "Your role does not allow reviewing decisions",
            denial[1] if denial else None,
            None if signatures_enabled else "Your organization's plan does not include controlled signatures",
        ]
        result[item.id] = {
            "can_review": can_review,
            "can_approve": can_approve,
            "can_sign": can_sign,
            "reason": None
            if can_review and can_approve and can_sign
            else next((text for text in reasons if text), None),
        }
    return result


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
    if any(is_administrator_role(role) for role in actor["roles"]):
        # Administrators never sign, whatever the plan or any authority says: refuse with that reason first.
        code, message = ADMINISTRATOR_CANNOT_SIGN
        audit(db, t, actor["user_id"], code, decision_id)
        db.commit()
        raise HTTPException(403, detail={"code": code, "message": message})
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
    if not same_object_version(payload.object_version, item.updated_at):
        raise HTTPException(
            409, detail={"code": "STALE_OBJECT_VERSION", "message": "Decision changed; re-review the current version"}
        )
    # Any of the person's roles may carry the approval authority; the one used is recorded as the signer's role.
    denial, signer_role = approval_check(db, t.id, actor["roles"], item, actor["user_id"])
    if denial:
        code, message = denial
        audit(db, t, actor["user_id"], code, decision_id)
        db.commit()
        raise HTTPException(403, detail={"code": code, "message": message})
    if not payload.remarks.strip():
        raise HTTPException(400, detail={"code": "REMARKS_REQUIRED", "message": "Remarks are required"})
    verify_signing_credentials(
        db,
        ctx,
        password=payload.password,
        mfa_code=payload.mfa_code,
        record_refusal=lambda action: audit(db, t, actor["user_id"], action, decision_id),
    )
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
        signer_role=signer_role,
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
    owner = _case_owner(data, t.id, item.investigation_id)
    from backend.app.workflow.hooks import case_business_id, on_decision_signed

    if _notify(
        "notify_signoff_completed",
        db,
        tenant_id=t.id,
        decision_id=item.id,
        investigation_id=item.investigation_id,
        decision=payload.decision,
        signer_user_id=actor["user_id"],
        owner_ref=owner,
        reference=item.business_id,
        investigation_business_id=case_business_id(data, t.id, item.investigation_id),
    ):
        db.commit()
    # The signature completes the decision's approval task. Saved after the signature; never undoes it.
    on_decision_signed(
        data, item, decision_value=payload.decision, actor_user_id=actor["user_id"], actor_role=signer_role
    )
    return {
        "signature_id": record.id,
        "business_id": record.business_id,
        "decision_business_id": item.business_id,
        "status": item.decision_status,
        "fingerprint": fingerprint,
        "signer": actor["display_name"],
        "role": signer_role,
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
    if not same_object_version(payload.expected_updated_at, item.updated_at):
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
    from backend.app.workflow.hooks import case_business_id, on_decision_material_change

    if _notify(
        "notify_review_pending",
        db,
        tenant_id=t.id,
        decision_id=item.id,
        investigation_id=item.investigation_id,
        requested_by=actor["user_id"],
        reference=item.business_id,
        investigation_business_id=case_business_id(data, t.id, item.investigation_id),
    ):
        db.commit()
    result = {"status": "RE_REVIEW_REQUIRED", "previous_version": current, "current_version": item.updated_at}
    # The changed decision needs a new approval: its approval task is replaced. Saved after the change; never
    # undoes it.
    on_decision_material_change(data, item, actor_user_id=actor["user_id"], actor_role=actor.get("active_role"))
    return result


def _case_owner(data, tenant_id, investigation_id) -> str | None:
    """The owner recorded on the decision's case (an account email), to tell them their case was signed off."""
    from backend.app.db.models.foundation import Investigation

    if investigation_id is None:
        return None
    case = (
        data.query(Investigation.owner_ref)
        .filter(Investigation.tenant_id == tenant_id, Investigation.id == investigation_id)
        .first()
    )
    return case.owner_ref if case else None


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
            "business_id": r.business_id,
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
                "business_id": r.business_id,
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
        "decision_business_id": item.business_id,
        "tenant_id": str(t.id),
        "verification_status": verification_status(result),
        "signatures": result,
    }


def verification_status(signatures: list[dict]) -> str:
    """The overall result: NOT_SIGNED without signatures, INVALID when any signature no longer matches what was
    signed (a changed record must show as a problem, never as merely unsigned), else VALID."""
    if not signatures:
        return "NOT_SIGNED"
    return "VALID" if all(item["valid"] for item in signatures) else "INVALID"
