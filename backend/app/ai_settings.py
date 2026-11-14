"""Who may send an organization's content to AI, and how much: the per-organization switch and monthly budget.

Customer administrators see their organization's AI use this month and switch AI processing on or off (off: every
feature answers from rules and nothing is sent to a model). Platform administrators can do the same for any
organization and set its monthly token budget. Every change is audited with its reason. Enforcement is in
``genai/governance.py``, on every model request.

Switching AI processing on needs ``acknowledgement: true``: the administrator confirms that the organization's
records may go to the contracted provider named on the screen (masked first). The audit event records the
acknowledgement and that provider's name, and every answer says which provider is in use and that masking is on.

In production, switching AI processing on is also refused until the AI release gate is met (ai_release_gate.py:
contracted provider, golden dataset signed off by a person, golden evaluation passed with this model, automatic trust
check); every answer carries the gate's four bars.

An organization on the Free Trial plan cannot have AI switched on while the trial chain (``MDARIX_AI_TRIAL_CHAIN``)
is empty, the default (409 AI_OFF_FOR_FREE_TRIALS). Once the owner sets it, a trial's administrator may switch AI on
with a second acknowledgement (``trial_acknowledgement``: sample data only, free AI services, possibly outside India;
owner decisions AI-D14a, T5, T7); its requests still carry sample data only (``genai/sample_gate.py``).

Per-feature switches (``features``, ``tenants.ai_features``): a customer administrator turns a feature on with a
reason and a fresh re-authentication (password and authenticator code, as for a signature); only features this server
allows (``MDARIX_AI_FEATURES``) and offers can be turned on. Each change is audited ``AI_FEATURE_SETTING_CHANGED`` with
the feature, its intended use and its risk.

Per-person AI flag for free trials (``auth_users.ai_access``): only a Platform Administrator sets it, for one person
or many, with a reason; each change is audited ``AI_USER_ACCESS_CHANGED`` with the old and new value. New people are
ACTIVE. It has no effect for paid organizations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app import support_access
from backend.app.ai_release_gate import require_for_switch_on as require_release_gate
from backend.app.access.authz import _admin_tenant, _require_platform_admin
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import get_db
from backend.app.enterprise_audit import change_diff, make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from genai import governance, pii
from genai.policy import NO_MODEL, allowed

router = APIRouter(prefix="/api/v1", tags=["AI settings"])
MAX_MONTHLY_TOKENS = 1_000_000_000


class CustomerAiSettings(BaseModel):
    ai_processing_allowed: bool
    reason: str = Field(min_length=5, max_length=1000)
    # Required (true) when switching AI processing on; see the module docstring.
    acknowledgement: bool = False
    # Free trials only, when switching AI on: sample data only, free AI services, possibly outside India.
    trial_acknowledgement: bool = False
    # Per-feature switches ({"ask": true}); turning one on needs the password and authenticator code below.
    features: dict[str, bool] | None = None
    password: str | None = Field(default=None, max_length=256)
    mfa_code: str | None = Field(default=None, max_length=16)


class PlatformAiSettings(BaseModel):
    ai_processing_allowed: bool | None = None
    # null: use the server default (MDARIX_GENAI_TENANT_MONTHLY_TOKENS).
    monthly_token_budget: int | None = Field(default=None, ge=0, le=MAX_MONTHLY_TOKENS)
    use_default_budget: bool = False
    reason: str = Field(min_length=5, max_length=1000)
    acknowledgement: bool = False
    trial_acknowledgement: bool = False


class UserAiAccess(BaseModel):
    ai_access: str = Field(pattern="^(ACTIVE|INACTIVE)$")
    reason: str = Field(min_length=5, max_length=1000)


class BulkUserAiAccess(UserAiAccess):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


def _models_in_use() -> list[dict]:
    """The configured model providers this server may send content to (names only, never keys)."""
    from genai.provider import GenAIProvider

    provider = GenAIProvider()
    if not provider.configured:
        return []
    return [
        {"provider": item.provider_name, "model": item.model}
        for item in [provider, *provider.fallbacks]
        if item.configured and item.provider_name != NO_MODEL and allowed(item.provider_name, item.model)
    ]


def _provider_name(models: list[dict] | None = None) -> str | None:
    """The provider an organization's records go to first (the primary configured, allowed one), or None."""
    models = _models_in_use() if models is None else models
    return models[0]["provider"] if models else None


