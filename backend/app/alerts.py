"""Operational alerts for the people running MDARIX (not customers).

``send_alert`` posts to ``MDARIX_ALERT_WEBHOOK`` (a Slack- or Teams-compatible incoming webhook taking
``{"text": ...}``) and emails ``MDARIX_ALERT_EMAIL``; either or both may be set. An alert that cannot be delivered is
logged at ERROR, so it still reaches the log collector. Alerts never contain customer records: only counts, job names
and error types.

``MDARIX_ALERT_FALLBACK_WEBHOOK`` (optional) is an independent channel: an alert that no usual channel delivered (the
email provider down, the main webhook failing) is posted there too. Unset, nothing changes.

A staging or production server with neither destination would alert nobody: ``send_alert`` then logs a clear
``NO ALERT DESTINATION CONFIGURED`` error with every alert (``config_check`` refuses to start such a server;
``scripts/send_test_alert.py`` proves the configured destinations work before anything goes wrong).
"""

from __future__ import annotations

import json
import logging
import os
from urllib import request as urlrequest

logger = logging.getLogger("mdarix.alerts")

NO_DESTINATION = "NO ALERT DESTINATION CONFIGURED"


def alerting_configured() -> bool:
    """True when at least one alert destination is set (webhook or email)."""
    return bool(os.getenv("MDARIX_ALERT_WEBHOOK", "").strip() or os.getenv("MDARIX_ALERT_EMAIL", "").strip())


def _post_webhook(url: str, text: str, timeout: float) -> None:
    """One POST to the incoming webhook. Separate so tests can replace the transport."""
    message = urlrequest.Request(
        url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "MDARIX-alerts/1.0"},
        method="POST",
    )
    with urlrequest.urlopen(message, timeout=timeout):
        pass


def send_alert(subject: str, body: str) -> dict:
    """Deliver one alert to every configured channel. Returns {channel: "SENT" | "FAILED" | "NOT_CONFIGURED"}."""
    from backend.app.runtime_env import environment, is_production_like

    title = f"[MDARIX {environment()}] {subject}"
    outcome = {"webhook": "NOT_CONFIGURED", "email": "NOT_CONFIGURED"}
    if not alerting_configured():
        if is_production_like():
            # Said once per alert, at ERROR, so the log collector is the one place this still shows up.
            logger.error(
                "%s: set MDARIX_ALERT_WEBHOOK and/or MDARIX_ALERT_EMAIL. Undelivered alert %s: %s",
                NO_DESTINATION,
                subject,
                body,
            )
        else:
            logger.error("ALERT %s: %s", subject, body)
        return outcome
    webhook = os.getenv("MDARIX_ALERT_WEBHOOK", "").strip()
    if webhook:
        try:
            _post_webhook(webhook, f"{title}\n{body}", float(os.getenv("MDARIX_ALERT_TIMEOUT_SECONDS", "10")))
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
    fallback = os.getenv("MDARIX_ALERT_FALLBACK_WEBHOOK", "").strip()
    if fallback and not delivered(outcome):
        # The independent channel (H1): used only when the usual ones failed, e.g. the email provider is down.
        try:
            _post_webhook(
                fallback,
                f"{title} (the usual alert channel failed)\n{body}",
                float(os.getenv("MDARIX_ALERT_TIMEOUT_SECONDS", "10")),
            )
            outcome["fallback_webhook"] = "SENT"
        except Exception as exc:
            outcome["fallback_webhook"] = "FAILED"
            logger.error("Alert fallback webhook delivery failed (%s): %s", type(exc).__name__, subject)
    if not delivered(outcome):
        logger.error("ALERT %s: %s", subject, body)
    return outcome


def delivered(outcome: dict) -> bool:
    """True when at least one channel accepted the alert."""
    return any(state == "SENT" for state in outcome.values())
