"""Authorization helpers for the access API: authenticated user, administrator and platform-administrator checks."""

import os
import uuid

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    AuthUser,
)
from backend.app.request_context import get_request_context


def _require_administrator(request: Request, db: Session) -> AuthUser:
    user = _authenticated_user(request, db)
    if (user.role or "").upper() not in {
        "ADMINISTRATOR",
        "ADMIN",
        "MDARIX ADMINISTRATOR",
        "PLATFORM_ADMIN",
        "CUSTOMER_ADMIN",
    }:
        raise HTTPException(403, detail={"code": "ADMINISTRATOR_REQUIRED", "message": "Administrator role required"})
    return user


def _role_code(user: AuthUser) -> str:
    return (user.role or "").strip().upper().replace(" ", "_")


def _is_platform_admin(user: AuthUser) -> bool:
    return _role_code(user) in {"PLATFORM_ADMIN", "MDARIX_ADMINISTRATOR", "ADMINISTRATOR", "ADMIN"}


def _is_customer_admin(user: AuthUser) -> bool:
    return _role_code(user) == "CUSTOMER_ADMIN"


def _require_platform_admin(request: Request, db: Session) -> AuthUser:
    user = _authenticated_user(request, db)
    if not _is_platform_admin(user):
        raise HTTPException(
            403, detail={"code": "PLATFORM_ADMIN_REQUIRED", "message": "Platform administrator role required"}
        )
    return user


def _authenticated_user(request: Request, db: Session) -> AuthUser:
    context = get_request_context(request, db)
    try:
        user = (
            db.query(AuthUser)
            .filter(AuthUser.id == uuid.UUID(context.user_id), AuthUser.tenant_id == context.tenant_id)
            .first()
        )
    except (ValueError, TypeError):
        user = None
    if user is None and os.getenv("MDARIX_ENV", "development").lower() == "development":
        user = (
            db.query(AuthUser)
            .filter(AuthUser.username == context.user_id.lower(), AuthUser.tenant_id == context.tenant_id)
            .first()
        )
    if user is None or user.status != "ACTIVE":
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    return user


def _admin_tenant(request: Request, db: Session) -> AuthUser:
    return _require_administrator(request, db)


def _admin_detail_tenant(request: Request, db: Session):
    return _admin_tenant(request, db).tenant_id