def _settings(db: Session, tenant_id) -> dict:
    from backend.app.ai_release_gate import status as release_gate

    models = _models_in_use()
    from genai.features import FEATURES, platform_features
    from genai.provider import trial_chain_names

    tenant = db.get(Tenant, uuid.UUID(str(tenant_id)))
    switches = dict((tenant.ai_features if tenant is not None else None) or {})
    allowed_here = platform_features()
    return {
        **governance.usage(db, tenant_id),
        # A free trial keeps AI off until the owner sets the trial chain; then sample data only.
        "free_trial": governance.is_free_trial(db, tenant_id),
        "trial_chain_on": bool(trial_chain_names()),
        "features": [
            {
                **item.public(),
                "enabled": switches.get(key) is True,
                "platform_allowed": item.offered and key in allowed_here,
            }
            for key, item in FEATURES.items()
        ],
        "models": models,
        "provider_name": _provider_name(models),
        "masking": pii.enabled(),
        # The four bars AI must pass before a pilot (enforced in production when switching AI on).
        "release_gate": release_gate(models),
    }


def _require_acknowledgement(switching_on: bool, acknowledgement: bool) -> None:
    """Switching AI processing on is refused unless the administrator acknowledged where the records go."""
    if switching_on and not acknowledgement:
        raise HTTPException(
            422,
            detail={
                "code": "AI_ACKNOWLEDGEMENT_REQUIRED",
                "message": "Confirm that your organization's records may be sent, with personal information masked, "
                "to the AI provider shown before switching AI processing on.",
            },
        )


FREE_TRIAL_AI_REFUSAL = {
    "code": "AI_OFF_FOR_FREE_TRIALS",
    "message": "AI stays off for free trials during the product validation phase, as the free trial agreement says. "
    "It can be switched on once the organization continues on a paid plan.",
}


TRIAL_ACKNOWLEDGEMENT_TEXT = (
    "AI in the free trial works on the sample data only, through free AI services that may process it outside India."
)


def _refuse_for_free_trial(db: Session, tenant_id, switching_on: bool, trial_acknowledgement: bool = False) -> bool:
    """Whether the organization is a free trial. Switching its AI on is refused (409) while the trial chain is empty,
    and needs ``trial_acknowledgement`` (422) once it is set."""
    from genai.provider import trial_chain_names

    trial = governance.is_free_trial(db, tenant_id)
    if switching_on and trial:
        if not trial_chain_names():
            raise HTTPException(409, detail=dict(FREE_TRIAL_AI_REFUSAL))
        if not trial_acknowledgement:
            raise HTTPException(
                422,
                detail={
                    "code": "AI_TRIAL_ACKNOWLEDGEMENT_REQUIRED",
                    "message": f"Confirm before switching AI on: {TRIAL_ACKNOWLEDGEMENT_TEXT}",
                },
            )
    return trial


def _trial_details(trial: bool, switching_on: bool) -> dict:
    return {"trial_acknowledgement": TRIAL_ACKNOWLEDGEMENT_TEXT} if trial and switching_on else {}


def _feature_changes(tenant: Tenant, features: dict[str, bool] | None) -> dict[str, tuple[bool, bool]]:
    """The requested per-feature changes {key: (before, after)}; unknown or not allowed features are refused."""
    from genai.features import FEATURES, platform_features

    if not features:
        return {}
    current = dict(tenant.ai_features or {})
    allowed_here = platform_features()
    changes = {}
    for key, value in features.items():
        item = FEATURES.get(key)
        if item is None:
            raise HTTPException(422, detail={"code": "AI_FEATURE_UNKNOWN", "message": f"Unknown AI feature: {key}"})
        if value and (not item.offered or key not in allowed_here):
            raise HTTPException(
                409,
                detail={
                    "code": "AI_FEATURE_NOT_ALLOWED",
                    "message": f"{item.label} is not available on this service, so it cannot be turned on.",
                },
            )
        before = current.get(key) is True
        if before != bool(value):
            changes[key] = (before, bool(value))
    return changes


def _require_reauthentication(db: Session, ctx, request: Request, payload, tenant_id) -> None:
    """Turning AI or a feature on is signature-grade: the current password and an authenticator code."""
    from backend.app.governance_router import verify_signing_credentials

    def refused(action: str) -> None:
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type="Tenant",
                entity_id=tenant_id,
                details={"attempt": "AI_FEATURE_SWITCH_ON"},
                request=request,
            )
        )

    verify_signing_credentials(db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused)


