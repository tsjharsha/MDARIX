"""Make a tenant's evidence searchable: chunk any evidence that has no chunks yet, then embed every chunk.

Content comes through EvidenceContentReader, so file-backed evidence is read only from evidence storage. Evidence whose
content cannot be read is reported, never guessed. Ground-truth evaluation records are left out (as in indexing).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceChunk
from backend.app.db.models.foundation import Evidence
from evidence.extractors.chunker import EvidenceChunker
from evidence.services.content_reader import ContentSecurityError, EvidenceContentReader
from retrieval.embedding_provider import EmbeddingProvider
from retrieval.service import TrustedRetrievalService


def chunk_unchunked_evidence(db: Session, tenant_id: uuid.UUID) -> dict[str, Any]:
    chunked = select(EvidenceChunk.evidence_id).where(EvidenceChunk.tenant_id == tenant_id)
    pending = (
        db.query(Evidence)
        .filter(Evidence.tenant_id == tenant_id, Evidence.id.notin_(chunked))
        .filter(~func.lower(Evidence.evidence_identifier).like("%ground_truth%"))
        .order_by(Evidence.evidence_identifier)
        .all()
    )
    reader, chunker = EvidenceContentReader(), EvidenceChunker()
    created, unreadable = 0, []
    for evidence in pending:
        try:
            content, metadata = reader.get_evidence_content(db, tenant_id, evidence.id)
        except ContentSecurityError:
            unreadable.append(evidence.evidence_identifier)
            continue
        created += len(chunker.create_chunks_for_evidence(db, tenant_id, evidence.id, content, metadata))
    db.commit()
    return {"evidence_chunked": len(pending) - len(unreadable), "chunks_created": created, "unreadable": unreadable}


def index_tenant_evidence(
    db: Session, tenant_id: uuid.UUID, provider: EmbeddingProvider | None = None, reprocess: bool = False
) -> dict[str, Any]:
    chunking = chunk_unchunked_evidence(db, tenant_id)
    indexing = TrustedRetrievalService(provider).index_evidence_chunks(db, tenant_id, reprocess=reprocess)
    return {"chunking": chunking, "indexing": indexing}
