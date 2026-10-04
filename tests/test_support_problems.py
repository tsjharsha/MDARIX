"""Problems reported from the help menu: stored in the reporter's organization, emailed to support through the
outbox, visible only to the reporter and to platform administrators, closed with a resolution on the record."""

import secrets
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from auth import emailer
from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.models.pilot_support import SupportProblemReport
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.support_api import deliver_problem_report
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

BASE = "/api/v1/support/problems"
ADMIN = "/api/v1/platform-admin/support/problems"


def two_active_tenants():
    with SessionLocal() as db:
        bind_system(db, "test: pick two organizations")
        rows = db.query(Tenant).filter(func.upper(Tenant.status) == "ACTIVE").order_by(Tenant.created_at).limit(2).all()
        db.expunge_all()
    if len(rows) < 2:
        pytest.skip("the test database holds fewer than two active organizations")
    return rows


def client_in_tenant(tenant, role="Investigator"):
    """A signed-in user of ``tenant``; returns (client, user id, email)."""
    now = datetime.now(timezone.utc)
    email = f"support-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid"
    with SessionLocal() as db:
        bind_system(db, "test: a user in one organization")
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name=f"{role} in {tenant.name}",
            company=tenant.name,
            password_hash=_hash("Support test 2026!"),
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
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant.id)
        db.commit()
        user_id = user.id
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id, email


@pytest.fixture(scope="module")
def reports():
    """One report in each of two organizations; cleaned up afterwards (audit events are immutable and stay)."""
    tenant_a, tenant_b = two_active_tenants()
    client_a, user_a, email_a = client_in_tenant(tenant_a)
    client_b, user_b, _ = client_in_tenant(tenant_b)
    made = {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "client_a": client_a,
        "client_b": client_b,
        "user_a": user_a,
        "email_a": email_a,
        "user_b": user_b,
    }
    yield made
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        ids = [uuid.UUID(made[key]) for key in ("id_a", "id_b") if key in made]
        db.query(OutboxEvent).filter(OutboxEvent.aggregate_id.in_(ids)).delete(synchronize_session=False)
        db.query(SupportProblemReport).filter(SupportProblemReport.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def _report(report_id):
    with SessionLocal() as db:
        bind_system(db, "test: read report")
        return db.get(SupportProblemReport, uuid.UUID(report_id))


def _audit(action, entity_id):
    with SessionLocal() as db:
        bind_system(db, "test: read audit")
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.action == action, AuditEvent.entity_id == uuid.UUID(entity_id))
            .order_by(AuditEvent.created_at.desc())
            .first()
        )


def test_a_signed_in_user_files_a_report_which_is_stored_audited_and_queued(reports):
    body = {
        "summary": "  The export button   does nothing ",
        "details": "I click Export on the investigation record and nothing happens.",
        "path": "/app/investigations/INV-001",
        "request_id": "req-abc12345",
    }
    response = reports["client_a"].post(BASE, json=body, headers={"User-Agent": "TestBrowser/1.0"})
    assert response.status_code == 201
    created = response.json()
    assert set(created) == {"id", "created_at"}
    reports["id_a"] = created["id"]
    row = _report(created["id"])
    assert row.tenant_id == reports["tenant_a"].id and row.user_id == reports["user_a"]
    assert row.reporter_ref == str(reports["user_a"]) and row.user_agent == "TestBrowser/1.0"
    assert row.summary == "The export button does nothing" and row.status == "OPEN"
    assert row.request_id == "req-abc12345" and row.path == "/app/investigations/INV-001"
    audit = _audit("SUPPORT_PROBLEM_REPORTED", created["id"])
    assert audit is not None and audit.tenant_id == reports["tenant_a"].id and audit.actor_ref == str(reports["user_a"])
    with SessionLocal() as db:
        bind_system(db, "test: read outbox")
        event = db.query(OutboxEvent).filter(OutboxEvent.aggregate_id == uuid.UUID(created["id"])).one()
    assert event.event_name == "SUPPORT_PROBLEM_REPORTED" and event.payload == {"report_id": created["id"]}
    assert "nothing happens" not in str(event.payload)

    second = reports["client_b"].post(BASE, json={"summary": "Sign-in slow", "details": "Takes a minute."})
    assert second.status_code == 201
    reports["id_b"] = second.json()["id"]


