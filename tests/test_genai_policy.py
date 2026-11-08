"""Contracted providers must also not keep customer content: zero data retention confirmed per provider, or the
operator's explicit acceptance of limited retention (genai/policy.py)."""

from genai import policy


def _production(monkeypatch, contracted="anthropic"):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", contracted.split(",")[0])
    monkeypatch.setenv("MDARIX_GENAI_FALLBACKS", "")
    monkeypatch.setenv("MDARIX_GENAI_CONTRACTED_PROVIDERS", contracted)
    for name in ("MDARIX_GENAI_ACCEPT_RETENTION", "MDARIX_GENAI_ANTHROPIC_ZDR", "MDARIX_GENAI_MISTRAL_ZDR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("MDARIX_GENAI_MODEL", raising=False)


def test_a_contracted_provider_without_zero_data_retention_is_refused_in_production(monkeypatch):
    _production(monkeypatch)
    assert not policy.allowed("anthropic", "claude-sonnet-5-5")
    problems = policy.configuration_problems()
    assert any("MDARIX_GENAI_ANTHROPIC_ZDR=true" in item for item in problems), problems
    monkeypatch.setenv("MDARIX_GENAI_ANTHROPIC_ZDR", "false")
    assert not policy.allowed("anthropic", "claude-sonnet-5-5")


def test_confirmed_zero_data_retention_clears_the_provider(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setenv("MDARIX_GENAI_ANTHROPIC_ZDR", "true")
    assert policy.allowed("anthropic", "claude-sonnet-5-5")
    assert policy.configuration_problems() == []


def test_accepted_retention_clears_every_contracted_provider_but_never_a_free_model(monkeypatch):
    _production(monkeypatch, "anthropic,mistral")
    monkeypatch.setenv("MDARIX_GENAI_ACCEPT_RETENTION", "true")
    assert policy.allowed("anthropic") and policy.allowed("mistral")
    assert not policy.allowed("openrouter", "some-model:free")
    assert not policy.allowed("gemini")  # still not under contract
    assert policy.configuration_problems() == []


def test_self_hosted_and_development_need_no_retention_flag(monkeypatch):
    _production(monkeypatch)
    assert policy.allowed("ollama")
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert policy.allowed("anthropic") and policy.configuration_problems() == []


def test_omniroute_is_a_router_so_production_needs_contract_and_retention_like_any_provider(monkeypatch):
    from genai.provider import OPENAI_COMPATIBLE

    assert "omniroute" in OPENAI_COMPATIBLE and "omniroute" not in policy.SELF_HOSTED
    _production(monkeypatch, "anthropic")
    monkeypatch.setenv("MDARIX_GENAI_ANTHROPIC_ZDR", "true")
    assert not policy.allowed("omniroute")  # not under contract
    _production(monkeypatch, "omniroute")
    monkeypatch.delenv("MDARIX_GENAI_OMNIROUTE_ZDR", raising=False)
    assert not policy.allowed("omniroute")  # under contract, retention not cleared
    monkeypatch.setenv("MDARIX_GENAI_OMNIROUTE_ZDR", "true")
    assert policy.allowed("omniroute")
