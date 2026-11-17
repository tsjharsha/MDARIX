"""Readiness reports the free-trial AI chain (review G10), without sending anything to an AI service."""

import socket

import pytest

from backend.app import readiness
from genai import provider as provider_module
from genai import vetted
from tests.fake_ai_gateway import register

pytestmark = pytest.mark.unit


@pytest.fixture
def chain(monkeypatch):
    provider_module._COOLDOWN_UNTIL.clear()
    monkeypatch.setenv("MDARIX_GENAI_SHARED_REST", "false")
    monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "freellmapi")
    monkeypatch.setenv("MDARIX_GENAI_FREELLMAPI_API_KEY", "test-key")
    monkeypatch.setenv("MDARIX_AI_FEATURES", "ask")
    monkeypatch.setattr(vetted, "load", lambda path=None: register())
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    monkeypatch.setenv(
        "MDARIX_GENAI_FREELLMAPI_BASE_URL", f"http://127.0.0.1:{listener.getsockname()[1]}/v1/chat/completions"
    )
    yield monkeypatch
    listener.close()
    provider_module._COOLDOWN_UNTIL.clear()


def test_off_when_no_trial_chain_is_set(monkeypatch):
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    assert readiness._check("trial_ai_chain", readiness._trial_ai_chain)["state"] == "OFF"


def test_a_reachable_gateway_is_ok(chain):
    result = readiness._check("trial_ai_chain", readiness._trial_ai_chain)
    assert result["ok"] is True and result["state"] == "ON" and result["features"] == ["ask"]
    assert result["providers"] == [{"provider": "freellmapi", "usable": True, "resting": False, "reachable": True}]


def test_a_gateway_that_is_down_is_reported_without_changing_the_status(chain):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed = probe.getsockname()[1]
    probe.close()
    chain.setenv("MDARIX_GENAI_FREELLMAPI_BASE_URL", f"http://127.0.0.1:{closed}/v1/chat/completions")
    result = readiness._check("trial_ai_chain", readiness._trial_ai_chain)
    assert result["ok"] is False and result["reason"] == "TRIAL_AI_CHAIN_DOWN"


def test_a_resting_provider_counts_as_down(chain):
    provider_module._rest("freellmapi", 60, "UNAVAILABLE")
    assert readiness._check("trial_ai_chain", readiness._trial_ai_chain)["reason"] == "TRIAL_AI_CHAIN_DOWN"


def test_a_chain_without_any_ai_feature_is_named(chain):
    chain.setenv("MDARIX_AI_FEATURES", "")
    assert readiness._check("trial_ai_chain", readiness._trial_ai_chain)["reason"] == "NO_AI_FEATURES"
