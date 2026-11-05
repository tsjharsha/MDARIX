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


def test_only_the_journey_process_raises_the_activation_limit_and_production_keeps_its_own(monkeypatch):
    # 0.10.89: back-to-back journeys activate many accounts from 127.0.0.1; the journey API alone lifts token:ip.
    import os
    import subprocess
    import sys

    from backend.app import rate_limit

    production = rate_limit.LIMITS["token:ip"]
    assert production == rate_limit.Limit(20, 3600)
    monkeypatch.setitem(rate_limit.LIMITS, "token:ip", production)  # restored after the test
    journey.raise_activation_limit()
    assert rate_limit.LIMITS["token:ip"] == rate_limit.Limit(journey.JOURNEY_ACTIVATION_LIMIT, 3600)
    # A fresh API process (as production starts) reads the unchanged setting: nothing outside the journey script
    # raises it, and no environment variable can.
    root = Path(__file__).resolve().parents[1]
    fresh = subprocess.run(
        [sys.executable, "-c", "from backend.app import rate_limit; print(rate_limit.LIMITS['token:ip'])"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "MDARIX_ENV": "production"},
        check=True,
    )
    assert fresh.stdout.strip() == "Limit(limit=20, window_seconds=3600)"
