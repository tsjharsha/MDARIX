"""Tamper-evident audit trail: verify each organization's hash chain.

The database chains every audit event when it is inserted (migration md18: ``chain_seq``, ``previous_hash``,
``event_hash`` = SHA-256 of the row's canonical content and the previous hash) and rejects updates and deletes
(``audit_events_immutable``). Verification recomputes the chain in the database with
``mdarix_verify_audit_chain``, so it uses exactly the canonical form the trigger used.

The scheduler verifies every organization daily (``verify_all``) and keeps each one's last verified head
(sequence number and hash) as an anchor in ``scheduler_runs.state``; the next run first checks the anchored row is
unchanged and then verifies only newer rows. A chain rewritten and re-hashed from the start would still break its
anchor. Each head is also written to the log, which is kept outside the database.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.audit_chain")


def verify_tenant_chain(db: Session, tenant_id, after_seq: int = 0, after_hash: str | None = None) -> dict:
    """Recompute an organization's chain (from the start, or after a verified anchor)."""
    row = (
        db.execute(
            text("SELECT * FROM public.mdarix_verify_audit_chain(:tenant, :after_seq, :after_hash)"),
            {"tenant": uuid.UUID(str(tenant_id)), "after_seq": int(after_seq), "after_hash": after_hash},
        )
        .mappings()
        .one()
    )
    return {
        "valid": row["first_broken_seq"] is None,
        "checked": int(row["checked"]),
        "first_broken_seq": row["first_broken_seq"],
        "last_seq": int(row["last_seq"]),
        "last_hash": row["last_hash"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def _anchor_intact(db: Session, tenant_id, anchor: dict) -> bool:
    stored = db.execute(
        text("SELECT event_hash FROM public.audit_events WHERE tenant_id = :tenant AND chain_seq = :seq"),
        {"tenant": uuid.UUID(str(tenant_id)), "seq": int(anchor["seq"])},
    ).scalar()
    return stored == anchor["hash"]


def verify_all(db: Session, state: dict) -> dict:
    """Verify every organization's chain from its anchor; returns totals and the organizations whose chain broke.

    ``state["anchors"]`` maps tenant id -> {"seq", "hash"} of the last verified head (kept between runs)."""
    anchors: dict = dict(state.get("anchors") or {})
    tenants = [row[0] for row in db.execute(text("SELECT DISTINCT tenant_id FROM public.audit_events")).all()]
    broken: list[dict] = []
    checked = 0
    for tenant_id in tenants:
        key = str(tenant_id)
        anchor = anchors.get(key)
        if anchor and not _anchor_intact(db, tenant_id, anchor):
            broken.append({"tenant_id": key, "reason": "ANCHOR_CHANGED", "seq": anchor["seq"]})
            continue
        result = verify_tenant_chain(db, tenant_id, anchor["seq"] if anchor else 0, anchor["hash"] if anchor else None)
        checked += result["checked"]
        if not result["valid"]:
            broken.append({"tenant_id": key, "reason": "CHAIN_BROKEN", "seq": result["first_broken_seq"]})
            continue
        if result["last_seq"]:
            anchors[key] = {"seq": result["last_seq"], "hash": result["last_hash"]}
            logger.info(
                "Audit chain verified tenant=%s head_seq=%s head_hash=%s", key, result["last_seq"], result["last_hash"]
            )
    state["anchors"] = anchors
    if broken:
        logger.error("Audit chain verification failed for %d organization(s): %s", len(broken), broken)
    return {"organizations": len(tenants), "events_checked": checked, "broken": broken}
