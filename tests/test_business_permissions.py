"""Role permissions on business actions: Viewers are read-only; every write, AI or export route is guarded."""

import re
import secrets
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.access.permissions import AI_RUN, DATA_EXPORT, RECORDS_WRITE, permissions_for_role
from backend.app.db.models.foundation import AuthUser, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.route_inventory import api_routes

ADMIN_PREFIXES = (
    "/api/v1/platform-admin",
    "/api/v1/platform/",
    "/api/v1/admin",
    "/api/v1/auth",
    "/api/v1/me",
    "/api/v1/customer-admin",
)
# Business routes that change state but are governed another way. Every entry needs a reason.
EXEMPT = {
    ("POST", "/api/v1/communication/resend/webhook"): "provider webhook, verified by signature",
    ("POST", "/api/v1/stage3/resend/webhook"): "provider webhook, verified by signature",
    ("POST", "/api/v1/governance/decisions/{decision_id}/sign"): "approval authority + segregation of duties",
    ("POST", "/api/v1/investigations/decisions/{decision_id}/reviews"): "approval authority + segregation of duties",
    ("POST", "/api/v1/regulatory/documents/{document_id}/status"): "checked in the route: approval permission + SoD",
    ("PUT", "/api/v1/workspace/context"): "the user's own workspace preferences",
    ("POST", "/api/v1/workspace/context/reset"): "the user's own workspace preferences",
    ("POST", "/api/v1/stage3/interactions/{interaction_id}/feedback"): "feedback on the user's own AI answer",
    ("POST", "/api/v1/trial/team"): "trial owner only, checked in the route",
    ("POST", "/api/v1/trial/team/{user_id}/resend-invitation"): "trial owner only, checked in the route",
    ("GET", "/api/v1/stage3/compliance-report"): "administrators only, checked in the route",
    ("GET", "/api/v1/reports/catalog"): "read-only list of report types",
    ("POST", "/api/v1/ask/"): "AI permission checked in the route (Ask resolves its own session)",
    ("GET", "/api/v1/stage3/reports/jobs/{job_id}"): "read-only job status; the download is guarded",
    ("GET", "/api/v1/trial/templates/{entity}.csv"): "blank CSV template, no customer data",
    ("GET", "/api/v1/data/import/templates/{entity}.csv"): "blank CSV template, no customer data",
    ("POST", "/api/v1/public/demo-requests"): "public website form; stores contact details only, rate limited",
    ("POST", "/api/v1/trial/feedback"): "the trial user's own feedback; trial workspaces only, checked in the route",
    ("POST", "/api/v1/trial/feedback/{feedback_id}/withdraw-consent"): "the user's own feedback only",
    ("POST", "/api/v1/client-errors"): "public error-boundary telemetry; size bounded and rate limited by source",
    ("POST", "/api/v1/support/problems"): "authenticated user's own tenant-scoped support report",
}


def _is_guarded(route) -> bool:
    return any("require_permission" in getattr(dep.dependency, "__qualname__", "") for dep in route.dependencies)


def _business_actions():
    for path, route in api_routes(app):
        if path.startswith(ADMIN_PREFIXES) or not path.startswith("/api/v1/"):
            continue
        for method in sorted(route.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
            exporting = method == "GET" and re.search(r"export|download|dossier|report|\.csv|estar", path)
            if method != "GET" or exporting:
                yield method, path, route


def test_every_business_write_ai_or_export_route_is_guarded_or_explicitly_exempt():
    # The sweep must actually see the routes (a broken route walker would otherwise pass vacuously).
    assert sum(1 for *_, route in _business_actions() if _is_guarded(route)) >= 28
    unguarded = [
        f"{method} {path}"
        for method, path, route in _business_actions()
        if not _is_guarded(route) and (method, path) not in EXEMPT
    ]
    assert unguarded == [], "Add require_permission(...) or a reviewed EXEMPT entry for: " + ", ".join(unguarded)


def _client_with_role(role: str) -> TestClient:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=f"perm-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role} user",
            company="Test",
            password_hash=_hash("Permission test 2026!"),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, user.tenant_id)
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client


def _call(client: TestClient, method: str, path: str):
    url = re.sub(r"\{[^}]+\}", lambda m: "products" if m.group(0) == "{entity}" else str(uuid.uuid4()), path)
    return client.request(method, url, json={})


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("Viewer", set()),
        ("Investigator", {RECORDS_WRITE, AI_RUN, DATA_EXPORT}),
        ("CUSTOMER_ADMIN", {DATA_EXPORT}),
        ("Something custom", set()),
    ],
)
def test_role_permissions(role, allowed):
    assert permissions_for_role(role) == allowed


def test_a_viewer_is_refused_on_every_guarded_route():
    viewer = _client_with_role("Viewer")
    allowed = []
    for method, path, route in _business_actions():
        if not _is_guarded(route):
            continue
        response = _call(viewer, method, path)
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else None
        if not (response.status_code == 403 and code == "PERMISSION_DENIED"):
            allowed.append(f"{method} {path} -> {response.status_code}")
    assert allowed == []


def test_an_investigator_passes_the_permission_check():
    investigator = _client_with_role("Investigator")
    response = _call(investigator, "POST", "/api/v1/investigations/{investigation_id}/analysis")
    assert not (response.status_code == 403 and response.json()["detail"].get("code") == "PERMISSION_DENIED")
