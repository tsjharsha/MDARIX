"""Server-side customer data-plane connection resolution.

The control plane remains authoritative for identity and tenant membership. A
data-plane URL is resolved only from deployment secrets named by the durable
tenant_data_planes registry; callers cannot provide a host, database, or
password.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from fastapi import Depends

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.app.db.session import get_db
from backend.app.db.tls import connect_args
from backend.app.request_context import get_request_context
from backend.app.runtime_env import is_local

# Workspaces without a dedicated database (free trials, the AcmeCare demo) name this marker in their registry row;
# their business data lives in the control database, keyed by tenant and isolated by row-level security.
SHARED_CONTROL_DATA_PLANE = "MDARIX_TRIAL_SHARED_CONTROL_PLANE"
TRIAL_SHARED_DATA_PLANE = SHARED_CONTROL_DATA_PLANE  # original name, kept for existing imports


def _secret_url(secret_ref: str) -> str:
    value = os.getenv(secret_ref)
    if not value:
        # Local validation fallback: the registry still controls the database
        # name and the caller never supplies a connection string. Hosted
        # deployments must provide the referenced secret explicitly.
        if not is_local():
            raise RuntimeError(f"DATA_PLANE_SECRET_NOT_CONFIGURED:{secret_ref}")
        tenant_key = secret_ref.removeprefix("MDARIX_DATA_PLANE_").removesuffix("_DATABASE_URL")
        ports = {"R1_TENANT_1": 5541, "R1_TENANT_2": 5542, "R1_TENANT_3": 5543, "R1_TENANT_4": 5544}
        port = ports.get(tenant_key)
        if port is None:
            raise RuntimeError(f"DATA_PLANE_SECRET_NOT_CONFIGURED:{secret_ref}")
        # The least-privilege role created by scripts/upgrade_data_planes.py when configured, else the plane's owner.
        user = os.getenv("MDARIX_DATA_PLANE_RUNTIME_USER", "").strip()
        password = os.getenv("MDARIX_DATA_PLANE_RUNTIME_PASSWORD", "") if user else ""
        if not (user and password):
            user, password = "mdarix_data", os.getenv("MDARIX_DATA_PLANE_PASSWORD", "change-this-local-secret")
        database = {
            "R1_TENANT_1": "mdarix_tenant_a",
            "R1_TENANT_2": "mdarix_tenant_b",
            "R1_TENANT_3": "mdarix_tenant_c",
            "R1_TENANT_4": "mdarix_tenant_d",
        }[tenant_key]
        value = f"postgresql+pg8000://{user}:{password}@127.0.0.1:{port}/{database}"
    return value


def get_data_plane_db(ctx=Depends(get_request_context), control_db=Depends(get_db)):
    """Resolve the approved plane from the control-plane registry.

    This dependency intentionally accepts only the authenticated tenant. No
    host, database, or secret reference can be supplied by an HTTP request.
    """
    from fastapi import HTTPException
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from uuid import UUID

    row = (
        control_db.query(TenantDataPlane)
        .filter(
            TenantDataPlane.tenant_id == UUID(str(ctx.tenant_id)),
            TenantDataPlane.status == "ACTIVE",
        )
        .first()
    )
    if row is None:
        # Every organization is registered (migration md20 registers new ones on the shared plane); one without an
        # ACTIVE plane (retired, suspended, failed) gets no business data.
        raise HTTPException(
            503, detail={"code": "DATA_PLANE_UNAVAILABLE", "message": "No active tenant data plane is registered"}
        )
    if row.connection_secret_ref == TRIAL_SHARED_DATA_PLANE:
        yield control_db
        return
    try:
        factory = session_factory(row.database_ref, row.connection_secret_ref)
        schema_ok = plane_schema_ok(row.database_ref, row.connection_secret_ref)
        db = factory()
    except Exception as exc:
        raise HTTPException(
            503, detail={"code": "DATA_PLANE_UNAVAILABLE", "message": "Tenant data plane is unavailable"}
        ) from exc
    if not schema_ok:
        db.close()
        raise HTTPException(
            503,
            detail={"code": "DATA_PLANE_SCHEMA_OUTDATED", "message": "Tenant data plane is being upgraded; try again"},
        )
    from backend.app.db.tenant_scope import bind_tenant

    # The plane enforces the same row-level security as the shared database, for this organization only.
    bind_tenant(db, UUID(str(ctx.tenant_id)))
    try:
        yield db
    finally:
        db.close()


_SCHEMA_CHECKED: dict[str, tuple[float, bool]] = {}
SCHEMA_CHECK_SECONDS = 60


@lru_cache(maxsize=1)
def schema_head() -> str:
    """The migration head this code expects (the control database and every dedicated plane must be at it)."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[3]
    return ScriptDirectory.from_config(Config(str(root / "alembic.ini"))).get_current_head()


