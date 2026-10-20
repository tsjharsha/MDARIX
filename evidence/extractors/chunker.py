import hashlib
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db.models.evidence_intelligence import EvidenceChunk
from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding


class EvidenceChunker:
    """Chunks evidence content into deterministic semantic blocks with source locators."""

    def __init__(self, target_chunk_size: int = 500, max_chunk_size: int = 1000):
        self.target_chunk_size = target_chunk_size
        self.max_chunk_size = max_chunk_size

    def create_chunks_for_evidence(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        evidence_id: uuid.UUID,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[EvidenceChunk]:
        """Splits content into EvidenceChunk records and persists them idempotently."""
        # Delete Day 9 embeddings first so Day 8 chunk reprocessing stays idempotent.
        existing_chunk_ids = [
            row.id
            for row in db.query(EvidenceChunk.id)
            .filter(
                EvidenceChunk.tenant_id == tenant_id,
                EvidenceChunk.evidence_id == evidence_id,
            )
            .all()
        ]
        if existing_chunk_ids:
            db.query(EvidenceChunkEmbedding).filter(
                EvidenceChunkEmbedding.tenant_id == tenant_id,
                EvidenceChunkEmbedding.chunk_id.in_(existing_chunk_ids),
            ).delete(synchronize_session=False)

        db.query(EvidenceChunk).filter(
            EvidenceChunk.tenant_id == tenant_id,
            EvidenceChunk.evidence_id == evidence_id,
        ).delete(synchronize_session=False)

        chunk_objects = self._chunk_rows(tenant_id, evidence_id, content)
        db.add_all(chunk_objects)
        db.flush()
        return chunk_objects

    def create_chunks_for_evidences(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        contents: Sequence[Tuple[uuid.UUID, str]],
        replace: Iterable[uuid.UUID] = (),
    ) -> int:
        """create_chunks_for_evidence for many evidence rows at once (an import, NEW-4).

        The chunks of the rows in ``replace``, and their embeddings, are deleted with one statement each per 1,000 rows;
        then the chunks of every row in ``contents`` (evidence id, text) are inserted in batches (db/bulk.py). A new
        evidence row has no chunks to replace. Returns how many chunks were added.
        """
        from backend.app.db.bulk import insert_rows

        replace = list(replace)
        for start in range(0, len(replace), 1000):
            part = replace[start : start + 1000]
            old_chunks = select(EvidenceChunk.id).where(
                EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.evidence_id.in_(part)
            )
            db.query(EvidenceChunkEmbedding).filter(
                EvidenceChunkEmbedding.tenant_id == tenant_id, EvidenceChunkEmbedding.chunk_id.in_(old_chunks)
            ).delete(synchronize_session=False)
            db.query(EvidenceChunk).filter(
                EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.evidence_id.in_(part)
            ).delete(synchronize_session=False)
        rows = [row for evidence_id, content in contents for row in self._chunk_values(tenant_id, evidence_id, content)]
        insert_rows(db, EvidenceChunk, rows)
        return len(rows)

    def _chunk_rows(self, tenant_id: uuid.UUID, evidence_id: uuid.UUID, content: str) -> List[EvidenceChunk]:
        """The EvidenceChunk rows of one evidence text, numbered from 1, not yet added to the session."""
        return [EvidenceChunk(**values) for values in self._chunk_values(tenant_id, evidence_id, content)]

    def _chunk_values(self, tenant_id: uuid.UUID, evidence_id: uuid.UUID, content: str) -> List[Dict[str, Any]]:
        """The column values of the chunks of one evidence text, numbered from 1."""
        return [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "evidence_id": evidence_id,
                "sequence_number": seq,
                "text_content": chunk_text,
                "source_anchor": anchor,
                "token_count": len(chunk_text.split()),
                "checksum": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
            }
            for seq, (chunk_text, anchor) in enumerate(self._chunk_text(content), start=1)
        ]

    def _chunk_text(self, content: str) -> List[tuple[str, Dict[str, Any]]]:
        """Deterministically breaks content into paragraph or section blocks."""
        chunks: List[tuple[str, Dict[str, Any]]] = []

        if not content or not content.strip():
            return [("", {"section": "empty", "character_range": [0, 0]})]

        # Break by double newline or CSV/JSON boundaries
        lines = content.splitlines()
        current_block: List[str] = []
        current_len = 0
        start_char = 0
        p_index = 0

        for line in lines:
            line_str = line.strip()
            if not line_str:
                if current_block:
                    block_text = "\n".join(current_block)
                    end_char = start_char + len(block_text)
                    anchor = {
                        "paragraph_index": p_index,
                        "character_range": [start_char, end_char],
                        "excerpt": block_text[:100],
                    }
                    chunks.append((block_text, anchor))
                    p_index += 1
                    start_char = end_char + 1
                    current_block = []
                    current_len = 0
                continue

            current_block.append(line)
            current_len += len(line)

            if current_len >= self.target_chunk_size:
                block_text = "\n".join(current_block)
                end_char = start_char + len(block_text)
                anchor = {
                    "paragraph_index": p_index,
                    "character_range": [start_char, end_char],
                    "excerpt": block_text[:100],
                }
                chunks.append((block_text, anchor))
                p_index += 1
                start_char = end_char + 1
                current_block = []
                current_len = 0

        if current_block:
            block_text = "\n".join(current_block)
            end_char = start_char + len(block_text)
            anchor = {
                "paragraph_index": p_index,
                "character_range": [start_char, end_char],
                "excerpt": block_text[:100],
            }
            chunks.append((block_text, anchor))

        return chunks
