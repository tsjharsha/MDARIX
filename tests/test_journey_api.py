"""scripts/journey_api.py (0.10.88, DEV-10): the browser journeys' API never sends e-mail; it captures it."""

import importlib.util
import json
import smtplib
from email.message import EmailMessage
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "journey_api", Path(__file__).resolve().parents[1] / "scripts" / "journey_api.py"
)
journey = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(journey)


def test_messages_are_captured_and_the_provider_can_be_made_to_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", smtplib.SMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", smtplib.SMTP_SSL)
    journey.install_capture(tmp_path)
    message = EmailMessage()
    message["To"], message["Subject"] = "owner@example.invalid", "Activate your MDARIX account"
    message.set_content("Open http://127.0.0.1:5231/activate-account?token=abc")
    with smtplib.SMTP("smtp.journey.invalid", 587) as client:
        client.starttls()
        client.login("journey", "x")
        client.send_message(message)
    captured = json.loads((tmp_path / "0001.json").read_text(encoding="utf-8"))
    assert captured["to"] == "owner@example.invalid" and "activate-account?token=abc" in captured["text"]
    (tmp_path / "control.json").write_text(json.dumps({"fail": True}))
    with pytest.raises(smtplib.SMTPConnectError):
        smtplib.SMTP("smtp.journey.invalid", 587)


def test_it_refuses_production(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setattr("sys.argv", ["journey_api.py"])
    with pytest.raises(SystemExit, match="Refusing"):
        journey.main()