def plane_schema_ok(database_ref: str, secret_ref: str) -> bool:
    """A dedicated plane serves requests only at the code's migration head (scripts/migrate_data_planes.py).

    A plane built by the older scripts records no revision; it is accepted in local development only. The answer is
    cached for a minute per plane."""
    import time

    from sqlalchemy import text

    cached = _SCHEMA_CHECKED.get(database_ref)
    if cached and time.monotonic() - cached[0] < SCHEMA_CHECK_SECONDS:
        return cached[1]
    db = session_factory(database_ref, secret_ref)()
    try:
        revision = (
            db.execute(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")).scalar()
            and db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        )
        ok = revision == schema_head() if revision else is_local()
    except Exception:
        ok = False
    finally:
        db.close()
    _SCHEMA_CHECKED[database_ref] = (time.monotonic(), ok)
    return ok


@lru_cache(maxsize=32)
def session_factory(database_ref: str, secret_ref: str) -> sessionmaker[Session]:
    """Return a cached SQLAlchemy session factory for an approved data plane."""
    url = _secret_url(secret_ref)
    engine = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        pool_size=int(os.getenv("MDARIX_DATA_PLANE_POOL_SIZE", "3")),
        max_overflow=int(os.getenv("MDARIX_DATA_PLANE_MAX_OVERFLOW", "5")),
        connect_args=connect_args(),
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def data_plane_session(database_ref: str, secret_ref: str):
    """Yield a tenant data-plane session for trusted server-side metadata."""
    factory = session_factory(database_ref, secret_ref)
    db = factory()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def open_tenant_data_session(tenant_id):
    """A session on one tenant's business data for work outside a request, such as a background step after an
    import. Resolved from the registry exactly like get_data_plane_db: the shared plane is the control database
    bound to the tenant (row-level security); a dedicated plane is its own database, bound the same way. A tenant
    without an ACTIVE plane raises RuntimeError("DATA_PLANE_UNAVAILABLE:...")."""
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system, bind_tenant

    control = SessionLocal()
    try:
        bind_system(control, "background job: resolve the tenant's data plane")
        row = (
            control.query(TenantDataPlane)
            .filter(TenantDataPlane.tenant_id == tenant_id, TenantDataPlane.status == "ACTIVE")
            .first()
        )
        if row is None:
            raise RuntimeError(f"DATA_PLANE_UNAVAILABLE:{tenant_id}")
        if row.connection_secret_ref == SHARED_CONTROL_DATA_PLANE:
            control.commit()
            bind_tenant(control, tenant_id)
            yield control
            return
        if not plane_schema_ok(row.database_ref, row.connection_secret_ref):
            raise RuntimeError(f"DATA_PLANE_SCHEMA_OUTDATED:{tenant_id}")
        db = session_factory(row.database_ref, row.connection_secret_ref)()
        bind_tenant(db, tenant_id)
        try:
            yield db
        finally:
            db.close()
    finally:
        control.close()


@contextmanager
def tenant_data_session(tenant_id):
    """open_tenant_data_session for request handlers that name a tenant (platform and admin screens): an unknown
    tenant, or one without an active plane, is 404; a plane whose schema is behind is 503."""
    from fastapi import HTTPException

    try:
        with open_tenant_data_session(tenant_id) as session:
            yield session
    except RuntimeError as exc:
        if str(exc).startswith("DATA_PLANE_SCHEMA_OUTDATED"):
            raise HTTPException(
                503,
                detail={"code": "DATA_PLANE_SCHEMA_OUTDATED", "message": "Tenant data plane is being upgraded"},
            ) from exc
        if str(exc).startswith("DATA_PLANE_UNAVAILABLE"):
            raise HTTPException(
                404,
                detail={"code": "TENANT_DATA_NOT_AVAILABLE", "message": "This organization's data is not available"},
            ) from exc
        raise
