import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.service import _verify
from backend.app.db.models.foundation import (
    ApprovalAuthority,
    AuditEvent,
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


# Audit actions that change a Decision's substance: the legacy material-change route (``/material-change``) and a
# late-evidence impact assessment that puts a signed decision under reconsideration (decision_followups/impact.py).
MATERIAL_EDIT_ACTIONS = ("RE_REVIEW_REQUIRED", "DECISION_UNDER_RECONSIDERATION")


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
    if sod:
        if sod.creator_cannot_approve and str(decision.authorized_by_ref) == str(user_id):
            return ("SOD_DENIED", "Approval by another authorized user is required"), None

        # Material edits are recorded in the immutable audit stream.  Using that stream here means the rule also
        # covers legacy mutation routes that do not have a dedicated ``last_material_editor`` column on Decision.
        # Only events that change the decision count (MATERIAL_EDIT_ACTIONS): the sign route itself writes
        # APPROVAL_REQUESTED and refusal events for the signer, which must not make them its "last editor".
        # Only a stored Decision has an audit stream to read. The Decision Brief signing path passes just the brief's
        # author (human_decision/service.py approval_subject) and enforces its own author/contributor rule.
        decision_id = getattr(decision, "id", None)
        if sod.last_material_editor_cannot_approve and decision_id is not None:
            material_edit = (
                db.query(AuditEvent)
                .filter(
                    AuditEvent.tenant_id == tenant_id,
                    AuditEvent.entity_type == "Decision",
                    AuditEvent.entity_id == decision_id,
                    AuditEvent.action.in_(MATERIAL_EDIT_ACTIONS),
                    AuditEvent.actor_ref.isnot(None),
                )
                .order_by(AuditEvent.created_at.desc(), AuditEvent.chain_seq.desc())
                .first()
            )
            if material_edit is not None and str(material_edit.actor_ref) == str(user_id):
                return ("SOD_DENIED", "Approval by the last material editor is not permitted"), None
    return None, role_used


SELF_REVIEW_DENIED = ("SOD_DENIED", "You recorded this decision; another user must review it")
# Decisions signed on a Decision Brief (Phase 6, backend/app/human_decision) are signed and verified there; the
# legacy signature, review and material-change endpoints leave them alone.
CASE_DECISION_TYPE = "CASE_DECISION"
BRIEF_DECISION_LOCKED = (
    "DECISION_SIGNED_ON_BRIEF",
    "This decision was signed on its Decision Brief and is never changed; a new decision supersedes it",
)


def is_brief_decision(decision) -> bool:
    return str(getattr(decision, "decision_kind", None) or "").upper() == "BRIEF"


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
) -> bool:
    """Re-authenticate the signed-in person before an electronic signature or a controlled approval.

    The one check behind every signature-grade action (decision signing here, regulatory document approval in
    regulatory_router.py): the current password, then - when signatures require MFA (``mfa.signatures_require_mfa``)
    - a current authenticator code from an enrolled account. Wrong passwords and wrong codes count together on the
    "sign" throttle (5 lock signing for 15 minutes); sign-in has its own lock, so signing cannot be used to guess
    passwords around it. Each refusal first rolls back ``db`` (whatever the request staged before the check is never
    committed with the refusal; the tenant scope is applied again when the next transaction begins), then calls
    ``record_refusal(action)`` (the caller's audit event), is committed, and raises 403. Returns True when an
    authenticator code was checked and accepted for this signature, False when none was asked (signatures do not
    require MFA): the signing audit event stores this as ``mfa_verified``.

    A code that is real but already used (typically the one just typed at sign-in) is refused with
    SIGNATURE_CODE_ALREADY_USED and does not count toward the lock: replay stays impossible (each code works once),
    and a guess that is not a real code still counts.

    The codes are about this signature only (SIGNATURE_CODE_INVALID, SIGNATURE_MFA_NOT_SET_UP), never MFA_REQUIRED:
    that one means the sign-in still owes its second factor, and the browser leaves the page for it, losing what the
    person typed into the signing form.
    """
    from backend.app import mfa

    signer = _signer(db, ctx)
    if signer is not None:
        mfa.ensure_not_locked(db, signer, scope="sign")
    password_ok = (
        signer is not None and bool(signer.password_hash) and bool(password) and _verify(password, signer.password_hash)
    )
    if not password_ok:
        db.rollback()
        record_refusal("SIGNATURE_REAUTHENTICATION_FAILED")
        if signer is not None:
            mfa.record_failure(db, signer, scope="sign")
        db.commit()
        raise HTTPException(
            403, detail={"code": "INVALID_REAUTHENTICATION", "message": "Current password was not verified"}
        )
    if mfa.signatures_require_mfa():
        if signer is None or not mfa.is_enrolled(signer):
            db.rollback()
            record_refusal("MFA_REQUIRED_FOR_SIGNATURE")
            db.commit()
            raise HTTPException(
                403,
                detail={
                    "code": "SIGNATURE_MFA_NOT_SET_UP",
                    "message": "Set up an authenticator app (My Account > Security) before signing decisions",
                },
            )
        if mfa_code and mfa.code_already_used(signer, mfa_code):
            # Replay stays refused, but it is not a wrong guess: no lock on stage after typing the sign-in code again.
            db.rollback()
            record_refusal("SIGNATURE_MFA_CODE_REUSED")
            db.commit()
            raise HTTPException(
                403,
                detail={
                    "code": "SIGNATURE_CODE_ALREADY_USED",
                    "message": "This code was just used. Wait for the next code from your authenticator app.",
                },
            )
        if not mfa_code or not mfa.check_code(signer, mfa_code, allow_recovery=False):
            db.rollback()
            record_refusal("SIGNATURE_MFA_FAILED")
            mfa.record_failure(db, signer, scope="sign")
            db.commit()
            raise HTTPException(
                403,
                detail={
                    "code": "SIGNATURE_CODE_INVALID",
                    "message": (
                        "That code didn't match. Enter the current code from your authenticator app."
                        if mfa_code
                        else "Enter the current code from your authenticator app."
                    ),
                },
            )
        code_checked = True
    else:
        code_checked = False
    if signer is not None:
        mfa.record_success(db, signer, scope="sign")
    return code_checked


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
        locked = str(item.decision_status or "").upper() in SIGNED_STATUSES or is_brief_decision(item)
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
    if is_brief_decision(item):
        raise HTTPException(409, detail={"code": BRIEF_DECISION_LOCKED[0], "message": BRIEF_DECISION_LOCKED[1]})
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
    mfa_verified = verify_signing_credentials(
        db,
        ctx,
        password=payload.password,
        mfa_code=payload.mfa_code,
        record_refusal=lambda action: audit(db, t, actor["user_id"], action, decision_id),
    )
    # Written once every check passed: a refused attempt leaves only its refusal event.
    audit(db, t, actor["user_id"], "APPROVAL_REQUESTED", decision_id)
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
        # Whether a current authenticator code was checked for this signature (verify_signing_credentials).
        {"signature_id": str(record.id), "fingerprint": fingerprint, "mfa_verified": mfa_verified},
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
    # Signals the case was opened for record that its decision is signed. Never undoes the signature.
    from backend.app.signals.hooks import on_case_decision_signed

    on_case_decision_signed(data, item, actor_user_id=actor["user_id"], actor_role=signer_role)
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
    if is_brief_decision(item):
        raise HTTPException(409, detail={"code": BRIEF_DECISION_LOCKED[0], "message": BRIEF_DECISION_LOCKED[1]})
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
    data: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    # Another organization's (or an unknown) decision answers 404, like signature-verification.
    if not data.query(Decision.id).filter(Decision.id == decision_id, Decision.tenant_id == t.id).first():
        raise HTTPException(
            404, detail={"code": "DECISION_NOT_FOUND", "message": "Decision is not available for this tenant"}
        )
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


