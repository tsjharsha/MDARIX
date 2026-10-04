"""Send one test alert through backend/app/alerts.py and report what each destination did.

    python scripts/send_test_alert.py                 # "[MDARIX production] Test alert" to every configured channel
    python scripts/send_test_alert.py --note "deploy 2026.10.3"

Run it after configuring ``MDARIX_ALERT_WEBHOOK`` / ``MDARIX_ALERT_EMAIL`` and after every change to them, so the
first real alert is not the first one anybody tried to deliver. Exit status 0 when at least one destination accepted
the alert, 1 when none did (or none is configured).
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.logging_setup import configure_logging  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--note", default="", help="a few words that identify this test in the alert (optional)")
    args = parser.parse_args(argv)
    configure_logging()
    from backend.app.alerts import alerting_configured, delivered, send_alert

    if not alerting_configured():
        print("No alert destination is configured: set MDARIX_ALERT_WEBHOOK and/or MDARIX_ALERT_EMAIL.")
        return 1
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = f"This is a test alert sent from {platform.node()} at {when}. No action is needed."
    if args.note:
        body += f" Note: {args.note}"
    outcome = send_alert("Test alert", body)
    print(json.dumps(outcome, indent=2))
    if delivered(outcome):
        print("Delivered: check that the alert arrived where you expect it.")
        return 0
    print("Not delivered to any destination. See the log lines above for the failure type.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
