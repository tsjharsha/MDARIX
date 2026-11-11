"""One way to sign a review (B6a 5.1, D6: no migration).

A review's content (period, filters, findings, the list reviewed) is JSON, hashed (SHA-256) and written as ONE audit
event holding the content in ``details["material"]``; the signature is a ``SignedApprovalRecord`` for that review with
``content_fingerprint`` = the hash, after re-authentication (password, and an authenticator code when signatures need
MFA; refusals counted on the "sign" throttle and audited). The audit chain makes the stored content tamper-evident.
Nothing is edited after signing: a correction is a new review that names the earlier one (``corrects``).

Everything lives in the control database (identity, configuration and the organization's audit reviews), so a signing
is one transaction on every plane. No signer-training document applies to these reviews (training covers market
question sets, the harm scale and disposition rules), so none is asked.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, SignedApprovalRecord
from backend.app.enterprise_audit import make_audit_event, safe_details

# kind -> (signed action, object type, signature meaning)
KINDS = {
    "audit-trail": (
        "AUDIT_TRAIL_REVIEW_SIGNED",
        "AuditTrailReview",
        "I reviewed this organization's audit trail for the period shown and recorded my findings.",
    ),
    "audit-trail-confirmation": (
        "AUDIT_TRAIL_REVIEW_CONFIRMED",
        "AuditTrailReview",
        "As a second reviewer I reviewed the flagged actions of the first reviewer and confirm the findings.",
    ),
    "access": (
        "ACCESS_REVIEW_SIGNED",
        "AccessReview",
        "I reviewed every active user's access and recorded Keep, Change or Remove for each.",
    ),
    "configuration": (
        "CONFIGURATION_SNAPSHOT_SIGNED",
        "ConfigurationSnapshot",
        "I confirm this is the configuration in force at the time shown.",
    ),
}
SIGNED_ACTIONS = {kind: action for kind, (action, _type, _meaning) in KINDS.items()}


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def as_material(value: dict) -> dict:
    """The content exactly as the audit row stores it: JSON types only, secret-named keys removed (``safe_details``),
    so the fingerprint of what is read back equals the fingerprint signed."""
    return safe_details(json.loads(json.dumps(value, default=str)))


def fingerprint_of(material: dict) -> str:
    from backend.app.human_decision.rules import fingerprint

    return fingerprint(material)


def sign(
    control_db: Session,
    ctx,
    *,
    kind: str,
    content: dict,
    findings: str,
    password: str | None,
    mfa_code: str | None,
    signer_role: str,
    review_id: uuid.UUID | None = None,
    version: str = "1",
    corrects: str | None = None,
    request=None,
) -> dict:
    """Re-authenticate, then write the signed review (audit event + signature) and commit. ``review_id`` names an
    existing review for a second signature on it (``version`` "2"); otherwise a new review id is made."""
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import signature_hash

    action, object_type, meaning = KINDS[kind]
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    review_id = review_id or uuid.uuid4()

    def refused(code: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=code,
                entity_type=object_type,
                entity_id=review_id,
                correlation_id=getattr(ctx, "correlation_id", None),
                details={"attempt": action},
                request=request,
            )
        )

    # Re-authenticate first: a refusal commits the control session, so nothing else may be pending in it yet.
    verify_signing_credentials(control_db, ctx, password=password, mfa_code=mfa_code, record_refusal=refused)
    material = as_material(
        {"kind": kind, "review_id": str(review_id), "content": content, "findings": findings, "corrects": corrects}
    )
    content_fingerprint = fingerprint_of(material)
    now = datetime.now(timezone.utc)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=object_type,
        object_id=review_id,
        object_version=version,
        decision_type=action,
        decision="SIGNED",
        remarks=findings,
        signer_user_id=str(ctx.user_id),
        signer_role=signer_role,
        signature_meaning=meaning,
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, str(ctx.user_id), version),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type=object_type,
            entity_id=review_id,
            correlation_id=getattr(ctx, "correlation_id", None),
            reason=findings,
            details={
                "material": material,
                "fingerprint": content_fingerprint,
                "signature_id": str(record.id),
                "signer_role": signer_role,
            },
            created_at=now,
            request=request,
        )
    )
    control_db.commit()
    return {"review_id": str(review_id), "signature_id": str(record.id), "fingerprint": content_fingerprint}


def signed_events(control_db: Session, tenant_id, kind: str, limit: int = 50) -> list[AuditEvent]:
    return (
        control_db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == SIGNED_ACTIONS[kind])
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )


def summary(event: AuditEvent) -> dict:
    material = (event.details or {}).get("material") or {}
    return {
        "review_id": str(event.entity_id),
        "kind": material.get("kind"),
        "signed_by": event.actor_ref,
        "signer_role": (event.details or {}).get("signer_role"),
        "signed_at": event.created_at.isoformat() if event.created_at else None,
        "findings": material.get("findings"),
        "corrects": material.get("corrects"),
        "fingerprint": (event.details or {}).get("fingerprint"),
    }


def read(control_db: Session, tenant_id, review_id: uuid.UUID) -> dict:
    """A signed review with its signatures; ``intact`` is True when the stored content still hashes to every
    signature's fingerprint. Another organization's review is 404 (tenant filter and row-level security)."""
    events = (
        control_db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id == tenant_id,
            AuditEvent.entity_id == review_id,
            AuditEvent.action.in_(sorted(SIGNED_ACTIONS.values())),
        )
        .order_by(AuditEvent.created_at.asc())
        .all()
    )
    if not events:
        raise error(404, "REVIEW_NOT_FOUND", "No such signed review in your organization")
    records = {
        str(row.id): row
        for row in control_db.query(SignedApprovalRecord).filter(
            SignedApprovalRecord.tenant_id == tenant_id, SignedApprovalRecord.object_id == review_id
        )
    }
    signatures = []
    intact = True
    for event in events:
        details = event.details or {}
        record = records.get(str(details.get("signature_id")))
        computed = fingerprint_of(details.get("material") or {})
        ok = record is not None and record.status == "SIGNED" and record.content_fingerprint == computed
        intact = intact and ok
        signatures.append({**summary(event), "intact": ok, "meaning": record.signature_meaning if record else None})
    first = events[0].details["material"]
    return {
        "review_id": str(review_id),
        "kind": first.get("kind"),
        "content": first.get("content"),
        "findings": first.get("findings"),
        "corrects": first.get("corrects"),
        "signatures": signatures,
        "intact": intact,
    }


def as_pdf(review: dict, organization: str | None) -> bytes:
    """A printable copy rendered from the stored, signed content (never from today's data)."""
    from reports import pdf

    titles = {"audit-trail": "Audit trail review", "access": "Access review", "configuration": "Configuration snapshot"}
    body: list[tuple[str, str]] = [("Findings", "heading"), (review.get("findings") or "None", "body")]
    for signature in review["signatures"]:
        body.append(
            (
                f"Signed {signature['signed_at'][:16].replace('T', ' ')} UTC by {signature['signed_by']} "
                f"({signature['signer_role']}): {signature['meaning'] or ''} Fingerprint {signature['fingerprint']}",
                "muted",
            )
        )
    body.append(("Content", "heading"))
    for line in json.dumps(review["content"], indent=1, sort_keys=True, ensure_ascii=False).splitlines():
        body.append((line, "body"))
    title = titles.get(review["kind"], "Signed review")
    return pdf.render(
        f"MDARIX {title.lower()}",
        [
            f"Organization: {organization or '-'}",
            f"Review {review['review_id']}" + (f", corrects {review['corrects']}" if review.get("corrects") else ""),
            "Content intact: yes" if review["intact"] else "Content intact: NO - the stored content does not match",
        ],
        body,
        watermark="SIGNED REVIEW",
        footer=f"{title} {review['review_id']}",
    )
