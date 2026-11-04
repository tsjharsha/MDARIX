"""The local language-model embedding: real semantic search over evidence, model-separated, and an honest fallback."""

import math

import pytest

from backend.app.db.models.foundation import Tenant
from backend.app.db.models.retrieval_intelligence import (
    EMBEDDING_MODEL,
    LOCAL_EMBEDDING_DIMENSION,
    LOCAL_EMBEDDING_MODEL,
    EvidenceChunkEmbedding,
)
from backend.app.db.session import SessionLocal
from retrieval.embedding_provider import (
    DeterministicEmbeddingProvider,
    EmbeddingUnavailable,
    LocalModelEmbeddingProvider,
    active_embedding_provider,
)
from retrieval.indexing import index_tenant_evidence
from tests.chunk_cleanup import restore_chunks
from retrieval.schemas import RetrievalRequest
from retrieval.service import TrustedRetrievalService

GOLDEN = "ACME_CARE_SYNTHETIC"


def _cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


@pytest.mark.model
def test_the_local_model_understands_meaning_not_just_words():
    provider = LocalModelEmbeddingProvider()
    query = provider.embed_query("supplier changed their manufacturing process")
    related = provider.embed_text("NovaCap notified a process change at the capacitor vendor.")
    unrelated = provider.embed_text("The cafeteria menu changes every Tuesday.")
    assert len(query) == LOCAL_EMBEDDING_DIMENSION
    assert _cosine(query, related) > _cosine(query, unrelated) + 0.1


@pytest.mark.unit
def test_provider_choice_defaults_to_the_language_model(monkeypatch):
    monkeypatch.delenv("MDARIX_EMBEDDING_PROVIDER", raising=False)
    assert isinstance(active_embedding_provider(), LocalModelEmbeddingProvider)
    monkeypatch.setenv("MDARIX_EMBEDDING_PROVIDER", "deterministic")
    assert isinstance(active_embedding_provider(), DeterministicEmbeddingProvider)


@pytest.fixture(scope="module")
def golden():
    db = SessionLocal()
    tenant = None
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN).one()
        with restore_chunks(db, tenant.id):
            index_tenant_evidence(db, tenant.id, provider=DeterministicEmbeddingProvider())
            first = index_tenant_evidence(db, tenant.id, provider=LocalModelEmbeddingProvider())
            again = index_tenant_evidence(db, tenant.id, provider=LocalModelEmbeddingProvider())
            yield {"db": db, "tenant": tenant, "first": first, "again": again}
    finally:
        # Leave no language-model vectors behind: other suites read this tenant's embedding rows.
        db.rollback()
        if tenant is not None:
            db.query(EvidenceChunkEmbedding).filter_by(
                tenant_id=tenant.id, embedding_model=LOCAL_EMBEDDING_MODEL
            ).delete()
            db.commit()
        db.close()


@pytest.mark.model
def test_all_golden_evidence_is_chunked_and_embedded_once(golden):
    db, tenant = golden["db"], golden["tenant"]
    assert golden["first"]["chunking"]["unreadable"] == []
    assert golden["again"]["indexing"]["indexed"] == 0 and golden["again"]["chunking"]["chunks_created"] == 0
    local = db.query(EvidenceChunkEmbedding).filter_by(tenant_id=tenant.id, embedding_model=LOCAL_EMBEDDING_MODEL)
    assert local.filter_by(indexing_status="INDEXED").count() >= 40
    assert {row.embedding_dimension for row in local} == {LOCAL_EMBEDDING_DIMENSION}
    # Rows of the word-hash model stay alongside, untouched.
    assert db.query(EvidenceChunkEmbedding).filter_by(tenant_id=tenant.id, embedding_model=EMBEDDING_MODEL).count()


def _search(golden, provider, query):
    request = RetrievalRequest(tenant_id=golden["tenant"].id, query_text=query, retrieval_mode="semantic", top_k=5)
    return TrustedRetrievalService(provider).retrieve(golden["db"], request)


@pytest.mark.model
def test_semantic_search_finds_the_evidence_by_meaning(golden):
    # No shared keywords with "Supplier process change became effective before Component Rev B."
    response = _search(golden, LocalModelEmbeddingProvider(), "vendor altered how they build the part")
    assert response.results_count >= 1
    assert "EV-VS001-001" in [item.evidence_identifier for item in response.results[:5]]
    assert response.results[0].provenance["embedding_model"] == LOCAL_EMBEDDING_MODEL


@pytest.mark.model
def test_each_model_searches_only_its_own_vectors(golden):
    hashed = _search(golden, DeterministicEmbeddingProvider(), "supplier process change")
    assert hashed.results_count >= 1
    assert all(item.provenance["embedding_dimension"] == 32 for item in hashed.results)


class _Unavailable(LocalModelEmbeddingProvider):
    def embed_query(self, text):
        raise EmbeddingUnavailable("not downloaded")


@pytest.mark.model
def test_an_unavailable_model_falls_back_to_structured_search_and_says_so(golden):
    request = RetrievalRequest(
        tenant_id=golden["tenant"].id, query_text="supplier process change", retrieval_mode="hybrid", top_k=5
    )
    response = TrustedRetrievalService(_Unavailable()).retrieve(golden["db"], request)
    assert any("Semantic search is unavailable" in item for item in response.limitations)
    assert all(item.retrieval_method == "structured" for item in response.results)


# ------------------------------------------------- DEV-02 (0.10.86): no download; a missing model says what to do


@pytest.fixture
def no_model(tmp_path, monkeypatch):
    """The provider pointed at an empty cache, with nothing loaded yet."""
    monkeypatch.setenv("MDARIX_EMBEDDING_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(LocalModelEmbeddingProvider, "_model", None)
    return tmp_path


@pytest.mark.unit
def test_a_missing_model_is_unavailable_with_what_to_do_and_is_never_downloaded(no_model, monkeypatch):
    import fastembed

    from retrieval.embedding_provider import local_model_problem

    asked = []

    class Loader:
        def __init__(self, *args, **options):
            asked.append(options)
            raise ValueError("Could not find the model in the cache")

    monkeypatch.setattr(fastembed, "TextEmbedding", Loader)
    with pytest.raises(EmbeddingUnavailable) as raised:
        LocalModelEmbeddingProvider().embed_query("supplier process change")
    message = str(raised.value)
    assert str(no_model) in message and "MDARIX_EMBEDDING_CACHE_DIR" in message
    assert "scripts/prepare_embedding_cache.py" in message and "structured matches only" in message
    # Before 0.10.86 a second attempt downloaded the model (local_files_only off) outside staging and production.
    assert asked and all(options.get("local_files_only") is True for options in asked)
    assert "not in" in local_model_problem(str(no_model))


@pytest.mark.db
def test_search_without_the_model_says_semantic_search_is_unavailable(no_model):
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN).one()
        request = RetrievalRequest(
            tenant_id=tenant.id, query_text="supplier process change", retrieval_mode="hybrid", top_k=5
        )
        response = TrustedRetrievalService(LocalModelEmbeddingProvider()).retrieve(db, request)
    finally:
        db.close()
    assert any("Semantic search is unavailable" in item for item in response.limitations)
    assert all(item.retrieval_method == "structured" for item in response.results)
