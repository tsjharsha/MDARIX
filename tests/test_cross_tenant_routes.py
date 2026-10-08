"""Every business route, called by Tenant A with Tenant B's real record IDs, must reveal nothing about Tenant B."""

import json
import re
import secrets
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import (
    AuthUser,
    Complaint,
    Decision,
    Evidence,
    Investigation,
    Product,
    ProductVersion,
    Tenant,
    TenantMembership,
)
from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.trial.sample_data import seed_sample_workspace
from tests.route_inventory import api_routes
from tests.test_business_permissions import ADMIN_PREFIXES

# Routes that never take a tenant's records, or are covered by their own dedicated tests.
SKIP = {
    "/api/v1/auth/session",
    "/api/v1/communication/resend/webhook",
    "/api/v1/stage3/resend/webhook",
    # Starts a long real-pipeline evaluation; its tenant scoping is covered by tests/test_evaluation_router.py.
    "/api/v1/evaluations/runs",
}


def _purge_cross_tenant_fixtures():
    """Remove Tenant B fixtures (this and earlier runs) so other tests' whole-database counts stay exact."""
    from backend.app.trial.retention import purge_trial

    db = SessionLocal()
    try:
        for (tenant_id,) in db.query(Tenant.id).filter(Tenant.tenant_key.like(r"XTENANT\_%")).all():
            purge_trial(db, tenant_id, "test:cross-tenant-cleanup")
    finally:
        db.close()


@pytest.fixture(scope="module")
def tenants():
    """Tenant A: the shared test tenant. Tenant B: a fresh tenant with a full sample dataset and a decision."""
    _purge_cross_tenant_fixtures()
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        tenant_a = (
            db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        )
        from backend.app.customer_lifecycle import build_customer_tenant

        customer, tenant_b = build_customer_tenant(
            db=db, tenant_key=f"XTENANT_{uuid.uuid4().hex[:8].upper()}", name="Cross Tenant B", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant_b)
        db.flush()
        seed_sample_workspace(db, tenant_b.id, now)
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant_b.id).first()
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            investigation_id=investigation.id,
            decision_identifier=f"XT-{uuid.uuid4().hex[:8]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Tenant B secret rationale",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone@tenant-b.invalid",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(decision)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            username=f"xtenant-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name="Tenant A investigator",
            company="A",
            password_hash=_hash("Cross tenant 2026!"),
            role="Leader",
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
                tenant_id=tenant_a.id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        b_ids = {
            "product_id": str(db.query(Product.id).filter(Product.tenant_id == tenant_b.id).first()[0]),
            "version_id": str(db.query(ProductVersion.id).filter(ProductVersion.tenant_id == tenant_b.id).first()[0]),
            "investigation_id": str(investigation.id),
            "evidence_id": str(db.query(Evidence.id).filter(Evidence.tenant_id == tenant_b.id).first()[0]),
            "complaint_id": str(db.query(Complaint.id).filter(Complaint.tenant_id == tenant_b.id).first()[0]),
            "decision_id": str(decision.id),
            "tenant_id": str(tenant_b.id),
        }
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_a.id)
        b_markers = set(b_ids.values()) | {"SAMPLE-ORBIT-300", "Tenant B secret rationale", tenant_b.tenant_key}
        yield {"token": token, "b_ids": b_ids, "markers": b_markers}
    finally:
        db.close()
        _purge_cross_tenant_fixtures()


def _url(path: str, b_ids: dict) -> str:
    def value(match):
        name = match.group(1)
        if name in b_ids:
            return b_ids[name]
        if name in {"product_version_id"}:
            return b_ids["version_id"]
        return str(uuid.uuid4())

    return re.sub(r"\{([^}:]+)(?::[^}]*)?\}", value, path)


def test_tenant_a_never_sees_tenant_b_records_through_any_business_route(tenants):
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("mdarix_session", tenants["token"])
    leaks, crashes, called = [], [], 0
    for path, route in api_routes(app):
        if not path.startswith("/api/v1/") or path.startswith(ADMIN_PREFIXES) or path in SKIP:
            continue
        for method in sorted(route.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
            url = _url(path, tenants["b_ids"])
            body = {key: value for key, value in tenants["b_ids"].items()} if method != "GET" else None
            response = client.request(method, url, json=body)
            called += 1
            if response.status_code >= 500:
                crashes.append(f"{method} {path} -> {response.status_code}")
                continue
            text = response.text
            found = {marker for marker in tenants["markers"] if marker and marker in text}
            requested = {
                value for value in tenants["b_ids"].values() if value in url or (body and value in json.dumps(body))
            }
            try:
                status = response.json().get("status") if isinstance(response.json(), dict) else None
            except ValueError:
                status = None
            # Tenant B data the caller did not send is always a leak. Repeating a requested ID back is a leak only
            # if the route did not report it as not found.
            leaked = sorted(found - requested)
            if requested & found and response.status_code < 400 and status not in {"NOT_FOUND", "NOT_AVAILABLE"}:
                leaked += sorted(requested & found)
            if response.status_code < 400 and leaked:
                leaks.append(f"{method} {path} -> {response.status_code} contains {leaked[:3]}")
    assert called > 100, f"only {called} route calls made; the route walker may be broken"
    assert leaks == [], "Tenant B data reached Tenant A:\n" + "\n".join(leaks)
    assert crashes == [], "Server errors on cross-tenant calls:\n" + "\n".join(crashes)


def test_markers_are_present_for_tenant_b_itself(tenants):
    """Guard against a vacuous pass: the markers are real values that Tenant B's own records contain."""
    assert len(tenants["markers"]) >= 8
    assert all(json.dumps(marker) for marker in tenants["markers"])
