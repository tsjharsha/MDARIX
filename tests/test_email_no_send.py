"""Demo and local runs can never hand an e-mail to a real SMTP host (review S2).

The developer's SMTP account is filled in from the dotenv file at import; these tests set a real-looking account and a
socket-level SMTP class that fails the test if it is ever constructed.
"""

import importlib.util
from pathlib import Path

import pytest

from auth import emailer
from backend.app import readiness

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


class _NeverConnect:
    def __init__(self, *args, **kwargs):
        raise AssertionError(f"an SMTP connection was opened: {args}")


@pytest.fixture
def real_account(monkeypatch):
    for name, value in {
        "MDARIX_SMTP_HOST": "smtp.real-provider.example",
        "MDARIX_SMTP_USERNAME": "user",
        "MDARIX_SMTP_PASSWORD": "secret",
        "MDARIX_SMTP_FROM": "no-reply@mdarix.example",
        "MDARIX_SMTP_VERIFIED_DOMAIN": "",
        "MDARIX_EMAIL_DELIVERY": "",
        "POSTGRES_DB": "mdarix_x_test",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(emailer.smtplib, "SMTP", _NeverConnect)
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", _NeverConnect)
    return monkeypatch


def test_the_guard_is_real_without_the_switch(real_account):
    with pytest.raises(AssertionError, match="SMTP connection was opened"):
        emailer._send_email("someone@example.invalid", "s", "b")


@pytest.mark.parametrize("name, value", [("MDARIX_EMAIL_DELIVERY", "off"), ("POSTGRES_DB", "mdarix_whif_demo")])
def test_the_switch_or_a_demo_database_sends_nothing(real_account, name, value):
    real_account.setenv(name, value)
    assert emailer._send_email("someone@example.invalid", "s", "b") == "NOT_CONFIGURED"
    assert emailer.smtp_configuration_status()["configured"] is False
    assert readiness._email() == {"delivery": "off"}


def _timing_script():
    spec = importlib.util.spec_from_file_location("demo_path_timing", ROOT / "scripts" / "demo_path_timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_timing_script_runs_its_backend_and_itself_with_delivery_off(real_account):
    script = _timing_script()
    env = script.backend_env("mdarix_whif_demo")
    assert env["MDARIX_EMAIL_DELIVERY"] == "off"
    assert env["MDARIX_SMTP_HOST"] == "" and env["MDARIX_ALERT_WEBHOOK"] == "" and env["MDARIX_ALERT_EMAIL"] == ""
    # The same values in this process: the script's own reads must not send either.
    for name, value in script.NO_SEND.items():
        real_account.setenv(name, value)
    assert emailer._send_email("someone@example.invalid", "s", "b") == "NOT_CONFIGURED"


def test_the_timing_script_starts_the_backend_with_the_no_send_env(real_account):
    script = _timing_script()
    seen = {}

    class _Popen:
        def __init__(self, args, **kwargs):
            seen.update(kwargs)
            self.returncode = 3

        def poll(self):
            return 3

    real_account.setattr(script.subprocess, "Popen", _Popen)
    with pytest.raises(SystemExit):
        script.start_backend("mdarix_whif_demo", 1)
    assert seen["env"]["MDARIX_EMAIL_DELIVERY"] == "off" and seen["env"]["POSTGRES_DB"] == "mdarix_whif_demo"


def test_the_switch_wins_over_an_account_a_dotenv_file_supplies(real_account, tmp_path):
    """A shell that deletes an empty variable (Windows PowerShell 5.1 does) lets the dotenv file fill the SMTP and
    Resend settings back in; with MDARIX_EMAIL_DELIVERY=off nothing is still handed to SMTP or Resend."""
    from dotenv import load_dotenv

    from communication.email import resend_provider
    from communication.email.provider import EmailMessage

    for name in ("MDARIX_SMTP_HOST", "MDARIX_SMTP_USERNAME", "MDARIX_SMTP_PASSWORD", "MDARIX_SMTP_FROM"):
        real_account.delenv(name)
    # Recorded as absent first, so monkeypatch removes what the dotenv file fills in after the test.
    for name in ("RESEND_API_KEY", "RESEND_FROM_EMAIL", "RESEND_VERIFIED_DOMAIN"):
        real_account.delenv(name, raising=False)
    real_account.setenv("MDARIX_EMAIL_DELIVERY", "off")
    dotenv = tmp_path / "dotenv"
    dotenv.write_text(
        "MDARIX_SMTP_HOST=smtp.real-provider.example\nMDARIX_SMTP_USERNAME=user\nMDARIX_SMTP_PASSWORD=secret\n"
        "MDARIX_SMTP_FROM=no-reply@mdarix.example\nRESEND_API_KEY=re_real_looking\nRESEND_FROM_EMAIL=a@mdarix.example\n"
        "MDARIX_EMAIL_DELIVERY=on\n",
        encoding="utf-8",
    )
    load_dotenv(dotenv)  # as the app does at import: fills only what the environment lacks
    import os

    assert os.environ["MDARIX_SMTP_HOST"] == "smtp.real-provider.example" and os.environ["RESEND_API_KEY"]
    assert os.environ["MDARIX_EMAIL_DELIVERY"] == "off"
    assert (
        emailer.send_trial_request_acknowledgement("someone@example.invalid", display_name="A", organization="B")
        == "NOT_CONFIGURED"
    )

    def never(*args, **kwargs):
        raise AssertionError("a Resend request was made")

    real_account.setattr(resend_provider, "urlopen", never)
    provider = resend_provider.ResendProvider()
    assert provider.health()["configured"] is False
    with pytest.raises(RuntimeError, match="EMAIL_DELIVERY_OFF"):
        provider.send(EmailMessage(recipient="someone@example.invalid", subject="s", text="b"))