def _apply_features(db: Session, tenant: Tenant, changes, actor: str, request: Request, reason: str) -> None:
    from genai.features import FEATURES

    if not changes:
        return
    tenant.ai_features = {**dict(tenant.ai_features or {}), **{key: after for key, (_, after) in changes.items()}}
    for key, (before, after) in changes.items():
        item = FEATURES[key]
        db.add(
            make_audit_event(
                tenant_id=tenant.id,
                actor_ref=actor,
                action="AI_FEATURE_SETTING_CHANGED",
                entity_type="Tenant",
                entity_id=tenant.id,
                details={"feature": key, "intended_use": item.intended_use, "risk": item.risk},
                request=request,
                reason=reason,
                old_values={"enabled": before},
                new_values={"enabled": after},
            )
        )


def _acknowledgement_details(switching_on: bool) -> dict:
    """What the audit event records about an enabling change: the acknowledgement and the contracted provider."""
    if not switching_on:
        return {}
    return {"acknowledgement": True, "provider_name": _provider_name() or "none configured", "masking": pii.enabled()}


def _settings_admin(request: Request, db: Session):
    """A customer administrator, or in a free trial (which has no customer administrator) the person who started it
    (decision T5: the trial's own administrator switches trial AI on)."""
    from backend.app.access.authz import _authenticated_user
    from backend.app.trial.team import is_trial_owner

    try:
        return _admin_tenant(request, db)
    except HTTPException as refused:
        user = _authenticated_user(request, db)
        if governance.is_free_trial(db, user.tenant_id) and is_trial_owner(db, user.tenant_id, user):
            return user
        raise refused


@router.get("/admin/ai-settings")
def get_customer_ai_settings(request: Request, db: Session = Depends(get_db)):
    admin = _settings_admin(request, db)
    return _settings(db, admin.tenant_id)