def test_the_support_team_is_emailed_with_summary_organization_user_path_and_request_id(reports, monkeypatch):
    sent = []
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@example.test")
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: sent.append({"to": to, "subject": subject, "text": text})
        or "SENT",
    )
    with SessionLocal() as db:
        bind_system(db, "test: deliver the report")
        assert deliver_problem_report(db, {"report_id": reports["id_a"]}) == "SENT"
    message = sent[0]
    assert message["to"] == "support@example.test"
    assert "The export button does nothing" in message["subject"] and reports["tenant_a"].name in message["subject"]
    for expected in (reports["email_a"], "/app/investigations/INV-001", "req-abc12345", "nothing happens"):
        assert expected in message["text"]


def test_without_a_support_address_the_event_is_acknowledged_not_retried(reports, monkeypatch):
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "")
    with SessionLocal() as db:
        bind_system(db, "test: deliver without recipient")
        assert deliver_problem_report(db, {"report_id": reports["id_a"]}) == "NOT_CONFIGURED"
        assert deliver_problem_report(db, {"report_id": str(uuid.uuid4())}) == "SKIPPED"


def test_a_user_sees_only_their_own_organizations_reports(reports):
    mine = {item["id"] for item in reports["client_a"].get(BASE).json()["items"]}
    theirs = {item["id"] for item in reports["client_b"].get(BASE).json()["items"]}
    assert reports["id_a"] in mine and reports["id_b"] not in mine
    assert reports["id_b"] in theirs and reports["id_a"] not in theirs


def test_validation_and_authentication(reports):
    assert reports["client_a"].post(BASE, json={"summary": "", "details": "x"}).status_code == 422
    assert reports["client_a"].post(BASE, json={"summary": "x" * 201, "details": "x"}).status_code == 422
    assert reports["client_a"].post(BASE, json={"summary": "   ", "details": "   "}).status_code == 422
    assert TestClient(app).post(BASE, json={"summary": "s", "details": "d"}).status_code == 401
    assert TestClient(app).get(ADMIN).status_code == 401


def test_platform_administrators_list_across_organizations_and_filter_by_status(reports):
    admin = authenticated_client()
    listed = admin.get(ADMIN, params={"status": "OPEN"}).json()
    items = {item["id"]: item for item in listed["items"]}
    assert {reports["id_a"], reports["id_b"]} <= set(items)
    assert items[reports["id_a"]]["tenant_name"] == reports["tenant_a"].name
    assert items[reports["id_a"]]["reporter"] == reports["email_a"]
    assert all(item["status"] == "OPEN" for item in listed["items"])
    assert set(listed["counts"]) == {"OPEN", "CLOSED"} and listed["counts"]["OPEN"] >= 2
    assert admin.get(ADMIN, params={"status": "bogus"}).status_code == 422
    everything = admin.get(ADMIN).json()["items"]
    assert {reports["id_a"], reports["id_b"]} <= {item["id"] for item in everything}


def test_closing_a_report_records_the_resolution_and_audits_it_in_the_reporters_organization(reports):
    admin = authenticated_client()
    refused = admin.post(f"{ADMIN}/{reports['id_a']}/close", json={"resolution": "ok"})
    assert refused.status_code == 422
    closed = admin.post(f"{ADMIN}/{reports['id_a']}/close", json={"resolution": "Fixed in release 2026.10.3"})
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"
    row = _report(reports["id_a"])
    assert row.status == "CLOSED" and row.closed_at is not None and row.resolution == "Fixed in release 2026.10.3"
    audit = _audit("SUPPORT_PROBLEM_CLOSED", reports["id_a"])
    assert audit is not None and audit.tenant_id == reports["tenant_a"].id
    assert audit.reason == "Fixed in release 2026.10.3" and audit.actor_ref == row.closed_by
    assert admin.post(f"{ADMIN}/{reports['id_a']}/close", json={"resolution": "again"}).status_code == 409
    assert admin.post(f"{ADMIN}/{uuid.uuid4()}/close", json={"resolution": "nothing"}).status_code == 404
    closed_ids = {item["id"] for item in admin.get(ADMIN, params={"status": "CLOSED"}).json()["items"]}
    open_ids = {item["id"] for item in admin.get(ADMIN, params={"status": "OPEN"}).json()["items"]}
    assert reports["id_a"] in closed_ids and reports["id_a"] not in open_ids and reports["id_b"] in open_ids


def test_customer_administrators_cannot_see_or_close_reports_of_the_platform(reports):
    customer_admin = _client_with_role("CUSTOMER_ADMIN")
    assert customer_admin.get(ADMIN).status_code == 403
    response = customer_admin.post(f"{ADMIN}/{reports['id_b']}/close", json={"resolution": "not yours"})
    assert response.status_code == 403 and _report(reports["id_b"]).status == "OPEN"
