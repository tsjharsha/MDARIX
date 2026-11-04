"""Saving a signature and the record it signs, recoverably, when they live in two databases (DEV-07, 0.10.86).

Signatures (``signed_approval_records``) and the control-plane audit trail are in the control database; an
organization's records (decisions, dispositions, market conclusions, reports, ...) are in its data plane. On the
shared plane the two are one database and a signing is one transaction, as before. On a dedicated plane no
transaction spans both, so a signing follows this state machine, every state durable:

1. PREPARE (data plane, not yet committed): the record, plus a receipt naming the signature (an audit row
   ``SIGNATURE_RECORD_SAVED`` that carries the signing's control-plane audit events) and an advisory lock on the
   signature's id, held until the data plane commits or rolls back.
2. PENDING (control plane, committed): the signature with status PENDING, without its audit events. A PENDING
   signature is never valid: verification and every screen need SIGNED.
3. SAVED (data plane, committed): the record and its receipt, together; the lock is released.
4. SIGNED (control plane, committed): ``settle`` finds the receipt, sets the signature's status and writes the audit
   events the receipt carries, exactly once (the signature row is locked, and only a PENDING one is settled).

Failures: if step 3 fails, ``settle`` finds no receipt and abandons the signature at once (it is removed, and
``SIGNATURE_ABANDONED`` is audited): nothing was signed, and the person may sign again. If the process dies at any
point, or step 4 fails, the signature stays PENDING until it is settled: by the scheduler's ``signature-settlement``
job (``settle_pending``), by a read of the signed record, or by the person retrying. ``settle`` first waits for the
signature's lock, so a signing still saving is never judged half-way. Settling is idempotent.

Audit events already flushed to the control database before ``commit`` stay in step 2's commit; the signing routes
add theirs just before committing, so they are carried by the receipt.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, SignedApprovalRecord
from backend.app.enterprise_audit import make_audit_event

logger = logging.getLogger("mdarix.signing")

PENDING = "PENDING"
RECEIPT = "SIGNATURE_RECORD_SAVED"
ABANDONED = "SIGNATURE_ABANDONED"
_EVENT_FIELDS = (
    "tenant_id",
    "actor_ref",
    "action",
    "entity_type",
    "entity_id",
    "correlation_id",
    "details",
    "source_ip",
    "user_agent",
    "reason",
    "old_values",
    "new_values",
    "created_at",
    "retention_until",
)
_MOMENTS = ("created_at", "retention_until")
_IDS = ("tenant_id", "entity_id")


def _reached(step: str) -> None:
    """A durable step is done (``pending``, ``saved``, ``signed``): the seam the failure-injection tests use."""


def _lock(data: Session, signature_id) -> None:
    data.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"mdarix:signature:{signature_id}"}
    )


def _event_dict(event: AuditEvent) -> dict:
    found = {}
    for field in _EVENT_FIELDS:
        value = getattr(event, field)
        found[field] = (
            value.isoformat() if isinstance(value, datetime) else str(value) if field in _IDS and value else value
        )
    return found


def _event_of(values: dict) -> AuditEvent:
    values = dict(values)
    for field in _MOMENTS:
        if values.get(field):
            values[field] = datetime.fromisoformat(values[field])
    for field in _IDS:
        if values.get(field):
            values[field] = uuid.UUID(values[field])
    return AuditEvent(id=None, **values)


def commit(data: Session, control_db: Session, what: str) -> None:
    """Commit a signing: one transaction on the shared plane, the state machine above on a dedicated one. ``what``
    names the record for the logs. Raises 503 SIGNING_INCOMPLETE when the record is saved but its signature could not
    be completed yet (it is completed later, never shown as valid meanwhile); re-raises when the record could not be
    saved (the signature is abandoned, nothing is signed)."""
    if data is control_db:
        control_db.commit()
        return
    signatures = [item for item in control_db.new if isinstance(item, SignedApprovalRecord)]
    if not signatures:
        control_db.commit()
        data.commit()
        return
    events = [item for item in control_db.new if isinstance(item, AuditEvent)]
    now = datetime.now(timezone.utc)
    for index, signature in enumerate(signatures):
        signature.id = signature.id or uuid.uuid4()
        _lock(data, signature.id)
        data.add(
            make_audit_event(
                tenant_id=signature.tenant_id,
                actor_ref=signature.signer_user_id,
                action=RECEIPT,
                entity_type="SignedApprovalRecord",
                entity_id=signature.id,
                created_at=now,
                details={
                    "status": signature.status,
                    "object_type": signature.object_type,
                    "object_id": str(signature.object_id),
                    # The control-plane audit events of the signing, written when it is settled (once, by the first).
                    "control_audit": [_event_dict(event) for event in events] if index == 0 else [],
                },
            )
        )
        signature.status = PENDING
    for event in events:
        control_db.expunge(event)
    control_db.commit()
    _reached("pending")
    try:
        data.commit()
    except Exception:
        logger.exception("The %s was not saved: its signature is abandoned", what)
        data.rollback()
        for signature in signatures:
            _settle_quietly(control_db, data, signature.id)
        raise
    _reached("saved")
    for signature in signatures:
        try:
            settle(control_db, data, signature.id)
        except Exception as exc:
            logger.exception("The %s is saved; its signature %s stays PENDING until settled", what, signature.id)
            _rollback(control_db)
            raise HTTPException(
                503,
                detail={
                    "code": "SIGNING_INCOMPLETE",
                    "message": "Your signature is recorded and is being completed. Reload in a minute to see it.",
                },
            ) from exc
    _reached("signed")


def settle(control_db: Session, data: Session, signature_id) -> str | None:
    """Finish one PENDING signature (SIGNED, with its audit events) when its record's receipt is in the data plane,
    or abandon it when the record was never saved. Returns the signature's status afterwards (ABANDONED when removed;
    None when there is no such signature). Commits the control session; leaves the data session's transaction open
    (its lock with it) for the caller to end."""
    signature = (
        control_db.query(SignedApprovalRecord)
        .filter(SignedApprovalRecord.id == signature_id)
        .with_for_update()
        .one_or_none()
    )
    if signature is None or signature.status != PENDING:
        status = signature.status if signature is not None else None
        control_db.commit()
        return status
    _lock(data, signature_id)  # a signing still saving its record finishes first
    receipt = (
        data.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == signature.tenant_id,
            AuditEvent.entity_type == "SignedApprovalRecord",
            AuditEvent.entity_id == signature_id,
            AuditEvent.action == RECEIPT,
        )
        .first()
    )
    if receipt is not None:
        details = receipt.details or {}
        signature.status = details.get("status") or "SIGNED"
        for values in details.get("control_audit") or []:
            control_db.add(_event_of(values))
        outcome = signature.status
    else:
        control_db.add(
            make_audit_event(
                tenant_id=signature.tenant_id,
                actor_ref=signature.signer_user_id,
                action=ABANDONED,
                entity_type=signature.object_type,
                entity_id=signature.object_id,
                reason="The record it signs was not saved, so nothing was signed; the person may sign again.",
                details={
                    "signature_id": str(signature.id),
                    "object_version": signature.object_version,
                    "decision": signature.decision,
                    "fingerprint": signature.content_fingerprint,
                },
            )
        )
        control_db.delete(signature)
        outcome = "ABANDONED"
    control_db.commit()
    return outcome


def _rollback(session: Session) -> None:
    try:
        session.rollback()
    except Exception:
        logger.exception("A session could not be rolled back")


def _settle_quietly(control_db: Session, data: Session, signature_id) -> None:
    try:
        settle(control_db, data, signature_id)
        data.rollback()
    except Exception:
        logger.exception("Signature %s stays PENDING until the settlement job settles it", signature_id)
        _rollback(control_db)
        _rollback(data)


def settle_pending(db: Session, older_than: timedelta = timedelta(minutes=2), now: datetime | None = None) -> dict:
    """The ``signature-settlement`` job: settle every signature PENDING for longer than ``older_than``, in its own
    organization's data plane (after a restart, a crash between the two commits, or a failed last step)."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.tenant_scope import bind_system

    now = now or datetime.now(timezone.utc)
    bind_system(db, "signature settlement")
    pending = [
        (row.id, row.tenant_id)
        for row in db.query(SignedApprovalRecord.id, SignedApprovalRecord.tenant_id).filter(
            SignedApprovalRecord.status == PENDING, SignedApprovalRecord.created_at <= now - older_than
        )
    ]
    db.commit()
    outcomes: dict[str, int] = {}
    failed = []
    for signature_id, tenant_id in pending:
        try:
            with open_tenant_data_session(tenant_id) as data:
                bind_system(db, "signature settlement")
                outcome = settle(db, data, signature_id) or "GONE"
                data.rollback()
        except Exception:
            logger.exception("Signature %s could not be settled; the next run tries again", signature_id)
            _rollback(db)
            failed.append(str(signature_id))
            continue
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {"pending": len(pending), "settled": outcomes, "failed": failed}
