"""Imported business records as searchable evidence, so Ask MDARIX and the investigator can find them.

Each imported complaint, investigation, CAPA, change, requirement, risk, failure mode or control gets one evidence row
(type SOURCE_RECORD) holding a readable summary of the record, linked to the record and to its product, version and
lot. The summary is chunked in the import's own transaction; embeddings for semantic search are added afterwards by
embed_tenant_evidence (run in the background so a large import does not wait for the embedding model).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
from backend.app.db.models.foundation import Evidence
from evidence.extractors.chunker import EvidenceChunker

RECORD_EVIDENCE_TYPE = "SOURCE_RECORD"
logger = logging.getLogger(__name__)


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


def embed_tenant_evidence(open_session, tenant_id) -> None:
    """Add embeddings for chunks that have none yet (background step after an import commits)."""
    from retrieval.service import TrustedRetrievalService

    try:
        with open_session(tenant_id) as db:
            TrustedRetrievalService().index_evidence_chunks(db, tenant_id)
            db.commit()
    except Exception:  # the import already succeeded; search falls back to the structured links until next run
        logger.exception("Embedding imported records failed for tenant %s", tenant_id)
