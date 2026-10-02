"""Shared helpers for the access API: audit events, provider calls, plan limits, invitation tokens."""

import ipaddress
import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request as UrlRequest
from backend.app.access.outbound import address_is_public, host_is_allowlisted, is_allowed_secret_ref, safe_urlopen

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.customer_lifecycle import (
    SupportAccessGrant,
    TenantEnvironment,
)
from backend.app.db.models.foundation import (
    AuthUser,
    ConnectorConfiguration,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.access.schemas import CustomerProvisionRequest
from backend.app.access.authz import _is_platform_admin, platform_account_clause
from backend.app.runtime_env import is_development


def _development_token(token: str | None) -> str | None:
    return token if is_development() else None


def _audit_configuration(
    db, admin, action, entity_type, entity_id, version, *, request=None, before=None, after=None, reason=None
):
    """Use the shared redaction/origin/diff contract for legacy mutations."""
    from backend.app.enterprise_audit import change_diff, make_audit_event

    old_values, new_values = change_diff(before, after)
    db.add(
        make_audit_event(
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={"version": version, "source": "ADMIN_CONTROL_PLANE"},
            request=request,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
        )
    )


def _safe_provider_url(endpoint: str, path: str, *, timeout: float = 10.0) -> str:
    """Build a provider URL and reject unsafe destinations before any network I/O."""
    parsed = urlparse(str(endpoint))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("CONNECTOR_ENDPOINT_INVALID")
    if not 0 < timeout <= 60:
        raise ValueError("CONNECTOR_TIMEOUT_INVALID")
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    # Explicitly allowlisted hosts (MDARIX_CONNECTOR_ALLOWED_HOSTS, e.g. local simulators) skip the address check.
    # Everything else must resolve to public addresses only; the live socket is checked again by safe_urlopen.
    if not host_is_allowlisted(host, parsed.port):
        try:
            addresses = {str(ipaddress.ip_address(host))}
        except ValueError:
            try:
                addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
            except OSError as exc:
                raise ValueError("CONNECTOR_HOST_UNRESOLVABLE") from exc
        if not addresses or not all(address_is_public(address) for address in addresses):
            raise ValueError("CONNECTOR_PRIVATE_DESTINATION_BLOCKED")
    safe_path = "/" + str(path or "health").lstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, safe_path, "", parsed.query, ""))


def _connector_credential(configuration: dict, *, allow_header: bool = True) -> str | None:
    ref = configuration.get("credential_ref")
    if ref is None:
        return None
    # Only MDARIX_CONNECTOR_SECRET_* names: a connector can never read database, AI, email or session secrets.
    if not is_allowed_secret_ref(ref):
        raise ValueError("CONNECTOR_CREDENTIAL_REF_INVALID")
    token = os.getenv(ref)
    if token and allow_header:
        return token
    return token


def _active_plan_limits(db: Session, tenant_id: uuid.UUID) -> dict:
    row = (
        db.query(TenantPlanAssignment)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(
            TenantPlanAssignment.tenant_id == tenant_id,
            TenantPlanAssignment.status == "ACTIVE",
            PlanDefinition.status == "ACTIVE",
        )
        .first()
    )
    limits: dict = {}
    entitlements = (
        db.query(FeatureEntitlement)
        .join(PlanDefinition, PlanDefinition.id == FeatureEntitlement.plan_id)
        .join(TenantPlanAssignment, TenantPlanAssignment.plan_id == PlanDefinition.id)
        .filter(
            TenantPlanAssignment.tenant_id == tenant_id,
            TenantPlanAssignment.status == "ACTIVE",
            FeatureEntitlement.status == "ACTIVE",
            FeatureEntitlement.enabled == True,
        )
        .all()
    )
    for entitlement in entitlements:
        if entitlement.limits:
            limits.update(entitlement.limits)
    # The tenant's own limits come last, so they take precedence over the shared plan's.
    limits.update(getattr(row, "limits", None) or {})
    return limits


def _ensure_email_not_used_elsewhere(db: Session, email: str, tenant_id: uuid.UUID | None) -> None:
    """A person may hold an account in several organizations (one account per organization, each with its own
    password, role and data); sign-in asks which organization when the email and password match more than one.
    Nothing to refuse here: duplicates inside one organization are refused where the account is created."""
    return None


