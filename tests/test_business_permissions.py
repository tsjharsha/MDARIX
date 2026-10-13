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
from backend.app.request_context import get_request_context
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
    ("POST", "/api/v1/cells/enroll"): "a tenant cell, not a person: the one-time enrollment token from its signed "
    "bundle (backend/app/cell_link_api.py)",
    ("POST", "/api/v1/cells/heartbeat"): "a tenant cell, not a person: its credential and, through the front door, "
    "its client certificate (backend/app/cell_link_api.py)",
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
    # "report" in "reportability": reads open to every member, like the complaint list; no export, no file.
    ("GET", "/api/v1/complaints/reportability"): "read-only reportability watch of the organization's complaints",
    ("GET", "/api/v1/complaints/reportability-settings"): "read-only reporting windows of the organization",
    ("POST", "/api/v1/ask/"): "AI permission checked in the route (Ask resolves its own session)",
    ("GET", "/api/v1/stage3/reports/jobs/{job_id}"): "read-only job status; the download is guarded",
    ("GET", "/api/v1/trial/templates/{entity}.csv"): "blank CSV template, no customer data",
    ("GET", "/api/v1/data/import/templates/{entity}.csv"): "blank CSV template, no customer data",
    ("POST", "/api/v1/public/demo-requests"): "public website form; stores contact details only, rate limited",
    ("POST", "/api/v1/trial/feedback"): "the trial user's own feedback; trial workspaces only, checked in the route",
    ("POST", "/api/v1/trial/feedback/{feedback_id}/withdraw-consent"): "the user's own feedback only",
    (
        "POST",
        "/api/v1/trial/demo-request",
    ): "the trial user's own demo request; trial workspaces only, checked in the route",
    (
        "POST",
        "/api/v1/trial/exit-request",
    ): "the owner's own request to end the trial; owner only, checked in the route",
    ("POST", "/api/v1/trial/exit-request/withdraw"): "the owner's own request; owner only, checked in the route",
    ("POST", "/api/v1/client-errors"): "public by design: the browser's error boundary reports from the sign-in page "
    "and after a session ended; stores no business data, body capped, rate limited per address",
    (
        "POST",
        "/api/v1/support/problems",
    ): "any signed-in user may report a problem (session required, own organization)",
    # My Work (backend/app/workflow/router.py): who may act on a task depends on the task (its assignee, the
    # permission of its type, investigation.assign to reassign), so each route checks it itself.
    ("POST", "/api/v1/tasks/{task_id}/accept"): "checked in the route: only the task's assignee",
    ("POST", "/api/v1/tasks/{task_id}/decline"): "checked in the route: only the task's assignee",
    ("POST", "/api/v1/tasks/{task_id}/claim"): "checked in the route: the task type's permission",
    ("POST", "/api/v1/tasks/{task_id}/release"): "checked in the route: only the task's assignee",
    ("POST", "/api/v1/tasks/{task_id}/reassign"): "checked in the route: investigation.assign",
    ("POST", "/api/v1/tasks/{task_id}/complete"): "checked in the route: only the task's assignee",
    # Case workflow (backend/app/case_workflow/router.py): the permission depends on the state asked for.
    (
        "POST",
        "/api/v1/investigations/{investigation_id}/transition",
    ): "checked in the route: investigation.work to start or hold a case, investigation.assign to cancel it",
    # Case reviews (backend/app/case_reviews/router.py): who may act depends on the review (the permission of its
    # type, its reviewer, its requester or investigation.assign), so each route checks it itself.
    ("POST", "/api/v1/case-reviews/{review_id}/start"): "checked in the route: the review type's permission",
    ("POST", "/api/v1/case-reviews/{review_id}/complete"): "checked in the route: only the review's reviewer",
    ("POST", "/api/v1/case-reviews/{review_id}/recuse"): "checked in the route: only the review's reviewer",
    ("POST", "/api/v1/case-reviews/{review_id}/cancel"): "checked in the route: requester or investigation.assign",
    # Decision follow-ups (backend/app/decision_followups/followups.py): the person a follow-up is assigned to (or,
    # with nobody named, anyone holding its role) works on it, whatever their permissions, so the route checks it.
    ("POST", "/api/v1/follow-ups/{follow_up_id}/start"): "checked in the route: the assignee or its role",
    ("POST", "/api/v1/follow-ups/{follow_up_id}/complete"): "checked in the route: the assignee or its role",
    # Evidence requests to a colleague (backend/app/evidence_workflow/requests.py): who may act depends on the request
    # (the person or role asked, its requester, or a permission), so each route checks it itself.
    (
        "POST",
        "/api/v1/evidence-requests/{request_id}/acknowledge",
    ): "checked in the route: only the person or role asked",
    ("POST", "/api/v1/evidence-requests/{request_id}/respond"): "checked in the route: only the person or role asked",
    (
        "POST",
        "/api/v1/evidence-requests/{request_id}/cannot-provide",
    ): "checked in the route: only the person or role asked",
    (
        "POST",
        "/api/v1/evidence-requests/{request_id}/cancel",
    ): "checked in the route: the requester or investigation.assign",
    (
        "POST",
        "/api/v1/evidence-requests/{request_id}/attachments",
    ): "checked in the route: the requester or the person asked",
    (
        "POST",
        "/api/v1/evidence-requests/{request_id}/review",
    ): "checked in the route: the requester or evidence.review",
    # The human decision (backend/app/human_decision/router.py): signing is checked in the route as legacy signing is
    # (no administrator, the signature entitlement, approval authority, segregation of duties, password and MFA).
    (
        "POST",
        "/api/v1/investigations/{investigation_id}/decision/sign",
    ): "approval authority + segregation of duties + re-authentication",
}
# Exempt routes that must still refuse anyone without a session: the exemption is from the business permission,
# never from authentication.
EXEMPT_BUT_SIGNED_IN = {
    ("POST", "/api/v1/support/problems"),
    ("POST", "/api/v1/investigations/{investigation_id}/decision/sign"),
}


