"""Session lifetime: one-hour windows renewed while in use, never past 12 hours after sign-in; the session endpoint
says when the session ends (absolute and idle) so the browser can warn; the licence state the session reports."""

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from auth import cookies
from auth.durable import new_session
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.request_context import _idle_limit, renew_session_if_due, session_expiry
from tests.test_auth_hardening import _user
from tests.test_customer_admin_account_security import _tenant
from tests.test_customer_admin_account_security import _user as _user_in

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def test_the_limits_are_one_hour_windows_within_twelve_hours():
    assert cookies.SESSION_SECONDS == 12 * 3600
    assert cookies.SESSION_WINDOW_SECONDS == 3600
    assert cookies.SESSION_RENEWAL_SECONDS == 30 * 60
    assert cookies.PENDING_MFA_SECONDS <= 600


# ------------------------------------------------------------------------------------------- renewal rule


def _row(created_minutes_ago: float, expires_in_minutes: float, mfa_state=None):
    return SimpleNamespace(
        created_at=NOW - timedelta(minutes=created_minutes_ago),
        expires_at=NOW + timedelta(minutes=expires_in_minutes),
        mfa_state=mfa_state,
        last_seen_at=NOW,
    )


def test_a_session_with_plenty_of_window_left_is_not_renewed():
    row = _row(10, 50)
    assert renew_session_if_due(row, NOW, None, None) is False
    assert row.expires_at == NOW + timedelta(minutes=50)


def test_a_session_in_use_near_the_end_of_its_window_gets_another_hour():
    row = _row(40, 20)
    assert renew_session_if_due(row, NOW, None, None) is True
    assert row.expires_at == NOW + timedelta(hours=1)


def test_renewal_never_passes_twelve_hours_after_sign_in():
    row = _row(11 * 60 + 40, 10)  # signed in 11h40m ago: 20 minutes of the absolute limit remain
    assert renew_session_if_due(row, NOW, None, None) is True
    assert row.expires_at == row.created_at + timedelta(hours=12)
    at_limit = _row(11 * 60 + 50, 10)  # the window already ends at the absolute limit
    assert renew_session_if_due(at_limit, NOW, None, None) is False
    assert at_limit.expires_at == at_limit.created_at + timedelta(hours=12)


def test_a_session_that_still_owes_mfa_is_never_renewed():
    row = _row(5, 5, mfa_state="VERIFY")
    assert renew_session_if_due(row, NOW, None, None) is False


def test_the_idle_deadline_is_the_earlier_of_idle_timeout_and_absolute_end():
    active = _row(10, 50)
    expiry = session_expiry(active, NOW)
    assert expiry["expires_at"] == active.expires_at.isoformat()
    assert expiry["idle_expires_at"] == min(active.expires_at, NOW + _idle_limit()).isoformat()
    ending = _row(10, 5)
    assert session_expiry(ending, NOW)["idle_expires_at"] == ending.expires_at.isoformat()


# ------------------------------------------------------------------------------------------- through the API


def _session_for(user, *, created_ago: timedelta, expires_in: timedelta):
    with SessionLocal() as db:
        token = new_session(db, user.id, user.tenant_id)
        row = db.query(AuthSession).filter(AuthSession.session_hash == hashlib.sha256(token.encode()).hexdigest()).one()
        now = datetime.now(timezone.utc)
        row.created_at = now - created_ago
        row.expires_at = now + expires_in
        row.last_seen_at = now
        db.commit()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, token


def _stored_expiry(token):
    with SessionLocal() as db:
        return (
            db.query(AuthSession.expires_at)
            .filter(AuthSession.session_hash == hashlib.sha256(token.encode()).hexdigest())
            .scalar()
        )


def _cookie_max_age(response) -> int | None:
    header = response.headers.get("set-cookie") or ""
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name.lower() == "max-age":
            return int(value)
    return None


