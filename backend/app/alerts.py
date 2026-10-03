"""Operational alerts for the people running MDARIX (not customers).

``send_alert`` posts to ``MDARIX_ALERT_WEBHOOK`` (a Slack- or Teams-compatible incoming webhook taking
``{"text": ...}``) and emails ``MDARIX_ALERT_EMAIL``; either or both may be set. An alert that cannot be delivered is
logged at ERROR, so it still reaches the log collector. Alerts never contain customer records: only counts, job names
and error types.
"""

from __future__ import annotations

import json
import logging
import os
from urllib import request as urlrequest

logger = logging.getLogger("mdarix.alerts")


def alerting_configured() -> bool:
    return bool(os.getenv("MDARIX_ALERT_WEBHOOK", "").strip() or os.getenv("MDARIX_ALERT_EMAIL", "").strip())


def send_alert(subject: str, body: str) -> dict:
    """Deliver one alert to every configured channel. Returns {channel: "SENT" | "FAILED" | "NOT_CONFIGURED"}."""
    from backend.app.runtime_env import environment

    title = f"[MDARIX {environment()}] {subject}"
    outcome = {"webhook": "NOT_CONFIGURED", "email": "NOT_CONFIGURED"}
    webhook = os.getenv("MDARIX_ALERT_WEBHOOK", "").strip()
    if webhook:
        try:
            message = urlrequest.Request(
                webhook,
                data=json.dumps({"text": f"{title}\n{body}"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "MDARIX-alerts/1.0"},
                method="POST",
            )
            with urlrequest.urlopen(message, timeout=float(os.getenv("MDARIX_ALERT_TIMEOUT_SECONDS", "10"))):
                pass
            outcome["webhook"] = "SENT"
        except Exception as exc:
            outcome["webhook"] = "FAILED"
            logger.error("Alert webhook delivery failed (%s): %s", type(exc).__name__, subject)
    recipient = os.getenv("MDARIX_ALERT_EMAIL", "").strip()
    if recipient:
        try:
            from auth.emailer import send_operations_alert

            outcome["email"] = send_operations_alert(recipient, title, body)
        except Exception as exc:
            outcome["email"] = "FAILED"
            logger.error("Alert email delivery failed (%s): %s", type(exc).__name__, subject)
    if outcome["webhook"] != "SENT" and outcome["email"] != "SENT":
        logger.error("ALERT %s: %s", subject, body)
    return outcome