def _signature_valid(data: Session, r: SignedApprovalRecord, item: Decision) -> bool:
    """Whether the signature still matches the signed material (fingerprint and signature hash) and is SIGNED."""
    if r.decision_type == CASE_DECISION_TYPE:
        # A decision signed on a Decision Brief (backend/app/human_decision): its material also binds the brief
        # version, the evidence set, the context snapshot, the conditions and the follow-ups.
        from backend.app.human_decision.service import signature_valid

        return signature_valid(data, r, item)
    material = {
        "decision_id": str(item.id),
        "version": r.object_version,
        "type": r.decision_type,
        "decision": r.decision,
        "remarks": r.remarks,
    }
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    expected = hashlib.sha256((fingerprint + r.signer_user_id + r.object_version).encode()).hexdigest()
    return fingerprint == r.content_fingerprint and expected == r.signature_hash and r.status == "SIGNED"


# What each kind of signed record is, in words, for the signed-records list.
SIGNED_RECORD_LABELS = {
    "Decision": "Decision",
    "FirstContactCheck": "First-contact check",
    "IntakeEvent": "Intake event",
    "TriageRecord": "Triage",
    "ComplaintMarketAssessment": "Market assessment",
    "ReportSnapshot": "Authority report",
    "ReportObligation": "Attached authority report",
    "ComplaintDisposition": "Disposition",
    "EventClosure": "Event closure",
    "DecisionGuideVersion": "Decision guide",
    "CapaEffectivenessCheck": "CAPA effectiveness check",
    "LotImpactList": "Lot impact list",
    "QmsDocumentVersion": "QMS document",
}


