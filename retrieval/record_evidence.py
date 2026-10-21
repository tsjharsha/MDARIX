"""Imported business records as searchable evidence, so Ask MDARIX and the investigator can find them.

Each imported complaint, investigation, CAPA, change, requirement, risk, failure mode or control gets one evidence row
(type SOURCE_RECORD) holding a readable summary of the record, linked to the record and to its product, version and
lot. The summary is chunked in the import's own transaction; embeddings for semantic search are added afterwards by
the background service (queue_embeddings, run_embeddings_job below), so neither the import nor the API waits for the
embedding model.

upsert_record_evidence writes one record; upsert_record_evidences writes a whole import's records with the same result
in a few statements (NEW-4): a 5,000-row complaints file took about 13 statements a row.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
from backend.app.db.models.foundation import Evidence
from evidence.extractors.chunker import EvidenceChunker

RECORD_EVIDENCE_TYPE = "SOURCE_RECORD"
logger = logging.getLogger(__name__)
# Identifiers per IN (...) list of the batch queries, well within PostgreSQL's limit of bind parameters.
BATCH = 1000


def record_identifier(kind: str, identifier: str) -> str:
    return f"RECORD:{kind}:{identifier}"[:120]


def summary(label: str, facts: dict[str, object], narrative: str | None = None) -> str:
    """'Complaint CMP-1. Product: PUMP-200. Severity: Major. ... Description: ...' with empty facts left out."""
    parts = [label + "."]
    for name, value in facts.items():
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            value = "yes" if value else "no"
        elif isinstance(value, datetime):
            value = value.date().isoformat()
        parts.append(f"{name}: {value}.")
    if narrative:
        parts.append(narrative.strip())
    return " ".join(parts)


def upsert_record_evidence(
    db: Session,
    tenant_id,
    *,
    kind: str,
    identifier: str,
    title: str,
    content: str,
    links: list[tuple[str, uuid.UUID | None]],
    source: str,
    investigation_id: uuid.UUID | None = None,
) -> Evidence:
    """Create or refresh the evidence row for one record; re-chunk it only when its text changed."""
    now = datetime.now(timezone.utc)
    evidence_identifier = record_identifier(kind, identifier)
    evidence = (
        db.query(Evidence)
        .filter(Evidence.tenant_id == tenant_id, Evidence.evidence_identifier == evidence_identifier)
        .first()
    )
    changed = True
    if evidence is None:
        evidence = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=evidence_identifier,
            evidence_type=RECORD_EVIDENCE_TYPE,
            title=title[:255],
            source_reference=f"{source}:{identifier}"[:1000],
            reliability_status="source_record",
            fact_type="source_fact",
            content=content,
            investigation_id=investigation_id,
            source_system=source,
            source_identifier=identifier,
            source_timestamp=now,
            effective_timestamp=now,
            recorded_timestamp=now,
            ingestion_timestamp=now,
            created_at=now,
            updated_at=now,
        )
        db.add(evidence)
        db.flush()
    else:
        changed = evidence.content != content
        evidence.title, evidence.content = title[:255], content
        evidence.investigation_id = investigation_id or evidence.investigation_id
        evidence.updated_at = evidence.recorded_timestamp = now
    db.query(EvidenceEntityLink).filter(
        EvidenceEntityLink.tenant_id == tenant_id, EvidenceEntityLink.evidence_id == evidence.id
    ).delete(synchronize_session=False)
    for entity_type, entity_id in links:
        if entity_id is not None:
            db.add(
                EvidenceEntityLink(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    evidence_id=evidence.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    raw_reference=identifier[:500],
                    resolution_status="RESOLVED",
                )
            )
    if changed:
        EvidenceChunker().create_chunks_for_evidence(
            db, tenant_id, evidence.id, content, {"record_type": kind, "record": identifier}
        )
    db.flush()
    return evidence


@dataclass(frozen=True)
class RecordEvidence:
    """One record's evidence, as upsert_record_evidence takes it."""

    kind: str
    identifier: str
    title: str
    content: str
    links: list[tuple[str, uuid.UUID | None]]
    source: str
    investigation_id: uuid.UUID | None = None


