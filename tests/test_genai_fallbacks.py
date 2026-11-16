"""Free AI providers as fallbacks: when the primary is limited or down, the next configured provider answers."""

import io
import json
from urllib import error as urlerror

import pytest

import genai.provider as provider_module
from genai.provider import GenAIProvider, GenAIUnavailable


@pytest.fixture(autouse=True)
def _ai_features_on_platform(monkeypatch):
    # These tests exercise the provider itself: every offered feature is on the platform list (genai/features.py).
    monkeypatch.setenv(
        "MDARIX_AI_FEATURES", "ask,summaries,case_analysis,drafting,evidence_extraction,code_suggestions"
    )


class _Response:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(
            {"choices": [{"message": {"content": self.text}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
        ).encode()


def _rate_limited(url):
    return urlerror.HTTPError(url, 429, "Too Many Requests", {"retry-after": "0"}, io.BytesIO(b"{}"))


@pytest.fixture(autouse=True)
def chain(monkeypatch):
    provider_module._COOLDOWN_UNTIL.clear()
    for name, value in {
        "MDARIX_GENAI_PROVIDER": "groq",
        "MDARIX_GENAI_API_KEY": "groq-key",
        "MDARIX_GENAI_MODEL": "openai/gpt-oss-120b",
        "MDARIX_GENAI_FALLBACKS": "cerebras, gemini",
        "MDARIX_GENAI_CEREBRAS_API_KEY": "cerebras-key",
        "MDARIX_GENAI_GEMINI_API_KEY": "gemini-key",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MDARIX_GENAI_BASE_URL", raising=False)
    monkeypatch.setattr(provider_module.time, "sleep", lambda seconds: None)
    yield
    provider_module._COOLDOWN_UNTIL.clear()


def _route(monkeypatch, behaviour: dict):
    """behaviour: provider host fragment -> "ok" | "limited" | "down"; records the calls in order."""
    calls = []

    def fake_urlopen(request, timeout):
        host = next(name for name in behaviour if name in request.full_url)
        calls.append((host, request.get_header("Authorization")))
        if behaviour[host] == "limited":
            raise _rate_limited(request.full_url)
        if behaviour[host] == "down":
            raise urlerror.URLError("connection refused")
        return _Response(f"answer from {host}")

    monkeypatch.setattr(provider_module.request, "urlopen", fake_urlopen)
    return calls


def test_a_rate_limited_primary_hands_over_to_the_next_free_provider_at_once(monkeypatch):
    calls = _route(monkeypatch, {"groq": "limited", "cerebras": "ok", "generativelanguage": "ok"})
    result = GenAIProvider().complete("Summarize the evidence", {"status": "open"}, feature="ask")
    assert result.provider == "cerebras" and result.output["answer"] == "answer from cerebras"
    # Groq was asked once (no waiting on a limit), then Cerebras with its own key.
    assert calls == [("groq", "Bearer groq-key"), ("cerebras", "Bearer cerebras-key")]
    # The limited provider rests: the next request goes straight to the fallback.
    calls.clear()
    assert GenAIProvider().complete("Again", {}, feature="ask").provider == "cerebras"
    assert [host for host, _ in calls] == ["cerebras"]


def test_a_structured_request_retries_rate_limited_primary_before_provider_fallback(monkeypatch):
    attempts = 0
    calls = []

    def fake_urlopen(request, timeout):
        nonlocal attempts
        host = "groq" if "groq" in request.full_url else "cerebras"
        calls.append(host)
        if host == "groq":
            attempts += 1
            if attempts == 1:
                raise _rate_limited(request.full_url)
            return _Response('{"summary":"primary recovered"}')
        return _Response('{"summary":"fallback"}')

    monkeypatch.setattr(provider_module.request, "urlopen", fake_urlopen)
    result = GenAIProvider(max_retries=1).complete("Analyse", {}, json_output=True, feature="ask")

    assert result.provider == "groq"
    assert calls == ["groq", "groq"]


def test_a_provider_that_is_down_is_skipped_too(monkeypatch):
    calls = _route(monkeypatch, {"groq": "down", "cerebras": "down", "generativelanguage": "ok"})
    result = GenAIProvider().complete("Summarize", {}, feature="ask")
    assert result.provider == "gemini" and result.output["human_review_required"] is True
    assert [host for host, _ in calls][-1] == "generativelanguage"


def test_when_every_provider_fails_the_caller_falls_back_to_rules(monkeypatch):
    _route(monkeypatch, {"groq": "limited", "cerebras": "limited", "generativelanguage": "down"})
    with pytest.raises(GenAIUnavailable):
        GenAIProvider().complete("Summarize", {}, feature="ask")


def test_fallbacks_without_a_key_are_not_tried(monkeypatch):
    monkeypatch.delenv("MDARIX_GENAI_GEMINI_API_KEY")
    calls = _route(monkeypatch, {"groq": "limited", "cerebras": "limited", "generativelanguage": "ok"})
    with pytest.raises(GenAIUnavailable):
        GenAIProvider().complete("Summarize", {}, feature="ask")
    assert "generativelanguage" not in [host for host, _ in calls]


def test_without_fallbacks_the_primary_keeps_its_retries(monkeypatch):
    monkeypatch.delenv("MDARIX_GENAI_FALLBACKS")
    calls = _route(monkeypatch, {"groq": "limited"})
    with pytest.raises(GenAIUnavailable):
        GenAIProvider(max_retries=2).complete("Summarize", {}, feature="ask")
    assert len(calls) == 3 and not provider_module._COOLDOWN_UNTIL


def test_without_a_primary_no_fallback_is_called(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "controlled")
    monkeypatch.delenv("MDARIX_GENAI_API_KEY")
    calls = _route(monkeypatch, {"cerebras": "ok", "generativelanguage": "ok"})
    result = GenAIProvider().complete("Summarize", {}, feature="ask")
    assert result.provider == "controlled" and calls == []


def test_health_lists_the_chain_without_keys():
    health = GenAIProvider().health()
    assert health["provider"] == "groq"
    assert [(item["provider"], item["configured"]) for item in health["fallbacks"]] == [
        ("cerebras", True),
        ("gemini", True),
    ]
    assert "key" not in json.dumps(health).lower().replace("api_key", "")
    assert health["skipped_fallbacks"] == {}


def test_a_retired_or_misspelt_fallback_is_skipped_and_shown(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_FALLBACKS", "github, gemini, geminy")
    monkeypatch.setenv("MDARIX_GENAI_GITHUB_API_KEY", "github-key")
    calls = _route(monkeypatch, {"groq": "limited", "generativelanguage": "ok", "github": "ok"})
    provider = GenAIProvider()
    assert [item.provider_name for item in provider.fallbacks] == ["gemini"]
    assert provider.complete("Summarize", {}, feature="ask").provider == "gemini"
    assert "github" not in [host for host, _ in calls]
    skipped = provider.health()["skipped_fallbacks"]
    assert set(skipped) == {"github", "geminy"} and "retired" in skipped["github"]


def test_a_local_ollama_fallback_keeps_time_to_load_its_model(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_FALLBACKS", "gemini, ollama")
    monkeypatch.setenv("MDARIX_GENAI_TIMEOUT_SECONDS", "30")
    gemini, ollama = GenAIProvider().fallbacks
    assert gemini.timeout == 30 and ollama.timeout == 120
    monkeypatch.setenv("MDARIX_GENAI_OLLAMA_TIMEOUT_SECONDS", "45")
    assert GenAIProvider().fallbacks[1].timeout == 45
