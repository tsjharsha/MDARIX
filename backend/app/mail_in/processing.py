"""B7b step 9 (spec 4.4 steps 2-4 and 7): what the worker does with one received message. Rule-based, no AI.

- Auto-replies and bounces (``Auto-Submitted``, ``Precedence: bulk``, an empty sender, a delivery report) go straight
  to "Not a case" with the reason, kept 30 days (B7-D11). Nothing is ever deleted silently.
- Each attachment gets the evidence checks (type, 10 MB, the organization's quota, content matching its type) and the
  virus scan. An infected one is never stored: the raw message is stored again without that part, and its masked
  name, hash and "virus found" are recorded. Small inline images (logos, under 20 KB) are ignored. At most 10.
- Threading: a reply to a message already on a Case (``In-Reply-To``/``References``, or the Case's reference in the
  subject) is offered as "Add to <Case>", never a new Case by itself (RT-29). The same body within 7 days shows
  "possible duplicate".
- The draft: the body as text (HTML reduced, quoted lines and the signature cut), personal data masked; the subject
  masked; the sender's domain only. Product, lot, serial and UDI matched against master data and the GS1 pattern, each
  "unconfirmed, source: E-mail" (ID-1). Harm and fault words, and "may not be English", flagged.
- Awareness: an earlier date in a forwarded message's header lines is offered as "possibly known earlier" (H1).
- Death or injury words: the in-app alert at once (the oversight sweep's e-mail item is due on receipt) and the urgent
  e-mail when the organization opted in.
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import uuid
from datetime import datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ACTOR = "system:mail-in"
KEEP_NOT_A_CASE = timedelta(days=30)
DUPLICATE_WINDOW = timedelta(days=7)
MAX_ATTACHMENTS = 10
INLINE_IGNORED_BYTES = 20 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
NOT_A_CASE_REASONS = ("SPAM", "AUTO_REPLY", "SETUP_MESSAGE", "INTERNAL", "DUPLICATE", "OTHER")
_REFERENCE = re.compile(r"\b(?:CALL|URG|SVC)-[0-9A-F]{6}\b")
_GS1_UDI = re.compile(r"\(01\)\s?(\d{14})|\b01(\d{14})(?=\D|$)")
_SERIAL = re.compile(r"\bserial(?:\s*(?:number|no\.?|#))?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-]{3,40})", re.IGNORECASE)
_FORWARDED_DATE = re.compile(r"^\s*>?\s*(?:Date|Sent)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _mask(value: str) -> str:
    from backend.app.trial.imports import _mask

    return _mask(value)


def auto_reply_reason(message: EmailMessage, empty_sender: bool) -> str | None:
    auto = str(message.get("Auto-Submitted") or "").strip().lower()
    precedence = str(message.get("Precedence") or "").strip().lower()
    if empty_sender or message.get_content_type() == "multipart/report":
        return "AUTO_REPLY"  # a bounce or delivery report
    if (auto and auto != "no") or precedence in ("bulk", "junk", "list", "auto_reply"):
        return "AUTO_REPLY"
    return None


def body_text(message: EmailMessage) -> str:
    """The message's words: plain text preferred, HTML reduced to text; quoted lines and the signature cut."""
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        text = part.get_content()
    except (LookupError, ValueError):
        text = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
    text = text[:MAX_TEXT_BYTES].replace("\r\n", "\n")
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.split(r"(?m)^-- ?$", text, maxsplit=1)[0]  # the signature block
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return re.sub(r"[ \t]+", " ", "\n".join(lines)).strip()


def earlier_dates(text: str, received_at: datetime) -> list[str]:
    """H1: dates in a forwarded message's header lines earlier than our receipt (a first-knowledge candidate)."""
    found = []
    for raw in _FORWARDED_DATE.findall(text):
        try:
            moment = parsedate_to_datetime(raw.strip())
        except (TypeError, ValueError, IndexError):
            continue
        if moment.tzinfo is not None and moment < received_at:
            found.append(moment.isoformat())
    return sorted(set(found))[:5]


def identifiers(db: Session, tenant_id, text: str) -> dict:
    """Product, lot, serial and UDI found in the words, each unconfirmed with source E-mail (ID-1)."""
    from backend.app.db.models.foundation import LotBatch, Product

    found: dict = {}
    plain = text.lower()
    for product in db.query(Product).filter(Product.tenant_id == tenant_id).limit(500):
        if product.name and len(product.name) >= 3 and product.name.lower() in plain:
            found["product"] = {"id": str(product.id), "text": product.name}
            break
    words = set(re.findall(r"[A-Za-z0-9\-]{3,}", text))
    if words:
        lot = (
            db.query(LotBatch)
            .filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier.in_(list(words)[:500]))
            .first()
        )
        if lot is not None:
            found["lot"] = {"id": str(lot.id), "text": lot.lot_identifier}
    serial = _SERIAL.search(text)
    if serial:
        found["serial"] = {"text": serial.group(1)}
    udi = _GS1_UDI.search(text)
    if udi:
        found["udi"] = {"text": "(01)" + (udi.group(1) or udi.group(2))}
    return {key: {**value, "status": "UNCONFIRMED", "source": "EMAIL"} for key, value in found.items()}


