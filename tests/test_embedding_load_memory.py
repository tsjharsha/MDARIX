"""Review O2: a local embedding model that cannot be loaded is not tried again on every search for five minutes, the
same question is embedded once, and readiness says whether the pinned model is there."""

import pytest

from backend.app import readiness
from retrieval import embedding_provider as ep

pytestmark = pytest.mark.unit


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(ep.LocalModelEmbeddingProvider, "_model", None)
    monkeypatch.setattr(ep.LocalModelEmbeddingProvider, "_failed", None)
    return monkeypatch


def test_a_failed_load_is_remembered_for_five_minutes(fresh):
    tries = []

    def missing():
        tries.append(1)
        raise ep.EmbeddingUnavailable("not in the cache")

    fresh.setattr(ep.LocalModelEmbeddingProvider, "_load_model", classmethod(lambda cls: missing()))
    clock = [1000.0]
    fresh.setattr(ep.time, "monotonic", lambda: clock[0])
    provider = ep.LocalModelEmbeddingProvider()
    for _ in range(3):
        with pytest.raises(ep.EmbeddingUnavailable, match="not in the cache"):
            provider.embed_query("alarms")
    assert len(tries) == 1
    clock[0] += ep.LOAD_RETRY_SECONDS + 1
    with pytest.raises(ep.EmbeddingUnavailable):
        provider.embed_query("alarms")
    assert len(tries) == 2


def test_the_same_question_is_embedded_once(fresh):
    asked = []

    class Model:
        def query_embed(self, texts):
            asked.extend(texts)
            yield [0.5, 0.25]

    fresh.setattr(ep.LocalModelEmbeddingProvider, "_model", Model())
    provider = ep.LocalModelEmbeddingProvider()
    assert provider.embed_query("why do pumps alarm?") == provider.embed_query("why do pumps alarm?") == [0.5, 0.25]
    assert asked == ["why do pumps alarm?"]


def test_readiness_reports_a_missing_embedding_model(fresh, tmp_path):
    fresh.setenv("MDARIX_EMBEDDING_PROVIDER", "local")
    fresh.setenv("MDARIX_EMBEDDING_CACHE_DIR", str(tmp_path))
    fresh.setattr(readiness, "_embedding_checked", False)
    check = readiness._check("embedding_model", readiness._embedding_model)
    assert check["ok"] is False and check["reason"] == "MODEL_MISSING"
    fresh.setenv("MDARIX_EMBEDDING_PROVIDER", "deterministic")
    assert readiness._check("embedding_model", readiness._embedding_model)["ok"] is True
