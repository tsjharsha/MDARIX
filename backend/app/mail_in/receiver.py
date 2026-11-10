"""B7b step 8 (spec 4.4 step 1, 4.5): ``mail-in``, the small SMTP receiver (open-source ``aiosmtpd``).

- Only a known, active intake address is accepted. Anything else is refused during the SMTP conversation (550), so
  nothing is stored and no bounce is sent. No relay: the receiver delivers nowhere else and never sends mail.
- 25 MB per message (552 above). TLS is offered (STARTTLS, opportunistic) when a certificate is configured.
- Over a limit (30 messages an hour per sending IP; the organization's daily limit, 200 by default) the sender gets a
  temporary refusal (451) and retries later. An organization's optional sender-domain allowlist refuses others (550).
- An accepted message: the raw bytes go to object storage under the organization (encrypted like other files), a row
  to ``inbound_messages`` (state NEW) and a processing job to the notifications outbox (step 9). The same Message-ID
  twice is stored once.

Run ``python -m backend.app.mail_in.receiver``. Unless ``MDARIX_EMAIL_INTAKE=on`` it exits at once: nothing listens.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from email.parser import BytesHeaderParser

from backend.app import mail_in

logger = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 25 * 1024 * 1024
PER_IP_PER_HOUR = 30
PROCESS_EVENT = "INBOUND_MAIL_RECEIVED"

REFUSED_RECIPIENT = "550 5.1.1 No such recipient here"
REFUSED_SENDER = "550 5.7.1 Sender not accepted for this address"
TOO_MANY = "451 4.7.1 Too many messages; try again later"
NO_RELAY = "550 5.7.1 Relay not permitted"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _domain_of(address: str) -> str:
    return address.rpartition("@")[2].strip().strip(">").lower()


def recipient_check(local_part: str, sender: str, now: datetime) -> tuple[str | None, uuid.UUID | None]:
    """(refusal, organization) for one recipient: the address, the organization's allowlist and daily limit."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.intake import InboundMessage
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from backend.app.mail_in.addresses import tenant_for
    from backend.app.oversight import service

    with SessionLocal() as control:
        bind_system(control, "mail-in: find the organization of an intake address")
        tenant_id = tenant_for(control, local_part, now)
    if tenant_id is None:
        return REFUSED_RECIPIENT, None
    with open_tenant_data_session(tenant_id) as db:
        settings = service.settings_row(db, tenant_id)
        allowed = [str(item).lower() for item in (settings.mail_allowed_domains if settings else []) or []]
        sender_domain = _domain_of(sender)
        if allowed and not any(sender_domain == d or sender_domain.endswith("." + d) for d in allowed):
            return REFUSED_SENDER, None
        limit = settings.mail_daily_limit if settings else 200
        today = (
            db.query(InboundMessage)
            .filter(InboundMessage.tenant_id == tenant_id, InboundMessage.received_at > now - timedelta(days=1))
            .count()
        )
        if today >= limit:
            logger.warning("mail-in: organization %s reached its daily limit (%s)", tenant_id, limit)
            return TOO_MANY, None
    return None, tenant_id


