"""Who may send an organization's content to AI, and how much: the per-organization switch and monthly budget.

Customer administrators see their organization's AI use this month and switch AI processing on or off (off: every
feature answers from rules and nothing is sent to a model). Platform administrators can do the same for any
organization and set its monthly token budget. Every change is audited with its reason. Enforcement is in
``genai/governance.py``, on every model request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.authz import _admin_tenant, _require_platform_admin
from backend.app.access.common import _audit_configuration
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from genai import governance
from genai.policy import NO_MODEL, allowed

router = APIRouter(prefix="/api/v1", tags=["AI settings"])
MAX_MONTHLY_TOKENS = 1_000_000_000


class CustomerAiSettings(BaseModel):
    ai_processing_allowed: bool
    reason: str = Field(min_length=5, max_length=1000)


class PlatformAiSettings(BaseModel):
    ai_processing_allowed: bool | None = None
    # null: use the server default (MDARIX_GENAI_TENANT_MONTHLY_TOKENS).
    monthly_token_budget: int | None = Field(default=None, ge=0, le=MAX_MONTHLY_TOKENS)
    use_default_budget: bool = False
    reason: str = Field(min_length=5, max_length=1000)


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


def _settings(db: Session, tenant_id) -> dict:
    return {**governance.usage(db, tenant_id), "models": _models_in_use()}


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
    before = {"ai_processing_allowed": tenant.ai_processing_allowed}
    tenant.ai_processing_allowed = payload.ai_processing_allowed
    tenant.updated_at = datetime.now(timezone.utc)
    _audit_configuration(
        db,
        admin,
        "AI_PROCESSING_SETTING_CHANGED",
        "Tenant",
        tenant.id,
        tenant.lock_version,
        request=request,
        before=before,
        after={"ai_processing_allowed": tenant.ai_processing_allowed},
        reason=payload.reason,
    )
    db.commit()
    return _settings(db, admin.tenant_id)


@router.get("/platform-admin/tenants/{tenant_id}/ai-settings")
def get_platform_ai_settings(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    return _settings(db, tenant_id)


@router.put("/platform-admin/tenants/{tenant_id}/ai-settings")
def update_platform_ai_settings(
    tenant_id: uuid.UUID, payload: PlatformAiSettings, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    before = {
        "ai_processing_allowed": tenant.ai_processing_allowed,
        "ai_monthly_token_budget": tenant.ai_monthly_token_budget,
    }
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
            details={"source": "PLATFORM_ADMIN"},
            request=request,
            reason=payload.reason,
            old_values=before,
            new_values=after,
            created_at=now,
        )
    )
    db.commit()
    return _settings(db, tenant_id)
