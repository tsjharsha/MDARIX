import pytest

from access_control.configuration_safety import safe_configuration
from backend.app.access.common import _safe_provider_url


def test_managed_secret_reference_is_allowed_but_secret_values_are_not_persistable():
    reference = "MDARIX_CONNECTOR_SECRET_TRACKWISE"
    assert (
        safe_configuration({"credential_ref": reference, "endpoint": "https://provider.example"})["credential_ref"]
        == reference
    )
    with pytest.raises(ValueError):
        safe_configuration({"api_token": "secret-value"})
    # Only the connector secret namespace may be referenced: never database, AI, email or arbitrary names.
    for forbidden in (
        "bad ref",
        "TRACKWISE_TOKEN",
        "POSTGRES_PASSWORD",
        "MDARIX_GENAI_API_KEY",
        "MDARIX_SMTP_PASSWORD",
    ):
        with pytest.raises(ValueError):
            safe_configuration({"credential_ref": forbidden})


def test_provider_urls_strip_fragments_and_reject_private_destinations_in_production(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    with pytest.raises(ValueError, match="PRIVATE_DESTINATION"):
        _safe_provider_url("http://127.0.0.1:8101", "health")
    assert _safe_provider_url("https://93.184.216.34/base", "/schema", timeout=5) == "https://93.184.216.34/schema"
    # Development no longer opens internal addresses; only an explicitly allowlisted host is reachable.
    monkeypatch.setenv("MDARIX_ENV", "development")
    monkeypatch.delenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", raising=False)
    with pytest.raises(ValueError, match="PRIVATE_DESTINATION"):
        _safe_provider_url("http://127.0.0.1:8101", "health")
    monkeypatch.setenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", "127.0.0.1:8101")
    assert _safe_provider_url("http://127.0.0.1:8101", "health") == "http://127.0.0.1:8101/health"
    with pytest.raises(ValueError, match="PRIVATE_DESTINATION"):
        _safe_provider_url("http://127.0.0.1:5432", "health")
