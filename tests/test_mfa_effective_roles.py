"""Code audit 1: the MFA policy reads every role a person holds (``roles_of_user``), not only the account role, and an
open session follows a role change on its next request. A person who now needs MFA is sent to the authenticator setup
(never a dead end); a role taken away lets the same session back in; a person already enrolled is not affected."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.workflow import UserAdditionalRole
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _client_for, _tenant, _user

pytestmark = pytest.mark.db

CONTEXT = "/api/v1/session/context"


@pytest.fixture(scope="module")
def world():
    with SessionLocal() as db:
        bind_system(db, "test: MFA for effective roles")
        tenant = _tenant(db, "MFAROLES")
        plain = _user(db, tenant, "Investigator", "mfa-roles-plain")
        enrolled = _user(db, tenant, "Investigator", "mfa-roles-enrolled")
        enrolled.mfa_enrolled_at, enrolled.mfa_secret_encrypted = datetime.now(timezone.utc), "set-up-already"
        db.commit()
        found = {
            "tenant_id": tenant.id,
            "plain_id": plain.id,
            "enrolled_id": enrolled.id,
            "plain": _client_for(db, plain),
            "enrolled": _client_for(db, enrolled),
        }
        db.commit()
        return found


def _grant(world, user_id, role: str, status: str = "ACTIVE") -> None:
    with SessionLocal() as db:
        bind_system(db, "test: additional role")
        row = (
            db.query(UserAdditionalRole)
            .filter(UserAdditionalRole.user_id == user_id, UserAdditionalRole.role_code == role)
            .one_or_none()
        )
        if row is None:
            row = UserAdditionalRole(
                id=uuid.uuid4(), tenant_id=world["tenant_id"], user_id=user_id, role_code=role, granted_by="test"
            )
            db.add(row)
        row.status = status
        db.commit()


def test_an_additional_approver_or_leader_role_sends_an_open_session_to_set_up_mfa(world, monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "LEADER,APPROVER")
    client = world["plain"]
    assert client.get(CONTEXT).status_code == 200
    for role in ("APPROVER", "LEADER"):
        _grant(world, world["plain_id"], role)
        refused = client.get(CONTEXT)
        assert refused.status_code == 403, role
        assert refused.json()["detail"]["code"] == "MFA_ENROLLMENT_REQUIRED"
        assert "role now requires two-factor sign-in" in refused.json()["detail"]["message"]
        # The way out is the setup sign-in uses: the same session may start it.
        assert client.post("/api/v1/auth/mfa/enroll").status_code == 200
        # The role taken away again: no longer required, the same session is let back in.
        _grant(world, world["plain_id"], role, "REVOKED")
        assert client.get(CONTEXT).status_code == 200, role


def test_a_person_already_enrolled_is_not_affected(world, monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "LEADER,APPROVER")
    _grant(world, world["enrolled_id"], "APPROVER")
    assert world["enrolled"].get(CONTEXT).status_code == 200


def test_without_a_policy_an_additional_role_changes_nothing(world, monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "")
    _grant(world, world["plain_id"], "APPROVER")
    try:
        assert world["plain"].get(CONTEXT).status_code == 200
    finally:
        _grant(world, world["plain_id"], "APPROVER", "REVOKED")


def test_the_welcome_email_at_activation_counts_an_additional_role(world, monkeypatch):
    """Check 3c: activation (``_redeem`` under the system scope, which survives its commit) reads the additional roles,
    so an invited Investigator who was also given Leader is told in the welcome e-mail that two-factor sign-in is
    required; without that role, not."""
    from fastapi.testclient import TestClient

    from auth.durable import issue_invitation
    from backend.app import auth_router
    from backend.app.db.models.foundation import Tenant
    from backend.app.main import app

    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "LEADER,APPROVER")
    sent: list[tuple] = []
    monkeypatch.setattr(auth_router, "_send_welcome_quietly", lambda *args: sent.append(args))
    for label, extra in (("mfa-roles-invited-leader", "LEADER"), ("mfa-roles-invited-plain", None)):
        with SessionLocal() as db:
            bind_system(db, "test: invited with an additional role")
            user = _user(db, db.get(Tenant, world["tenant_id"]), "Investigator", label)
            user.status, user.email_verified = "INVITED", False
            db.commit()
            user_id = user.id
            token = issue_invitation(db, user_id, world["tenant_id"])
            db.commit()
        if extra:
            _grant(world, user_id, extra)
        activated = TestClient(app).post(
            "/api/v1/auth/activate-account", json={"token": token, "password": "A passphrase only I know 2026"}
        )
        assert activated.status_code == 200, activated.text
    assert [args[2] for args in sent] == [True, False]
