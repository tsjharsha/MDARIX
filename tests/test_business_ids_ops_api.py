"""Business identifiers (md26) in the platform operations API: trial and demo requests, support reports, feedback,
plans and subscriptions, provisioning, data exports, legal holds and the administrator read models.

The first tests check the response shapes without a database; the rest need the control-plane test database.
"""

import csv
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app import demo_requests, support_api
from backend.app.db.models.pilot_support import SupportProblemReport
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.tenant_export import READABLE_TABLES, describe, run_export
from backend.app.trial import feedback
from tests.conftest import authenticated_client
from tests.test_free_trial import PASSWORD, _activation_token, _purge_trial_business_data, _request_id, _request_trial
from tests.test_person_export import _client_in
from tests.test_support_problems import client_in_tenant, two_active_tenants
from tests.test_tenant_data import make_organization, use_local_storage


def _is(prefix: str, value) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"{prefix}\d{{6,}}", value) is not None


NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------------------------------- no database


@pytest.mark.unit
def test_readable_export_sheets_start_with_the_mdarix_identifier():
    for _name, columns in READABLE_TABLES.values():
        assert columns[0] == "business_id" and columns.count("business_id") == 1
        assert "id" in columns  # the technical key stays in the sheet


@pytest.mark.unit
def test_export_demo_support_and_feedback_payloads_carry_business_id():
    export = SimpleNamespace(
        id=uuid.uuid4(),
        business_id="DEXP000001",
        status="READY",
        requested_by="someone",
        reason="r",
        size_bytes=1,
        sha256="x",
        summary={},
        error=None,
        created_at=NOW,
        completed_at=NOW,
        expires_at=NOW,
    )
    assert describe(export)["business_id"] == "DEXP000001"

    demo = SimpleNamespace(
        id=uuid.uuid4(),
        business_id="DEMO000001",
        display_name="Priya",
        email="p@example.invalid",
        phone="+1 555 0100",
        status="NEW",
        created_at=NOW,
        handled_at=None,
        note=None,
    )
    assert demo_requests._serialize(demo)["business_id"] == "DEMO000001"

    report = SimpleNamespace(
        id=uuid.uuid4(),
        business_id="SUPT000001",
        tenant_id=uuid.uuid4(),
        summary="s",
        details="d",
        path=None,
        request_id=None,
        user_agent=None,
        status="OPEN",
        created_at=NOW,
        closed_at=None,
        closed_by=None,
        resolution=None,
    )
    own = support_api._serialize(report)
    assert own["business_id"] == "SUPT000001" and own["tenant_business_id"] is None and own["reporter"] is None
    listed = support_api._serialize(
        report,
        {
            "tenant_name": "Acme",
            "tenant_business_id": "TEN000001",
            "customer_business_id": "CUST000001",
            "reporter": "a@example.invalid",
            "reporter_business_id": "USR000001",
        },
    )
    assert listed["tenant_name"] == "Acme" and listed["tenant_business_id"] == "TEN000001"
    assert listed["customer_business_id"] == "CUST000001" and listed["reporter_business_id"] == "USR000001"

    response = SimpleNamespace(
        id=uuid.uuid4(),
        business_id="FDBK000001",
        tenant_id=uuid.uuid4(),
        created_at=NOW,
        consent_at=NOW,
        reviewed_at=None,
        rating_overall=5,
        publish_consent="PRIVATE",
        publication_status="NOT_REQUESTED",
        quote=None,
        **{
            column: None
            for column in (
                "organization_name",
                "role_area",
                "job_title",
                "rating_ease",
                "rating_usefulness",
                "rating_ai_trust",
                "rating_speed",
                "rating_import",
                "recommend_score",
                "features_used",
                "liked",
                "improve",
                "missing",
                "adoption",
                "consent_text",
                "contact_ok",
            )
        },
    )
    assert feedback._mine(response)["business_id"] == "FDBK000001"
    row = feedback._admin_row(response, {response.tenant_id: ("ACME", "TEN000002")})
    assert (
        row["business_id"] == "FDBK000001" and row["tenant_key"] == "ACME" and row["tenant_business_id"] == "TEN000002"
    )
    assert feedback._admin_row(response, {})["tenant_business_id"] is None


# ------------------------------------------------------------------------------------------- database


@pytest.fixture
def platform():
    return authenticated_client()


def test_plans_and_expiring_subscriptions_carry_business_ids(platform):
    plans = platform.get("/api/v1/platform-admin/plans").json()
    assert plans and all(_is("PLAN", plan["business_id"]) for plan in plans)
    expiring = platform.get("/api/v1/platform/subscriptions/expiring").json()
    for row in expiring:
        assert _is("SUB", row["business_id"]) and _is("TEN", row["tenant_business_id"])
        assert row["subscription_id"] and row["tenant_id"]  # the UUIDs stay