@router.get("/signed-records")
def signed_records(
    limit: int = 20,
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The organization's latest signatures of every kind, newest first: what was signed (``object_type`` and
    ``record_label``), who signed (by name), what the signature means, when, whether an authenticator code was checked,
    the signer's training, and whether the record still matches what was signed (WHIF review F-E2, F-E6: verification
    opens on these). ``fingerprint_ok`` is checked now for decisions; it is null for the kinds that have no check here
    (their own screens verify them)."""
    from backend.app.workflow.people import names_by_id

    actor = session_actor(db, ctx)
    t = tenant(db, actor)
    rows = (
        db.query(SignedApprovalRecord)
        .filter_by(tenant_id=t.id)
        .order_by(SignedApprovalRecord.signed_at.desc(), SignedApprovalRecord.id)
        .limit(min(100, max(1, limit)))
        .all()
    )
    decision_ids = {r.object_id for r in rows if r.object_type == "Decision"}
    decisions = (
        {
            item.id: item
            for item in data.query(Decision).filter(Decision.tenant_id == t.id, Decision.id.in_(decision_ids))
        }
        if decision_ids
        else {}
    )
    signers = names_by_id(db, t.id, [r.signer_user_id for r in rows])
    mfa_by_signature = _mfa_by_signature(db, t.id, rows)
    training = _signer_training(data, t.id, {r.signer_user_id for r in rows})
    items = []
    for r in rows:
        is_decision = r.object_type == "Decision"
        item = decisions.get(r.object_id) if is_decision else None
        items.append(
            {
                "signature_id": str(r.id),
                "business_id": r.business_id,
                "object_type": r.object_type,
                "object_id": str(r.object_id),
                "record_label": SIGNED_RECORD_LABELS.get(r.object_type, r.object_type),
                "decision_id": str(r.object_id) if is_decision else None,
                "decision_business_id": item.business_id if item is not None else None,
                "decision": r.decision,
                "signer_name": signers.get(str(r.signer_user_id)),
                "signer_role": r.signer_role,
                "meaning": r.signature_meaning,
                "signed_at": r.signed_at,
                "mfa_verified": mfa_by_signature.get(str(r.id)),
                "training": (training.get(str(r.signer_user_id)) or {}).get("documents", []),
                # A decision that is gone (another plane, deleted) has nothing to match, so it is not OK.
                "fingerprint_ok": bool(item is not None and _signature_valid(data, r, item)) if is_decision else None,
            }
        )
    return {"items": items}


def _mfa_by_signature(db: Session, tenant_id, rows) -> dict[str, bool]:
    """``{signature id: mfa_verified}`` from the signing audit event of any kind that records it (decisions, case
    decisions, and every other signing path or seed that writes ``signature_id`` with ``mfa_verified``). The search
    starts a day before the oldest signature, so it reads the tenant's recent audit events only."""
    ids = {str(r.id) for r in rows}
    if not ids:
        return {}
    since = min(r.signed_at for r in rows) - timedelta(days=1)
    events = db.query(AuditEvent.details).filter(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.created_at >= since,
        AuditEvent.details["signature_id"].astext.in_(ids),
    )
    return {
        details["signature_id"]: bool(details["mfa_verified"])
        for (details,) in events
        if details and "mfa_verified" in details
    }


