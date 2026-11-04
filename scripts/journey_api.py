"""Local browser journeys only: run the API with outgoing e-mail captured to a folder instead of sent.

    MDARIX_JOURNEY_MAIL_DIR=<folder> python scripts/journey_api.py --port 8121

Every message the API would hand to the SMTP provider is written to ``<folder>/<n>.eml`` (the full message, so a
journey reads its activation link from the e-mail as a person would). The SMTP settings are stand-ins pointing at
nothing; no message ever leaves the machine. ``<folder>/control.json`` is read on every send, so a journey can change
it while the server runs: ``{"delay": 20}`` holds each message that many seconds (a slow provider), ``{"fail": true}``
refuses it (the provider is down). Refuses a production or staging environment.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _control(folder: Path) -> dict:
    try:
        return json.loads((folder / "control.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def install_capture(folder: Path) -> None:
    """Replace the SMTP client with one that writes each message to ``folder``."""
    import smtplib

    folder.mkdir(parents=True, exist_ok=True)
    numbers = itertools.count(len(list(folder.glob("*.eml"))) + 1)

    class CapturedSMTP:
        def __init__(self, *args, **kwargs):
            control = _control(folder)
            time.sleep(float(control.get("delay") or 0))
            if control.get("fail"):
                raise smtplib.SMTPConnectError(421, b"journey: the provider is down")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, **kwargs):
            return (220, b"ready")

        def login(self, *args):
            return (235, b"ok")

        def send_message(self, message):
            name = f"{next(numbers):04d}"
            (folder / f"{name}.eml").write_bytes(bytes(message))
            plain = message.get_body(("plain",))
            summary = {"to": message["To"], "subject": message["Subject"], "text": plain.get_content() if plain else ""}
            (folder / f"{name}.json").write_text(json.dumps(summary), encoding="utf-8")
            return {}

    smtplib.SMTP = CapturedSMTP
    smtplib.SMTP_SSL = CapturedSMTP


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8121)
    args = parser.parse_args()
    env = os.environ.get("MDARIX_ENV", "development").lower()
    if env in {"production", "staging"}:
        raise SystemExit("Refusing: journeys run on a local development or test environment only")
    folder = os.environ.get("MDARIX_JOURNEY_MAIL_DIR")
    if not folder:
        raise SystemExit("Set MDARIX_JOURNEY_MAIL_DIR to the folder that captures the e-mail")
    # Stand-ins: the capture never connects anywhere, but the API sends only when SMTP looks configured.
    for name, value in {
        "MDARIX_ENV": env,
        "MDARIX_SMTP_HOST": "smtp.journey.invalid",
        "MDARIX_SMTP_PORT": "587",
        "MDARIX_SMTP_USERNAME": "journey",
        "MDARIX_SMTP_PASSWORD": "journey-capture-only",
        "MDARIX_SMTP_FROM": "MDARIX <no-reply@journey.invalid>",
        "MDARIX_SMTP_VERIFIED_DOMAIN": "journey.invalid",
        "MDARIX_TRIAL_ALERT_EMAIL": "operators@journey.invalid",
        # auth/emailer.py loads a .env from a parent folder: present values keep its keys out.
        "RESEND_API_KEY": "",
        "MDARIX_GENAI_PROVIDER": "controlled",
        "MDARIX_GENAI_API_KEY": "",
        "MDARIX_GENAI_BASE_URL": "",
        "MDARIX_GENAI_FALLBACKS": "",
    }.items():
        os.environ[name] = value
    install_capture(Path(folder))
    sys.path.insert(0, str(ROOT))
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