def _leaf_parts(message: EmailMessage, body) -> list[EmailMessage]:
    return [part for part in message.walk() if not part.is_multipart() and part is not body]


def _attachments(db: Session, tenant_id, row, message: EmailMessage, storage) -> tuple[list, bool]:
    """Check, scan and store the attachments; returns (CaseAttachment rows, whether a part was stripped)."""
    from backend.app.db.models.intake import CaseAttachment
    from backend.app.stage3_workflow_router import (
        ALLOWED_ATTACHMENT_TYPES,
        MAX_ATTACHMENT_BYTES,
        _content_matches_type,
        attachment_bytes_used,
        attachment_quota_bytes,
        safe_filename,
    )
    from backend.app.trial.imports import file_label
    from object_storage.service import StorageError

    body = message.get_body(preferencelist=("plain", "html"))
    rows, stripped, counted = [], False, 0
    for part in _leaf_parts(message, body):
        content = part.get_payload(decode=True) or b""
        content_type = part.get_content_type().lower()
        name = part.get_filename()
        if content_type.startswith("text/") and not name:
            continue  # an alternative body (the HTML of a plain-text message)
        if (
            content_type.startswith("image/")
            and len(content) < INLINE_IGNORED_BYTES
            and (part.get("Content-ID") or part.get_content_disposition() == "inline")
        ):
            continue  # a logo in a signature
        counted += 1
        reason = None
        if counted > MAX_ATTACHMENTS:
            reason = f"Refused: more than {MAX_ATTACHMENTS} attachments"
        elif content_type not in ALLOWED_ATTACHMENT_TYPES:
            reason = "Refused: this type of file is not accepted"
        elif len(content) > MAX_ATTACHMENT_BYTES:
            reason = "Refused: larger than 10 MB"
        elif attachment_bytes_used(db, tenant_id) + len(content) > attachment_quota_bytes(db, tenant_id):
            reason = "Refused: your organization's file storage is full"
        elif not storage.scan(content, content_type):
            reason = "Refused: virus found"
            part.clear()
            part.set_content("[attachment removed by MDARIX: virus found]")
            stripped = True
        elif not _content_matches_type(content, content_type):
            reason = "Refused: the content does not match its type"
        stored = None
        if reason is None:
            try:
                stored = storage.put(
                    str(tenant_id), f"mail-{row.id.hex}-{uuid.uuid4().hex}", content, content_type=content_type
                )
            except StorageError:
                reason = "Refused: the file could not be stored"
        attachment = CaseAttachment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            inbound_message_id=row.id,
            object_key=stored["object_key"] if stored else None,
            filename_masked=file_label(safe_filename(name)) or "file",
            content_type=content_type[:120],
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            usable=reason is None,
            unusable_reason=reason,
            source="EMAIL",
            created_by=ACTOR,
            created_at=row.received_at,
        )
        db.add(attachment)
        db.flush()  # the next file's quota check counts this one
        rows.append(attachment)
    return rows, stripped


def attachment_view(row) -> dict:
    return {
        "id": str(row.id),
        "file_name": row.filename_masked,
        "content_type": row.content_type,
        "size": row.size,
        "usable": row.usable,
        "reason": row.unusable_reason,
    }


def thread_case(db: Session, tenant_id, references: list[str], subject: str):
    """The Case a reply belongs to: a message it answers that is on a Case, a Case made from it, or a Case's
    reference in the subject."""
    from backend.app.db.models.intake import InboundMessage, IntakeEvent

    if references:
        on_case = (
            db.query(InboundMessage.intake_event_id)
            .filter(
                InboundMessage.tenant_id == tenant_id,
                InboundMessage.message_id.in_(references),
                InboundMessage.intake_event_id.isnot(None),
            )
            .first()
        )
        if on_case is not None:
            return db.get(IntakeEvent, on_case[0])
        made = (
            db.query(IntakeEvent)
            .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.channel_ref.in_(references))
            .first()
        )
        if made is not None:
            return made
    named = _REFERENCE.search(subject or "")
    if named:
        return (
            db.query(IntakeEvent)
            .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == named.group(0))
            .first()
        )
    return None