def _signer_training(data: Session, tenant_id, signers) -> dict[str, dict]:
    """``{signer: {"state": CURRENT | NOT_CURRENT, "documents": [...]}}`` on the disposition documents."""
    from backend.app.signer_training import service as training

    wanted = training.for_disposition()
    found = {}
    for signer in signers:
        documents = training.status(data, tenant_id, signer, wanted)
        state = "CURRENT" if all(item["state"] == "CURRENT" for item in documents) else "NOT_CURRENT"
        found[str(signer)] = {
            "state": state,
            "documents": [
                {
                    "code": item["code"],
                    "title": item["title"],
                    "version": item["version"],
                    "current": item["state"] == "CURRENT",
                    "state": item["state"],
                    "trained_at": item["trained_at"],
                }
                for item in documents
            ],
        }
    return found


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
    # Each signer by name, the signed-in person too (DEV-024): the organization's own accounts only.
    from backend.app.workflow.people import names_by_id

    signers = names_by_id(db, t.id, [r.signer_user_id for r in rows])
    signed_brief = _signed_brief_label(data, item)
    mfa_by_signature = _mfa_by_signature(db, t.id, rows)
    training = _signer_training(data, t.id, {r.signer_user_id for r in rows})
    result = []
    for r in rows:
        valid = _signature_valid(data, r, item)
        result.append(
            {
                "signature_id": str(r.id),
                "business_id": r.business_id,
                "valid": valid,
                "decision": r.decision,
                "signer_user_id": r.signer_user_id,
                "signer_name": signers.get(str(r.signer_user_id)),
                "signer_role": r.signer_role,
                # True/False as recorded when it was signed; None for a signature from before this was recorded.
                "mfa_verified": mfa_by_signature.get(str(r.id)),
                # The signer's training on the documents a decision relies on, as it stands now.
                "signer_training": training.get(str(r.signer_user_id)),
                "object_version": r.object_version,
                # The signed version in words, for people: "Decision Brief DBV000012 version 2" for a decision on a
                # brief (its object_version is the brief's content hash); None for a legacy approval, whose version is
                # the moment the decision was last changed (the screen shows that date).
                "version_label": (
                    signed_brief[1]
                    if r.decision_type == CASE_DECISION_TYPE and signed_brief and signed_brief[0] == r.object_version
                    else None
                ),
                "signed_at": r.signed_at,
                "meaning": r.signature_meaning,
                # A decision signed on a Decision Brief: the UI links its record (/api/v1/decisions/{id}/record).
                **(
                    {"kind": CASE_DECISION_TYPE, "decision_id": str(item.id)}
                    if r.decision_type == CASE_DECISION_TYPE
                    else {}
                ),
            }
        )
    return {
        "decision_id": str(decision_id),
        "decision_business_id": item.business_id,
        "tenant_id": str(t.id),
        "verification_status": verification_status(result),
        "signatures": result,
    }


def _signed_brief_label(data: Session, decision: Decision) -> tuple[str | None, str] | None:
    """(content hash, "Decision Brief DBV000012 version 2") of the brief version a decision was made on, else None."""
    from backend.app.db.models.reviews import DecisionBriefVersion

    if not decision.brief_version_id:
        return None
    brief = (
        data.query(DecisionBriefVersion.business_id, DecisionBriefVersion.version, DecisionBriefVersion.content_hash)
        .filter(
            DecisionBriefVersion.tenant_id == decision.tenant_id,
            DecisionBriefVersion.id == decision.brief_version_id,
        )
        .first()
    )
    if brief is None:
        return None
    return brief.content_hash, f"Decision Brief {brief.business_id} version {brief.version}"


def verification_status(signatures: list[dict]) -> str:
    """The overall result: NOT_SIGNED without signatures, INVALID when any signature no longer matches what was
    signed (a changed record must show as a problem, never as merely unsigned), else VALID."""
    if not signatures:
        return "NOT_SIGNED"
    return "VALID" if all(item["valid"] for item in signatures) else "INVALID"
