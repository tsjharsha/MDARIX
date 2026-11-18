"""Sample texts that older trials still hold, upgraded to today's text (scripts/refresh_trial_story.py), idempotent.

The free-trial AI gate (genai/sample_gate.py) accepts a sample record only while its text is one the sample loader
writes today, so a trial seeded before G-06 (17 Nov 2026) holds a SAMPLE-EV-003 ("Complaint trend summary") that
reads as edited and Ask MDARIX and case analysis refuse it. Only a row still holding one of the exact old texts below
is changed: a text a person edited is left as it is. The evidence's single search chunk keeps its id (citations point
to it) and gets the new text, anchor, token count and checksum; a record without a chunk gets one. The caller commits
and then re-embeds the changed chunks (``reindex``).

This module is deliberately not named ``sample*.py``: the gate's catalogue reads every string constant of those
modules, and the old texts below must not count as sample text.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

# evidence identifier -> the texts earlier sample loaders wrote (git history of trial/sample_data.py since 0.10.0).
OLD_TEXTS = {
    "SAMPLE-EV-003": (
        "Pressure-alarm complaints averaged 0.8 per month on Rev A and 5.6 per month after Rev B, with "
        "most from lots 003 and 004.",
        "Pressure-alarm complaints averaged 0.8 per month in the 150 days before Rev B and 5.6 per month after Rev "
        "B, with most from lots 003 and 004.",
    ),
}


def _current() -> dict[str, str]:
    from backend.app.trial.sample_data import TREND_SUMMARY

    return {"SAMPLE-EV-003": TREND_SUMMARY}


def _owed(db: Session, tenant_id) -> list:
    from sqlalchemy import or_

    from backend.app.db.models.foundation import Evidence
    from backend.app.trial.sample_source import SAMPLE_SOURCE

    return (
        db.query(Evidence)
        .filter(
            Evidence.tenant_id == tenant_id,
            Evidence.source_system == SAMPLE_SOURCE,
            or_(
                *(
                    (Evidence.evidence_identifier == identifier) & Evidence.content.in_(texts)
                    for identifier, texts in OLD_TEXTS.items()
                )
            ),
        )
        .order_by(Evidence.evidence_identifier)
        .all()
    )


def refresh(db: Session, tenant_id, apply: bool) -> int:
    """How many sample evidence records still hold a known old text; with ``apply`` each gets today's text and its
    chunk follows (flushed; old embeddings of the chunk removed, so ``reindex`` embeds the new text)."""
    from evidence.extractors.chunker import EvidenceChunker

    from backend.app.db.models.evidence_intelligence import EvidenceChunk
    from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding

    owed = _owed(db, tenant_id)
    if not apply:
        return len(owed)
    chunker = EvidenceChunker()
    for evidence in owed:
        text = _current()[evidence.evidence_identifier]
        evidence.content = text
        chunks = db.query(EvidenceChunk).filter(
            EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.evidence_id == evidence.id
        )
        values = chunker._chunk_values(tenant_id, evidence.id, text)
        if chunks.count() == 1 and len(values) == 1:
            chunk = chunks.one()
            for key in ("text_content", "source_anchor", "token_count", "checksum"):
                setattr(chunk, key, values[0][key])
            db.query(EvidenceChunkEmbedding).filter(
                EvidenceChunkEmbedding.tenant_id == tenant_id, EvidenceChunkEmbedding.chunk_id == chunk.id
            ).delete(synchronize_session=False)
        else:
            # No chunk yet (or not the one the loader writes): chunked as the loader does.
            chunker.create_chunks_for_evidence(db, tenant_id, evidence.id, text)
    db.flush()
    return len(owed)


def reindex(db: Session, tenant_id) -> dict:
    """Embed the tenant's chunks that have no current embedding (the upgraded ones among them). Commits."""
    from retrieval.service import TrustedRetrievalService

    return TrustedRetrievalService().index_evidence_chunks(db, tenant_id)