def analyse(db: Session, control_db: Session | None, tenant_id, row, content: bytes, storage) -> None:
    """Fill the message's row from its bytes (see the module docstring). Flushes; the caller commits."""
    from backend.app.db.models.intake import InboundMessage
    from backend.app.intake import rules

    message = BytesParser(policy=policy.default).parsebytes(content)
    subject = str(message.get("Subject") or "")
    sender = str(message.get("From") or "")
    row.from_domain = (sender.rpartition("@")[2].strip(" >").lower() or None) if "@" in sender else None
    row.subject_masked = _mask(subject)[:500] or None
    row.in_reply_to = str(message.get("In-Reply-To") or "").strip()[:998] or None
    references = str(message.get("References") or "").split()
    row.references = references[:50]
    encrypted = message.get_content_type() in ("multipart/encrypted", "application/pkcs7-mime") or (
        "-----BEGIN PGP MESSAGE-----" in str(message.get_body() or "")
    )
    text = "" if encrypted else body_text(message)
    row.body_sha256 = hashlib.sha256(re.sub(r"\s+", " ", text).strip().lower().encode()).hexdigest() if text else None
    row.header_dates = earlier_dates(text, row.received_at)
    attachments, stripped = _attachments(db, tenant_id, row, message, storage)
    if stripped:
        # The raw message is kept without the infected part (spec 4.4 step 2).
        clean = message.as_bytes()
        stored = storage.put(
            str(tenant_id), f"mail-{row.id.hex}-clean", clean, content_type="message/rfc822", internal=True
        )
        old, row.raw_object_key, row.raw_size = row.raw_object_key, stored["object_key"], len(clean)
        storage.delete(str(tenant_id), old)
    row.attachments = [attachment_view(item) for item in attachments]
    words = _mask(text)[: rules.WORDS_MAX]
    harm, fault = rules.harm_words(text), rules.fault_words(text)
    case = thread_case(db, tenant_id, ([row.in_reply_to] if row.in_reply_to else []) + references, subject)
    duplicate = None
    if row.body_sha256:
        duplicate = (
            db.query(InboundMessage)
            .filter(
                InboundMessage.tenant_id == tenant_id,
                InboundMessage.id != row.id,
                InboundMessage.body_sha256 == row.body_sha256,
                InboundMessage.received_at > row.received_at - DUPLICATE_WINDOW,
            )
            .order_by(InboundMessage.received_at)
            .first()
        )
    row.flags = {
        **(row.flags or {}),
        "checked": True,
        "harm_words": harm,
        "fault_words": fault,
        "may_not_be_english": rules.may_not_be_english(text),
        "encrypted": encrypted,
        **({"add_to_case": {"id": str(case.id), "reference": case.reference}} if case is not None else {}),
        **(
            {"possible_duplicate": {"id": str(duplicate.id), "received_at": duplicate.received_at.isoformat()}}
            if duplicate is not None
            else {}
        ),
    }
    row.draft = {
        "words": words if not encrypted else "",
        "identifiers": identifiers(db, tenant_id, text) if text else {},
        "note": "Cannot be read: encrypted" if encrypted else None,
    }
    reason = auto_reply_reason(message, bool((row.flags or {}).get("empty_sender")))
    if reason:
        row.state, row.reason, row.decided_by, row.decided_at = "NOT_A_CASE", reason, ACTOR, row.received_at
        row.purge_after = row.received_at + KEEP_NOT_A_CASE
        return
    if harm:
        from backend.app.oversight import service, urgent_alert

        urgent_alert.queue(
            db,
            control_db,
            tenant_id,
            reference="E-mail to check",
            subject_id=row.id,
            received_at=row.received_at,
            actor=ACTOR,
        )
        db.flush()
        try:
            with db.begin_nested():
                service.sweep(db, control_db, tenant_id)  # the in-app alert at once: the item is due on receipt
        except Exception:
            logger.exception("The alert for an e-mail with harm words waits for the next sweep")


def process(control_db: Session, payload: dict) -> None:
    """The outbox job ``INBOUND_MAIL_RECEIVED``. Idempotent: a message already checked is left as it is."""
    from object_storage.service import ObjectStorageService

    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.intake import InboundMessage

    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    with open_tenant_data_session(tenant_id) as db:
        row = (
            db.query(InboundMessage)
            .filter(InboundMessage.tenant_id == tenant_id, InboundMessage.id == uuid.UUID(str(payload["message_id"])))
            .first()
        )
        if row is None or (row.flags or {}).get("checked") or not row.raw_object_key:
            return
        storage = ObjectStorageService()
        analyse(db, control_db, tenant_id, row, storage.get(str(tenant_id), row.raw_object_key), storage)
        db.commit()