def _parts(values: list, size: int = BATCH):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def upsert_record_evidences(db: Session, tenant_id, items: Iterable[RecordEvidence]) -> list[uuid.UUID]:
    """upsert_record_evidence for many records, with the same rows, links and chunks as calling it for each in turn.

    The existing evidence rows are read in one query per 1,000 identifiers; the new rows, the links and the chunks are
    inserted in batches (db/bulk.py), and the old links (and the old chunks of a record whose text changed, with their
    embeddings) are deleted together (NEW-4). A record listed twice ends as the one-by-one calls would leave it: the
    last text, title and links, the first one's source, the last investigation given, re-chunked when any step changed
    its text. Returns the ids of the evidence rows, in the order their records first appear. New rows are not loaded
    into the session.
    """
    from backend.app.db.bulk import insert_rows

    items = list(items)
    if not items:
        return []
    now = datetime.now(timezone.utc)
    order: list[str] = []
    first: dict[str, RecordEvidence] = {}
    last: dict[str, RecordEvidence] = {}
    investigation: dict[str, uuid.UUID] = {}
    texts: dict[str, list[str]] = {}
    for item in items:
        key = record_identifier(item.kind, item.identifier)
        if key not in first:
            order.append(key)
            first[key] = item
        last[key] = item
        texts.setdefault(key, []).append(item.content)
        if item.investigation_id is not None:
            investigation[key] = item.investigation_id
    existing: dict[str, Evidence] = {}
    for part in _parts(order):
        for evidence in db.query(Evidence).filter(
            Evidence.tenant_id == tenant_id, Evidence.evidence_identifier.in_(part)
        ):
            existing.setdefault(evidence.evidence_identifier, evidence)

    rows: list[tuple[uuid.UUID, RecordEvidence]] = []
    added: list[dict] = []
    changed: list[tuple[uuid.UUID, RecordEvidence]] = []
    replaced: list[uuid.UUID] = []
    for key in order:
        item, evidence = last[key], existing.get(key)
        if evidence is None:
            origin = first[key]
            added.append(
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "evidence_identifier": key,
                    "evidence_type": RECORD_EVIDENCE_TYPE,
                    "title": item.title[:255],
                    "source_reference": f"{origin.source}:{origin.identifier}"[:1000],
                    "reliability_status": "source_record",
                    "fact_type": "source_fact",
                    "content": item.content,
                    "investigation_id": investigation.get(key),
                    "source_system": origin.source,
                    "source_identifier": origin.identifier,
                    "source_timestamp": now,
                    "effective_timestamp": now,
                    "recorded_timestamp": now,
                    "ingestion_timestamp": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            rows.append((added[-1]["id"], item))
            changed.append(rows[-1])
        else:
            # Re-chunked when any of the record's texts differed from the one before it, as one call at a time does.
            previous, differs = evidence.content, False
            for text in texts[key]:
                differs, previous = differs or text != previous, text
            if differs:
                changed.append((evidence.id, item))
                replaced.append(evidence.id)
            evidence.title, evidence.content = item.title[:255], item.content
            evidence.investigation_id = investigation.get(key) or evidence.investigation_id
            evidence.updated_at = evidence.recorded_timestamp = now
            rows.append((evidence.id, item))
    db.flush()
    insert_rows(db, Evidence, added)

    for part in _parts([evidence.id for evidence in existing.values()]):
        db.query(EvidenceEntityLink).filter(
            EvidenceEntityLink.tenant_id == tenant_id, EvidenceEntityLink.evidence_id.in_(part)
        ).delete(synchronize_session=False)
    insert_rows(
        db,
        EvidenceEntityLink,
        [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "evidence_id": evidence_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "raw_reference": item.identifier[:500],
                "resolution_status": "RESOLVED",
            }
            for evidence_id, item in rows
            for entity_type, entity_id in item.links
            if entity_id is not None
        ],
    )
    EvidenceChunker().create_chunks_for_evidences(
        db, tenant_id, [(evidence_id, item.content) for evidence_id, item in changed], replace=replaced
    )
    return [evidence_id for evidence_id, _ in rows]


# ------------------------------------------------------------------------------------- embeddings after an import
#
# An import's records are embedded by the background service, not by the API (0.10.42): the embedding model is
# CPU-bound, and in the API process it slowed every request for minutes after a large import. The import queues one
# outbox event once its signals are found (backend/app/trial/imports.py after_import); the outbox worker
# (scripts/run_outbox_worker.py) embeds in slices of about EMBEDDING_SLICE_SECONDS, each slice queueing the next, so
# its heartbeat and the other events (emails) never wait long. A failure is tried again by the outbox (outbox/worker.py:
# 30 s, doubling, then dead-lettered and alerted); the import itself is long saved by then. Until the embeddings are
# in, search finds the new records by their text and links (structured search), as before.

EMBEDDINGS_EVENT = "RECORD_EMBEDDINGS_REQUESTED"
EMBEDDING_SLICE_SECONDS = 20.0
# The embedding thread's niceness (Linux): it yields to the scheduler and anything else in the background service.
EMBEDDING_NICE = 10


