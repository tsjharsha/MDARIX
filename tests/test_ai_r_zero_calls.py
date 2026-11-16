"""Proof of off (AI-R step 7): with any one switch off, no feature sends anything to a model and no call record is
written. A network guard fails the test on any connection to a host other than this machine, and every request to
a model address is recorded; only the "all on" case may make one (to a fake provider).

Levels: platform (``MDARIX_GENAI_PROVIDER=controlled``, even with fallbacks configured), platform feature list
(``MDARIX_AI_FEATURES``), organization switch, organization feature switch, monthly budget. The free-trial levels
(trial chain empty, non-sample record, person INACTIVE) are in ``tests/test_ai_trial_gate.py``; the production
qualification level comes with part C.
"""

from __future__ import annotations

import socket

import pytest

from backend.app.db.models.ai_records import AiCall
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from genai import governance
from genai import provider as provider_module
from genai.features import FEATURES
from genai.provider import GenAIProvider, GenAIUnavailable
from tests.fake_ai_gateway import Reply, answer, install

pytestmark = pytest.mark.db

OFFERED = [key for key, item in FEATURES.items() if item.offered]
LEVELS = ("platform", "feature_list", "organization", "organization_feature", "budget")


@pytest.fixture
def guard(monkeypatch):
    """Any connection off this machine fails the test; model requests are recorded and answered by a fake."""
    real_connect = socket.socket.connect

    def connect(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            pytest.fail(f"network call to {host} with AI off")
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)

    return install(monkeypatch, default=lambda: Reply(answer("ok")))["sent"]


@pytest.fixture
def paid(monkeypatch):
    """The synthetic paid organization with every switch on; each test turns one off."""
    provider_module._COOLDOWN_UNTIL.clear()
    monkeypatch.setenv("MDARIX_GENAI_SHARED_REST", "false")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "dev-key")
    monkeypatch.setenv("MDARIX_GENAI_MAX_RETRIES", "0")
    monkeypatch.delenv("MDARIX_GENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MDARIX_GENAI_FALLBACKS", raising=False)
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    monkeypatch.setenv("MDARIX_AI_FEATURES", ",".join(OFFERED))
    with SessionLocal() as db:
        bind_system(db, "test")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        saved = (tenant.ai_processing_allowed, tenant.ai_monthly_token_budget, dict(tenant.ai_features or {}))
        tenant_id = tenant.id
    _set(tenant_id, ai_processing_allowed=True, ai_monthly_token_budget=None, ai_features=dict.fromkeys(FEATURES, True))
    yield tenant_id
    _set(tenant_id, ai_processing_allowed=saved[0], ai_monthly_token_budget=saved[1], ai_features=saved[2])


def _set(tenant_id, **values):
    with SessionLocal() as db:
        bind_system(db, "test")
        db.query(Tenant).filter(Tenant.id == tenant_id).update(values)
        db.commit()


def _calls(tenant_id) -> int:
    with SessionLocal() as db:
        bind_system(db, "test")
        return db.query(AiCall).filter(AiCall.tenant_id == tenant_id).count()


def _switch_off(level: str, tenant_id, feature: str, monkeypatch) -> None:
    if level == "platform":
        monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "controlled")
        # Fallbacks follow a configured primary only: configured here, they change nothing.
        monkeypatch.setenv("MDARIX_GENAI_FALLBACKS", "groq,cerebras")
        monkeypatch.setenv("MDARIX_GENAI_GROQ_API_KEY", "k")
        monkeypatch.setenv("MDARIX_GENAI_CEREBRAS_API_KEY", "k")
    elif level == "feature_list":
        monkeypatch.setenv("MDARIX_AI_FEATURES", ",".join(key for key in OFFERED if key != feature))
    elif level == "organization":
        _set(tenant_id, ai_processing_allowed=False)
    elif level == "organization_feature":
        _set(tenant_id, ai_features={**dict.fromkeys(FEATURES, True), feature: False})
    elif level == "budget":
        _set(tenant_id, ai_monthly_token_budget=0)


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("feature", list(FEATURES))
def test_any_switch_off_means_zero_model_calls(guard, paid, monkeypatch, feature, level):
    _switch_off(level, paid, feature, monkeypatch)
    before = _calls(paid)
    with governance.tenant_scope(paid):
        try:
            result = GenAIProvider().complete("Summarize the record.", {"status": "open"}, feature=feature)
        except GenAIUnavailable as refused:
            assert refused.user_message, "a refusal says why, so the rules answer can show it"
        else:
            assert level == "platform" and result.output["status"] == "PROVIDER_NOT_CONFIGURED"
    assert guard == []
    assert _calls(paid) == before


@pytest.mark.parametrize("feature", OFFERED)
def test_with_every_switch_on_one_call_is_made_and_recorded(guard, paid, feature):
    before = _calls(paid)
    with governance.tenant_scope(paid):
        result = GenAIProvider().complete("Summarize the record.", {"status": "open"}, feature=feature)
    assert result.output["answer"] == "ok" and result.call_id
    assert guard == [provider_module.GROQ_BASE_URL]
    assert _calls(paid) == before + 1


def test_the_local_evidence_search_model_is_not_an_ai_call(guard):
    """AI-D17: the evidence search embeds text with the model shipped in the image; it sends nothing out."""
    from retrieval.embedding_provider import DeterministicEmbeddingProvider

    vector = DeterministicEmbeddingProvider().embed_query("pressure alarm")
    assert len(vector) > 0 and guard == []
