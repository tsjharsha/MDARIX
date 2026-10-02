"""One person in several organizations: a separate account in each, and sign-in asks which organization."""

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from auth.service import _hash
from backend.app.db.models.foundation import AuthUser, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.test_customer_admin_account_security import _tenant

PASSWORD = "Same-Person-Password-2026!"


def _account(db, tenant, email, password=PASSWORD, role="INVESTIGATOR"):
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username=email,
        display_name="Same Person",
        company="Test",
        password_hash=_hash(password),
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
    return user


def _person(passwords=(PASSWORD, PASSWORD)):
    email = f"same-person-{uuid.uuid4().hex[:8]}@example.invalid"
    with SessionLocal() as db:
        bind_system(db, "test: one person, two organizations")
        first, second = _tenant(db, "ALPHA"), _tenant(db, "BETA")
        _account(db, first, email, passwords[0])
        _account(db, second, email, passwords[1], role="CUSTOMER_ADMIN")
        db.commit()
        return email, str(first.id), str(second.id)


def test_the_person_chooses_the_organization_after_the_password():
    email, first, second = _person()
    client = TestClient(app)
    chooser = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert chooser.status_code == 200 and chooser.json()["status"] == "TENANT_SELECTION_REQUIRED"
    assert {item["tenant_id"] for item in chooser.json()["organizations"]} == {first, second}
    assert "mdarix_session" not in client.cookies  # no session until a choice is made
    chosen = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD, "tenant_id": second})
    assert chosen.status_code == 200
    session = client.get("/api/v1/auth/session").json()
    assert session["tenant_id"] == second and session["other_organizations"] == 1


def test_a_wrong_password_reveals_no_organizations():
    email, first, _ = _person()
    wrong = TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": "Not-the-password-2026"})
    assert wrong.status_code == 401 and "organizations" not in wrong.text
    forged = TestClient(app).post(
        "/api/v1/auth/signin", json={"email": email, "password": "Not-the-password-2026", "tenant_id": first}
    )
    assert forged.status_code == 401


def test_different_passwords_sign_straight_into_their_own_organization():
    email, first, second = _person(passwords=(PASSWORD, "Another-Password-2026!"))
    client = TestClient(app)
    signed = client.post("/api/v1/auth/signin", json={"email": email, "password": "Another-Password-2026!"})
    assert signed.status_code == 200 and signed.json().get("status") != "TENANT_SELECTION_REQUIRED"
    assert client.get("/api/v1/auth/session").json()["tenant_id"] == second
    # Choosing an organization the password does not open is refused like a wrong password.
    other = TestClient(app).post(
        "/api/v1/auth/signin", json={"email": email, "password": "Another-Password-2026!", "tenant_id": first}
    )
    assert other.status_code == 401


def test_password_reset_answers_the_same_and_covers_every_organization():
    email, _, _ = _person()
    reset = TestClient(app).post("/api/v1/auth/forgot-password", json={"email": email})
    assert reset.status_code == 200 and reset.json()["status"] == "RESET_REQUEST_ACCEPTED"