class EmbeddingsIncomplete(RuntimeError):
    """Some chunks could not be embedded: the outbox tries the event again later."""


def _add_embeddings_event(tenant_id, payload: dict) -> None:
    """One RECORD_EMBEDDINGS_REQUESTED event for the organization, committed on its own (control database)."""
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_name=EMBEDDINGS_EVENT,
                aggregate_type="Evidence",
                payload={**payload, "tenant_id": str(tenant_id)},
                occurred_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


def queue_embeddings(tenant_id, *, source: str, records: int = 0, imported_at: str | None = None) -> None:
    """Ask the background service to embed the organization's records that have none yet: an import's follow-up step,
    after its signals (a background task of the route). The payload holds counts and times only, never record text.
    Never raises: a failure is logged, and the scheduled embedding catch-up embeds them later."""
    tenant = uuid.UUID(str(tenant_id))
    try:
        _add_embeddings_event(
            tenant,
            {
                "source": source,
                "records": int(records or 0),
                "imported_at": imported_at or datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        logger.exception(
            "Embeddings after %s could not be queued for tenant %s; the scheduled catch-up embeds them", source, tenant
        )


def _at_low_priority(work):
    """``work()`` in a thread of its own at niceness EMBEDDING_NICE (Linux sets the priority per thread; elsewhere it
    runs at the usual priority), so the lower priority ends with it. Returns its result or raises its error."""
    import os
    import threading

    outcome: dict = {}

    def run():
        try:
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), EMBEDDING_NICE)
        except (AttributeError, OSError):  # not Linux, or not allowed: the work still runs
            pass
        try:
            outcome["result"] = work()
        except BaseException as exc:  # handed to the caller below
            outcome["error"] = exc

    thread = threading.Thread(target=run, name="mdarix-embeddings")
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


def _seconds_since(stamp) -> float | None:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(stamp))).total_seconds()
    except (TypeError, ValueError):
        return None


def run_embeddings_job(payload: dict, open_session=None, slice_seconds: float = EMBEDDING_SLICE_SECONDS) -> dict:
    """Deliver one RECORD_EMBEDDINGS_REQUESTED event (outbox worker): embed the organization's chunks that have no
    current embedding for about ``slice_seconds``, in its data plane bound to it (``open_tenant_data_session``).
    Work left over is queued as the next event, with the counts so far; chunks that could not be embedded raise
    EmbeddingsIncomplete once nothing else is left (or at once when nothing could be embedded), so the outbox tries
    again. An organization without an active data plane (deleted meanwhile) has nothing to embed."""
    from retrieval.service import TrustedRetrievalService

    if open_session is None:
        from backend.app.db.data_plane import open_tenant_data_session as open_session
    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    source = str(payload.get("source") or "import")
    started = time.monotonic()

    def work():
        with open_session(tenant_id) as db:
            return TrustedRetrievalService().index_evidence_chunks(db, tenant_id, budget_seconds=slice_seconds)

    try:
        result = _at_low_priority(work)
    except RuntimeError as exc:
        if str(exc).startswith("DATA_PLANE_UNAVAILABLE"):
            logger.warning("Embeddings after %s skipped: tenant %s has no active data plane", source, tenant_id)
            return {"indexed": 0, "failed": 0, "deferred": 0}
        raise
    took = time.monotonic() - started
    embedded = int(payload.get("embedded") or 0) + int(result["indexed"])
    seconds = float(payload.get("seconds") or 0) + took
    # A slice that embedded something hands the rest on; one that embedded nothing (the model is down) does not, or
    # the slices would chase the same failing chunks for ever: it fails, and the outbox backs off.
    if result["deferred"] and (result["indexed"] or not result["failed"]):
        logger.info(
            "Embeddings after %s: %d chunks embedded in %.1f s, %d left for the next slice (tenant %s)",
            source,
            result["indexed"],
            took,
            result["deferred"],
            tenant_id,
        )
        _add_embeddings_event(tenant_id, {**payload, "embedded": embedded, "seconds": round(seconds, 1)})
        return result
    if result["failed"]:
        logger.warning(
            "Embeddings after %s: %d chunks could not be embedded (tenant %s); the outbox tries again",
            source,
            result["failed"],
            tenant_id,
        )
        raise EmbeddingsIncomplete(f"{result['failed']} chunk(s) could not be embedded")
    since = _seconds_since(payload.get("imported_at"))
    logger.info(
        "Embeddings after %s finished in %.1f s, %s after the import (%d records imported, %d chunks embedded, "
        "tenant %s)",
        source,
        seconds,
        f"{since:.1f} s" if since is not None else "unknown",
        int(payload.get("records") or 0),
        embedded,
        tenant_id,
    )
    return result
