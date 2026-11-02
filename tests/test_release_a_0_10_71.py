"""0.10.71, Release A of the "Simplicity and WoW" plan: the first five minutes.

- A1: a new free trial is created on the new navigation; existing organizations keep theirs. A fresh sign-up through
  the public flow (request, approval, activation e-mail, password, authenticator) reaches the new navigation without
  anyone switching it.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from auth import emailer, totp
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE
from tests.test_free_trial import PASSWORD, _request_id

pytestmark = pytest.mark.db


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, uuid.UUID(str(tenant_id)), "test:release-a-cleanup")


@pytest.fixture()
def mail_sink(monkeypatch):
    """A test mail sink: every e-mail MDARIX would send is kept here, never sent."""
    sent: list[dict] = []

    def keep(recipient, subject, body, html_body=None, *, reply_to=None):
        sent.append({"to": recipient, "subject": subject, "text": body})
        return "SENT"

    monkeypatch.setattr(emailer, "_send_email", keep)
    return sent


def test_a_fresh_signup_through_the_public_flow_lands_on_the_new_navigation(mail_sink):
    admin = authenticated_client()
    email = f"fresh-{uuid.uuid4().hex[:10]}@example.invalid"
    # 1. The public request (the website's form): nothing but a request.
    _ok(
        TestClient(app).post(
            "/api/v1/auth/signup",
            json={"email": email, "display_name": "Fresh Quality", "organization": "Fresh Devices Ltd", **PROFILE},
        )
    )
    # 2. A platform administrator approves it; nobody touches the navigation.
    approval = _ok(admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"))
    tenant_id = approval["tenant_id"]
    try:
        # 3. The activation e-mail, from the sink: its link carries the token.
        links = [
            found.group(0)
            for message in mail_sink
            if message["to"] == email
            for found in [re.search(r"\S*/activate-account\?token=[^\s\"<>]+", message["text"])]
            if found
        ]
        assert len(links) == 1, [message["subject"] for message in mail_sink]
        link = links[0]
        token = parse_qs(urlparse(link).query)["token"][0]
        # 4. The password, then sign-in, then the authenticator.
        user = TestClient(app)
        _ok(user.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}))
        _ok(user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}))
        secret = _ok(user.post("/api/v1/auth/mfa/enroll"))["secret"]
        _ok(user.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)}))
        # 5. The first screen: the new navigation, a trial with the sample, and no administrator switched anything.
        context = _ok(user.get("/api/v1/session/context"))
        assert context["navigation"] == "new"
        status = _ok(user.get("/api/v1/trial/status"))
        assert status["is_trial"] and status["sample"]["complaints"] > 0
        with SessionLocal() as db:
            bind_system(db, "test: who set the navigation")
            from backend.app.db.models.foundation import AuditEvent

            switched = (
                db.query(AuditEvent)
                .filter(AuditEvent.entity_id == uuid.UUID(tenant_id), AuditEvent.action == "TENANT_UPDATED")
                .count()
            )
        assert switched == 0
    finally:
        _purge(tenant_id)


def test_only_new_trials_get_the_new_navigation_existing_organizations_keep_theirs():
    with SessionLocal() as db:
        bind_system(db, "test: the navigation of every organization before")
        before = {row.id: row.navigation for row in db.query(Tenant.id, Tenant.navigation)}
    admin = authenticated_client()
    email = f"nav-{uuid.uuid4().hex[:10]}@example.invalid"
    _ok(
        TestClient(app).post(
            "/api/v1/auth/signup",
            json={"email": email, "display_name": "Nav Quality", "organization": "Nav Devices Ltd", **PROFILE},
        )
    )
    approval = _ok(admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"))
    try:
        with SessionLocal() as db:
            bind_system(db, "test: the navigation of every organization after")
            after = {row.id: row.navigation for row in db.query(Tenant.id, Tenant.navigation)}
        new_id = uuid.UUID(approval["tenant_id"])
        assert after.pop(new_id) == "new"
        # Every organization that existed keeps its navigation (trials and pilots, classic or new).
        assert {key: value for key, value in after.items() if key in before} == before
        assert "classic" in before.values()
    finally:
        _purge(approval["tenant_id"])


def test_an_organization_created_outside_the_trial_approval_stays_classic():
    from datetime import datetime, timezone

    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        bind_system(db, "test: a pilot's tenant")
        _, tenant = build_customer_tenant(
            db=db, tenant_key="PILOT_NAV_CHECK", name="Pilot Nav Check", status="ACTIVE", now=datetime.now(timezone.utc)
        )
        db.rollback()
    # Not set in code: the column's default, classic, applies when it is written.
    assert tenant.navigation in (None, "classic")
