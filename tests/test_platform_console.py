"""Platform-wide console views: real data across tenants, readable names, and no customer business content."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.access.platform_subscriptions import reminder_schedules
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.models.foundation import AIExecution, AuditEvent, AuthUser, PlanDefinition
from backend.app.db.session import SessionLocal
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

SECRET = "CONFIDENTIAL-COMPLAINT-NARRATIVE"


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture
def customer(platform):
    code = f"PCO{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Console Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()


def _plan_id(code="STARTER") -> str:
    db = SessionLocal()
    try:
        return str(db.query(PlanDefinition.id).filter(PlanDefinition.code == code).scalar())
    finally:
        db.close()


def _add(*rows):
    db = SessionLocal()
    try:
        for row in rows:
            db.add(row)
        db.commit()
        # Keep the rows readable (their ids) after the session closes.
        for row in rows:
            db.refresh(row)
            db.expunge(row)
    finally:
        db.close()


def test_renewals_list_each_licence_with_its_tenant_and_plan(platform, customer):
    now = datetime.now(timezone.utc)
    changed = platform.post(
        f"/api/v1/platform/customers/{customer['id']}/subscription",
        json={
            "plan_id": _plan_id(),
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(days=20)).isoformat(),
            "reason": "Annual licence",
        },
    )
    assert changed.status_code == 200, changed.text
    renewals = platform.get("/api/v1/platform-admin/console/renewals").json()["items"]
    mine = [item for item in renewals if item["tenant_id"] == customer["id"]]
    assert len(mine) == 1
    assert mine[0]["tenant_key"] == customer["tenant_key"] and mine[0]["customer_name"] == customer["name"]
    assert mine[0]["plan_name"] and 18 <= mine[0]["days_remaining"] <= 20
    expiries = [item["expires_at"] for item in renewals]
    assert expiries == sorted(expiries)


def test_reminder_settings_show_the_saved_policy_and_templates_and_drive_the_schedule(platform, customer):
    tenant = customer["id"]
    empty = platform.get(f"/api/v1/platform-admin/tenants/{tenant}/reminder-settings").json()
    assert empty["policy"] is None and empty["default_thresholds"] == [60, 30, 7] and empty["templates"] == []
    assert empty["template_variables"] == ["customer_name", "expiry_date", "days_remaining", "activation_link"]
    saved = platform.post(
        f"/api/v1/platform/subscriptions/{tenant}/reminder-policies",
        json={"name": "Longer notice", "thresholds": [90, 45, 14], "recipient_types": ["CUSTOMER_ADMIN"]},
    )
    assert saved.status_code == 200, saved.text
    template = platform.post(
        f"/api/v1/platform/subscriptions/{tenant}/email-templates",
        json={
            "stage": "EXPIRING",
            "version": "v1",
            "subject": "Your MDARIX licence",
            "body": "Hello {{customer_name}}, your licence ends on {{expiry_date}}.",
            "allowed_variables": ["customer_name", "expiry_date"],
        },
    )
    assert template.status_code == 200, template.text
    settings = platform.get(f"/api/v1/platform-admin/tenants/{tenant}/reminder-settings").json()
    assert settings["policy"]["thresholds"] == [90, 45, 14] and settings["policy"]["name"] == "Longer notice"
    assert [item["subject"] for item in settings["templates"]] == ["Your MDARIX licence"]
    # The lifecycle run follows the tenant's policy instead of the fixed 60/30/7 days.
    db = SessionLocal()
    try:
        assert reminder_schedules(db)[uuid.UUID(tenant)] == [90, 45, 14]
    finally:
        db.close()
    missing = platform.get(f"/api/v1/platform-admin/tenants/{uuid.uuid4()}/reminder-settings")
    assert missing.status_code == 404


def test_integration_runs_span_tenants_and_filter_problems(platform, customer):
    now = datetime.now(timezone.utc)
    tenant = uuid.UUID(customer["id"])
    good = ConnectorRun(
        id=uuid.uuid4(),
        tenant_id=tenant,
        connection_id=f"conn-{customer['tenant_key'].lower()}",
        source_system="TrackWise",
        status="SUCCEEDED",
        records_received=10,
        records_accepted=10,
        started_at=now,
        created_at=now,
    )
    bad = ConnectorRun(
        id=uuid.uuid4(),
        tenant_id=tenant,
        connection_id=f"conn-{customer['tenant_key'].lower()}",
        source_system="TrackWise",
        status="FAILED",
        records_received=5,
        records_rejected=5,
        failure_category="AUTHENTICATION",
        reconciliation_status="MISMATCH",
        started_at=now,
        created_at=now,
    )
    _add(good, bad)
    runs = platform.get("/api/v1/platform-admin/console/integration-runs", params={"tenant_id": customer["id"]}).json()
    assert {item["id"] for item in runs["items"]} == {str(good.id), str(bad.id)}
    assert all(item["tenant_key"] == customer["tenant_key"] for item in runs["items"])
    problems = platform.get(
        "/api/v1/platform-admin/console/integration-runs", params={"tenant_id": customer["id"], "status": "problems"}
    ).json()
    assert [item["id"] for item in problems["items"]] == [str(bad.id)]
    reconciled = platform.get(
        "/api/v1/platform-admin/console/integration-runs", params={"tenant_id": customer["id"], "reconciled": "true"}
    ).json()
    assert [item["reconciliation_status"] for item in reconciled["items"]] == ["MISMATCH"]
    assert runs["last_30_days"]["by_status"].get("FAILED", 0) >= 1
    assert runs["last_30_days"]["by_reconciliation"].get("MISMATCH", 0) >= 1


def test_ai_activity_counts_every_tenant_without_returning_inputs_or_outputs(platform, customer):
    now = datetime.now(timezone.utc)
    execution = AIExecution(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(customer["id"]),
        provider="groq",
        model_name="openai/gpt-oss-120b",
        structured_input={"question": SECRET},
        structured_output={"answer": SECRET},
        rationale_summary=SECRET,
        validation_status="PASSED",
        execution_timestamp=now,
        latency_ms=1234,
        error_state="TIMEOUT",
    )
    _add(execution)
    response = platform.get("/api/v1/platform-admin/console/ai-activity")
    assert response.status_code == 200 and SECRET not in response.text
    activity = response.json()
    assert activity["total"] >= 1 and activity["failed"] >= 1 and activity["p95_latency_ms"] is not None
    latest = next(item for item in activity["latest"] if item["id"] == str(execution.id))
    assert latest["tenant_key"] == customer["tenant_key"] and latest["failed"] is True
    assert {"structured_output", "structured_input", "rationale_summary"}.isdisjoint(latest)


def test_the_audit_trail_names_tenants_and_actors_and_hides_record_values(platform, customer):
    db = SessionLocal()
    try:
        actor = db.query(AuthUser).filter(AuthUser.username == "r1-user-01@synthetic.invalid").first()
        actor_ref = str(actor.id) if actor else None
    finally:
        db.close()
    event = AuditEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(customer["id"]),
        actor_ref=actor_ref,
        action="APPROVAL_AUTHORITY_DENIED",
        entity_type="Investigation",
        details={"reason": "Not an approver", "narrative": SECRET},
        old_values={"text": SECRET},
        new_values={"text": SECRET},
        created_at=datetime.now(timezone.utc),
    )
    _add(event)
    response = platform.get("/api/v1/platform-admin/console/audit", params={"tenant_id": customer["id"]})
    assert response.status_code == 200 and SECRET not in response.text
    item = next(row for row in response.json()["items"] if row["id"] == str(event.id))
    assert item["tenant_key"] == customer["tenant_key"] and item["reason"] == "Not an approver"
    if actor_ref:
        assert item["actor"] and item["actor"] != actor_ref
    flagged = platform.get(
        "/api/v1/platform-admin/console/audit", params={"tenant_id": customer["id"], "attention": "true"}
    ).json()
    assert str(event.id) in {row["id"] for row in flagged["items"]}
    searched = platform.get("/api/v1/platform-admin/console/audit", params={"q": "authority_denied", "page_size": 5})
    assert searched.json()["items"] and all("DENIED" in row["action"] for row in searched.json()["items"])


def test_security_posture_reports_isolation_and_residency_from_the_database(platform):
    posture = platform.get("/api/v1/platform-admin/console/security").json()
    isolation = posture["isolation"]
    assert (
        isolation["tenant_tables"] > 50
        and isolation["protected"] + len(isolation["unprotected"]) == isolation["tenant_tables"]
    )
    # Every tenant table without row-level security is a platform table excluded on purpose.
    assert isolation["unexpected"] == []
    assert posture["sign_in"]["active_accounts"] >= posture["sign_in"]["mfa_enrolled"]
    assert posture["residency"] and posture["retention"]["audit_events"] > 0


def test_support_access_and_operations_are_readable(platform, customer):
    grants = platform.get("/api/v1/platform-admin/console/support-access")
    assert grants.status_code == 200 and isinstance(grants.json()["items"], list)
    operations = platform.get("/api/v1/platform-admin/console/operations").json()
    assert operations["database"] == "OK"
    assert {"pending", "dead_lettered", "pending_by_event"} <= set(operations["queue"])
    assert operations["email"]["reminder_delivery"] == "NOT_CONNECTED"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/platform-admin/console/renewals",
        "/api/v1/platform-admin/console/integration-runs",
        "/api/v1/platform-admin/console/ai-activity",
        "/api/v1/platform-admin/console/audit",
        "/api/v1/platform-admin/console/security",
        "/api/v1/platform-admin/console/support-access",
        "/api/v1/platform-admin/console/operations",
    ],
)
def test_only_a_platform_administrator_sees_platform_wide_views(path):
    assert _client_with_role("CUSTOMER_ADMIN").get(path).status_code == 403