def _seat_counts(db: Session, tenant_id: uuid.UUID) -> dict:
    users = (
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id == tenant_id,
            AuthUser.status.in_(["INVITED", "ACTIVE", "PENDING_VERIFICATION"]),
            # MDARIX staff accounts in the tenant are not the customer's licensed users.
            ~platform_account_clause(),
        )
        .all()
    )
    admins = [user for user in users if (user.role or "").upper() == "CUSTOMER_ADMIN"]
    return {"allocated_users": len(users), "allocated_customer_admins": len(admins)}


def _enforce_invite_limits(db: Session, tenant_id: uuid.UUID, role: str):
    limits = _active_plan_limits(db, tenant_id)
    counts = _seat_counts(db, tenant_id)
    licensed_limit = int(limits.get("licensed_users_limit") or limits.get("licensed_users") or 100000)
    admin_limit = int(limits.get("customer_admin_limit") or limits.get("customer_admins") or 100000)
    if counts["allocated_users"] >= licensed_limit:
        raise HTTPException(
            409,
            detail={
                "code": "LICENSED_USER_LIMIT_REACHED",
                "message": "Licensed user limit reached",
                "licensed_users": licensed_limit,
                "allocated": counts["allocated_users"],
                "available": 0,
            },
        )
    if role.strip().upper() == "CUSTOMER_ADMIN" and counts["allocated_customer_admins"] >= admin_limit:
        raise HTTPException(
            409,
            detail={
                "code": "CUSTOMER_ADMIN_LIMIT_REACHED",
                "message": "Customer Administrator limit reached",
                "allowed": admin_limit,
                "allocated": counts["allocated_customer_admins"],
                "available": 0,
            },
        )


def _admin_target_tenant(
    admin: AuthUser, payload_tenant_id: uuid.UUID | None, company: str | None = None, db: Session | None = None
) -> uuid.UUID:
    if payload_tenant_id and payload_tenant_id != admin.tenant_id and not _is_platform_admin(admin):
        raise HTTPException(
            403,
            detail={
                "code": "FOREIGN_TENANT_ACCESS_DENIED",
                "message": "Customer administrators can only administer their own tenant",
            },
        )
    if payload_tenant_id:
        return payload_tenant_id
    if _is_platform_admin(admin) and company and db is not None:
        matches = (
            db.query(Tenant)
            .filter(func.lower(Tenant.name) == company.strip().lower(), func.upper(Tenant.status) == "ACTIVE")
            .all()
        )
        if len(matches) == 1:
            return matches[0].id
        if not matches:
            raise HTTPException(
                404, detail={"code": "TENANT_NOT_FOUND", "message": "No active customer matches the Company name"}
            )
        raise HTTPException(
            409, detail={"code": "TENANT_NAME_AMBIGUOUS", "message": "Company name matches more than one active tenant"}
        )
    return payload_tenant_id or admin.tenant_id


def _validate_onboarding_payload(payload: CustomerProvisionRequest, db: Session) -> dict:
    """Validate the complete wizard payload without mutating the database."""
    key = payload.tenant_code.strip().upper()
    email = payload.customer_admin_email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(
            422, detail={"code": "INVALID_ADMIN_EMAIL", "message": "Initial Customer Administrator email is invalid"}
        )
    region, residency = payload.region.strip().lower(), payload.residency.strip().lower()
    if region != residency and residency not in {"default", "unspecified"}:
        raise HTTPException(
            422,
            detail={
                "code": "RESIDENCY_POLICY_CONFLICT",
                "message": "Region and residency require an approved cross-border policy",
            },
        )
    existing = db.query(Tenant).filter(Tenant.tenant_key == key).first()
    _ensure_email_not_used_elsewhere(db, email, existing.id if existing else None)
    if (
        existing is not None
        and not db.query(AuthUser).filter(AuthUser.tenant_id == existing.id, AuthUser.username == email).first()
    ):
        raise HTTPException(
            409,
            detail={
                "code": "ONBOARDING_KEY_CONFLICT",
                "message": "Tenant code belongs to a different onboarding request",
            },
        )
    plan = (
        db.query(PlanDefinition)
        .filter(PlanDefinition.code == payload.plan_code, PlanDefinition.status == "ACTIVE")
        .first()
    )
    if plan is None:
        raise HTTPException(
            422, detail={"code": "PLAN_NOT_PUBLISHED", "message": "Selected plan must be published and active"}
        )
    entitlement = (
        db.query(FeatureEntitlement)
        .filter(
            FeatureEntitlement.plan_id == plan.id,
            FeatureEntitlement.feature_code == "ADMIN_CONTROL_PLANE",
            FeatureEntitlement.enabled.is_(True),
            FeatureEntitlement.status == "ACTIVE",
        )
        .first()
    )
    if entitlement is None:
        raise HTTPException(
            422,
            detail={
                "code": "ENTITLEMENT_MISSING",
                "message": "Selected plan does not grant administration entitlement",
            },
        )
    limit = (entitlement.limits or {}).get("licensed_users_limit")
    if isinstance(limit, int) and payload.licensed_users_limit > limit:
        raise HTTPException(
            422,
            detail={"code": "SEAT_LIMIT_EXCEEDED", "message": "Requested seat cap exceeds the published plan limit"},
        )
    environment_limit = (entitlement.limits or {}).get("environment_limit")
    existing_environment_count = (
        db.query(TenantEnvironment)
        .filter(TenantEnvironment.tenant_id == (existing.id if existing else uuid.UUID(int=0)))
        .count()
    )
    if isinstance(environment_limit, int) and existing_environment_count >= environment_limit:
        raise HTTPException(
            422,
            detail={
                "code": "ENVIRONMENT_LIMIT_EXCEEDED",
                "message": "Tenant has reached the published environment limit",
            },
        )
    return {
        "customer": True,
        "tenant": True,
        "region_residency": True,
        "plan": True,
        "entitlements": True,
        "seats": True,
        "identity": True,
    }


