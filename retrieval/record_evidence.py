"""Imported business records as searchable evidence, so Ask MDARIX and the investigator can find them.

Each imported complaint, investigation, CAPA, change, requirement, risk, failure mode or control gets one evidence row
(type SOURCE_RECORD) holding a readable summary of the record, linked to the record and to its product, version and
lot. The summary is chunked in the import's own transaction; embeddings for semantic search are added afterwards by
embed_tenant_evidence (run in the background so a large import does not wait for the embedding model).

upsert_record_evidence writes one record; upsert_record_evidences writes a whole import's records with the same result
in a few statements (NEW-4): a 5,000-row complaints file took about 13 statements a row.
"""

from __future__ import annotations

import logging
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


def embed_tenant_evidence(open_session, tenant_id) -> None:
    """Add embeddings for chunks that have none yet (background step after an import commits)."""
    from retrieval.service import TrustedRetrievalService

    try:
        with open_session(tenant_id) as db:
            TrustedRetrievalService().index_evidence_chunks(db, tenant_id)
            db.commit()
    except Exception:  # the import already succeeded; search falls back to the structured links until next run
        logger.exception("Embedding imported records failed for tenant %s", tenant_id)