def test_provisioning_returns_the_customer_tenant_and_administrator_identifiers(platform):
    suffix = uuid.uuid4().hex[:6].upper()
    provisioned = platform.post(
        "/api/v1/platform/tenants/provision",
        json={
            "company_name": f"Bizid Ops {suffix}",
            "tenant_code": f"BZO{suffix}",
            "plan_code": "STARTER",
            "customer_admin_email": f"bizid-ops-{suffix.lower()}@example.invalid",
            "customer_admin_display_name": "Bizid Admin",
            "invitation_required": False,
        },
    )
    assert provisioned.status_code == 200, provisioned.text
    body = provisioned.json()
    assert _is("CUST", body["customer_business_id"]) and _is("TEN", body["tenant_business_id"])
    assert _is("USR", body["customer_admin_business_id"])
    assert body["customer_identifier"] and body["tenant_identifier"]  # kept for existing clients
    job = platform.get(f"/api/v1/platform-admin/provisioning-jobs/{body['job_id']}").json()
    assert job["customer_business_id"] == body["customer_business_id"]
    assert job["tenant_business_id"] == body["tenant_business_id"]

    subscription = platform.get(f"/api/v1/platform-admin/customers/{body['tenant_id']}/subscription")
    assert subscription.status_code == 200, subscription.text
    assert subscription.json()["tenant_business_id"] == body["tenant_business_id"]
    assert _is("PLAN", subscription.json()["plan_business_id"])


@pytest.fixture
def demo_email():
    email = f"demo-bizid-{uuid.uuid4().hex[:10]}@example.invalid"
    yield email
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM demo_requests WHERE email = :email"), {"email": email})


def test_demo_requests_carry_their_business_id(platform, demo_email):
    sent = TestClient(app).post(
        "/api/v1/public/demo-requests", json={"name": "Priya Sharma", "email": demo_email, "phone": "+91 98765 43210"}
    )
    assert sent.status_code == 200 and "business_id" not in sent.json()  # the public answer echoes nothing
    items = platform.get("/api/v1/platform-admin/demo-requests").json()["items"]
    mine = next(item for item in items if item["email"] == demo_email)
    assert _is("DEMO", mine["business_id"])
    changed = platform.post(f"/api/v1/platform-admin/demo-requests/{mine['id']}/status", json={"status": "CONTACTED"})
    assert changed.status_code == 200 and changed.json()["business_id"] == mine["business_id"]


@pytest.fixture
def support_report():
    tenant, _other = two_active_tenants()
    client, user_id, email = client_in_tenant(tenant)
    made = {"tenant": tenant, "client": client, "user_id": user_id, "email": email}
    yield made
    if "id" in made:
        with SessionLocal() as db:
            bind_system(db, "test cleanup")
            report_id = uuid.UUID(made["id"])
            db.query(OutboxEvent).filter(OutboxEvent.aggregate_id == report_id).delete(synchronize_session=False)
            db.query(SupportProblemReport).filter(SupportProblemReport.id == report_id).delete(
                synchronize_session=False
            )
            db.commit()


def test_support_reports_name_their_organization_customer_and_reporter_by_business_id(platform, support_report):
    created = support_report["client"].post(
        "/api/v1/support/problems", json={"summary": "Bizid check", "details": "Testing business identifiers."}
    )
    assert created.status_code == 201, created.text
    support_report["id"] = created.json()["id"]
    business_id = created.json()["business_id"]
    assert _is("SUPT", business_id)
    own = support_report["client"].get("/api/v1/support/problems").json()["items"]
    assert next(item for item in own if item["id"] == support_report["id"])["business_id"] == business_id

    listed = platform.get("/api/v1/platform-admin/support/problems").json()["items"]
    item = next(item for item in listed if item["id"] == support_report["id"])
    assert item["business_id"] == business_id
    assert item["tenant_business_id"] == support_report["tenant"].business_id
    assert _is("CUST", item["customer_business_id"]) and _is("USR", item["reporter_business_id"])
    assert item["reporter"] == support_report["email"]

    closed = platform.post(
        f"/api/v1/platform-admin/support/problems/{support_report['id']}/close", json={"resolution": "Checked"}
    )
    assert closed.status_code == 200 and closed.json()["reporter_business_id"] == item["reporter_business_id"]


@pytest.fixture
def trial_cleanup():
    """Trial workspaces made here leave no business data behind (other tests count rows across the database)."""
    yield
    _purge_trial_business_data()