@router.put("/admin/ai-settings")
def update_customer_ai_settings(
    payload: CustomerAiSettings,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    admin = _settings_admin(request, db)
    tenant = db.get(Tenant, admin.tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    switching_on = payload.ai_processing_allowed and not tenant.ai_processing_allowed
    trial = _refuse_for_free_trial(db, tenant.id, switching_on, payload.trial_acknowledgement)
    _require_acknowledgement(switching_on, payload.acknowledgement)
    if not trial:
        # The release gate is about the paid provider; trial AI is never qualified (decision T4).
        require_release_gate(switching_on)
    changes = _feature_changes(tenant, payload.features)
    if any(after for _, after in changes.values()):
        _require_reauthentication(db, ctx, request, payload, tenant.id)
        tenant = db.get(Tenant, admin.tenant_id)
    _apply_features(db, tenant, changes, str(admin.id), request, payload.reason)
    before = {"ai_processing_allowed": tenant.ai_processing_allowed}
    tenant.ai_processing_allowed = payload.ai_processing_allowed
    tenant.updated_at = datetime.now(timezone.utc)
    old_values, new_values = change_diff(before, {"ai_processing_allowed": tenant.ai_processing_allowed})
    db.add(
        make_audit_event(
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="AI_PROCESSING_SETTING_CHANGED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={
                "version": tenant.lock_version,
                "source": "ADMIN_CONTROL_PLANE",
                **_acknowledgement_details(switching_on),
                **_trial_details(trial, switching_on),
            },
            request=request,
            reason=payload.reason,
            old_values=old_values,
            new_values=new_values,
        )
    )
    db.commit()
    return _settings(db, admin.tenant_id)


@router.get("/platform-admin/tenants/{tenant_id}/ai-settings")
def get_platform_ai_settings(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    platform_admin = _require_platform_admin(request, db)
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    support_access.require_customer_approved_access(
        db, platform_admin, tenant_id, support_access.CONFIGURATION, request=request
    )
    return _settings(db, tenant_id)


@router.put("/platform-admin/tenants/{tenant_id}/ai-settings")
def update_platform_ai_settings(
    tenant_id: uuid.UUID, payload: PlatformAiSettings, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    # Whether the organization's content may go to an AI model is the customer's decision.
    support_access.require_customer_approved_access(
        db, platform_admin, tenant_id, support_access.CONFIGURATION, write=True, request=request
    )
    tenant = db.get(Tenant, tenant_id)
    before = {
        "ai_processing_allowed": tenant.ai_processing_allowed,
        "ai_monthly_token_budget": tenant.ai_monthly_token_budget,
    }
    switching_on = bool(payload.ai_processing_allowed) and not tenant.ai_processing_allowed
    trial = _refuse_for_free_trial(db, tenant.id, switching_on, payload.trial_acknowledgement)
    _require_acknowledgement(switching_on, payload.acknowledgement)
    if not trial:
        require_release_gate(switching_on)
    if payload.ai_processing_allowed is not None:
        tenant.ai_processing_allowed = payload.ai_processing_allowed
    if payload.use_default_budget:
        tenant.ai_monthly_token_budget = None
    elif payload.monthly_token_budget is not None:
        tenant.ai_monthly_token_budget = payload.monthly_token_budget
    now = datetime.now(timezone.utc)
    tenant.updated_at = now
    after = {
        "ai_processing_allowed": tenant.ai_processing_allowed,
        "ai_monthly_token_budget": tenant.ai_monthly_token_budget,
    }
    db.add(
        make_audit_event(
            tenant_id=tenant.id,
            actor_ref=str(platform_admin.id),
            action="AI_PROCESSING_SETTING_CHANGED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={
                "source": "PLATFORM_ADMIN",
                **_acknowledgement_details(switching_on),
                **_trial_details(trial, switching_on),
            },
            request=request,
            reason=payload.reason,
            old_values=before,
            new_values=after,
            created_at=now,
        )
    )
    db.commit()
    return _settings(db, tenant_id)


# ------------------------------------------------------------------------------------- per-person AI flag (trials)


def _trial_tenant_for_platform(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    if not governance.is_free_trial(db, tenant_id):
        # The flag is for free trials only; for a paid organization it has no effect, so it is not offered.
        raise HTTPException(
            409,
            detail={
                "code": "AI_USER_FLAG_TRIAL_ONLY",
                "message": "The per-person AI flag applies to free trials only.",
            },
        )
    return tenant


def _set_user_ai_access(
    db: Session, platform_admin, tenant_id: uuid.UUID, user_ids, value: str, reason: str, request: Request
) -> list[dict]:
    from backend.app.db.models.foundation import AuthUser

    wanted = list(dict.fromkeys(user_ids))
    people = {
        row.id: row for row in db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.id.in_(wanted)).all()
    }
    missing = [str(item) for item in wanted if item not in people]
    if missing:
        raise HTTPException(
            404, detail={"code": "USER_NOT_FOUND", "message": "One or more people are not in this organization"}
        )
    now = datetime.now(timezone.utc)
    changed = []
    for user_id in wanted:
        person = people[user_id]
        before = person.ai_access or governance.USER_AI_ACTIVE
        if before == value:
            changed.append({"user_id": str(user_id), "ai_access": value, "changed": False})
            continue
        person.ai_access = value
        person.updated_at = now
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(platform_admin.id),
                action="AI_USER_ACCESS_CHANGED",
                entity_type="AuthUser",
                entity_id=user_id,
                details={"source": "PLATFORM_ADMIN", "user_id": str(user_id)},
                request=request,
                reason=reason,
                old_values={"ai_access": before},
                new_values={"ai_access": value},
                created_at=now,
            )
        )
        changed.append({"user_id": str(user_id), "ai_access": value, "changed": True})
    db.commit()
    return changed