def _parse_support_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "INVALID_SUPPORT_TIME", "message": f"{field} must be ISO-8601"}
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _expire_support_grants(db: Session, tenant_id: uuid.UUID | None = None) -> int:
    now = datetime.now(timezone.utc)
    query = db.query(SupportAccessGrant).filter(
        SupportAccessGrant.status == "APPROVED", SupportAccessGrant.expires_at <= now
    )
    if tenant_id is not None:
        query = query.filter(SupportAccessGrant.tenant_id == tenant_id)
    rows = query.all()
    for row in rows:
        row.status = "EXPIRED"
        row.updated_at = now
    if rows:
        db.flush()
    return len(rows)


def _provider_get(row: ConnectorConfiguration, path_key: str):
    configuration = row.configuration or {}
    endpoint = configuration.get("endpoint")
    if not endpoint:
        return {"status": "NOT_CONFIGURED", "reason": "CONNECTOR_ENDPOINT_MISSING", "connector_id": str(row.id)}
    timeout = float(configuration.get("timeout_seconds", 5))
    try:
        url = _safe_provider_url(endpoint, configuration.get(path_key, "health"), timeout=timeout)
        token = _connector_credential(configuration)
    except ValueError as exc:
        return {"status": "INVALID_CONFIGURATION", "reason": str(exc), "connector_id": str(row.id)}
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with safe_urlopen(UrlRequest(url, headers=headers, method="GET"), timeout=timeout) as response:
            payload = response.read(1_000_001).decode("utf-8")
            if len(payload) > 1_000_000:
                return {"status": "FAILED", "reason": "PROVIDER_RESPONSE_TOO_LARGE"}
            return {
                "status": "HEALTHY",
                "http_status": response.status,
                "payload": json.loads(payload) if payload else {},
            }
    except HTTPError as exc:
        return {"status": "FAILED", "http_status": exc.code, "reason": "PROVIDER_HTTP_ERROR"}
    except (URLError, TimeoutError, ValueError):
        return {"status": "FAILED", "reason": "PROVIDER_UNREACHABLE"}


def _safe_connector_summary(row: ConnectorConfiguration) -> dict:
    configuration = row.configuration or {}
    return {
        "id": str(row.id),
        "code": row.code,
        "connector_type": row.connector_type,
        "version": row.version,
        "status": row.status,
        "endpoint": configuration.get("endpoint"),
        "health_path": configuration.get("health_path", "health"),
        "schema_path": configuration.get("schema_path", "schema"),
        "records_path": configuration.get("records_path"),
        "credential_configured": bool(
            is_allowed_secret_ref(configuration.get("credential_ref"))
            and os.getenv(str(configuration.get("credential_ref")))
        ),
        "credential_ref": configuration.get("credential_ref"),
        "mapping_version": configuration.get("mapping_version"),
        "tenant_key": configuration.get("tenant_key"),
    }
