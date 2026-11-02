"""Browser-facing protections: cross-site requests, HTTPS-only, password-reset answers and CSV formulas."""

import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from tests.test_business_permissions import _client_with_role


def test_a_cookie_request_from_a_foreign_site_is_refused_even_locally():
    user = _client_with_role("INVESTIGATOR")
    path = "/api/v1/stage3/interactions"
    foreign = user.post(path, json={"prompt": "Hi"}, headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403 and foreign.json()["detail"]["code"] == "CSRF_ORIGIN_DENIED"
    referer = user.post(path, json={"prompt": "Hi"}, headers={"Referer": "https://evil.example/page"})
    assert referer.status_code == 403
    for origin in ("http://127.0.0.1:5177", "http://localhost:5177"):
        assert user.post(path, json={"prompt": ""}, headers={"Origin": origin}).status_code != 403


def test_production_requires_the_apps_own_origin(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.mdarix.example")
    user = _client_with_role("INVESTIGATOR")
    # Production reads only the host-bound cookie name (auth/cookies.py).
    user.cookies.set("__Host-mdarix_session", user.cookies.get("mdarix_session"))
    no_origin = user.post("/api/v1/stage3/interactions", json={"prompt": "Hi"})
    assert no_origin.status_code == 403
    local = user.post("/api/v1/stage3/interactions", json={"prompt": "Hi"}, headers={"Origin": "http://127.0.0.1:5177"})
    assert local.status_code == 403
    own = user.post(
        "/api/v1/stage3/interactions", json={"prompt": ""}, headers={"Origin": "https://app.mdarix.example"}
    )
    assert own.status_code != 403


def test_https_only_header_in_production(monkeypatch):
    client = TestClient(app)
    assert "strict-transport-security" not in client.get("/health/live").headers
    monkeypatch.setenv("MDARIX_ENV", "production")
    header = client.get("/health/live").headers.get("strict-transport-security", "")
    assert "max-age=31536000" in header


def test_password_reset_answers_the_same_for_every_email(monkeypatch):
    monkeypatch.setenv("MDARIX_SMTP_HOST", "smtp.example.invalid")
    for name in ("MDARIX_SMTP_USERNAME", "MDARIX_SMTP_PASSWORD", "MDARIX_SMTP_FROM"):
        monkeypatch.setenv(name, "configured")
    monkeypatch.setattr("backend.app.auth_router.send_password_reset_email", lambda email, token: "SENT")
    client = TestClient(app)
    known = client.post("/api/v1/auth/forgot-password", json={"email": "legacy-test-auth@synthetic.invalid"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex}@example.invalid"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == {"status": "RESET_REQUEST_ACCEPTED", "email_delivery": "ACCEPTED"}


def test_spreadsheet_formulas_are_refused_in_imports():
    user = _client_with_role("INVESTIGATOR")
    csv = 'complaint_id,product_id,received_date,description\nF-1,P-1,2026-10-01,"=HYPERLINK(""http://evil.example"",""x"")"\n'
    checked = user.post("/api/v1/data/import/complaints/check", content=csv, headers={"Content-Type": "text/csv"})
    issues = checked.json().get("issues", [])
    assert any("formula" in issue["message"] for issue in issues), checked.text
