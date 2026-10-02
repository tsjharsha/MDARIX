"""Leave a tenant's evidence chunks as a test found them (other suites read the golden tenant's chunks)."""

from __future__ import annotations

from contextlib import contextmanager

from backend.app.db.models.evidence_intelligence import EvidenceChunk
from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding


@contextmanager
def restore_chunks(db, tenant_id):
    """Chunks (and their vectors) created inside the block are removed afterwards; existing ones are kept."""
    before = {row.id for row in db.query(EvidenceChunk.id).filter(EvidenceChunk.tenant_id == tenant_id)}
    try:
        yield
    finally:
        db.rollback()
        created = [
            row.id
            for row in db.query(EvidenceChunk.id).filter(EvidenceChunk.tenant_id == tenant_id)
            if row.id not in before
        ]
        if created:
            db.query(EvidenceChunkEmbedding).filter(
                EvidenceChunkEmbedding.tenant_id == tenant_id, EvidenceChunkEmbedding.chunk_id.in_(created)
            ).delete(synchronize_session=False)
            db.query(EvidenceChunk).filter(EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.id.in_(created)).delete(
                synchronize_session=False
            )
            db.commit()