@router.get("/platform-admin/tenants/{tenant_id}/users/ai-access")
def list_user_ai_access(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Each person of a free trial with their own AI flag (Platform Administrator only)."""
    from backend.app.db.models.foundation import AuthUser

    _require_platform_admin(request, db)
    _trial_tenant_for_platform(db, tenant_id)
    rows = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).order_by(AuthUser.display_name).all()
    return {
        "items": [
            {"user_id": str(row.id), "display_name": row.display_name, "ai_access": row.ai_access} for row in rows
        ]
    }


@router.put("/platform-admin/tenants/{tenant_id}/users/{user_id}/ai-access")
def set_user_ai_access(
    tenant_id: uuid.UUID, user_id: uuid.UUID, payload: UserAiAccess, request: Request, db: Session = Depends(get_db)
):
    """Set one person's AI flag in a free trial (Platform Administrator only; audited with the reason)."""
    platform_admin = _require_platform_admin(request, db)
    _trial_tenant_for_platform(db, tenant_id)
    changed = _set_user_ai_access(db, platform_admin, tenant_id, [user_id], payload.ai_access, payload.reason, request)
    return changed[0]


@router.put("/platform-admin/tenants/{tenant_id}/users/ai-access")
def set_users_ai_access(
    tenant_id: uuid.UUID, payload: BulkUserAiAccess, request: Request, db: Session = Depends(get_db)
):
    """Set many people's AI flag in a free trial at once (Platform Administrator only; one audit event each)."""
    platform_admin = _require_platform_admin(request, db)
    _trial_tenant_for_platform(db, tenant_id)
    changed = _set_user_ai_access(
        db, platform_admin, tenant_id, payload.user_ids, payload.ai_access, payload.reason, request
    )
    return {"items": changed}


# ------------------------------------------------------------------------------------------------- AI status
# What every signed-in user's screens need to know: may AI be used for this organization now, and if not, why and
# what still works by hand. No network call: "available" means a provider is configured and allowed here.

AI_STATUS_MESSAGES = {
    "AI_DISABLED": "AI processing is switched off for your organization. Every step still works by hand, and Ask "
    "MDARIX answers from your records. An administrator can switch AI on under Security › AI processing.",
    "PROVIDER_UNAVAILABLE": "No AI service is configured or allowed here. Every step still works by hand, and Ask "
    "MDARIX answers from your records.",
    "BUDGET_EXHAUSTED": "Your organization's monthly AI allowance is used up. Every step still works by hand, and Ask "
    "MDARIX answers from your records. An administrator can raise the allowance.",
    None: "AI assistance is available. AI results are interpretations: review them before relying on them.",
}
MANUAL_PATHS = {
    "hypotheses": True,
    "unknowns": True,
    "failure_chain": True,
    "observations": True,
    "ask": "record-based answers",
}


def ai_status_for(state: dict | None, models: list[dict]) -> dict:
    """The AI status of an organization from its usage state (``governance.usage``) and the usable models."""
    enabled = bool(state and state.get("ai_processing_allowed"))
    available = bool(models)
    budget = None
    if state is not None:
        limit = int(state.get("monthly_token_budget") or 0)
        used = int(state.get("tokens_used") or 0)
        budget = {"used": used, "limit": limit, "remaining": max(0, limit - used)}
    # No AI service on this server is the first reason: switching the organization on would change nothing.
    if not available:
        reason = "PROVIDER_UNAVAILABLE"
    elif not enabled:
        reason = "AI_DISABLED"
    elif budget is not None and budget["remaining"] <= 0:
        reason = "BUDGET_EXHAUSTED"
    else:
        reason = None
    return {
        "enabled": enabled,
        "available": available,
        "budget": budget,
        "reason_code": reason,
        "message": AI_STATUS_MESSAGES[reason],
        "manual_paths": dict(MANUAL_PATHS),
    }


def ai_ready(db: Session, tenant_id) -> bool:
    """Whether AI really answers for this organization now: a provider is configured and allowed here, the
    organization switched AI on, and its allowance is not used up."""
    try:
        if governance.is_free_trial(db, tenant_id):
            return False
        return ai_status_for(governance.usage(db, tenant_id), _models_in_use())["reason_code"] is None
    except Exception:
        return False


# A free trial runs without AI: its screens say so plainly instead of naming an administrator setting.
TRIAL_AI_OFF_MESSAGE = "AI is off for free trials. Every step works by hand, and Ask MDARIX answers from your records."


@router.get("/ai/status")
def ai_status(db: Session = Depends(get_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """Whether AI may be used for the signed-in user's organization now, and why not (any signed-in user). ``trial``
    is true for a free trial, whose AI is off."""
    from backend.app.trial.service import trial_subscription

    trial = trial_subscription(db, ctx.tenant_id) is not None
    state = governance.usage(db, ctx.tenant_id)
    if trial:
        # Off whatever the switch says (genai/governance.py refuses a trial's model requests).
        state = {**state, "ai_processing_allowed": False}
    status = ai_status_for(state, _models_in_use())
    status["trial"] = trial
    if trial and status["reason_code"] in ("PROVIDER_UNAVAILABLE", "AI_DISABLED"):
        status["message"] = TRIAL_AI_OFF_MESSAGE
    return status
