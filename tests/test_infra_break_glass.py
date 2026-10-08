"""Break-glass MFA reset for platform administrators (scripts/reset_platform_admin_mfa.py), against the test database."""

from __future__ import annotations

import importlib.util
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reset_script = _load("reset_platform_admin_mfa")
create_script = _load("create_platform_admin")


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "test: break-glass MFA reset")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _account(db, role: str) -> AuthUser:
    """An MFA-enrolled account in the MDARIX_PLATFORM organization (created on first use, as the bootstrap does)."""
    now = datetime.now(timezone.utc)
    tenant = create_script._operator_tenant(db, now)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username=f"break-glass-{uuid.uuid4().hex[:10]}@mdarix-ci.test",
        display_name="Break Glass",
        company=tenant.display_name,
        password_hash="unusable",
        role=role,
        status="ACTIVE",
        email_verified=True,
        mfa_required=True,
        mfa_secret_encrypted="ciphertext",
        mfa_recovery_hashes=["hash"],
        mfa_enrolled_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    bind_system(db, "test: break-glass MFA reset")
    return user


def test_a_platform_administrators_mfa_is_cleared_and_audited(db):
    user = _account(db, "PLATFORM_ADMIN")
    reason = f"Lost phone, ticket OPS-{secrets.randbelow(10_000)}"

    result = reset_script.reset_platform_admin_mfa(db, user.username, reason, "ci-operator")
    db.commit()
    bind_system(db, "test: break-glass MFA reset")

    assert result["status"] == "RESET" and result["was_enrolled"] is True
    db.refresh(user)
    assert user.mfa_secret_encrypted is None and user.mfa_recovery_hashes is None and user.mfa_enrolled_at is None
    event = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_id == user.id, AuditEvent.action == reset_script.AUDIT_ACTION)
        .one()
    )
    assert event.tenant_id == user.tenant_id
    assert event.actor_ref == "break-glass:ci-operator"
    assert event.reason == reason
    assert event.details["source"] == "scripts/reset_platform_admin_mfa.py"


def test_other_accounts_are_left_to_their_administrators(db):
    user = _account(db, "INVESTIGATOR")
    result = reset_script.reset_platform_admin_mfa(db, user.username, "Lost phone, ticket OPS-1", "ci-operator")
    assert result["status"] == "NOT_PLATFORM_ADMIN"
    db.rollback()
    bind_system(db, "test: break-glass MFA reset")
    db.refresh(user)
    assert user.mfa_enrolled_at is not None


def test_an_unknown_address_changes_nothing(db):
    result = reset_script.reset_platform_admin_mfa(db, "nobody@mdarix-ci.test", "Lost phone, ticket OPS-1", "ci")
    assert result["status"] == "NOT_FOUND"


def test_the_command_requires_a_real_reason(capsys):
    assert reset_script.main(["admin@mdarix-ci.test", "--reason", "lost"]) == 2
    assert "at least 10 characters" in capsys.readouterr().err
