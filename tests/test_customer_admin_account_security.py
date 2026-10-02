"""Customer Administrator account: privilege-escalation, self-lockout and tenant-boundary checks against the live API."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash, auth_service
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.conftest import authenticated_client

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


def test_sign_in_uses_the_active_account_when_an_email_also_has_an_unused_invitation():
    db = SessionLocal()
    try:
        invited_tenant = _tenant(db, "INV")
        active_tenant = _tenant(db, "ACT")
        email = f"dual-{uuid.uuid4().hex[:8]}@synthetic.invalid"
        # The unused invitation is stored first, so an unordered lookup finds it first.
        invited = _user(db, invited_tenant, "CUSTOMER_ADMIN", "dual-invited")
        invited.username, invited.status, invited.email_verified = email, "INVITED", False
        invited.password_hash = _hash(uuid.uuid4().hex)
        db.flush()
        active = _user(db, active_tenant, "CUSTOMER_ADMIN", "dual-active")
        active.username = email
        db.commit()
        active_tenant_id = str(active_tenant.id)
    finally:
        db.close()
    client = TestClient(app)
    for _ in range(3):
        response = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        assert response.json()["tenant_id"] == active_tenant_id


def _two_active_accounts(admin_password, investigator_password, *, admin_password_newer):
    """The same email active in two tenants: Customer Administrator in one, Investigator (created later) in another."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        admin_tenant = _tenant(db, "ADM")
        other_tenant = _tenant(db, "INVG")
        email = f"two-roles-{uuid.uuid4().hex[:8]}@synthetic.invalid"
        admin = _user(db, admin_tenant, "CUSTOMER_ADMIN", "two-admin")
        investigator = _user(db, other_tenant, "INVESTIGATOR", "two-investigator")
        admin.username, investigator.username = email, email
        admin.password_hash, investigator.password_hash = _hash(admin_password), _hash(investigator_password)
        # The Investigator account is newer, which used to decide the sign-in.
        admin.created_at, investigator.created_at = now - timedelta(days=10), now - timedelta(days=2)
        admin.password_changed_at = now if admin_password_newer else now - timedelta(days=5)
        investigator.password_changed_at = now - timedelta(days=1) if admin_password_newer else now
        db.commit()
        return email, str(admin_tenant.id), str(other_tenant.id)
    finally:
        db.close()


def test_sign_in_uses_the_account_the_password_belongs_to():
    email, admin_tenant, other_tenant = _two_active_accounts(
        "Customer admin password 123", "Investigator password 456", admin_password_newer=False
    )
    client = TestClient(app)
    as_admin = client.post("/api/v1/auth/signin", json={"email": email, "password": "Customer admin password 123"})
    assert as_admin.status_code == 200, as_admin.text
    assert as_admin.json()["tenant_id"] == admin_tenant
    as_investigator = TestClient(app).post(
        "/api/v1/auth/signin", json={"email": email, "password": "Investigator password 456"}
    )
    assert as_investigator.status_code == 200 and as_investigator.json()["tenant_id"] == other_tenant
    wrong = TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": "Not the password 789"})
    assert wrong.status_code in {400, 401}


def test_with_the_same_password_the_account_set_most_recently_wins():
    # The person just accepted the Customer Administrator invitation and chose a password they also use elsewhere.
    email, admin_tenant, _ = _two_active_accounts(
        "Shared password 12345", "Shared password 12345", admin_password_newer=True
    )
    response = TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": "Shared password 12345"})
    assert response.status_code == 200 and response.json()["tenant_id"] == admin_tenant


def test_a_tenant_user_cannot_be_created_with_an_email_live_in_another_tenant(world):
    client, _ = world
    db = SessionLocal()
    try:
        elsewhere = _user(db, _tenant(db, "ELSE"), "INVESTIGATOR", "elsewhere")
        retired = _user(db, _tenant(db, "RETD"), "INVESTIGATOR", "retired")
        retired.status = "OFFBOARDED"
        db.commit()
        live_email, retired_email = elsewhere.username, retired.username
    finally:
        db.close()

    def invite(email):
        return client.post(
            "/api/v1/admin/identity/users",
            json={"email": email, "display_name": "Second account", "company": "Synthetic", "role": "Viewer"},
        )

    refused = invite(live_email)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "EMAIL_IN_USE"
    # A retired account elsewhere does not block the email.
    assert invite(retired_email).status_code == 200


def test_platform_accounts_in_the_tenant_are_invisible_to_the_customer_administrator(world):
    client, ids = world
    platform_id, member_id = ids["platform_user"], ids["member"]
    users = {row["id"] for row in client.get("/api/v1/admin/identity/users").json()}
    assert member_id in users and ids["admin"] in users
    assert platform_id not in users
    # Opening it directly behaves as if it did not exist.
    for path in (
        f"/api/v1/admin/identity/users/{platform_id}",
        f"/api/v1/admin/identity/users/{platform_id}/effective-access",
    ):
        response = client.get(path)
        assert response.status_code == 404 and response.json()["detail"]["code"] == "USER_NOT_FOUND"
    for path in (
        "/api/v1/admin/identity/memberships",
        "/api/v1/admin/identity/persona-assignments",
        "/api/v1/admin/identity/role-assignments",
    ):
        assert platform_id not in {row["user_id"] for row in client.get(path).json()}, path
    # The dashboard counts only the customer's own people.
    dashboard = client.get("/api/v1/admin/tenant-dashboard").json()
    assert dashboard["metrics"]["users"] == len(users)


def test_the_customer_administrator_cannot_act_on_a_platform_account(world):
    client, ids = world
    platform_id = ids["platform_user"]
    persona = client.post(
        "/api/v1/admin/identity/persona-assignments", json={"user_id": platform_id, "persona_code": "INVESTIGATOR"}
    )
    assert persona.status_code == 404
    membership = client.post("/api/v1/admin/identity/memberships", json={"user_id": platform_id, "is_default": True})
    assert membership.status_code == 404
    db = SessionLocal()
    try:
        email = db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(platform_id)).scalar()
    finally:
        db.close()
    reset = client.post("/api/v1/admin/identity/users/password-reset", json={"email": email})
    assert reset.status_code == 200 and reset.json()["email_delivery"] == "NOT_SENT"


def test_platform_actions_in_the_audit_trail_name_the_platform_not_the_person(world):
    client, ids = world
    event_id = uuid.uuid4()
    db = SessionLocal()
    try:
        db.add(
            AuditEvent(
                id=event_id,
                tenant_id=ids["tenant"],
                actor_ref=ids["platform_user"],
                action="SUPPORT_REVIEW",
                entity_type="Tenant",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()
    rows = {row["id"]: row for row in client.get("/api/v1/admin/audit-history").json()}
    event = rows[str(event_id)]
    assert event["actor_ref"] is None and event["actor_label"] == "MDARIX platform administrator"


def test_platform_administrators_still_see_platform_accounts():
    platform = authenticated_client()
    roles = {str(row["role"]).upper() for row in platform.get("/api/v1/admin/identity/users").json()}
    assert "ADMINISTRATOR" in roles
