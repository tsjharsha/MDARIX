"""Customer Administrator account: privilege-escalation, self-lockout and tenant-boundary checks against the live API."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash, auth_service
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuthUser, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.main import app

PASSWORD = "Customer admin test password 123"


def _tenant(db, label):
    now = datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    customer = Customer(
        id=uuid.uuid4(),
        customer_identifier=f"CA-SEC-{label}-{suffix}",
        legal_name=f"Customer Admin Security {label}",
        display_name=f"Customer Admin Security {label}",
        customer_type="DESIGN_PARTNER",
        country="US",
        lifecycle_status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(customer)
    db.flush()
    tenant = Tenant(
        id=uuid.uuid4(),
        customer_id=customer.id,
        tenant_key=f"CA-SEC-{label}-{suffix}",
        tenant_identifier=f"CA-SEC-{label}-{suffix}",
        name=f"CA Security {label} {suffix}",
        display_name=f"CA Security {label}",
        tenant_slug=f"ca-sec-{label.lower()}-{suffix}",
        tenant_type="STANDARD",
        deployment_model="SHARED",
        primary_region="US",
        residency_region="US",
        cross_border_processing_allowed=False,
        provisioning_status="PROVISIONED",
        status="ACTIVE",
        lock_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    db.flush()
    return tenant


def _user(db, tenant, role, label):
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username=f"{label}-{uuid.uuid4().hex[:8]}@synthetic.invalid",
        display_name=label,
        company=tenant.name,
        password_hash=_hash(PASSWORD),
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
    db.flush()
    return user


def _client_for(db, user):
    token = auth_service.signin_persisted(
        user.username,
        PASSWORD,
        user_id=user.id,
        display_name=user.display_name,
        tenant_id=user.tenant_id,
        password_hash=user.password_hash,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified,
    )
    persist_session(db, token, user.id, user.tenant_id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client


@pytest.fixture(scope="module")
def world():
    db = SessionLocal()
    try:
        tenant = _tenant(db, "A")
        other_tenant = _tenant(db, "B")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "ca-admin")
        member = _user(db, tenant, "Viewer", "ca-member")
        platform_user = _user(db, tenant, "Administrator", "ca-platform")
        foreign = _user(db, other_tenant, "Viewer", "ca-foreign")
        db.commit()
        ids = {
            "tenant": tenant.id,
            "admin": str(admin.id),
            "member": str(member.id),
            "platform_user": str(platform_user.id),
            "foreign": str(foreign.id),
        }
        client = _client_for(db, admin)
        db.commit()
    finally:
        db.close()
    return client, ids


def _invite(client, role):
    return client.post(
        "/api/v1/admin/identity/users",
        json={
            "email": f"invite-{uuid.uuid4().hex[:8]}@synthetic.invalid",
            "display_name": "Invited",
            "company": "Synthetic",
            "role": role,
        },
    )


@pytest.mark.parametrize("role", ["ADMINISTRATOR", "Admin", "mdarix administrator", "platform_admin", "PLATFORM ADMIN"])
def test_customer_admin_cannot_invite_any_platform_role_spelling(world, role):
    client, _ = world
    response = _invite(client, role)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PLATFORM_ROLE_NOT_ALLOWED"


def test_customer_admin_can_invite_a_tenant_user(world):
    client, _ = world
    response = _invite(client, "Viewer")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "INVITED"


def test_customer_admin_cannot_escalate_through_the_generic_editor(world):
    client, ids = world
    promote = client.patch(f"/api/v1/admin/control-plane/users/{ids['member']}", json={"values": {"role": "ADMIN"}})
    assert promote.status_code == 403
    assert promote.json()["detail"]["code"] == "PLATFORM_ROLE_NOT_ALLOWED"
    self_promote = client.patch(
        f"/api/v1/admin/control-plane/users/{ids['admin']}", json={"values": {"role": "PLATFORM_ADMIN"}}
    )
    assert self_promote.status_code == 403
    rename_self = client.patch(
        f"/api/v1/admin/control-plane/users/{ids['admin']}", json={"values": {"display_name": "Renamed Admin"}}
    )
    assert rename_self.status_code == 200, rename_self.text


def test_customer_admin_cannot_lock_themselves_out(world):
    client, ids = world
    suspend_self = client.patch(f"/api/v1/admin/identity/users/{ids['admin']}/status", json={"status": "SUSPENDED"})
    assert suspend_self.status_code == 409
    assert suspend_self.json()["detail"]["code"] == "SELF_CHANGE_NOT_ALLOWED"
    demote_self = client.patch(f"/api/v1/admin/control-plane/users/{ids['admin']}", json={"values": {"role": "Viewer"}})
    assert demote_self.status_code == 409


def test_customer_admin_cannot_change_platform_users_or_other_tenants(world):
    client, ids = world
    protected = client.patch(
        f"/api/v1/admin/identity/users/{ids['platform_user']}/status", json={"status": "SUSPENDED"}
    )
    assert protected.status_code == 403
    assert protected.json()["detail"]["code"] == "PLATFORM_USER_PROTECTED"
    foreign = client.patch(f"/api/v1/admin/identity/users/{ids['foreign']}/status", json={"status": "SUSPENDED"})
    assert foreign.status_code == 404


def test_customer_admin_can_suspend_and_restore_a_tenant_user(world):
    client, ids = world
    suspended = client.patch(f"/api/v1/admin/identity/users/{ids['member']}/status", json={"status": "SUSPENDED"})
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    restored = client.patch(f"/api/v1/admin/identity/users/{ids['member']}/status", json={"status": "ACTIVE"})
    assert restored.status_code == 200


def test_suspending_a_user_revokes_their_sessions_and_is_audited(world):
    client, ids = world
    db = SessionLocal()
    try:
        member = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(ids["member"])).one()
        member_client = _client_for(db, member)
        db.commit()
    finally:
        db.close()
    assert member_client.get("/api/v1/auth/session").status_code == 200
    assert (
        client.patch(f"/api/v1/admin/identity/users/{ids['member']}/status", json={"status": "SUSPENDED"}).status_code
        == 200
    )
    assert (
        client.patch(f"/api/v1/admin/identity/users/{ids['member']}/status", json={"status": "ACTIVE"}).status_code
        == 200
    )
    # Restoring the account must not revive the session that existed before the suspension.
    assert member_client.get("/api/v1/auth/session").status_code == 401
    audit = client.get("/api/v1/admin/audit-history", params={"action": "USER_STATUS_CHANGED"}).json()
    assert any(row["entity_id"] == ids["member"] and row["new_values"] == {"status": "SUSPENDED"} for row in audit)


def test_customer_admin_cannot_reactivate_a_platform_user(world):
    client, ids = world
    db = SessionLocal()
    try:
        db.query(AuthUser).filter(AuthUser.id == uuid.UUID(ids["platform_user"])).update({"status": "OFFBOARDED"})
        db.commit()
    finally:
        db.close()
    response = client.post(f"/api/v1/admin/identity/users/{ids['platform_user']}/reactivate")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PLATFORM_USER_PROTECTED"


def test_customer_admin_can_read_tenant_lifecycle(world):
    client, ids = world
    response = client.get("/api/v1/admin/tenant/lifecycle")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_id"] == str(ids["tenant"])
    assert body["lifecycle_status"] == "ACTIVE"
    assert body["customer_admin_actions"] == ["REQUEST_RENEWAL"]


def test_session_context_names_the_administrators_tenant(world):
    client, ids = world
    context = client.get("/api/v1/session/context").json()
    assert context["current_tenant"]["tenant_id"] == str(ids["tenant"])
    assert context["current_tenant"]["tenant_name"].startswith("CA Security A")
