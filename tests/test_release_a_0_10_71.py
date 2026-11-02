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


# ------------------------------------------------------------------------------------------- A2: sample-only trials

IMPORT_PREFIXES = ("/api/v1/data/import", "/api/v1/trial/imports")
# Not an import: a set-aside row dismissed with a reason brings nothing in (a sample row may be dismissed).
NOT_IMPORTS = {("POST", "/api/v1/data/import/quarantine/{row_id}/dismiss")}


def _import_routes():
    from tests.route_inventory import api_routes

    for path, route in api_routes(app):
        if not path.startswith(IMPORT_PREFIXES):
            continue
        for method in sorted(route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            if (method, path) not in NOT_IMPORTS:
                yield method, path, route


def _set_tenant(admin, tenant_id, **changes):
    detail = _ok(admin.get(f"/api/v1/platform-admin/tenants/{tenant_id}"))
    tenant = detail.get("tenant", detail)
    return admin.patch(
        f"/api/v1/platform-admin/tenants/{tenant_id}",
        json={**changes, "reason": "Judge trial for the event (test)", "lock_version": tenant["lock_version"]},
    )


@pytest.fixture(scope="module")
def trial():
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    try:
        yield {"user": user, "tenant_id": approval["tenant_id"]}
    finally:
        _purge(approval["tenant_id"])


def test_every_import_route_refuses_a_sample_only_trial():
    from backend.app.data_import_router import refuse_sample_only

    routes = list(_import_routes())
    # The check, the import and a set-aside row's fix and re-process, and the trial's two aliases (distribution and
    # every other template is an entity of the same routes).
    assert {path for _, path, _ in routes} == {
        "/api/v1/data/import/{entity}/check",
        "/api/v1/data/import/{entity}",
        "/api/v1/data/import/quarantine/{row_id}/reprocess",
        "/api/v1/trial/imports/{entity}/check",
        "/api/v1/trial/imports/{entity}",
    }
    for method, path, route in routes:
        assert any(dep.dependency is refuse_sample_only for dep in route.dependencies), f"{method} {path}"


def test_a_sample_only_trial_is_refused_in_plain_words_and_a_normal_trial_keeps_its_upload(trial):
    from backend.app.data_import_router import SAMPLE_ONLY_MESSAGE

    admin, user, tenant_id = authenticated_client(), trial["user"], trial["tenant_id"]
    assert _ok(user.get("/api/v1/session/context"))["sample_only"] is False
    csv = b"complaint_id,product_id,description\nOWN-1,SAMPLE-PULSE-410,Display flickers\n"
    headers = {"Content-Type": "text/csv"}
    # A normal trial checks its own file (whatever the check finds, it is not refused).
    assert user.post("/api/v1/data/import/complaints/check", content=csv, headers=headers).status_code != 403
    # The trial's own user may not set it; a platform administrator does, with a reason, audited.
    assert user.patch(
        f"/api/v1/platform-admin/tenants/{tenant_id}", json={"sample_only": True, "reason": "x" * 12, "lock_version": 1}
    ).status_code in (401, 403)
    changed = _set_tenant(admin, tenant_id, sample_only=True)
    assert changed.status_code == 200, changed.text
    assert changed.json()["updated"] == {"sample_only": True} and changed.json()["tenant"]["sample_only"] is True
    assert _ok(user.get("/api/v1/session/context"))["sample_only"] is True
    try:
        row = uuid.uuid4()
        for path in (
            "/api/v1/data/import/complaints/check",
            "/api/v1/data/import/complaints",
            "/api/v1/data/import/distribution",
            "/api/v1/trial/imports/complaints/check",
            "/api/v1/trial/imports/complaints",
        ):
            refused = user.post(path, content=csv, headers=headers)
            assert refused.status_code == 403, (path, refused.text)
            assert refused.json()["detail"] == {"code": "SAMPLE_ONLY_TRIAL", "message": SAMPLE_ONLY_MESSAGE}
        refused = user.post(f"/api/v1/data/import/quarantine/{row}/reprocess", json={"row": {"description": "x"}})
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SAMPLE_ONLY_TRIAL"
        # Reading the sample's data-quality reports stays open.
        assert user.get("/api/v1/data/import/runs").status_code == 200
        with SessionLocal() as db:
            bind_system(db, "test: the change is audited")
            from backend.app.db.models.foundation import AuditEvent

            event = (
                db.query(AuditEvent)
                .filter(AuditEvent.entity_id == uuid.UUID(tenant_id), AuditEvent.action == "TENANT_UPDATED")
                .order_by(AuditEvent.created_at.desc())
                .first()
            )
            assert event.details["after"] == {"sample_only": True} and event.details["reason"]
    finally:
        assert _set_tenant(admin, tenant_id, sample_only=False).status_code == 200
    assert user.post("/api/v1/data/import/complaints/check", content=csv, headers=headers).status_code != 403
