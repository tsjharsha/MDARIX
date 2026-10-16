import json
import pytest
import genai.provider as provider_module
from genai.provider import GenAIProvider, GenAIUnavailable, redact_context


def test_genai_defaults_fail_safe_without_provider(monkeypatch):
    monkeypatch.delenv("MDARIX_GENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MDARIX_GENAI_API_KEY", raising=False)
    result = GenAIProvider().complete("Explain this", {"token": "secret", "status": "open"})
    assert result.provider == "controlled"
    assert result.output["human_review_required"] is True
    assert result.output["causality_state"] == "NOT_ESTABLISHED"


def test_context_redaction_and_input_limit():
    assert redact_context({"password": "x", "status": "open"}) == {"password": "[REDACTED]", "status": "open"}
    with pytest.raises(GenAIUnavailable, match="TOKEN_LIMIT"):
        GenAIProvider(max_input_tokens=1).complete("a very long prompt", {})


def test_provider_outage_is_bounded(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "test")
    with pytest.raises(GenAIUnavailable, match="PROVIDER_UNAVAILABLE"):
        GenAIProvider(timeout_seconds=1, max_retries=0).complete("hello", {})


def test_groq_mode_uses_chat_completions_contract(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "Evidence requires human review."}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 7},
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "test-key")
    monkeypatch.setenv("MDARIX_GENAI_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("MDARIX_GENAI_TIMEOUT_SECONDS", "20")
    monkeypatch.setattr(provider_module.request, "urlopen", fake_urlopen)

    result = provider_module.GenAIProvider(max_retries=0).complete("Summarize the evidence", {"status": "open"})

    assert captured["url"] == provider_module.GROQ_BASE_URL
    assert captured["body"]["messages"][0]["role"] == "user"
    assert captured["body"]["temperature"] == 0
    assert captured["timeout"] == 20
    assert result.provider == "groq"
    assert result.output["answer"] == "Evidence requires human review."
    assert result.human_review_required is True


def test_groq_structured_request_uses_strict_schema_and_reasoning_budget(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": '{"summary":"ready"}'}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 7},
                }
            ).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "test-key")
    monkeypatch.setenv("MDARIX_GENAI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(provider_module.request, "urlopen", fake_urlopen)
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    provider_module.GenAIProvider(max_retries=0).complete(
        "Return an analysis", {}, json_output=True, response_schema=schema, max_output_tokens=2500
    )

    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True
    assert captured["body"]["response_format"]["json_schema"]["schema"] == schema
    assert captured["body"]["reasoning_effort"] == "low"
    assert captured["body"]["reasoning_format"] == "hidden"
    assert captured["body"]["max_completion_tokens"] == 2500


def test_invalid_structured_response_is_retried_before_fallback(monkeypatch):
    calls = 0

    class Response:
        def __init__(self, content):
            self.content = content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        return Response("not-json" if calls == 1 else '{"summary":"repaired"}')

    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "test-key")
    monkeypatch.setenv("MDARIX_GENAI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setattr(provider_module.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(provider_module.time, "sleep", lambda seconds: None)

    result = provider_module.GenAIProvider(max_retries=1).complete("Return JSON", {}, json_output=True)

    assert calls == 2
    assert json.loads(result.output["answer"]) == {"summary": "repaired"}


def test_empty_numeric_settings_mean_the_defaults(monkeypatch):
    """The production template leaves MDARIX_GENAI_COST_PER_1K_TOKENS empty: the API must start, not crash on it."""
    for name in (
        "MDARIX_GENAI_TIMEOUT_SECONDS",
        "MDARIX_GENAI_MAX_RETRIES",
        "MDARIX_GENAI_MAX_INPUT_TOKENS",
        "MDARIX_GENAI_MAX_OUTPUT_TOKENS",
        "MDARIX_GENAI_COST_PER_1K_TOKENS",
    ):
        monkeypatch.setenv(name, "")
    provider = GenAIProvider(provider_name="controlled", fallbacks=[])
    assert (provider.timeout, provider.retries, provider.max_input, provider.max_output, provider.cost_per_1k) == (
        20,
        2,
        4000,
        1000,
        0.0,
    )


def test_vertex_builds_its_address_and_signs_in_as_the_vm(monkeypatch):
    captured = []

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self.body).encode()

    def fake_urlopen(request, timeout):
        captured.append(request)
        if request.full_url == provider_module.VERTEX_TOKEN_URL:
            return Response({"access_token": "vm-token", "expires_in": 3599, "token_type": "Bearer"})
        return Response({"choices": [{"message": {"content": "From the records."}}], "usage": {}})

    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    monkeypatch.setenv("MDARIX_GENAI_PROJECT", "mdarix-test")
    for name in ("MDARIX_GENAI_API_KEY", "MDARIX_GENAI_BASE_URL", "MDARIX_GENAI_LOCATION", "MDARIX_GENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provider_module, "_VERTEX_TOKEN", {"value": None, "expires": 0.0})
    monkeypatch.setattr(provider_module.request, "urlopen", fake_urlopen)

    provider = GenAIProvider(max_retries=0)
    assert provider.configured
    assert provider.model == "google/gemini-2.5-flash"
    assert provider.base_url == (
        "https://asia-south1-aiplatform.googleapis.com/v1/projects/mdarix-test"
        "/locations/asia-south1/endpoints/openapi/chat/completions"
    )
    for _ in range(2):
        result = provider.complete("Summarize the evidence", {"status": "open"})
        assert result.provider == "vertex"
        assert result.output["answer"] == "From the records."
    token_calls = [r for r in captured if r.full_url == provider_module.VERTEX_TOKEN_URL]
    model_calls = [r for r in captured if r.full_url == provider.base_url]
    # One token for both requests (it is reused until a minute before it expires), sent as a bearer token.
    assert len(token_calls) == 1
    assert token_calls[0].get_header("Metadata-flavor") == "Google"
    assert [r.get_header("Authorization") for r in model_calls] == ["Bearer vm-token", "Bearer vm-token"]


def test_vertex_without_a_project_is_not_configured(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    for name in ("MDARIX_GENAI_PROJECT", "MDARIX_GENAI_API_KEY", "MDARIX_GENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    provider = GenAIProvider()
    assert not provider.configured
    assert provider.complete("hello", {}).output["status"] == "PROVIDER_NOT_CONFIGURED"
    assert provider_module.vertex_url("p1", "europe-west4").startswith(
        "https://europe-west4-aiplatform.googleapis.com/"
    )
