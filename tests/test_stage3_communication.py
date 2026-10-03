import hashlib
import hmac

from communication.email.inbound import classify_inbound_event, verify_webhook
from communication.email.resend_provider import ResendProvider


def test_resend_health_never_exposes_secret(monkeypatch):
    monkeypatch.delenv("RESEND_VERIFIED_DOMAIN", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "secret-value")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "sender@example.test")
    result = ResendProvider().health()
    assert result["configured"] is True
    assert "secret-value" not in str(result)


def test_webhook_signature_and_manual_review_gate():
    body = b'{"id":"evt-1","type":"email.received"}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_webhook(body, signature, "secret") is True
    assert classify_inbound_event({"id": "evt-1", "type": "email.received"})["status"] == "PENDING_HUMAN_REVIEW"
    assert classify_inbound_event({"id": "evt-2", "type": "email.sent"})["status"] == "REJECTED"


def test_sender_domain_is_verified_before_resend_delivery(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "secret-value")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "sender@example.test")
    monkeypatch.setenv("RESEND_VERIFIED_DOMAIN", "verified.example")
    result = ResendProvider().health()
    assert result["configured"] is False
    assert result["sender_domain_verified"] is False


def test_bounce_is_a_persistable_review_state():
    result = classify_inbound_event({"id": "evt-bounce", "type": "email.bounced"})
    assert result["status"] == "DELIVERY_FAILURE_REVIEW"
    assert result["processing_state"] == "BOUNCE_RECORDED"


def _svix_headers(body: bytes, secret_bytes: bytes, message_id="msg_1", timestamp=None):
    import base64
    import hashlib
    import hmac
    import time

    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signed = f"{message_id}.{timestamp}.".encode() + body
    signature = base64.b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": message_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"}


def test_resend_webhooks_are_verified_the_svix_way(monkeypatch):
    import base64
    import time

    from communication.email.inbound import verify_resend_webhook

    key = b"0123456789abcdef0123456789abcdef"
    secret = "whsec_" + base64.b64encode(key).decode()
    body = b'{"type":"email.received","id":"evt-1"}'
    monkeypatch.setenv("MDARIX_ENV", "production")
    good = _svix_headers(body, key)
    assert verify_resend_webhook(body, good, secret) is True
    assert verify_resend_webhook(body + b" ", good, secret) is False  # body changed
    stale = _svix_headers(body, key, timestamp=int(time.time()) - 600)
    assert verify_resend_webhook(body, stale, secret) is False  # replayed later
    rotated = dict(good, **{"svix-signature": "v1,bm90LXRoZS1zaWduYXR1cmU= " + good["svix-signature"]})
    assert verify_resend_webhook(body, rotated, secret) is True  # one of several signatures matches
    # The older plain HMAC header is refused outside local development.
    import hmac

    hmac_hex = hmac.new(b"secret", body, "sha256").hexdigest()
    assert verify_resend_webhook(body, {"x-resend-signature": hmac_hex}, "secret") is False
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert verify_resend_webhook(body, {"x-resend-signature": hmac_hex}, "secret") is True
