"""Operational alerts reach every configured destination, and a server with none says so loudly."""

import importlib.util
import logging
from pathlib import Path

import pytest

from auth import emailer
from backend.app import alerts


@pytest.fixture
def no_destinations(monkeypatch):
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "")
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "")


@pytest.fixture
def webhook(monkeypatch):
    """A fake webhook transport that records what would be posted."""
    posted = []
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "https://hooks.example.test/mdarix")
    monkeypatch.setattr(alerts, "_post_webhook", lambda url, text, timeout: posted.append((url, text, timeout)))
    return posted


@pytest.fixture
def mailbox(monkeypatch):
    """Capture what the email channel would send over SMTP."""
    sent = []
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "ops@example.test")
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text}) or "SENT"
        ),
    )
    return sent


def test_the_webhook_gets_the_environment_subject_and_body(webhook, monkeypatch):
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "")
    monkeypatch.setenv("MDARIX_ALERT_TIMEOUT_SECONDS", "3")
    outcome = alerts.send_alert("Scheduled job failing: x", "Failed 3 times: RuntimeError")
    assert outcome == {"webhook": "SENT", "email": "NOT_CONFIGURED"}
    url, text, timeout = webhook[0]
    assert url == "https://hooks.example.test/mdarix" and timeout == 3.0
    assert text == "[MDARIX development] Scheduled job failing: x\nFailed 3 times: RuntimeError"


def test_a_failing_webhook_is_reported_not_raised(monkeypatch, caplog):
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "https://hooks.example.test/mdarix")
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "")

    def refuse(url, text, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(alerts, "_post_webhook", refuse)
    with caplog.at_level(logging.ERROR, logger="mdarix.alerts"):
        outcome = alerts.send_alert("Worker stopped", "no heartbeat")
    assert outcome["webhook"] == "FAILED" and not alerts.delivered(outcome)
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "OSError" in messages and "ALERT Worker stopped: no heartbeat" in messages


def test_the_email_channel_uses_the_operations_alert_template(mailbox, monkeypatch):
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "")
    outcome = alerts.send_alert("Dead-letter queue grew", "2 more event(s) are dead-lettered.")
    assert outcome == {"webhook": "NOT_CONFIGURED", "email": "SENT"} and alerts.delivered(outcome)
    assert mailbox[0]["to"] == "ops@example.test"
    assert mailbox[0]["subject"] == "[MDARIX development] Dead-letter queue grew"
    assert "2 more event(s) are dead-lettered." in mailbox[0]["text"]


def test_both_channels_are_used_when_both_are_set(webhook, mailbox):
    assert alerts.send_alert("Test", "body") == {"webhook": "SENT", "email": "SENT"}
    assert len(webhook) == 1 and len(mailbox) == 1


def test_production_without_a_destination_logs_a_clear_error(no_destinations, monkeypatch, caplog):
    monkeypatch.setenv("MDARIX_ENV", "production")
    assert not alerts.alerting_configured()
    with caplog.at_level(logging.ERROR, logger="mdarix.alerts"):
        outcome = alerts.send_alert("Audit trail integrity check failed", "tenant x")
    assert outcome == {"webhook": "NOT_CONFIGURED", "email": "NOT_CONFIGURED"}
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert errors and alerts.NO_DESTINATION in errors[0].getMessage()
    assert "MDARIX_ALERT_WEBHOOK" in errors[0].getMessage() and "tenant x" in errors[0].getMessage()


def test_development_without_a_destination_still_logs_the_alert(no_destinations, caplog):
    with caplog.at_level(logging.ERROR, logger="mdarix.alerts"):
        alerts.send_alert("Something", "happened")
    messages = [record.getMessage() for record in caplog.records]
    assert "ALERT Something: happened" in messages
    assert not any(alerts.NO_DESTINATION in message for message in messages)


def _script():
    spec = importlib.util.spec_from_file_location(
        "send_test_alert", Path(__file__).resolve().parents[1] / "scripts" / "send_test_alert.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_test_alert_script_fails_without_a_destination(no_destinations, capsys):
    assert _script().main([]) == 1
    assert "No alert destination is configured" in capsys.readouterr().out


def test_the_test_alert_script_sends_and_reports_each_channel(webhook, monkeypatch, capsys):
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "")
    assert _script().main(["--note", "deploy 2026.10.3"]) == 0
    out = capsys.readouterr().out
    assert '"webhook": "SENT"' in out and "Delivered" in out
    assert "Test alert" in webhook[0][1] and "deploy 2026.10.3" in webhook[0][1]


def test_the_test_alert_script_fails_when_nothing_was_delivered(monkeypatch, capsys):
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "https://hooks.example.test/x")
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "")
    monkeypatch.setattr(alerts, "_post_webhook", lambda *_: (_ for _ in ()).throw(OSError("down")))
    assert _script().main([]) == 1
    assert "Not delivered" in capsys.readouterr().out


@pytest.fixture
def fallback(monkeypatch):
    """The independent fallback webhook, with a stub transport that records every post by URL."""
    posted = []
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "")
    monkeypatch.setenv("MDARIX_ALERT_FALLBACK_WEBHOOK", "https://fallback.example.test/mdarix")
    monkeypatch.setattr(alerts, "_post_webhook", lambda url, text, timeout: posted.append((url, text)))
    return posted


def test_when_the_email_alert_fails_the_fallback_webhook_gets_it(fallback, monkeypatch):
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "ops@example.test")

    def provider_down(*_args, **_kwargs):
        raise OSError("email provider unreachable")

    monkeypatch.setattr(emailer, "_send_email", provider_down)
    outcome = alerts.send_alert("Backup failed", "pg_dump exited 1")
    assert outcome["email"] != "SENT" and outcome["fallback_webhook"] == "SENT" and alerts.delivered(outcome)
    assert fallback == [
        (
            "https://fallback.example.test/mdarix",
            "[MDARIX development] Backup failed (the usual alert channel failed)\npg_dump exited 1",
        )
    ]


def test_the_fallback_webhook_stays_quiet_while_email_works(fallback, mailbox):
    outcome = alerts.send_alert("Backup failed", "pg_dump exited 1")
    assert outcome == {"webhook": "NOT_CONFIGURED", "email": "SENT"} and fallback == [] and len(mailbox) == 1


def test_without_a_fallback_webhook_nothing_changes(monkeypatch):
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "")
    monkeypatch.setenv("MDARIX_ALERT_FALLBACK_WEBHOOK", "")
    monkeypatch.setenv("MDARIX_ALERT_EMAIL", "ops@example.test")
    monkeypatch.setattr(emailer, "_send_email", lambda *_a, **_k: "FAILED")
    monkeypatch.setattr(alerts, "_post_webhook", lambda *_: pytest.fail("no webhook is configured"))
    outcome = alerts.send_alert("Backup failed", "pg_dump exited 1")
    assert "fallback_webhook" not in outcome and not alerts.delivered(outcome)
