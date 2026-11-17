"""AI-R and the free-trial chain at the choke point (``GenAIProvider.complete``), on fake providers only.

No test here reaches a real AI service: every request goes to a fake ``urlopen`` that records it, and the
organization check is replaced by a fixed answer (trial or paid). The database-backed checks (organization
switches, the sample-data gate, the per-person flag) are in ``tests/test_ai_trial_gate.py``.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib import error as urlerror

import pytest

from genai import call_record, features, governance, policy, sample_gate, vetted
from genai import provider as provider_module
from genai.provider import GenAIProvider, GenAIUnavailable

pytestmark = pytest.mark.unit

from tests.fake_ai_gateway import FREELLMAPI, GROQ, OMNI_CEREBRAS, OMNIROUTE, install
from tests.fake_ai_gateway import Reply as _Reply
from tests.fake_ai_gateway import answer as _answer
from tests.fake_ai_gateway import http_error as _http_error
from tests.fake_ai_gateway import register as _register


@pytest.fixture
def chain(monkeypatch):
    """The trial chain FreeLLMAPI -> OmniRoute -> Groq, all configured with test keys; every request recorded."""
    provider_module._COOLDOWN_UNTIL.clear()
    provider_module._DOWN_ALERTED_AT.clear()
    # The operator alert runs in its own thread in the app; here it runs inline so a test can see it.
    monkeypatch.setattr(provider_module, "_alert_beside_the_request", provider_module._send_provider_alert)
    monkeypatch.setenv("MDARIX_GENAI_SHARED_REST", "false")
    monkeypatch.setenv("MDARIX_AI_FEATURES", "ask,summaries,case_analysis")
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi,omniroute,groq")
    for name in ("FREELLMAPI", "OMNIROUTE", "GROQ"):
        monkeypatch.setenv(f"MDARIX_GENAI_{name}_API_KEY", "test-key")
        monkeypatch.delenv(f"MDARIX_GENAI_{name}_BASE_URL", raising=False)
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "controlled")
    monkeypatch.delenv("MDARIX_GENAI_FALLBACKS", raising=False)
    monkeypatch.setattr(vetted, "load", lambda path=None: _register())
    monkeypatch.setattr(provider_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(governance, "record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(governance, "count_refusal", lambda *args, **kwargs: None)
    written = []
    monkeypatch.setattr(
        call_record, "write", lambda access, call, result, **kwargs: written.append((result, kwargs)) or "call-1"
    )
    trial = {"value": True}
    monkeypatch.setattr(
        governance,
        "check_allowed",
        lambda tokens, feature=None, trial_chain_on=False: governance.Access("t-1", trial["value"], "u-1"),
    )
    monkeypatch.setattr(sample_gate, "check", lambda *args, **kwargs: None)
    state = install(monkeypatch)
    yield {"state": state, "written": written, "trial": trial}
    provider_module._COOLDOWN_UNTIL.clear()


def _ask(provider: GenAIProvider | None = None, **kwargs):
    return (provider or GenAIProvider()).complete(
        "Summarize the sample complaints.", {}, feature=kwargs.pop("feature", "summaries"), **kwargs
    )


# --------------------------------------------------------------------------------------------- features (C3, C4)


def test_a_high_risk_feature_cannot_be_declared():
    high = features.Feature("decide", "Decide", "Decide reportability.", "HIGH", "Decide.", "decide-1")
    with pytest.raises(ValueError, match="AI may not decide"):
        features._validate([*features.FEATURES.values(), high])


def test_every_declared_feature_is_low_or_medium():
    assert {item.risk for item in features.FEATURES.values()} <= {"LOW", "MEDIUM"}


@pytest.mark.parametrize("feature", [None, "", "root_cause", "ASK "])
def test_a_missing_or_unknown_feature_is_refused_before_anything_else(chain, feature):
    if feature == "ASK ":
        # Spelling and spacing are normalized: this is the known feature "ask".
        assert features.known(feature).key == "ask"
        return
    with pytest.raises(GenAIUnavailable) as refused:
        GenAIProvider().complete("Hello", {}, feature=feature)
    assert refused.value.code == "GENAI_FEATURE_UNKNOWN"
    assert chain["state"]["sent"] == []


def test_an_empty_platform_feature_list_refuses_every_feature(chain, monkeypatch):
    monkeypatch.setenv("MDARIX_AI_FEATURES", "")
    for key in features.FEATURES:
        with pytest.raises(GenAIUnavailable) as refused:
            _ask(feature=key)
        assert refused.value.code in {"GENAI_FEATURE_OFF_ON_PLATFORM", "GENAI_FEATURE_NOT_OFFERED"}
    assert chain["state"]["sent"] == []


def test_only_the_listed_feature_passes_the_platform_level(chain, monkeypatch):
    monkeypatch.setenv("MDARIX_AI_FEATURES", "summaries")
    chain["state"]["replies"][FREELLMAPI] = _Reply(_answer(), {"x-routed-via": "cerebras/m-1"})
    assert _ask(feature="summaries").output["answer"] == "From the sample records."
    with pytest.raises(GenAIUnavailable, match="GENAI_FEATURE_OFF_ON_PLATFORM"):
        _ask(feature="ask")


def test_the_decision_advisory_is_not_offered_even_when_listed(chain, monkeypatch):
    monkeypatch.setenv("MDARIX_AI_FEATURES", "decision_advisory")
    with pytest.raises(GenAIUnavailable) as refused:
        _ask(feature="decision_advisory")
    assert refused.value.code == "GENAI_FEATURE_NOT_OFFERED"
    assert chain["state"]["sent"] == []


def test_controlled_mode_without_a_trial_chain_reads_and_sends_nothing(chain, monkeypatch):
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "")
    monkeypatch.setattr(governance, "check_allowed", lambda *a, **k: pytest.fail("no organization check when off"))
    assert _ask().output["status"] == "PROVIDER_NOT_CONFIGURED"
    assert chain["state"]["sent"] == []


# ---------------------------------------------------------------------------------- chains and failover (N1, N3)


def test_failover_order_is_freellmapi_then_omniroute_then_groq(chain):
    state = chain["state"]
    state["replies"][FREELLMAPI] = _http_error(FREELLMAPI, 503)
    state["replies"][OMNIROUTE] = _http_error(OMNIROUTE, 429)
    state["replies"][GROQ] = _Reply(_answer(model="llama-x-70b"))
    result = _ask()
    assert state["sent"] == [FREELLMAPI, OMNIROUTE, GROQ]
    assert result.provider == "groq" and result.upstream_provider == "groq" and result.upstream_model == "llama-x-70b"
    assert result.organisation_type == "TRIAL" and result.chain == "trial" and result.chain_position == 3
    assert [item["outcome"] for item in result.attempts] == ["UNAVAILABLE", "RATE_LIMITED"]
    # The rate-limited provider rests for 15 minutes, the unavailable one for a minute.
    rest = provider_module._COOLDOWN_UNTIL
    assert rest["omniroute"] - rest["freellmapi"] > 800


def test_the_first_provider_answers_and_names_its_actual_upstream(chain):
    chain["state"]["replies"][FREELLMAPI] = _Reply(_answer(), {"x-routed-via": "cerebras/gpt-oss-120b"})
    result = _ask()
    assert chain["state"]["sent"] == [FREELLMAPI]
    assert (result.provider, result.upstream_provider, result.upstream_model) == (
        "freellmapi",
        "cerebras",
        "gpt-oss-120b",
    )
    assert result.region == "US" and result.call_id == "call-1"
    assert chain["written"][0][1]["outcome"] == "ANSWERED"


def test_a_request_the_provider_rejects_as_wrong_stops_the_chain(chain):
    chain["state"]["replies"][FREELLMAPI] = _http_error(FREELLMAPI, 400)
    with pytest.raises(GenAIUnavailable):
        _ask()
    assert chain["state"]["sent"] == [FREELLMAPI]
    assert chain["written"][0][1]["outcome"] == "FAILED"


def test_a_refused_key_moves_on_rests_an_hour_and_alerts(chain, monkeypatch):
    alerts = []
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda title, body: alerts.append(title))
    chain["state"]["replies"][FREELLMAPI] = _http_error(FREELLMAPI, 401)
    chain["state"]["replies"][OMNIROUTE] = _Reply(_answer(), OMNI_CEREBRAS)
    result = _ask()
    assert result.provider == "omniroute" and result.upstream_provider == "cerebras"
    assert provider_module._COOLDOWN_UNTIL["freellmapi"] - provider_module.time.time() > 3000
    assert alerts == ["Trial AI provider problem"]


@pytest.mark.parametrize(
    "headers",
    [{"x-routed-via": "mistral/small-1"}, {"x-routed-via": "unknownai/m"}, {"x-routed-via": "cache"}, {}],
)
def test_a_reply_from_an_unvetted_or_unnamed_upstream_is_discarded(chain, monkeypatch, headers):
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda title, body: None)
    chain["state"]["replies"][FREELLMAPI] = _Reply(_answer("SECRET UNVETTED TEXT"), headers)
    chain["state"]["replies"][OMNIROUTE] = _Reply(_answer("Vetted answer."), OMNI_CEREBRAS)
    result = _ask()
    assert result.output["answer"] == "Vetted answer."
    assert result.attempts[0]["outcome"] == "UPSTREAM_NOT_VETTED"


def test_omniroute_names_its_upstream_in_headers_not_in_the_body_model(monkeypatch):
    monkeypatch.setattr(vetted, "load", lambda path=None: _register())
    # Groq's own model ids carry a slash: the body "model" must not be read as "provider/model".
    found = vetted.identify(
        "omniroute",
        headers={"X-OmniRoute-Provider": "groq", "X-OmniRoute-Model": "openai/gpt-oss-120b"},
        raw={"model": "openai/gpt-oss-120b"},
    )
    assert (found.provider, found.model) == ("groq", "openai/gpt-oss-120b")
    with pytest.raises(vetted.UpstreamNotVetted):
        vetted.identify("omniroute", headers={}, raw={"model": "cerebras/m-2"})
    with pytest.raises(vetted.UpstreamNotVetted, match="cache"):
        vetted.identify("omniroute", headers={**OMNI_CEREBRAS, "X-OmniRoute-Cache": "HIT"}, raw={})


def test_every_provider_failing_gives_the_rules_answer(chain):
    with pytest.raises(GenAIUnavailable) as refused:
        _ask()
    assert refused.value.code == "GENAI_AI_BUSY"
    assert "AI is busy" in refused.value.user_message and "try again" in refused.value.user_message
    assert chain["state"]["sent"] == [FREELLMAPI, OMNIROUTE, GROQ]


def test_resting_providers_are_skipped_and_the_next_click_answers_at_once(chain, monkeypatch):
    """Review G4: resting providers were only moved to the end, so every click waited for each of them again."""
    with pytest.raises(GenAIUnavailable):
        _ask()
    chain["state"]["sent"].clear()
    started = provider_module.time.monotonic()
    with pytest.raises(GenAIUnavailable) as refused:
        _ask()
    assert refused.value.code == "GENAI_AI_BUSY"
    assert chain["state"]["sent"] == [], "a resting provider is not tried"
    assert provider_module.time.monotonic() - started < 1.0
    # One that rested and then answers is tried again, keeping its place in the chain.
    provider_module._COOLDOWN_UNTIL.pop("omniroute")
    chain["state"]["replies"][OMNIROUTE] = _Reply(_answer(), OMNI_CEREBRAS)
    result = _ask()
    assert chain["state"]["sent"] == [OMNIROUTE] and result.chain_position == 2


def test_a_click_waits_at_most_twenty_seconds_for_the_whole_chain():
    assert provider_module.TRIAL_DEADLINE_SECONDS <= 20
    assert max(provider_module.TRIAL_TIMEOUTS.values()) <= 15 and provider_module.TRIAL_DEFAULT_TIMEOUT <= 10


def test_a_down_provider_alerts_the_operators_once_an_hour(chain, monkeypatch):
    """Review G10: a gateway that is down (UNAVAILABLE) was silent; now it alerts, at most hourly per provider."""
    alerts = []
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda title, body: alerts.append(body))
    with pytest.raises(GenAIUnavailable):
        _ask()
    assert len(alerts) == 3 and all("failed with UNAVAILABLE" in body for body in alerts)
    provider_module._COOLDOWN_UNTIL.clear()
    with pytest.raises(GenAIUnavailable):
        _ask()
    assert len(alerts) == 3, "not again within the hour"


def test_the_total_deadline_ends_the_chain(chain, monkeypatch):
    monkeypatch.setattr(provider_module, "TRIAL_DEADLINE_SECONDS", 0.0)
    with pytest.raises(GenAIUnavailable):
        _ask()
    assert chain["state"]["sent"] == []


def test_a_structured_request_moves_on_at_once_after_an_invalid_answer(chain):
    chain["state"]["replies"][FREELLMAPI] = _Reply(_answer("not json"), {"x-routed-via": "cerebras/m-1"})
    chain["state"]["replies"][OMNIROUTE] = _Reply(_answer('{"ok": true}'), OMNI_CEREBRAS)
    result = _ask(json_output=True)
    assert result.provider == "omniroute" and result.attempts[0]["outcome"] == "INVALID_OUTPUT"


def test_a_paid_organization_never_reaches_a_free_provider(chain, monkeypatch):
    chain["trial"]["value"] = False
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    monkeypatch.setenv("MDARIX_GENAI_PROJECT", "mdarix-test")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "paid-key")
    for name in ("MDARIX_GENAI_BASE_URL", "MDARIX_GENAI_LOCATION", "MDARIX_GENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    # The free providers would answer; the paid one is down.
    chain["state"]["replies"][FREELLMAPI] = _Reply(_answer(), {"x-routed-via": "cerebras/m-1"})
    chain["state"]["replies"][OMNIROUTE] = _Reply(_answer(), OMNI_CEREBRAS)
    chain["state"]["replies"][GROQ] = _Reply(_answer())
    with pytest.raises(GenAIUnavailable):
        _ask(GenAIProvider(max_retries=0))
    sent = chain["state"]["sent"]
    assert sent and all("aiplatform.googleapis.com" in url for url in sent)
    assert not {FREELLMAPI, OMNIROUTE, GROQ} & set(sent)


def test_a_trial_organization_never_reaches_the_paid_provider(chain, monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    monkeypatch.setenv("MDARIX_GENAI_PROJECT", "mdarix-test")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "paid-key")
    chain["state"]["replies"][FREELLMAPI] = _Reply(_answer(), {"x-routed-via": "cerebras/m-1"})
    result = _ask()
    assert result.provider == "freellmapi"
    assert all("googleapis" not in url for url in chain["state"]["sent"])


def test_an_empty_trial_chain_leaves_the_paid_side_unchanged(chain, monkeypatch):
    chain["trial"]["value"] = False
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "dev-key")
    chain["state"]["replies"][GROQ] = _Reply(_answer())
    result = _ask(GenAIProvider(max_retries=0))
    assert result.chain == "paid" and result.organisation_type == "PAID"


# ------------------------------------------------------------------------------- register and configuration (N4)


def test_trial_chain_names_must_be_vetted_and_never_paid(monkeypatch):
    monkeypatch.setattr(vetted, "load", lambda path=None: _register(groq={"commercial_use": None}))
    problems = provider_module.trial_chain_problems(["freellmapi", "vertex", "groq", "cerebras", "nonsense"])
    assert "freellmapi" not in problems
    assert "paid provider" in problems["vertex"]
    assert "commercial use" in problems["groq"]
    assert "only through a gateway" in problems["cerebras"]
    assert "nonsense" in problems


def test_the_shipped_register_vets_only_the_owner_confirmed_upstreams():
    # Owner, 17 Nov 2026: Groq, Cloudflare Workers AI and OpenRouter (training opt-out set) passed the terms check.
    register = vetted.load()
    checked = date(2026, 11, 18)
    for name in ("groq", "cloudflare", "cloudflare-ai", "openrouter"):
        row = next(item for item in register["providers"] if item["provider"] == name)
        assert vetted.upstream_problem(row, register, today=checked) is None, name
    assert vetted.chain_problem("groq", register, today=checked) is None
    assert vetted.identify("freellmapi", headers={"x-routed-via": "cloudflare/llama"}, raw={}).provider == "cloudflare"
    for unvetted in ("gemini/flash", "nvidia/llama", "cohere/command"):
        with pytest.raises(vetted.UpstreamNotVetted):
            vetted.identify("freellmapi", headers={"x-routed-via": unvetted}, raw={})


def test_an_old_terms_check_warns_at_six_months_and_refuses_at_twelve():
    register = _register()
    row = next(item for item in register["providers"] if item["provider"] == "cerebras")
    old = {**row, "date_checked": (date.today() - timedelta(days=200)).isoformat()}
    assert vetted.upstream_problem(old, register) is None and vetted.stale_warning(old, register)
    older = {**row, "date_checked": (date.today() - timedelta(days=400)).isoformat()}
    assert "older than the refusal limit" in vetted.upstream_problem(older, register)


def test_production_refuses_a_gateway_off_this_server(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setattr(vetted, "load", lambda path=None: _register())
    monkeypatch.setenv("MDARIX_GENAI_FREELLMAPI_BASE_URL", "http://10.0.0.5:3011/v1/chat/completions")
    assert "127.0.0.1" in provider_module.trial_chain_problems(["freellmapi"])["freellmapi"]


def test_production_configuration_keeps_the_chains_apart_and_models_pinned(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setattr(vetted, "load", lambda path=None: _register())
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    monkeypatch.setenv("MDARIX_GENAI_FALLBACKS", "omniroute")
    monkeypatch.setenv("MDARIX_GENAI_MODEL", "gemini-flash-latest")
    monkeypatch.delenv("MDARIX_GENAI_MODEL_VERSION", raising=False)
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi,vertex")
    monkeypatch.setenv("MDARIX_AI_FEATURES", "ask,mind_reading")
    found = " | ".join(policy.configuration_problems())
    assert "MDARIX_GENAI_FALLBACKS names omniroute, a free-trial chain provider" in found
    assert "MDARIX_AI_TRIAL_CHAIN: vertex" in found
    assert "moving model name" in found and "MDARIX_GENAI_MODEL_VERSION must name" in found
    assert "unknown feature: mind_reading" in found


@pytest.mark.parametrize(
    "model, moving",
    [
        ("gemini-flash-latest", True),
        ("auto", True),
        ("mistral-small-latest", True),
        ("gemini-flash", True),
        ("google/gemini-2.5-flash", False),
        ("gpt-oss-120b", False),
    ],
)
def test_moving_model_names_are_recognised(model, moving):
    assert policy.moving_model(model) is moving


def test_a_pinned_model_with_its_version_passes_in_production(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_MODEL_VERSION", "001")
    assert policy.pin_problems("vertex", "google/gemini-2.5-flash", True) == []


def test_vertex_sends_the_reasoning_effort_and_reports_its_region(monkeypatch):
    sent = []
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    monkeypatch.setenv("MDARIX_GENAI_PROJECT", "mdarix-test")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "k")
    monkeypatch.setenv("MDARIX_AI_FEATURES", "summaries")
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    for name in ("MDARIX_GENAI_BASE_URL", "MDARIX_GENAI_LOCATION", "MDARIX_GENAI_VERTEX_REASONING_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    usage = {"completion_tokens": 9, "completion_tokens_details": {"reasoning_tokens": 7}}

    def urlopen(req, timeout=None):
        sent.append(json.loads(req.data))
        return _Reply({"choices": [{"message": {"content": "ok"}}], "usage": usage})

    monkeypatch.setattr(provider_module.request, "urlopen", urlopen)
    result = GenAIProvider(max_retries=0).complete("Hi", {}, feature="summaries")
    assert sent[0]["reasoning_effort"] == "low"
    assert result.region == "asia-south1" and result.thinking_tokens == 7


def test_the_vertex_metadata_server_down_means_no_model_call(monkeypatch):
    calls = []
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "vertex")
    monkeypatch.setenv("MDARIX_GENAI_PROJECT", "mdarix-test")
    monkeypatch.setenv("MDARIX_AI_FEATURES", "summaries")
    monkeypatch.delenv("MDARIX_GENAI_API_KEY", raising=False)
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    monkeypatch.setattr(provider_module, "_VERTEX_TOKEN", {"value": None, "expires": 0.0})

    def urlopen(req, timeout=None):
        calls.append(req.full_url)
        raise urlerror.URLError("metadata server unreachable")

    monkeypatch.setattr(provider_module.request, "urlopen", urlopen)
    with pytest.raises(GenAIUnavailable) as refused:
        GenAIProvider(max_retries=0).complete("Hi", {}, feature="summaries")
    assert refused.value.code == "GENAI_UNAVAILABLE"
    assert calls == [provider_module.VERTEX_TOKEN_URL]


def test_the_vertex_token_is_refreshed_after_it_expires(monkeypatch):
    tokens = iter(["first", "second"])
    monkeypatch.setattr(provider_module, "_VERTEX_TOKEN", {"value": None, "expires": 0.0})
    monkeypatch.setattr(
        provider_module.request,
        "urlopen",
        lambda req, timeout=None: _Reply({"access_token": next(tokens), "expires_in": 3600}),
    )
    assert provider_module.vertex_token(5) == "first"
    assert provider_module.vertex_token(5) == "first"
    provider_module._VERTEX_TOKEN["expires"] = 0.0
    assert provider_module.vertex_token(5) == "second"


# ------------------------------------------------------------------------------------------- call record hashes


def test_the_call_record_keeps_hashes_of_what_was_sent_not_the_content():
    item = features.FEATURES["ask"]
    call = provider_module._Call(item, "Prompt [MASKED]", {"a": 1}, [], "System", False, None, None, 3, 0.0, [])
    assert call_record.prompt_hash(call) == call_record.sha256("System\x00Prompt [MASKED]")
    assert len(call_record.content_hash(call)) == 64
    assert call_record.content_hash(call) != call_record.prompt_hash(call)


# --------------------------------------------------------------------------------------------- sample catalogue


def test_the_sample_catalogue_holds_sample_text_and_not_other_text():
    assert sample_gate.matches_catalogue("Monitor's SpO2 reading dropped out overnight;")
    assert sample_gate.matches_catalogue("  OrbitCare 300 Rev B:   pressure sensor sourced from NovaSense Components ")
    assert sample_gate.matches_catalogue(None) and sample_gate.matches_catalogue("")
    assert not sample_gate.matches_catalogue("Patient John Real of 12 Real Street had a fall")
