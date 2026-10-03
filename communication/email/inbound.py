"""Inbound email webhooks from Resend: signature checks and event classification.

Resend signs webhooks the Svix way: headers ``svix-id``, ``svix-timestamp`` and ``svix-signature`` ("v1,<base64>",
several separated by spaces during a secret rotation), an HMAC-SHA256 of ``<id>.<timestamp>.<body>`` keyed with the
base64 part of the ``whsec_...`` secret (``RESEND_WEBHOOK_SECRET``). A timestamp more than five minutes off is
refused, so a captured request cannot be replayed later. The older plain HMAC header (``x-resend-signature``) is
accepted in local development only.
"""

import base64
import hashlib
import hmac
import os
import time

TOLERANCE_SECONDS = 300


def verify_webhook(payload: bytes, signature: str | None, secret: str | None = None) -> bool:
    """The older plain HMAC-SHA256 (hex) of the body (local development and tests only; see verify_resend_webhook)."""
    configured = secret or os.getenv("RESEND_WEBHOOK_SECRET")
    if not configured or not signature:
        return False
    expected = hmac.new(configured.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _svix_key(secret: str) -> bytes:
    value = secret.strip()
    if value.startswith("whsec_"):
        value = value[len("whsec_") :]
    return base64.b64decode(value + "=" * (-len(value) % 4))


def verify_svix(
    payload: bytes,
    message_id: str | None,
    timestamp: str | None,
    signatures: str | None,
    secret: str | None = None,
    now: float | None = None,
) -> bool:
    configured = secret or os.getenv("RESEND_WEBHOOK_SECRET")
    if not configured or not message_id or not timestamp or not signatures:
        return False
    try:
        sent_at = int(timestamp)
        key = _svix_key(configured)
    except (ValueError, TypeError):
        return False
    if abs((now if now is not None else time.time()) - sent_at) > TOLERANCE_SECONDS:
        return False
    signed = f"{message_id}.{timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for candidate in signatures.split():
        version, _, value = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(expected, value):
            return True
    return False


def verify_resend_webhook(payload: bytes, headers, secret: str | None = None, now: float | None = None) -> bool:
    """Accept a Resend webhook only with a valid Svix signature (or, in local development, the older HMAC header)."""
    if headers.get("svix-signature"):
        return verify_svix(
            payload,
            headers.get("svix-id"),
            headers.get("svix-timestamp"),
            headers.get("svix-signature"),
            secret,
            now,
        )
    from backend.app.runtime_env import is_production_like

    return not is_production_like() and verify_webhook(payload, headers.get("x-resend-signature"), secret)


def classify_inbound_event(event: dict) -> dict:
    event_type = event.get("type")
    if event_type in {"email.bounced", "email.complained"}:
        return {
            "status": "DELIVERY_FAILURE_REVIEW",
            "processing_state": "BOUNCE_RECORDED",
            "trusted_provider_event_id": event.get("id"),
            "evidence_acceptance": "NEVER_AUTOMATIC",
        }
    if event_type != "email.received":
        return {"status": "REJECTED", "reason": "UNSUPPORTED_EVENT_TYPE"}
    return {
        "status": "PENDING_HUMAN_REVIEW",
        "processing_state": "RECEIVED",
        "trusted_provider_event_id": event.get("id"),
        "evidence_acceptance": "NEVER_AUTOMATIC",
    }
