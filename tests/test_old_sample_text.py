"""W1e: the trial refresh upgrades SAMPLE-EV-003's pre-G-06 trend texts, so older trials pass the AI sample gate.

An older trial holds one of two known old texts (and a search chunk with it); the free-trial AI gate reads that as an
edited sample record. ``scripts/refresh_trial_story.py --apply`` gives it today's text, keeps the chunk's id, re-embeds
it, and the gate then accepts it. A text a person typed is left alone. Idempotent.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant

ROOT = Path(__file__).resolve().parents[1]
EV = "SAMPLE-EV-003"


def _script():
    spec = importlib.util.spec_from_file_location("refresh_trial_story", ROOT / "scripts" / "refresh_trial_story.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_old_texts_are_not_sample_text_and_todays_is():
    from genai import sample_gate
    from backend.app.trial.old_sample_text import OLD_TEXTS
    from backend.app.trial.sample_data import TREND_SUMMARY

    assert all(not sample_gate.matches_catalogue(text) for text in OLD_TEXTS[EV])
    assert sample_gate.matches_catalogue(TREND_SUMMARY)


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    _, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield tenant_id, approval["tenant_key"]
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:w1e-cleanup")


def _set_text(tenant_id, text: str, *, chunk: bool = True) -> tuple[uuid.UUID, uuid.UUID | None]:
    """EV-003 as an older trial holds it: ``text`` in the record and in its single chunk (or no chunk)."""
    from evidence.extractors.chunker import EvidenceChunker

    from backend.app.db.models.evidence_intelligence import EvidenceChunk
    from backend.app.db.models.foundation import Evidence
    from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        evidence = db.query(Evidence).filter_by(tenant_id=tenant_id, evidence_identifier=EV).one()
        evidence.content = text
        chunks = db.query(EvidenceChunk).filter_by(tenant_id=tenant_id, evidence_id=evidence.id)
        if chunk:
            row = chunks.one()
            values = EvidenceChunker()._chunk_values(tenant_id, evidence.id, text)[0]
            for key in ("text_content", "source_anchor", "token_count", "checksum"):
                setattr(row, key, values[key])
            chunk_id = row.id
        else:
            db.query(EvidenceChunkEmbedding).filter_by(tenant_id=tenant_id, evidence_id=evidence.id).delete()
            chunks.delete(synchronize_session=False)
            chunk_id = None
        db.commit()
        return evidence.id, chunk_id


def _gate_problem(tenant_id, evidence_id):
    from genai import sample_gate

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return sample_gate._record_problem(db, tenant_id, {"table": "evidence", "id": str(evidence_id)})


def _state(tenant_id, evidence_id):
    from backend.app.db.models.evidence_intelligence import EvidenceChunk
    from backend.app.db.models.foundation import Evidence
    from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        content = db.get(Evidence, evidence_id).content
        chunks = db.query(EvidenceChunk).filter_by(tenant_id=tenant_id, evidence_id=evidence_id).all()
        embedded = {
            (row.chunk_id, row.chunk_checksum)
            for row in db.query(EvidenceChunkEmbedding).filter_by(
                tenant_id=tenant_id, evidence_id=evidence_id, indexing_status="INDEXED"
            )
        }
        return content, [(chunk.id, chunk.text_content, chunk.checksum) for chunk in chunks], embedded


@pytest.mark.db
@pytest.mark.parametrize("which", [0, 1])
def test_an_old_trial_is_upgraded_and_then_passes_the_sample_gate(trial, which):
    from backend.app.trial.old_sample_text import OLD_TEXTS
    from backend.app.trial.sample_data import TREND_SUMMARY

    tenant_id, key = trial
    script = _script()
    evidence_id, chunk_id = _set_text(tenant_id, OLD_TEXTS[EV][which])
    assert "was edited" in _gate_problem(tenant_id, evidence_id)

    with SessionLocal() as db:
        planned = {item["tenant"]: item for item in script.refresh(db, apply=False)}[key]
    assert any("SAMPLE-EV-003" in item for item in planned["sample"])
    assert any("SAMPLE-EV-003" in line for line in script.count_lines([planned]))
    assert _state(tenant_id, evidence_id)[0] == OLD_TEXTS[EV][which]  # the dry run changed nothing

    with SessionLocal() as db:
        script.refresh(db, apply=True)
    content, chunks, embedded = _state(tenant_id, evidence_id)
    assert content == TREND_SUMMARY
    assert [(cid, text) for cid, text, _ in chunks] == [(chunk_id, TREND_SUMMARY)]  # same chunk, new text
    assert (chunk_id, chunks[0][2]) in embedded  # re-embedded on the new checksum
    assert _gate_problem(tenant_id, evidence_id) is None

    with SessionLocal() as db:
        assert {item["tenant"]: item["result"] for item in script.refresh(db, apply=False)}[key] == (
            "already has the story"
        )


@pytest.mark.db
def test_a_record_without_a_chunk_gets_one(trial):
    from backend.app.trial import old_sample_text
    from backend.app.trial.sample_data import TREND_SUMMARY

    tenant_id, _ = trial
    evidence_id, _ = _set_text(tenant_id, old_sample_text.OLD_TEXTS[EV][0], chunk=False)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert old_sample_text.refresh(db, tenant_id, apply=True) == 1
        db.commit()
    content, chunks, _ = _state(tenant_id, evidence_id)
    assert content == TREND_SUMMARY and [text for _, text, _ in chunks] == [TREND_SUMMARY]
    assert _gate_problem(tenant_id, evidence_id) is None


@pytest.mark.db
def test_a_text_a_person_edited_is_left_alone(trial):
    from backend.app.trial import old_sample_text

    tenant_id, _ = trial
    edited = "Pressure-alarm complaints averaged 0.8 per month on Rev A and 5.6 per month after Rev B, see ticket 4471."
    evidence_id, chunk_id = _set_text(tenant_id, edited)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert old_sample_text.refresh(db, tenant_id, apply=True) == 0
        db.commit()
    content, chunks, _ = _state(tenant_id, evidence_id)
    assert content == edited and [(cid, text) for cid, text, _ in chunks] == [(chunk_id, edited)]
    assert "was edited" in _gate_problem(tenant_id, evidence_id)
