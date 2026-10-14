"""The two tools between the AI provider contract and a pilot with AI on (no database, nothing sent anywhere): the
provider preflight (scripts/ai_provider_preflight.py) and the golden dataset review pack
(scripts/golden_review_pack.py)."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preflight = _load("ai_provider_preflight")
review_pack = _load("golden_review_pack")


@pytest.fixture
def clean_ai_settings(monkeypatch):
    for name in (
        "MDARIX_GENAI_PROVIDER",
        "MDARIX_GENAI_API_KEY",
        "MDARIX_GENAI_MODEL",
        "MDARIX_GENAI_FALLBACKS",
        "MDARIX_GENAI_CONTRACTED_PROVIDERS",
        "MDARIX_GENAI_ANTHROPIC_ZDR",
        "MDARIX_GENAI_ACCEPT_RETENTION",
        "MDARIX_GENAI_COST_PER_1K_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _statuses(results) -> dict[str, str]:
    return {what: state for state, what, _ in results}


def test_without_a_provider_the_preflight_says_so_and_stops(clean_ai_settings):
    results = preflight.checks()
    assert results == [
        (preflight.FAIL, "Provider chosen", "MDARIX_GENAI_PROVIDER is not set: every AI feature answers from rules.")
    ]


def test_a_provider_without_contract_settings_is_not_ready(clean_ai_settings):
    clean_ai_settings.setenv("MDARIX_GENAI_PROVIDER", "anthropic")
    clean_ai_settings.setenv("MDARIX_GENAI_API_KEY", "test-key")
    found = _statuses(preflight.checks())
    assert found["Provider chosen"] == preflight.PASS and found["Credentials"] == preflight.PASS
    assert found["Under contract"] == preflight.FAIL and found["Data retention"] == preflight.FAIL
    assert found["Cost per 1,000 tokens"] == preflight.FAIL
    # The API key itself is never shown.
    assert all("test-key" not in detail for _, _, detail in preflight.checks())


def test_a_contracted_provider_with_zero_retention_and_a_price_is_ready(clean_ai_settings):
    for name, value in {
        "MDARIX_GENAI_PROVIDER": "anthropic",
        "MDARIX_GENAI_API_KEY": "test-key",
        "MDARIX_GENAI_CONTRACTED_PROVIDERS": "anthropic",
        "MDARIX_GENAI_ANTHROPIC_ZDR": "true",
        "MDARIX_GENAI_COST_PER_1K_TOKENS": "0.009",
    }.items():
        clean_ai_settings.setenv(name, value)
    results = preflight.checks()
    assert {state for state, _, _ in results} == {preflight.PASS}, results
    assert results[0][2] == "anthropic claude-sonnet-5-5"


def test_the_review_pack_lays_out_every_scenario_and_the_sign_off():
    from evaluation.release_record import LOCK, SIGN_OFF_STATEMENT, read

    scenarios = review_pack._read(review_pack.SCENARIOS)
    canonical = review_pack._read(review_pack.CANONICAL)
    lock = read(LOCK)
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    text = review_pack.build(scenarios, canonical, lock, None, now)
    assert text.count("\n## VS") == 15
    assert "## VS013: Prompt Injection in Evidence" in text and "`CANARY-7731`" in text
    assert "synthetic personal details sit in the evidence" in text
    assert "Leading question: the investigator asks" in text
    assert SIGN_OFF_STATEMENT in text and review_pack.SIGN_OFF_COMMAND in text
    assert "No person has signed off the golden dataset lock yet." in text
    for value in lock["hashes"].values():
        assert value in text
    signed = {
        "sign_off_version": "MDARIX_AI_GOLDEN_HUMAN_SIGN_OFF_V1",
        "approved_by": "Dana Whitfield",
        "role": "Head of Quality",
        "lock_hashes": lock["hashes"],
    }
    assert "Human sign-off: signed by Dana Whitfield" in review_pack.build(scenarios, canonical, lock, signed, now)
