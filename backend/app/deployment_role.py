"""Which part of MDARIX this deployment is: one codebase, one image, three roles (ADR-013).

``MDARIX_DEPLOYMENT_ROLE``:

- ``MULTI`` (the default): today's multi-tenant deployment. Every route, every job, every organization in one
  database. Development, CI and the trial sandbox run this way.
- ``PLATFORM``: the MDARIX control plane. Platform administration only (customers, tenants, licences, standards,
  releases); platform staff sign in; the investigation workspace is not served, and no customer's records are here.
- ``CELL``: one customer's tenant cell. The workspace and the customer administration of exactly one organization
  (``MDARIX_CELL_TENANT_ID`` / ``MDARIX_CELL_TENANT_KEY``), in its own database; platform administration is not
  served and platform staff cannot sign in.

A route the role does not serve answers 404 (``backend/app/main.py``), an account the role does not serve cannot sign
in and an existing session of one is refused (``auth_router.py``, ``request_context.py``), and the scheduled jobs and
the worker run only what the role owns (``scheduler.py``, ``outbox/worker.py``). The role is read from the
environment on every call so a process never caches a wrong answer and tests can set it.
"""

from __future__ import annotations

import os
import uuid

MULTI = "MULTI"
PLATFORM = "PLATFORM"
CELL = "CELL"
ROLES = frozenset({MULTI, PLATFORM, CELL})

# What a request path belongs to.
OPS = "ops"  # health, API documentation
SHARED = "shared"  # sign-in, sessions, public pages, the administration of one's own organization, support
PLATFORM_ROUTES = "platform"  # platform administration across organizations
WORKSPACE = "workspace"  # the investigation workspace of an organization
SANDBOX = "sandbox"  # free trials: the MULTI sandbox only (ADR-011)

_SERVED = {
    MULTI: frozenset({OPS, SHARED, PLATFORM_ROUTES, WORKSPACE, SANDBOX}),
    PLATFORM: frozenset({OPS, SHARED, PLATFORM_ROUTES}),
    CELL: frozenset({OPS, SHARED, WORKSPACE}),
}
_PLATFORM_PREFIXES = ("/api/v1/platform-admin/", "/api/v1/platform/")
_SHARED_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/session/",
    "/api/v1/me/",
    "/api/v1/public/",
    "/api/v1/client-errors",
    "/api/v1/admin/",
    "/api/v1/support/",
)


def deployment_role() -> str:
    """The configured role, MULTI when unset. An unknown value is refused here (and reported by config_check)."""
    value = os.getenv("MDARIX_DEPLOYMENT_ROLE", "").strip().upper() or MULTI
    if value not in ROLES:
        raise RuntimeError(f"MDARIX_DEPLOYMENT_ROLE must be one of {', '.join(sorted(ROLES))}, not {value!r}")
    return value


def is_cell() -> bool:
    return deployment_role() == CELL


def is_platform() -> bool:
    return deployment_role() == PLATFORM


def cell_tenant_id() -> uuid.UUID | None:
    """The one organization a CELL serves (None when unset or not a UUID; config_check reports that)."""
    value = os.getenv("MDARIX_CELL_TENANT_ID", "").strip()
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        return None


def cell_tenant_key() -> str:
    return os.getenv("MDARIX_CELL_TENANT_KEY", "").strip()


def route_kind(path: str) -> str:
    """Classify a request path (see the constants above). Everything under /api/v1 that is neither platform
    administration, shared nor the trial sandbox is the workspace."""
    if path.startswith("/health") or path in {"/docs", "/redoc", "/openapi.json"} or path.startswith("/docs/"):
        return OPS
    if path.startswith(_PLATFORM_PREFIXES):
        return PLATFORM_ROUTES
    if path.startswith("/api/v1/trial/") or path == "/api/v1/trial":
        return SANDBOX
    if path.startswith(_SHARED_PREFIXES) or path.rstrip("/") in {"/api/v1/session", "/api/v1/me", "/api/v1/admin"}:
        return SHARED
    if path.startswith("/api/v1/"):
        return WORKSPACE
    return SHARED


def serves_path(path: str) -> bool:
    return route_kind(path) in _SERVED[deployment_role()]


def serves_account(tenant_id, role: str | None) -> bool:
    """Whether this deployment signs in, and keeps signed in, an account of ``tenant_id`` with ``role``:
    a CELL only its own organization's non-platform accounts, the PLATFORM only platform administrators."""
    from backend.app.role_codes import is_strict_platform_admin_role

    current = deployment_role()
    if current == CELL:
        return str(tenant_id) == str(cell_tenant_id()) and not is_strict_platform_admin_role(role)
    if current == PLATFORM:
        return is_strict_platform_admin_role(role)
    return True


def serves_tenant(tenant_id) -> bool:
    """Whether a background job of this deployment works on ``tenant_id``: in a CELL only its own organization."""
    return not is_cell() or str(tenant_id) == str(cell_tenant_id())


def served_tenants_clause(column):
    """A filter for ``column`` (a tenant id column): every organization, or in a CELL only its own."""
    from sqlalchemy import true

    if not is_cell():
        return true()
    cell = cell_tenant_id()
    # An unset cell tenant matches nothing rather than everything.
    return column == cell if cell is not None else column.is_(None)
