"""Free trial end to end: request -> Platform Admin approval -> activation -> sample workspace -> CSV import."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from auth.durable import issue_invitation
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuthUser, Complaint, Product, Tenant
from backend.app.db.models.stage2 import OnboardingRequest, SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.trial.service import trial_subscription
from backend.app.db.session import engine
from tests.conftest import authenticated_client

PASSWORD = "Trial password 2026!"

# Business tables a trial workspace writes to, children first. Other tests count rows in some of these across the
# whole test database, so trial workspaces created here must not leave business data behind.
_TRIAL_BUSINESS_TABLES = (
    "retrieval_queries",  # Ask logs its evidence search against the investigation
    "evidence_entity_links",  # imported records are linked to their evidence for AI search
    "evidence_chunk_embeddings",
    "evidence_chunks",
    "investigation_evidence",
    "investigation_complaints",
    "evidence",
    "investigations",
    "complaints",
    "lot_batches",
    "product_components",
    "component_suppliers",
    "components",
    "product_versions",
    "products",
    "suppliers",
    "changes",
    "manufacturing_sites",
)


def _purge_trial_business_data():
    with engine.begin() as connection:
        for table in _TRIAL_BUSINESS_TABLES:
            connection.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN (SELECT id FROM tenants WHERE tenant_key LIKE :pattern)"),
                {"pattern": "TRIAL\\_%"},
            )


@pytest.fixture(autouse=True, scope="module")
def _clean_trial_workspaces():
    _purge_trial_business_data()
    yield
    _purge_trial_business_data()


def _request_trial(organization="Trial Devices Inc") -> str:
    email = f"trial-{uuid.uuid4().hex[:10]}@example.invalid"
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Taylor Quality", "organization": organization},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ONBOARDING_REQUEST_ACCEPTED"
    return email


def _request_id(admin, email) -> str:
    items = admin.get("/api/v1/platform-admin/trial-requests").json()["items"]
    return next(item["id"] for item in items if item["email"] == email)


def _activation_token(approval: dict, email: str) -> str:
    if approval.get("activation_path"):
        return parse_qs(urlparse(approval["activation_path"]).query)["token"][0]
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.username == email).one()
        return issue_invitation(db, user.id, user.tenant_id)
    finally:
        db.close()


def _approved_trial_client():
    admin = authenticated_client()
    email = _request_trial()
    approval = admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve")
    assert approval.status_code == 200, approval.text
    body = approval.json()
    user = TestClient(app)
    activated = user.post(
        "/api/v1/auth/activate-account", json={"token": _activation_token(body, email), "password": PASSWORD}
    )
    assert activated.status_code == 200, activated.text
    signed_in = user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    return user, body, email


def test_signup_no_longer_needs_a_password_and_creates_nothing_but_a_request():
    email = _request_trial()
    db = SessionLocal()
    try:
        row = db.query(OnboardingRequest).filter(OnboardingRequest.email == email).one()
        assert row.status == "PENDING_REVIEW" and row.tenant_id is None
        assert db.query(AuthUser).filter(AuthUser.username == email).first() is None
    finally:
        db.close()


def test_only_platform_admins_can_review_trial_requests():
    email = _request_trial()
    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/platform-admin/trial-requests").status_code == 401
    admin = authenticated_client()
    request_id = _request_id(admin, email)
    assert anonymous.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve").status_code == 401


def test_approval_creates_a_private_trial_workspace_with_sample_data():
    user, approval, email = _approved_trial_client()
    assert approval["status"] == "APPROVED" and approval["tenant_key"].startswith("TRIAL_")
    db = SessionLocal()
    try:
        tenant_id = uuid.UUID(approval["tenant_id"])
        account = db.query(AuthUser).filter(AuthUser.username == email).one()
        assert account.tenant_id == tenant_id and account.role == "Leader" and account.status == "ACTIVE"
        subscription = trial_subscription(db, tenant_id)
        assert 29 <= (subscription.expires_at - datetime.now(timezone.utc)).days <= 30
        plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant_id).one()
        assert plane.status == "ACTIVE"
        assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 3
        assert db.query(Complaint).filter(Complaint.tenant_id == tenant_id).count() == 28
    finally:
        db.close()

    status = user.get("/api/v1/trial/status").json()
    assert status["is_trial"] and status["days_left"] == 30 and status["sample"]["products"] == 3
    # The workspace tells the trial team when its data will be deleted: 30 days after the trial ends.
    ends, deleted = (datetime.fromisoformat(status[key]) for key in ("expires_at", "data_deleted_at"))
    assert deleted - ends == timedelta(days=30)
    # The workspace dashboard reads the trial's own data, not another tenant's.
    counts = user.get("/api/v1/analytics/command-center").json()["counts"]
    assert counts["products"] == 3 and counts["complaints"] == 28
    insights = user.get("/api/v1/trial/insights").json()
    assert insights["scope"] == "sample data" and insights["findings"]


def test_a_request_cannot_be_approved_twice_or_after_decline():
    admin = authenticated_client()
    email = _request_trial()
    request_id = _request_id(admin, email)
    assert (
        admin.post(f"/api/v1/platform-admin/trial-requests/{request_id}/decline", json={"reason": "x"}).status_code
        == 422
    )
    declined = admin.post(
        f"/api/v1/platform-admin/trial-requests/{request_id}/decline", json={"reason": "Not a device company"}
    )
    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED"
    again = admin.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve")
    assert again.status_code == 409


def test_csv_import_checks_everything_before_saving():
    user, approval, _ = _approved_trial_client()
    template = user.get("/api/v1/trial/templates/products.csv")
    assert template.status_code == 200 and template.text.startswith("product_id,product_name,version")

    products = "product_id,product_name,version,version_release_date\nPUMP-1,Pump One,Rev A,2026-01-10\nPUMP-1,Pump One,Rev B,2026-06-01\n"
    check = user.post("/api/v1/trial/imports/products/check", content=products).json()
    assert check["ready"] and check["new_records"] == 3
    assert user.post("/api/v1/trial/imports/products", content=products).status_code == 200

    lots = "lot_id,product_id,version\nL-100,PUMP-1,Rev B\n"
    assert user.post("/api/v1/trial/imports/lots", content=lots).status_code == 200

    # Extra columns, unknown products and personal data are all refused, and nothing is saved.
    bad = "complaint_id,product_id,description,patient_name\nC-1,PUMP-1,Alarm,Jane\n"
    report = user.post("/api/v1/trial/imports/complaints/check", content=bad).json()
    assert not report["ready"] and "patient_name" in report["issues"][0]["message"]
    personal = (
        "complaint_id,product_id,description\n"
        "C-1,PUMP-1,Reported by Dr. Smith on 555-123-4567\n"
        "C-2,NOPE,Alarm sounded\n"
    )
    report = user.post("/api/v1/trial/imports/complaints/check", content=personal).json()
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert not report["ready"] and "personal data" in messages
    rejected = user.post("/api/v1/trial/imports/complaints", content=personal)
    assert rejected.status_code == 422

    good = (
        "complaint_id,product_id,description,version,lot_id,received_date\n"
        "C-1,PUMP-1,Occlusion alarm with no occlusion present,Rev B,L-100,2026-07-02\n"
        "C-2,PUMP-1,Occlusion alarm during setup,Rev B,L-100,2026-07-09\n"
    )
    imported = user.post("/api/v1/trial/imports/complaints", content=good)
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 2 and imported.json()["insights"]["scope"] == "your data"
    # Re-uploading updates instead of duplicating.
    assert user.post("/api/v1/trial/imports/complaints", content=good).json()["updated"] == 2
    status = user.get("/api/v1/trial/status").json()
    assert status["own_data"] == {"products": 1, "lots": 1, "complaints": 2}
    assert status["usage"]["rows"] == 6


def test_import_is_only_for_trial_workspaces():
    customer = authenticated_client()
    assert customer.get("/api/v1/trial/status").json() == {"is_trial": False}
    assert customer.post("/api/v1/trial/imports/products/check", content="product_id\n").status_code == 404


def test_trial_closes_on_its_end_date():
    user, approval, email = _approved_trial_client()
    db = SessionLocal()
    try:
        row = (
            db.query(SubscriptionLifecycle)
            .filter(SubscriptionLifecycle.tenant_id == uuid.UUID(approval["tenant_id"]))
            .one()
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert user.get("/api/v1/trial/status").status_code == 403
    again = TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert again.status_code == 403 and again.json()["detail"]["code"] == "TRIAL_ENDED"
    db = SessionLocal()
    try:
        # Ending the trial keeps the workspace and its data for conversion.
        assert db.query(Tenant).filter(Tenant.id == uuid.UUID(approval["tenant_id"])).one().status == "ACTIVE"
    finally:
        db.close()


def test_ask_mdarix_is_grounded_in_the_trial_sample_investigation():
    user, approval, _ = _approved_trial_client()
    db = SessionLocal()
    try:
        from backend.app.db.models.foundation import Investigation

        investigation = (
            db.query(Investigation)
            .filter(
                Investigation.tenant_id == uuid.UUID(approval["tenant_id"]),
                Investigation.investigation_identifier == "SAMPLE-INV-001",
            )
            .one()
        )
        investigation_id = str(investigation.id)
    finally:
        db.close()
    answer = user.post(
        "/api/v1/stage3/interactions",
        json={
            "prompt": "Why did pressure-alarm complaints rise after Rev B?",
            "investigation_id": investigation_id,
            "page_context": "ASK_MDARIX",
            "temporal_mode": "CURRENT",
        },
    )
    assert answer.status_code == 200, answer.text
    response = answer.json()["response"]
    assert response["grounding"]["tenant_scope_enforced"] is True
    cited = {item["evidence_identifier"] for item in response["sources_provenance"]}
    assert cited and all(identifier.startswith("SAMPLE-EV-") for identifier in cited)


def _activate_and_sign_in(email: str, token: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}).status_code == 200
    assert client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200
    return client


def test_trial_owner_invites_colleagues_up_to_the_user_limit():
    owner, approval, owner_email = _approved_trial_client()
    assert owner.get("/api/v1/trial/status").json()["is_owner"] is True

    first = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post("/api/v1/trial/team", json={"email": first, "display_name": "Casey Review"})
    assert invited.status_code == 200, invited.text
    second = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    assert owner.post("/api/v1/trial/team", json={"email": second, "display_name": "Robin QA"}).status_code == 200
    # Three users is the limit, an existing account cannot be invited again, and bad input is refused.
    full = owner.post("/api/v1/trial/team", json={"email": "extra@example.invalid", "display_name": "Extra"})
    assert full.status_code == 409 and full.json()["detail"]["code"] == "TRIAL_USER_LIMIT_REACHED"
    assert owner.post("/api/v1/trial/team", json={"email": owner_email, "display_name": "Me"}).status_code == 409

    roster = owner.get("/api/v1/trial/team").json()
    assert roster["seats_used"] == 3 and roster["can_invite"] is True
    assert [member["is_owner"] for member in roster["members"]].count(True) == 1

    colleague = _activate_and_sign_in(first, _activation_token(invited.json(), first))
    assert colleague.get("/api/v1/trial/status").json()["is_owner"] is False
    # A colleague works in the same workspace but cannot invite or administer.
    assert colleague.get("/api/v1/analytics/command-center").json()["counts"]["products"] == 3
    refused = colleague.post("/api/v1/trial/team", json={"email": "x@example.invalid", "display_name": "X"})
    assert refused.status_code == 403
    assert colleague.get("/api/v1/platform-admin/trial-requests").status_code == 403


def test_closed_trial_data_is_deleted_after_30_days():
    user, approval, email = _approved_trial_client()
    _recent, recent_approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for target, ended in (
            (tenant_id, now - timedelta(days=31)),
            (uuid.UUID(recent_approval["tenant_id"]), now - timedelta(days=10)),
        ):
            row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == target).one()
            row.expires_at = ended
        db.commit()
    finally:
        db.close()

    admin = authenticated_client()
    due = {item["tenant_id"] for item in admin.get("/api/v1/platform-admin/trial-retention").json()["due"]}
    assert approval["tenant_id"] in due and recent_approval["tenant_id"] not in due
    assert TestClient(app).post("/api/v1/platform-admin/trial-retention/run").status_code == 401
    run = admin.post("/api/v1/platform-admin/trial-retention/run").json()
    purged = next(item for item in run["trials"] if item["tenant_id"] == approval["tenant_id"])
    assert purged["deleted_records"]["products"] == 3 and purged["not_deleted_tables"] == []

    db = SessionLocal()
    try:
        assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 0
        assert db.query(Tenant).filter(Tenant.id == tenant_id).one().status == "ARCHIVED"
        # The trial's people are pseudonymized: their email address is gone and nobody can sign in.
        assert db.query(AuthUser).filter(AuthUser.username == email).count() == 0
        assert {user.status for user in db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id)} == {"REMOVED"}
        # The trial that closed 10 days ago keeps its data.
        assert db.query(Product).filter(Product.tenant_id == uuid.UUID(recent_approval["tenant_id"])).count() == 3
    finally:
        db.close()
    assert user.get("/api/v1/trial/status").status_code == 401
    assert TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code != 200
    queue = admin.get("/api/v1/platform-admin/trial-requests").json()["items"]
    assert next(item for item in queue if item["tenant_id"] == approval["tenant_id"])["data_deleted"] is True


def test_new_trial_request_alerts_the_platform_admin(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "auth.emailer.send_trial_request_alert", lambda recipient, **details: sent.append((recipient, details))
    )
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "admin-alerts@example.invalid")
    email = _request_trial("Alerted Devices")
    assert sent == [
        (
            "admin-alerts@example.invalid",
            {"organization": "Alerted Devices", "display_name": "Taylor Quality", "email": email},
        )
    ]
    # Repeating the same request does not alert again.
    again = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Taylor Quality", "organization": "Alerted Devices"},
    )
    assert again.status_code == 200 and len(sent) == 1


def test_a_failing_alert_never_breaks_sign_up(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("auth.emailer.send_trial_request_alert", boom)
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "admin-alerts@example.invalid")
    _request_trial("Resilient Devices")  # asserts the sign-up still succeeds
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "")
    monkeypatch.setattr("auth.emailer.send_trial_request_alert", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    _request_trial("Quiet Devices")  # no alert address configured: nothing is sent
