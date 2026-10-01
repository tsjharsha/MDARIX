"""A missing or unknown MDARIX_ENV must mean production: no tokens on screen, strict network checks, no API docs."""

import pytest

from backend.app import runtime_env


@pytest.mark.parametrize("value", [None, "", "prod", "Development ", "anything"])
def test_unset_or_unknown_environment_is_production(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MDARIX_ENV", raising=False)
    else:
        monkeypatch.setenv("MDARIX_ENV", value)
    expected = runtime_env.DEVELOPMENT if value == "Development " else runtime_env.PRODUCTION
    assert runtime_env.environment() == expected


def test_reset_and_invite_tokens_are_never_returned_without_an_explicit_development_setting(monkeypatch):
    from backend.app.access.common import _development_token as access_token
    from backend.app.auth_router import _development_token as auth_token

    monkeypatch.delenv("MDARIX_ENV", raising=False)
    assert auth_token("secret-reset-token") is None
    assert access_token("secret-invite-token") is None
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert auth_token("secret-reset-token") == "secret-reset-token"


def test_connector_urls_to_private_addresses_are_refused_without_an_explicit_development_setting(monkeypatch):
    from backend.app.access.common import _safe_provider_url

    monkeypatch.delenv("MDARIX_ENV", raising=False)
    for url in ("http://127.0.0.1:5432/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/api"):
        with pytest.raises(ValueError, match="CONNECTOR_PRIVATE_DESTINATION_BLOCKED"):
            _safe_provider_url(url, "health")