def test_the_session_endpoint_reports_both_deadlines():
    client, token = _session_for(_user(), created_ago=timedelta(minutes=5), expires_in=timedelta(minutes=55))
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200, response.text
    body = response.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    idle_expires_at = datetime.fromisoformat(body["idle_expires_at"])
    assert expires_at == _stored_expiry(token)
    assert idle_expires_at <= expires_at
    assert idle_expires_at - datetime.now(timezone.utc) <= _idle_limit()
    # Nothing to renew yet; the cookie is re-issued anyway, to the server's own end of the session.
    assert expires_at - datetime.now(timezone.utc) > timedelta(minutes=50)
    assert abs(_cookie_max_age(response) - (expires_at - datetime.now(timezone.utc)).total_seconds()) < 60


def test_an_active_session_is_renewed_by_the_session_endpoint_and_its_cookie_reissued():
    client, token = _session_for(_user(), created_ago=timedelta(hours=1), expires_in=timedelta(minutes=10))
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200, response.text
    renewed = _stored_expiry(token)
    assert renewed - datetime.now(timezone.utc) > timedelta(minutes=55)
    assert datetime.fromisoformat(response.json()["expires_at"]) == renewed
    assert 3500 <= _cookie_max_age(response) <= 3600


def test_any_signed_in_request_renews_but_never_past_twelve_hours():
    client, token = _session_for(_user(), created_ago=timedelta(hours=11, minutes=45), expires_in=timedelta(minutes=5))
    # A route that resolves the session itself renews it on the server...
    response = client.get("/api/v1/me/context")
    assert response.status_code == 200, response.text
    renewed = _stored_expiry(token)
    remaining = renewed - datetime.now(timezone.utc)
    assert timedelta(minutes=13) < remaining <= timedelta(minutes=15)
    # ...and the browser's next session check brings the cookie up to the same end, capped at twelve hours.
    check = client.get("/api/v1/auth/session")
    assert check.status_code == 200 and datetime.fromisoformat(check.json()["expires_at"]) == renewed
    assert 13 * 60 < _cookie_max_age(check) <= 15 * 60


def test_a_route_with_the_context_as_a_dependency_reissues_the_cookie_itself():
    client, token = _session_for(_user(), created_ago=timedelta(hours=1), expires_in=timedelta(minutes=10))
    listed = client.get("/api/v1/support/problems")
    assert listed.status_code == 200, listed.text
    assert _stored_expiry(token) - datetime.now(timezone.utc) > timedelta(minutes=55)
    assert 3500 <= _cookie_max_age(listed) <= 3600


# ------------------------------------------------------------------------------------------- licence state


@pytest.mark.parametrize("with_plan", [True, False])
def test_the_licence_is_active_only_for_an_active_organization_with_a_plan(with_plan):
    # Each case makes its own ACTIVE organization, so the answer never depends on what another test left behind.
    from backend.app.db.models.foundation import PlanDefinition, TenantPlanAssignment

    with SessionLocal() as db:
        bind_system(db, "test: an organization with or without a plan")
        organization = _tenant(db, "LIC")
        if with_plan:
            plan = db.query(PlanDefinition).filter(PlanDefinition.status == "ACTIVE").first()
            assert plan is not None, "the seeded plans include an active one"
            now = datetime.now(timezone.utc)
            db.add(
                TenantPlanAssignment(
                    tenant_id=organization.id,
                    plan_id=plan.id,
                    status="ACTIVE",
                    effective_from=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        person = _user_in(db, organization, "Investigator", "licence-user")
        db.commit()
        db.refresh(person)
        db.expunge(person)
    client, _ = _session_for(person, created_ago=timedelta(minutes=1), expires_in=timedelta(minutes=59))
    license_state = client.get("/api/v1/session/context").json()["license"]
    expected = "ACTIVE" if with_plan else "INACTIVE"
    assert license_state == {"state": expected, "effective": with_plan}
