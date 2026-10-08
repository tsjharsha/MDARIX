"""Demo requests from the website: the public form is validated and rate limited; only Platform Admins see them."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

URL = "/api/v1/public/demo-requests"


def _email() -> str:
    return f"demo-{uuid.uuid4().hex[:10]}@example.invalid"


def _rows(email: str) -> list:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT display_name, phone, status FROM demo_requests WHERE email=:e"), {"e": email}
        ).all()


@pytest.fixture(autouse=True)
def _clean_up():
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM demo_requests WHERE email LIKE 'demo-%@example.invalid'"))


def _submit(client, **fields):
    body = {"name": "Priya  Sharma", "email": _email(), "phone": "+91 98765 43210", **fields}
    return client.post(URL, json=body), body


def test_a_visitor_requests_a_demo_without_signing_in():
    response, body = _submit(TestClient(app))
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "DEMO_REQUEST_RECEIVED"}
    # Stored as typed, with extra spaces removed; nothing about the request is echoed back.
    assert _rows(body["email"]) == [("Priya Sharma", "+91 98765 43210", "NEW")]


@pytest.mark.parametrize(
    "fields, field",
    [
        ({"name": "<script>alert(1)</script>"}, "name"),
        ({"name": "http://spam.example"}, "name"),
        ({"email": "not-an-email"}, "email"),
        ({"phone": "call me maybe"}, "phone"),
        ({"phone": "+1 (12)"}, "phone"),
    ],
)
def test_invalid_details_are_refused_with_the_field_named(fields, field):
    response, body = _submit(TestClient(app), **fields)
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == field
    assert _rows(body["email"]) == []


def test_a_repeat_request_while_one_is_open_is_not_stored_twice():
    client = TestClient(app)
    email = _email()
    assert _submit(client, email=email)[0].status_code == 200
    assert _submit(client, email=email)[0].status_code == 200
    assert len(_rows(email)) == 1


def test_an_automated_submission_is_answered_but_not_stored():
    response, body = _submit(TestClient(app), website="http://spam.example")
    assert response.status_code == 200
    assert _rows(body["email"]) == []


def test_one_sender_is_rate_limited(monkeypatch):
    monkeypatch.setenv("MDARIX_DEMO_REQUESTS_PER_SOURCE_HOUR", "2")
    monkeypatch.setenv("MDARIX_DEMO_REQUEST_SALT", uuid.uuid4().hex)  # a fresh sender for this test
    client = TestClient(app)
    assert _submit(client)[0].status_code == 200
    assert _submit(client)[0].status_code == 200
    refused, body = _submit(client)
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "DEMO_REQUEST_LIMIT"
    assert _rows(body["email"]) == []


def test_only_platform_admins_list_and_update_demo_requests():
    _, body = _submit(TestClient(app))
    assert TestClient(app).get("/api/v1/platform-admin/demo-requests").status_code == 401
    assert _client_with_role("CUSTOMER_ADMIN").get("/api/v1/platform-admin/demo-requests").status_code == 403

    admin = authenticated_client()
    listed = admin.get("/api/v1/platform-admin/demo-requests").json()
    item = next(i for i in listed["items"] if i["email"] == body["email"])
    assert item["name"] == "Priya Sharma" and item["phone"] == "+91 98765 43210" and item["status"] == "NEW"
    assert listed["counts"]["NEW"] >= 1

    updated = admin.post(
        f"/api/v1/platform-admin/demo-requests/{item['id']}/status", json={"status": "contacted", "note": "Call booked"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "CONTACTED" and updated.json()["note"] == "Call booked"
    assert (
        admin.post(f"/api/v1/platform-admin/demo-requests/{item['id']}/status", json={"status": "DELETED"}).status_code
        == 422
    )
    with engine.connect() as conn:
        audited = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE action='DEMO_REQUEST_STATUS_CHANGED' AND entity_id=:id"),
            {"id": item["id"]},
        ).scalar_one()
    assert audited == 1


def test_the_visitor_gets_one_acknowledgement_and_a_mail_failure_never_shows(monkeypatch):
    from auth import emailer

    sent = []
    monkeypatch.setattr(
        emailer,
        "send_demo_request_acknowledgement",
        lambda recipient, **kw: sent.append((recipient, kw["display_name"])) or "SENT",
    )
    client = TestClient(app)
    response, body = _submit(client)
    assert response.status_code == 200
    assert sent == [(body["email"], "Priya Sharma")]
    _submit(client, email=body["email"])  # the same open request again: no second email
    _submit(client, website="http://spam.example")  # automated: nothing stored, nothing sent
    assert len(sent) == 1

    def refuse(*_args, **_kwargs):
        raise emailer.EmailDeliveryError("provider down")

    monkeypatch.setattr(emailer, "send_demo_request_acknowledgement", refuse)
    failed, failed_body = _submit(client)
    assert failed.status_code == 200 and failed.json() == {"status": "DEMO_REQUEST_RECEIVED"}
    assert len(_rows(failed_body["email"])) == 1