def _is_guarded(route) -> bool:
    # require_permission(one) or require_any_permission(several): both refuse without the permission.
    return any(
        name in getattr(dep.dependency, "__qualname__", "")
        for dep in route.dependencies
        for name in ("require_permission", "require_any_permission")
    )


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


def _requires_session(dependant) -> bool:
    """True when the route (or any dependency it pulls in) resolves the signed-in request context."""
    return any(
        dep.call is get_request_context or _requires_session(dep) for dep in getattr(dependant, "dependencies", [])
    )


def test_exempt_routes_that_need_a_session_require_one():
    routes = {(method, path): route for method, path, route in _business_actions()}
    for key in EXEMPT_BUT_SIGNED_IN:
        assert key in routes, f"{key} is no longer a route; update EXEMPT_BUT_SIGNED_IN"
        assert _requires_session(routes[key].dependant), f"{key} must depend on get_request_context"
        method, path = key
        anonymous = TestClient(app).request(method, path, json={"summary": "s", "details": "d"})
        assert anonymous.status_code == 401, f"{key} answered {anonymous.status_code} without a session"


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
        # Phase 1 workflow permissions are added to the Investigator's original three; none is taken away.
        (
            "Investigator",
            {
                RECORDS_WRITE,
                AI_RUN,
                DATA_EXPORT,
                "investigation.create",
                "investigation.work",
                "evidence.review",
                "evidence.request",
            },
        ),
        # Investigator-level rights in the workspace; never regulatory approval (decision of 2026-10).
        ("CUSTOMER_ADMIN", {RECORDS_WRITE, AI_RUN, DATA_EXPORT}),
        ("Customer Administrator", {RECORDS_WRITE, AI_RUN, DATA_EXPORT}),
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