def store(tenant_id: uuid.UUID, content: bytes, sender: str, now: datetime) -> uuid.UUID | None:
    """Keep one accepted message for one organization; None when its Message-ID is already stored."""
    from object_storage.service import ObjectStorageService

    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.intake import InboundMessage
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.notifications import _queue

    headers = BytesHeaderParser().parsebytes(content)
    message_id = str(headers.get("Message-ID") or "").strip()[:998]
    if not message_id:
        # A message without one is still kept once: the hash of its bytes stands for it.
        message_id = f"<sha256-{hashlib.sha256(content).hexdigest()}@{mail_in.domain()}>"
    with open_tenant_data_session(tenant_id) as db:
        known = (
            db.query(InboundMessage.id)
            .filter(InboundMessage.tenant_id == tenant_id, InboundMessage.message_id == message_id)
            .first()
        )
        if known is not None:
            return None
        row_id = uuid.uuid4()
        stored = ObjectStorageService().put(
            str(tenant_id), f"mail-{row_id.hex}", content, content_type="message/rfc822", internal=True
        )
        db.add(
            InboundMessage(
                id=row_id,
                tenant_id=tenant_id,
                message_id=message_id,
                received_at=now,
                raw_object_key=stored["object_key"],
                raw_size=len(content),
                flags={"empty_sender": True} if not sender.strip("<> ") else {},
                created_at=now,
            )
        )
        db.commit()
    with SessionLocal() as control:
        bind_tenant(control, tenant_id)
        # shortcut: a job lost between the two commits leaves the message "being checked"; re-queue from the
        # 15-minute pass if that is ever seen.
        _queue(control, tenant_id, PROCESS_EVENT, "InboundMessage", row_id, {"message_id": str(row_id)})
        control.commit()
    return row_id


class IntakeHandler:
    """The aiosmtpd handler. Database work runs in a thread; the event loop only talks SMTP."""

    def __init__(self) -> None:
        # shortcut: per process, in memory; one mail-in container. A shared counter if it is ever scaled out.
        self._per_ip: dict[str, deque] = {}

    def _over_ip_limit(self, ip: str) -> bool:
        seen = self._per_ip.setdefault(ip, deque())
        hour_ago = time.monotonic() - 3600
        while seen and seen[0] < hour_ago:
            seen.popleft()
        return len(seen) >= PER_IP_PER_HOUR

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        local_part, _, host = address.strip("<>").rpartition("@")
        if host.lower() != mail_in.domain():
            return NO_RELAY
        if self._over_ip_limit(str((session.peer or ("?",))[0])):
            return TOO_MANY
        refusal, tenant_id = await asyncio.get_running_loop().run_in_executor(
            None, recipient_check, local_part, envelope.mail_from or "", _now()
        )
        if refusal:
            return refusal
        envelope.rcpt_tos.append(address)
        envelope.__dict__.setdefault("mdarix_tenants", set()).add(tenant_id)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        content = envelope.original_content or envelope.content
        if isinstance(content, str):
            content = content.encode("utf-8", "surrogateescape")
        self._per_ip.setdefault(str((session.peer or ("?",))[0]), deque()).append(time.monotonic())
        now = _now()
        loop = asyncio.get_running_loop()
        try:
            for tenant_id in envelope.__dict__.get("mdarix_tenants", ()):
                await loop.run_in_executor(None, store, tenant_id, content, envelope.mail_from or "", now)
        except Exception:
            # The sender keeps the message and retries for days: nothing is lost in a short outage.
            logger.exception("mail-in: a message could not be stored")
            return "451 4.3.0 Temporary failure; try again later"
        return "250 Message accepted"


def _tls_context():
    cert, key = os.getenv("MDARIX_MAIL_IN_CERT", "").strip(), os.getenv("MDARIX_MAIL_IN_KEY", "").strip()
    if not (cert and key):
        return None
    import ssl

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert, key)
    return context


def controller(hostname: str, port: int):
    """The receiver, not yet started. Opportunistic TLS: STARTTLS offered when configured, never required."""
    from aiosmtpd.controller import Controller

    return Controller(
        IntakeHandler(),
        hostname=hostname,
        port=port,
        data_size_limit=MAX_MESSAGE_BYTES,
        tls_context=_tls_context(),
        require_starttls=False,
        ident="MDARIX intake",
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if not mail_in.enabled():
        logger.info("mail-in: e-mail intake is switched off (MDARIX_EMAIL_INTAKE); not listening")
        return 0
    receiver = controller(os.getenv("MDARIX_MAIL_IN_HOST", "0.0.0.0"), int(os.getenv("MDARIX_MAIL_IN_PORT", "2525")))
    receiver.start()
    logger.info("mail-in: listening on %s:%s for %s", receiver.hostname, receiver.port, mail_in.domain())
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
