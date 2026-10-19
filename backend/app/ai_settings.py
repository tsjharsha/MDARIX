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

An organization on the Free Trial plan cannot have AI switched on during the product validation phase (409
AI_OFF_FOR_FREE_TRIALS), by its own administrators or by a Platform Administrator, and ``genai/governance.py`` refuses
its model requests whatever the switch says: the trial agreement, the terms and the privacy policy promise it.
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


class PlatformAiSettings(BaseModel):
    ai_processing_allowed: bool | None = None
    # null: use the server default (MDARIX_GENAI_TENANT_MONTHLY_TOKENS).
    monthly_token_budget: int | None = Field(default=None, ge=0, le=MAX_MONTHLY_TOKENS)
    use_default_budget: bool = False
    reason: str = Field(min_length=5, max_length=1000)
    acknowledgement: bool = False


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
    return {
        **governance.usage(db, tenant_id),
        # A free trial keeps AI off during the product validation phase; switching it on is refused.
        "free_trial": governance.is_free_trial(db, tenant_id),
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


def _refuse_for_free_trial(db: Session, tenant_id, switching_on: bool) -> None:
    """Switching AI processing on for an organization on the Free Trial plan is refused (409)."""
    if switching_on and governance.is_free_trial(db, tenant_id):
        raise HTTPException(409, detail=dict(FREE_TRIAL_AI_REFUSAL))


def _acknowledgement_details(switching_on: bool) -> dict:
    """What the audit event records about an enabling change: the acknowledgement and the contracted provider."""
    if not switching_on:
        return {}
    return {"acknowledgement": True, "provider_name": _provider_name() or "none configured", "masking": pii.enabled()}


@router.get("/admin/ai-settings")
def get_customer_ai_settings(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    return _settings(db, admin.tenant_id)


@router.put("/admin/ai-settings")
def update_customer_ai_settings(payload: CustomerAiSettings, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    tenant = db.get(Tenant, admin.tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    switching_on = payload.ai_processing_allowed and not tenant.ai_processing_allowed
    _refuse_for_free_trial(db, tenant.id, switching_on)
    _require_acknowledgement(switching_on, payload.acknowledgement)
    require_release_gate(switching_on)
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
    _refuse_for_free_trial(db, tenant.id, switching_on)
    _require_acknowledgement(switching_on, payload.acknowledgement)
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
            details={"source": "PLATFORM_ADMIN", **_acknowledgement_details(switching_on)},
            request=request,
            reason=payload.reason,
            old_values=before,
            new_values=after,
            created_at=now,
        )
    )
    db.commit()
    return _settings(db, tenant_id)


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