def test_trial_requests_team_insights_and_feedback_carry_business_ids(platform, trial_cleanup):
    organization = f"Bizid Devices {uuid.uuid4().hex[:4]} fbt"
    email = _request_trial(organization)
    request_id = _request_id(platform, email)
    queued = next(
        item
        for item in platform.get("/api/v1/platform-admin/trial-requests").json()["items"]
        if item["id"] == request_id
    )
    assert _is("TRQ", queued["business_id"]) and queued["tenant_business_id"] is None

    approval = platform.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve")
    assert approval.status_code == 200, approval.text
    approved = approval.json()
    assert approved["business_id"] == queued["business_id"] and _is("TEN", approved["tenant_business_id"])

    user = TestClient(app)
    token = _activation_token(approved, email)
    assert user.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}).status_code == 200
    assert user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200

    members = user.get("/api/v1/trial/team").json()["members"]
    assert members and all(_is("USR", member["business_id"]) for member in members)

    insights = user.get("/api/v1/trial/insights").json()
    assert insights["by_product"] and all(_is("PROD", row["product_business_id"]) for row in insights["by_product"])
    assert all(_is("PV", row["version_business_id"]) for row in insights["by_version"])
    assert all(_is("LOT", row["lot_business_id"]) for row in insights["by_lot"])

    answers = {"rating_overall": 5, "publish_consent": "PRIVATE"}
    sent = user.post("/api/v1/trial/feedback", json=answers)
    assert sent.status_code == 200, sent.text
    feedback_id = sent.json()["id"]
    try:
        assert _is("FDBK", sent.json()["business_id"])
        mine = user.get("/api/v1/trial/feedback").json()["submissions"]
        assert next(item for item in mine if item["id"] == feedback_id)["business_id"] == sent.json()["business_id"]
        listed = platform.get("/api/v1/platform-admin/feedback").json()["items"]
        item = next(item for item in listed if item["id"] == feedback_id)
        assert item["business_id"] == sent.json()["business_id"]
        assert item["tenant_business_id"] == approved["tenant_business_id"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM trial_feedback WHERE id = :id"), {"id": feedback_id})


def test_trial_retention_lists_due_trials_with_their_tenant_business_id(platform):
    due = platform.get("/api/v1/platform-admin/trial-retention").json()["due"]
    for trial in due:
        assert _is("TEN", trial["tenant_business_id"])


@pytest.fixture
def organization(platform, monkeypatch, tmp_path):
    use_local_storage(monkeypatch, tmp_path)
    return make_organization(platform)


def test_exports_their_readable_sheets_and_manifest_carry_business_ids(platform, organization):
    tenant_id = organization["tenant_id"]
    base = f"/api/v1/platform-admin/tenants/{tenant_id}/exports"
    queued = platform.post(base, json={"reason": "Customer asked for a copy of its data"})
    assert queued.status_code == 202, queued.text
    export_id = queued.json()["id"]
    assert _is("DEXP", queued.json()["business_id"])
    assert run_export(export_id)["business_id"] == queued.json()["business_id"]
    listed = platform.get(base).json()["exports"]
    assert next(row for row in listed if row["id"] == export_id)["business_id"] == queued.json()["business_id"]

    archive = zipfile.ZipFile(io.BytesIO(platform.get(f"{base}/{export_id}/download").content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["organization"]["id"] == str(tenant_id) and _is("TEN", manifest["organization"]["business_id"])
    products = [json.loads(line) for line in archive.read("data/public.products.jsonl").splitlines()]
    assert products and all(_is("PROD", product["business_id"]) for product in products)
    for _table, (name, _columns) in READABLE_TABLES.items():
        if name in archive.namelist():
            header = next(csv.reader(io.StringIO(archive.read(name).decode("utf-8"))))
            assert header[0] == "business_id" and "id" in header


def test_legal_hold_answers_name_the_organization_and_the_administrator(platform, organization):
    url = f"/api/v1/platform-admin/tenants/{organization['tenant_id']}/legal-hold"
    before = platform.get(url).json()
    assert _is("TEN", before["tenant_business_id"]) and before["legal_hold_set_by_business_id"] is None
    reason = "Recall investigation REF-2026-17: preserve all records (regulator letter 2026-10-01)"
    held = platform.put(url, json={"hold": True, "reason": reason})
    assert held.status_code == 200, held.text
    assert held.json()["tenant_business_id"] == before["tenant_business_id"]
    assert _is("USR", held.json()["legal_hold_set_by_business_id"])
    released = platform.put(url, json={"hold": False, "reason": "Regulator closed REF-2026-17; retention resumes"})
    assert released.status_code == 200 and released.json()["legal_hold_set_by_business_id"] is None


def test_a_persons_export_carries_their_account_business_id(organization):
    admin, _admin_id = _client_in(organization["tenant_id"], "CUSTOMER_ADMIN")
    document = admin.get(f"/api/v1/admin/people/{organization['user_id']}/export")
    assert document.status_code == 200, document.text
    assert _is("USR", document.json()["account"]["business_id"])


def test_administrator_read_models_carry_business_ids(platform):
    dashboard = platform.get("/api/v1/admin/tenant-dashboard").json()
    assert _is("TEN", dashboard["tenant"]["business_id"])
    for row in platform.get("/api/v1/admin/integrations/credentials").json():
        assert _is("CNX", row["business_id"])
    for row in platform.get("/api/v1/admin/ai-executions").json():
        assert _is("AIEX", row["business_id"])
        if row["investigation_id"]:
            assert _is("INV", row["investigation_business_id"])
    for row in platform.get("/api/v1/admin/audit-history").json():
        assert "actor_business_id" in row
        if row["actor_business_id"] is not None:
            assert _is("USR", row["actor_business_id"])
