"""The staging/production configuration gate (backend/app/config_check.py), one rule at a time.

Each test starts from a complete, valid production configuration (no database needed: ``offline=True`` unless the test
is about the database checks) and breaks exactly one thing, so a rule that stops firing, or fires on a good server,
fails here by name.
"""

from __future__ import annotations

import base64
import os
import secrets
from types import SimpleNamespace

import pytest

from backend.app import config_check

KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def production(monkeypatch, tmp_path):
    """A production environment that passes every offline check."""
    for name in list(os.environ):
        if name.startswith(("MDARIX_", "POSTGRES_SSL")):
            monkeypatch.delenv(name, raising=False)
    legal = tmp_path / "legal"
    legal.mkdir()
    for name in ("privacy.md", "terms.md", "trial-agreement.md"):
        (legal / name).write_text("# approved\n", encoding="utf-8")
    values = {
        "MDARIX_ENV": "production",
        "MDARIX_APP_URL": "https://app.mdarix-pilot.test",
        "MDARIX_DOMAIN": "app.mdarix-pilot.test",
        "POSTGRES_SSLMODE": "verify-full",
        "MDARIX_DB_RUNTIME_USER": "mdarix_runtime",
        "MDARIX_DB_RUNTIME_PASSWORD": secrets.token_urlsafe(32),
        "MDARIX_DB_OWNER_USER": "mdarix_owner",
        "MDARIX_RLS_SYSTEM_TOKEN": secrets.token_urlsafe(48),
        "MDARIX_MFA_ENCRYPTION_KEY": KEY,
        "MDARIX_CONNECTOR_ENCRYPTION_KEY": KEY,
        "MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY": KEY,
        "MDARIX_OBJECT_STORAGE_SIGNING_SECRET": secrets.token_urlsafe(40),
        "MDARIX_DEMO_REQUEST_SALT": secrets.token_urlsafe(40),
        "MDARIX_RATE_LIMIT_SALT": secrets.token_urlsafe(40),
        "MDARIX_OBJECT_STORAGE_PROVIDER": "local",
        "MDARIX_CLAMD_HOST": "clamav",
        "MDARIX_SMTP_HOST": "smtp.mdarix-pilot.test",
        "MDARIX_SMTP_USERNAME": "mailer",
        "MDARIX_SMTP_PASSWORD": secrets.token_urlsafe(16),
        "MDARIX_SMTP_FROM": "MDARIX <no-reply@mdarix-pilot.test>",
        "MDARIX_SUPPORT_EMAIL": "support@mdarix-pilot.test",
        "MDARIX_PRIVACY_EMAIL": "privacy@mdarix-pilot.test",
        "MDARIX_COMPANY_LEGAL_NAME": "MDARIX Pilot Ltd",
        "MDARIX_COMPANY_ADDRESS": "1 Quality Street",
        "MDARIX_LEGAL_TEXT_APPROVED": "true",
        "MDARIX_LEGAL_DIR": str(legal),
        "MDARIX_ALERT_WEBHOOK": "https://hooks.mdarix-pilot.test/ops",
        "MDARIX_TRIAL_ALERT_EMAIL": "sales@mdarix-pilot.test",
        "MDARIX_TRUSTED_PROXY_HOPS": "1",
        "MDARIX_GENAI_PROVIDER": "controlled",
        "MDARIX_BACKUP_AGE_RECIPIENT": "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p",
        "MDARIX_BACKUP_S3_URI": "s3://mdarix-pilot-backups/prod",
        "MDARIX_BACKUP_HEARTBEAT_URL": "https://hc.mdarix-pilot.test/backup",
        "MDARIX_SCHEDULER_HEARTBEAT_URL": "https://hc.mdarix-pilot.test/scheduler",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def found(**kwargs) -> str:
    return "\n".join(config_check.problems(offline=True, **kwargs))


def test_the_baseline_production_configuration_passes(production):
    assert config_check.problems(offline=True) == []


def test_development_and_test_runs_are_never_checked(production):
    production.setenv("MDARIX_ENV", "development")
    production.delenv("MDARIX_SMTP_HOST")
    assert config_check.problems() == []
    production.setenv("MDARIX_ENV", "test")
    assert config_check.problems() == []


def test_an_unset_environment_is_checked_as_production(production):
    production.delenv("MDARIX_ENV")
    production.setenv("POSTGRES_SSLMODE", "require")
    assert "verify-full in production" in found()


# ------------------------------------------------------------------ alerting


def test_operational_alerts_need_a_destination(production):
    production.delenv("MDARIX_ALERT_WEBHOOK")
    assert "operational alerts need a destination" in found()
    production.setenv("MDARIX_ALERT_EMAIL", "ops@mdarix-pilot.test")
    assert "operational alerts need a destination" not in found()


def test_staff_must_hear_about_trial_and_demo_requests(production):
    production.delenv("MDARIX_TRIAL_ALERT_EMAIL")
    assert "trial and demo requests" in found()
    production.setenv("MDARIX_DEMO_ALERT_EMAIL", "sales@mdarix-pilot.test")
    assert "trial and demo requests" not in found()


# ------------------------------------------------------------------ MFA and sessions


def test_the_mfa_policy_may_not_be_emptied(production):
    production.setenv("MDARIX_REQUIRE_MFA_ROLES", "")
    assert "MDARIX_REQUIRE_MFA_ROLES must not be empty" in found()
    production.setenv("MDARIX_REQUIRE_MFA_ROLES", "PLATFORM_ADMIN,CUSTOMER_ADMIN")
    assert "MDARIX_REQUIRE_MFA_ROLES" not in found()


@pytest.mark.parametrize("value", ["false", "0", "no", "FALSE"])
def test_signatures_must_keep_requiring_a_fresh_code(production, value):
    production.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", value)
    assert "MDARIX_REQUIRE_MFA_FOR_SIGNATURES must not be false" in found()


@pytest.mark.parametrize(
    "value,ok", [("30", True), ("5", True), ("120", True), ("4", False), ("121", False), ("x", False)]
)
def test_the_idle_timeout_stays_within_bounds(production, value, ok):
    production.setenv("MDARIX_SESSION_IDLE_MINUTES", value)
    assert ("MDARIX_SESSION_IDLE_MINUTES" not in found()) is ok


# ------------------------------------------------------------------ database


def test_production_requires_a_verified_database_certificate_and_host(production):
    for mode in ("disable", "require", "verify-ca"):
        production.setenv("POSTGRES_SSLMODE", mode)
        assert "POSTGRES_SSLMODE must be verify-full in production" in found()


def test_staging_accepts_a_verified_ca_without_the_host_check(production):
    production.setenv("MDARIX_ENV", "staging")
    production.delenv("MDARIX_TRUSTED_PROXY_HOPS")
    production.setenv("POSTGRES_SSLMODE", "verify-ca")
    assert "POSTGRES_SSLMODE" not in found()
    production.setenv("POSTGRES_SSLMODE", "require")
    assert "POSTGRES_SSLMODE must be verify-ca or verify-full in staging" in found()


def test_an_unreadable_database_ca_bundle_is_reported(production, tmp_path):
    production.setenv("POSTGRES_SSLROOTCERT", str(tmp_path / "missing-ca.pem"))
    assert "POSTGRES_SSLROOTCERT is set but" in found()
    bundle = tmp_path / "ca.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    production.setenv("POSTGRES_SSLROOTCERT", str(bundle))
    assert "POSTGRES_SSLROOTCERT" not in found()


def test_a_running_service_refuses_the_owner_password(production):
    production.setenv("MDARIX_DB_OWNER_PASSWORD", secrets.token_urlsafe(24))
    assert "MDARIX_DB_OWNER_PASSWORD must not be in a long-running service's environment" in found()


def test_a_running_service_refuses_the_backup_password(production):
    production.setenv("MDARIX_BACKUP_DB_PASSWORD", secrets.token_urlsafe(24))
    assert "MDARIX_BACKUP_DB_PASSWORD must not be in a long-running service's environment" in found()


def test_a_running_service_refuses_dedicated_plane_owner_urls(production):
    production.setenv("MDARIX_DATA_PLANE_ACME_DATABASE_URL", "postgresql+pg8000://mdarix_runtime:x@db/acme")
    assert "_OWNER" not in found()
    production.setenv("MDARIX_DATA_PLANE_ACME_DATABASE_URL_OWNER", "postgresql+pg8000://owner:x@db/acme")
    assert "MDARIX_DATA_PLANE_ACME_DATABASE_URL_OWNER must not be in a long-running service's environment" in found()


def test_the_runtime_login_must_not_be_the_schema_owner(production):
    production.setenv("MDARIX_DB_RUNTIME_USER", "mdarix_owner")
    assert "MDARIX_DB_RUNTIME_USER must not be the schema owner" in found()


def test_the_runtime_credentials_are_required(production):
    production.delenv("MDARIX_DB_RUNTIME_PASSWORD")
    assert "MDARIX_DB_RUNTIME_USER and MDARIX_DB_RUNTIME_PASSWORD must be set" in found()


class _FakeEngine:
    """Stands in for the runtime engine: answers the role query with the given row."""

    def __init__(self, row=None, error: Exception | None = None):
        self.row, self.error = row, error

    def connect(self):
        engine = self

        class _Connection:
            def __enter__(self):
                if engine.error:
                    raise engine.error
                return self

            def __exit__(self, *_exc):
                return False

            def execute(self, _statement):
                return SimpleNamespace(one=lambda: engine.row)

        return _Connection()


def _runtime_role(monkeypatch, row=None, error=None) -> str | None:
    from backend.app.db import session

    monkeypatch.setattr(session, "runtime_engine", _FakeEngine(row, error))
    return config_check._runtime_role_problem()


def test_the_server_refuses_a_superuser_or_bypassrls_login(production):
    problem = _runtime_role(production, SimpleNamespace(rolname="mdarix_app", unrestricted=True))
    assert problem and "superuser or has BYPASSRLS" in problem


def test_the_server_refuses_to_connect_as_the_schema_owner(production):
    problem = _runtime_role(production, SimpleNamespace(rolname="mdarix_owner", unrestricted=False))
    assert problem and "connects as the schema owner mdarix_owner" in problem


def test_a_least_privilege_runtime_login_passes(production):
    assert _runtime_role(production, SimpleNamespace(rolname="mdarix_runtime", unrestricted=False)) is None


def test_an_unreachable_database_is_reported_not_raised(production):
    problem = _runtime_role(production, error=ConnectionRefusedError())
    assert problem == "Could not check the database role the server runs as (ConnectionRefusedError)"


def test_offline_skips_only_the_database_checks(production):
    calls = []
    production.setattr(config_check, "_runtime_role_problem", lambda: calls.append("role") or "role problem")
    production.setattr(config_check, "_database_token_problem", lambda: calls.append("token") or "token problem")
    assert config_check.problems(offline=True) == []
    assert calls == []
    assert config_check.problems() == ["token problem", "role problem"]
    assert calls == ["token", "role"]


# ------------------------------------------------------------------ addresses, network and placeholders


@pytest.mark.parametrize(
    "name,value",
    [
        ("MDARIX_APP_URL", "https://app.example.com"),
        ("MDARIX_DOMAIN", "app.example.com"),
        ("MDARIX_SMTP_FROM", "MDARIX <no-reply@example.com>"),
        ("MDARIX_SUPPORT_EMAIL", "changeme@mdarix-pilot.test"),
        ("MDARIX_PRIVACY_EMAIL", "privacy@example.test"),
    ],
)
def test_template_values_are_refused(production, name, value):
    production.setenv(name, value)
    assert f"{name} still holds a placeholder value" in found()


def test_the_app_address_must_be_https(production):
    production.setenv("MDARIX_APP_URL", "http://app.mdarix-pilot.test")
    assert "MDARIX_APP_URL must be the https address" in found()


def test_extra_origins_must_be_https(production):
    production.setenv("MDARIX_ALLOWED_ORIGINS", "https://admin.mdarix-pilot.test, http://insecure.mdarix-pilot.test")
    assert "https origins only (got http://insecure.mdarix-pilot.test)" in found()


@pytest.mark.parametrize("value,ok", [(None, False), ("", False), ("0", False), ("x", False), ("1", True), ("2", True)])
def test_production_must_state_its_trusted_proxy_hops(production, value, ok):
    if value is None:
        production.delenv("MDARIX_TRUSTED_PROXY_HOPS")
    else:
        production.setenv("MDARIX_TRUSTED_PROXY_HOPS", value)
    assert ("MDARIX_TRUSTED_PROXY_HOPS" not in found()) is ok


def test_private_connector_hosts_need_an_explicit_acknowledgement(production):
    production.setenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", "10.0.0.5:443")
    assert "bypassing the SSRF block" in found()
    production.setenv("MDARIX_CONNECTOR_ALLOWED_HOSTS_ACKNOWLEDGED", "true")
    assert "SSRF" not in found()


# ------------------------------------------------------------------ backups and outside monitors


@pytest.mark.parametrize(
    "name",
    ["MDARIX_BACKUP_AGE_RECIPIENT", "MDARIX_BACKUP_HEARTBEAT_URL", "MDARIX_SCHEDULER_HEARTBEAT_URL"],
)
def test_production_requires_each_backup_and_monitoring_setting(production, name):
    production.delenv(name)
    assert f"{name} must be set in production" in found()


def test_the_backup_key_must_be_a_public_key(production):
    production.setenv("MDARIX_BACKUP_AGE_RECIPIENT", "AGE-SECRET-KEY-1QQQ")
    assert "must be an age public key" in found()
    production.setenv("MDARIX_BACKUP_AGE_RECIPIENT", "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB ops@mdarix")
    assert "MDARIX_BACKUP_AGE_RECIPIENT" not in found()


@pytest.mark.parametrize("name", ["MDARIX_BACKUP_HEARTBEAT_URL", "MDARIX_SCHEDULER_HEARTBEAT_URL"])
def test_heartbeats_must_be_https(production, name):
    production.setenv(name, "http://hc.mdarix-pilot.test/ping")
    assert f"{name} must be an https:// address" in found()


def test_backups_must_leave_the_server(production):
    production.delenv("MDARIX_BACKUP_S3_URI")
    assert "Backups must leave the server" in found()
    production.setenv("MDARIX_BACKUP_OFFSITE_ACKNOWLEDGED", "true")
    assert config_check.problems(offline=True) == []
    production.setenv("MDARIX_BACKUP_S3_URI", "/mnt/backups")
    assert "MDARIX_BACKUP_S3_URI must be an s3:// address" in found()


def test_staging_does_not_require_backups_or_monitors(production):
    production.setenv("MDARIX_ENV", "staging")
    production.setenv("POSTGRES_SSLMODE", "verify-ca")
    for name in ("MDARIX_BACKUP_AGE_RECIPIENT", "MDARIX_BACKUP_HEARTBEAT_URL", "MDARIX_SCHEDULER_HEARTBEAT_URL"):
        production.delenv(name)
    production.delenv("MDARIX_BACKUP_S3_URI")
    assert config_check.problems(offline=True) == []


# ------------------------------------------------------------------ legal documents


def _write_legal(name: str, text: str) -> None:
    from pathlib import Path

    (Path(os.environ["MDARIX_LEGAL_DIR"]) / name).write_text(text, encoding="utf-8")


def test_every_legal_document_must_be_present(production):
    from pathlib import Path

    (Path(os.environ["MDARIX_LEGAL_DIR"]) / "terms.md").unlink()
    assert "MDARIX_LEGAL_DIR is missing terms.md" in found()


def test_a_legal_document_with_the_draft_banner_is_refused(production):
    _write_legal("privacy.md", "# Privacy policy\n\n**DRAFT FOR LEGAL REVIEW. Not yet in effect.**\n")
    assert "privacy.md (the DRAFT banner)" in found()


def test_a_legal_document_with_a_placeholder_is_refused(production):
    _write_legal(
        "terms.md", "# Terms\n\nThese terms are governed by the laws of [GOVERNING LAW].\nNotice: [30] days.\n"
    )
    assert "terms.md (2 [PLACEHOLDER] text(s), first [GOVERNING LAW])" in found()


def test_links_and_ordinary_brackets_are_not_placeholders(production):
    _write_legal(
        "trial-agreement.md",
        "# Free trial agreement\n\nOur [Terms of service](/terms) and [Privacy policy][privacy] apply "
        "(see [section 4]). The draft of a plan is not a DRAFT banner unless written in capitals.\n",
    )
    assert "trial-agreement.md" in found()  # the capitalised DRAFT above
    _write_legal(
        "trial-agreement.md", "# Free trial agreement\n\nOur [Terms of service](/terms) apply (see [section 4]).\n"
    )
    assert config_check.problems(offline=True) == []


def test_the_draft_legal_documents_in_the_repository_are_refused(production):
    """The drafts in legal/ are for the lawyer: a server pointed at them must not start, even with approval set."""
    from pathlib import Path

    production.setenv("MDARIX_LEGAL_DIR", str(Path(__file__).resolve().parents[1] / "legal"))
    problems = found()
    for name in ("privacy.md", "terms.md", "trial-agreement.md"):
        assert f"{name} (the DRAFT banner and" in problems


# ------------------------------------------------------------------ AI cost


def test_a_model_provider_needs_a_cost_rate(production):
    production.setenv("MDARIX_GENAI_PROVIDER", "ollama")
    assert "MDARIX_GENAI_COST_PER_1K_TOKENS must be above 0" in found()
    production.setenv("MDARIX_GENAI_COST_PER_1K_TOKENS", "not-a-number")
    assert "MDARIX_GENAI_COST_PER_1K_TOKENS must be above 0" in found()
    production.setenv("MDARIX_GENAI_COST_PER_1K_TOKENS", "0.002")
    assert "MDARIX_GENAI_COST_PER_1K_TOKENS" not in found()


def test_no_model_needs_no_cost_rate(production):
    production.setenv("MDARIX_GENAI_PROVIDER", "controlled")
    assert "MDARIX_GENAI_COST_PER_1K_TOKENS" not in found()


# ------------------------------------------------------------------ command line


def test_the_command_lists_problems_and_fails(production, capsys):
    production.delenv("MDARIX_SMTP_HOST")
    assert config_check.main(["--offline"]) == 1
    output = capsys.readouterr().out
    assert "Offline check" in output
    assert "- MDARIX_SMTP_HOST must be set" in output


def test_the_command_passes_a_good_configuration(production, capsys):
    assert config_check.main(["--offline"]) == 0
    assert "- " not in capsys.readouterr().out


def test_the_command_explains_that_development_is_not_checked(production, capsys):
    production.setenv("MDARIX_ENV", "development")
    assert config_check.main([]) == 0
    assert "configuration checks apply to staging and production only" in capsys.readouterr().out
