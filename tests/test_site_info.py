"""Website company details and lawyer-supplied legal documents (backend/app/site_info.py)."""

from fastapi.testclient import TestClient

from backend.app import config_check
from backend.app.main import app

client = TestClient(app)


def test_site_info_shows_the_configured_company(monkeypatch):
    monkeypatch.setenv("MDARIX_COMPANY_LEGAL_NAME", "Example Labs Ltd")
    monkeypatch.setenv("MDARIX_COMPANY_ADDRESS", "1 Main Street, Boston MA")
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@example.com")
    monkeypatch.delenv("MDARIX_PRIVACY_EMAIL", raising=False)
    monkeypatch.setenv("MDARIX_LEGAL_TEXT_APPROVED", "false")
    body = client.get("/api/v1/public/site-info").json()
    assert body["company_name"] == "Example Labs Ltd" and body["support_email"] == "support@example.com"
    assert body["privacy_email"] is None and body["legal_text_approved"] is False
    assert body["trial"]["data_deleted_after_days"] == 30


def test_sign_up_reads_the_free_mail_domains_that_automatic_approval_uses():
    """The website's note for a personal address uses the server's own list, so the two never disagree."""
    from backend.app.trial.auto_approval import FREE_MAIL_DOMAINS, is_company_domain

    domains = client.get("/api/v1/public/site-info").json()["trial"]["free_mail_domains"]
    assert domains == sorted(FREE_MAIL_DOMAINS) and "gmail.com" in domains
    assert not any(is_company_domain(domain) for domain in domains)


def test_the_version_the_server_runs_is_answered_fresh_without_a_session(monkeypatch):
    """An open tab compares it with the version it was built as (frontend/src/features/shared/appVersion.ts)."""
    from backend.app.version import APP_VERSION

    monkeypatch.setenv("MDARIX_RELEASE", "2026.10.3")  # a deployment's release tag does not change the number
    response = TestClient(app).get("/api/v1/public/version")  # no cookie: the check never touches a session
    assert response.status_code == 200
    assert response.json() == {"version": APP_VERSION}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("set-cookie") is None


def test_a_legal_document_is_served_only_once_it_has_been_supplied(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_LEGAL_DIR", str(tmp_path))
    assert client.get("/api/v1/public/legal/privacy").json() == {
        "document": "privacy",
        "available": False,
        "markdown": None,
    }
    (tmp_path / "privacy.md").write_text("# Privacy policy\n\nApproved text.", encoding="utf-8")
    body = client.get("/api/v1/public/legal/privacy").json()
    assert body["available"] is True and body["markdown"].startswith("# Privacy policy")


def test_only_the_known_legal_documents_can_be_read(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_LEGAL_DIR", str(tmp_path))
    (tmp_path / "secret.md").write_text("not public", encoding="utf-8")
    for name in ("secret", "..%2Fsecret", "privacy.md"):
        assert client.get(f"/api/v1/public/legal/{name}").status_code == 404


def test_production_needs_every_approved_legal_document(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.delenv("MDARIX_LEGAL_DIR", raising=False)
    assert any("MDARIX_LEGAL_DIR must be" in item for item in config_check.problems())
    monkeypatch.setenv("MDARIX_LEGAL_DIR", str(tmp_path))
    (tmp_path / "privacy.md").write_text("x", encoding="utf-8")
    found = [item for item in config_check.problems() if "MDARIX_LEGAL_DIR" in item]
    assert found == ["MDARIX_LEGAL_DIR is missing terms.md, trial-agreement.md"]
    (tmp_path / "terms.md").write_text("x", encoding="utf-8")
    (tmp_path / "trial-agreement.md").write_text("x", encoding="utf-8")
    assert not any("MDARIX_LEGAL_DIR" in item for item in config_check.problems())
