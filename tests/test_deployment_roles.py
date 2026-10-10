"""One codebase, three deployment roles (ADR-013, backend/app/deployment_role.py).

MULTI is today's deployment and the default. A PLATFORM serves platform administration and signs in platform staff
only; a CELL serves one organization's workspace and administration and never platform staff. A route the role does
not serve answers 404 before any handler runs, an account the role does not serve cannot sign in and its session is
refused, the scheduler runs only the role's jobs, and the configuration check names what each role needs.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import deployment_role as roles
from backend.app import scheduler
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_mapping_release_self_approval import _admin, _organization

PLATFORM_PATH = "/api/v1/platform-admin/customers"
WORKSPACE_PATH = "/api/v1/investigations/mine/summary"
CONTEXT = "/api/v1/session/context"


def _set_role(monkeypatch, role: str, tenant=None) -> None:
    monkeypatch.setenv("MDARIX_DEPLOYMENT_ROLE", role)
    if tenant is None:
        monkeypatch.delenv("MDARIX_CELL_TENANT_ID", raising=False)
        monkeypatch.delenv("MDARIX_CELL_TENANT_KEY", raising=False)
    else:
        monkeypatch.setenv("MDARIX_CELL_TENANT_ID", str(tenant.id))
        monkeypatch.setenv("MDARIX_CELL_TENANT_KEY", tenant.tenant_key)
        # A cell reports to the platform (backend/app/cell_link.py).
        monkeypatch.setenv("MDARIX_PLATFORM_URL", "https://platform.test")
        # A cell pins the platform's package-signing key (backend/app/cell_packages.py).
        from backend.app.cell_packages import generate_keypair

        monkeypatch.setenv("MDARIX_PLATFORM_SIGNING_PUBLIC_KEY", generate_keypair()[1])


def _tenant(tenant_id) -> Tenant:
    db = SessionLocal()
    try:
        bind_system(db, "test: read an organization")
        row = db.query(Tenant).filter(Tenant.id == uuid.UUID(str(tenant_id))).one()
        db.expunge(row)
        return row
    finally:
        db.close()


def _email(user_id) -> str:
    db = SessionLocal()
    try:
        bind_system(db, "test: read an account's email")
        return db.query(AuthUser.username).filter(AuthUser.id == user_id).scalar()
    finally:
        db.close()


def test_every_route_has_a_kind_and_each_role_serves_its_share(monkeypatch):
    paths = list(app.openapi()["paths"])
    kinds = {path: roles.route_kind(path) for path in paths}
    assert kinds["/health/live"] == roles.OPS
    assert kinds["/api/v1/auth/signin"] == roles.SHARED
    assert kinds["/api/v1/public/site-info"] == roles.SHARED
    assert kinds[PLATFORM_PATH] == roles.PLATFORM_ROUTES
    assert kinds[WORKSPACE_PATH] == roles.WORKSPACE
    assert all(kind == roles.PLATFORM_ROUTES for path, kind in kinds.items() if path.startswith("/api/v1/platform"))
    assert all(kind == roles.SHARED for path, kind in kinds.items() if path.startswith("/api/v1/admin/"))
    platform = {path for path, kind in kinds.items() if kind == roles.PLATFORM_ROUTES}
    workspace = {path for path, kind in kinds.items() if kind == roles.WORKSPACE}
    sandbox = {path for path, kind in kinds.items() if kind == roles.SANDBOX}
    assert len(platform) > 50 and len(workspace) > 100 and sandbox

    _set_role(monkeypatch, "MULTI")
    assert {path for path in paths if roles.serves_path(path)} == set(paths)
    _set_role(monkeypatch, "CELL")
    served = {path for path in paths if roles.serves_path(path)}
    assert served == set(paths) - platform - sandbox
    _set_role(monkeypatch, "PLATFORM")
    served = {path for path in paths if roles.serves_path(path)}
    assert served == set(paths) - workspace - sandbox


def test_a_route_the_role_does_not_serve_answers_404_before_any_handler(monkeypatch):
    anonymous = TestClient(app)
    trial_path = next(path for path in app.openapi()["paths"] if path.startswith("/api/v1/trial/"))

    _set_role(monkeypatch, "MULTI")
    assert anonymous.get(PLATFORM_PATH).status_code == 401
    assert anonymous.get(WORKSPACE_PATH).status_code == 401

    _set_role(monkeypatch, "CELL")
    refused = anonymous.get(PLATFORM_PATH)
    assert refused.status_code == 404 and refused.json()["detail"]["code"] == "NOT_SERVED_BY_THIS_DEPLOYMENT"
    assert anonymous.get(trial_path).status_code == 404
    assert anonymous.get(WORKSPACE_PATH).status_code == 401
    assert anonymous.get("/health/live").status_code == 200

    _set_role(monkeypatch, "PLATFORM")
    assert anonymous.get(WORKSPACE_PATH).status_code == 404
    assert anonymous.get(PLATFORM_PATH).status_code == 401
    assert anonymous.get("/health/live").status_code == 200


def test_a_cell_signs_in_only_its_own_organization_and_the_platform_only_platform_staff(monkeypatch):
    organization = _tenant(_organization())
    other = _tenant(_organization())
    admin, admin_id = _admin(str(organization.id))
    credentials = {"email": _email(admin_id), "password": "Release test 2026!"}
    anonymous = TestClient(app)

    _set_role(monkeypatch, "MULTI")
    assert anonymous.post("/api/v1/auth/signin", json=credentials).status_code == 200
    _set_role(monkeypatch, "CELL", organization)
    assert anonymous.post("/api/v1/auth/signin", json=credentials).status_code == 200
    assert admin.get(CONTEXT).status_code == 200
    _set_role(monkeypatch, "CELL", other)
    refused = anonymous.post("/api/v1/auth/signin", json=credentials)
    assert refused.status_code == 401 and refused.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert admin.get(CONTEXT).status_code == 401
    _set_role(monkeypatch, "PLATFORM")
    assert anonymous.post("/api/v1/auth/signin", json=credentials).status_code == 401
    assert admin.get(CONTEXT).status_code == 401

    # Platform staff: served by MULTI and PLATFORM, never by a cell, whatever database their session is in.
    platform_admin = authenticated_client()
    staff_tenant = _tenant(platform_admin.get(CONTEXT).json()["tenant_id"])
    assert platform_admin.get(CONTEXT).status_code == 200
    _set_role(monkeypatch, "CELL", staff_tenant)
    assert platform_admin.get(CONTEXT).status_code == 401
    _set_role(monkeypatch, "MULTI")
    assert platform_admin.get(CONTEXT).json()["deployment_role"] == "MULTI"


def test_the_scheduler_runs_only_the_jobs_its_role_owns(monkeypatch):
    names = {job.name for job in scheduler.JOBS}
    _set_role(monkeypatch, "MULTI")
    # Everything but the cell's call home: a MULTI deployment is its own platform.
    assert {job.name for job in scheduler.active_jobs()} == names - {"platform-sync"}
    _set_role(monkeypatch, "CELL")
    cell = {job.name for job in scheduler.active_jobs()}
    assert {"signal_detection", "connector-sync", "embedding-catch-up", "audit-chain-verification"} <= cell
    assert not {"tenant-lifecycle", "subscription-lifecycle", "trial-reminders", "trial-retention"} & cell
    _set_role(monkeypatch, "PLATFORM")
    platform = {job.name for job in scheduler.active_jobs()}
    assert {"tenant-lifecycle", "subscription-lifecycle", "operations-alerts", "audit-chain-verification"} <= platform
    assert not {"signal_detection", "connector-sync", "embedding-catch-up", "export-expiry"} & platform
    assert cell | platform == names


def test_the_configuration_check_names_what_each_role_needs(monkeypatch):
    from backend.app.config_check import _cell_tenant_problem, _deployment_role_problems

    monkeypatch.delenv("MDARIX_DATA_PLANE_R1_TENANT_1_DATABASE_URL", raising=False)
    _set_role(monkeypatch, "MULTI")
    organization = _tenant(_organization())  # through platform administration, which only MULTI and PLATFORM serve
    assert _deployment_role_problems() == []
    monkeypatch.setenv("MDARIX_DEPLOYMENT_ROLE", "SOMETHING")
    assert "MULTI, PLATFORM or CELL" in _deployment_role_problems()[0]
    with pytest.raises(RuntimeError):
        roles.deployment_role()

    _set_role(monkeypatch, "CELL")
    monkeypatch.delenv("MDARIX_PLATFORM_SIGNING_PUBLIC_KEY", raising=False)
    problems = " ".join(_deployment_role_problems())
    assert "MDARIX_CELL_TENANT_ID" in problems and "MDARIX_CELL_TENANT_KEY" in problems
    assert "MDARIX_PLATFORM_SIGNING_PUBLIC_KEY" in problems
    _set_role(monkeypatch, "CELL", organization)
    assert _deployment_role_problems() == []
    monkeypatch.setenv("MDARIX_PLATFORM_SIGNING_PUBLIC_KEY", "not-a-key")
    assert "MDARIX_PLATFORM_SIGNING_PUBLIC_KEY" in _deployment_role_problems()[0]
    monkeypatch.setenv("MDARIX_PLATFORM_SIGNING_PUBLIC_KEY", "AAAA")  # base64, but not 32 bytes
    assert "32 bytes" in _deployment_role_problems()[0]
    _set_role(monkeypatch, "CELL", organization)
    assert _cell_tenant_problem() is None
    monkeypatch.setenv("MDARIX_DATA_PLANE_R1_TENANT_1_DATABASE_URL", "postgresql+pg8000://x:y@localhost/z")
    assert "one database" in _deployment_role_problems()[0]
    monkeypatch.delenv("MDARIX_DATA_PLANE_R1_TENANT_1_DATABASE_URL")
    monkeypatch.setenv("MDARIX_CELL_TENANT_KEY", "SOME_OTHER_KEY")
    assert "does not match" in (_cell_tenant_problem() or "")
    monkeypatch.setenv("MDARIX_CELL_TENANT_ID", str(uuid.uuid4()))
    assert "does not hold" in (_cell_tenant_problem() or "")

    _set_role(monkeypatch, "PLATFORM")
    monkeypatch.setenv("MDARIX_CELL_TENANT_ID", str(organization.id))
    assert "for a CELL" in _deployment_role_problems()[0]
