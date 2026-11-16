"""The free-trial AI matrix (trial-chain plan N10), on the server's single model entry with the real database checks:
trial chain on/off x organization switch on/off x the user's AI switch Active/Inactive x the record (unedited sample,
edited sample, the trial's own upload). Exactly one combination calls the (fake) gateway and writes one call record;
every other one is refused before any AI service, with the first rule that stops it, and writes nothing.

Every request goes to the shared fake gateway (``tests/fake_ai_gateway.py``); no AI service is called.
"""

from __future__ import annotations

import itertools

import pytest

from tests.fake_ai_gateway import FREELLMAPI
from tests.test_ai_trial_gate import (  # noqa: F401 (fixtures)
    _calls,
    _copy,
    _set_tenant,
    _set_user,
    _summarize,
    chain_on,
    trial,
)
from genai.provider import GenAIUnavailable

pytestmark = pytest.mark.db

CASES = list(itertools.product((True, False), (True, False), ("ACTIVE", "INACTIVE"), ("sample", "edited", "own")))


def expected(chain: bool, organization: bool, person: str, record: str) -> str | None:
    """The refusal the governance order gives (genai/governance.py, then the sample gate), or None for a call."""
    if not chain:
        return "GENAI_OFF_FOR_FREE_TRIAL"
    if not organization:
        return "GENAI_DISABLED_FOR_ORGANIZATION"
    if person != "ACTIVE":
        return "GENAI_USER_AI_INACTIVE"
    if record != "sample":
        return "GENAI_TRIAL_SAMPLE_ONLY"
    return None


@pytest.mark.parametrize(
    "chain,organization,person,record",
    CASES,
    ids=[f"chain-{c}-org-{o}-{p.lower()}-{r}" for c, o, p, r in CASES],
)
def test_the_trial_matrix(trial, chain_on, monkeypatch, chain, organization, person, record):  # noqa: F811
    if not chain:
        # No trial chain, even with the paid provider configured: a trial never reaches it.
        monkeypatch.setenv("MDARIX_AI_TRIAL_CHAIN", "")
        monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
        monkeypatch.setenv("MDARIX_GENAI_API_KEY", "dev-key")
    _set_tenant(trial["tenant_id"], ai_processing_allowed=organization)
    _set_user(trial["user_id"], person)
    sample = trial["sample"][0]
    ids = {
        "sample": [sample],
        "edited": [_copy(sample, description="Mrs Real Person fell at home when the alarm failed.")],
        "own": [_copy(sample, source_system="TRIAL_UPLOAD")],
    }[record]
    before = _calls(trial["tenant_id"])
    refusal = expected(chain, organization, person, record)
    if refusal is None:
        result = _summarize(trial, ids)
        assert result.output["answer"] == "From the sample."
        assert chain_on == [FREELLMAPI]
        assert _calls(trial["tenant_id"]) == before + 1
        return
    with pytest.raises(GenAIUnavailable) as refused:
        _summarize(trial, ids)
    assert refused.value.code == refusal
    assert chain_on == [], "a refused request reaches no AI service"
    assert _calls(trial["tenant_id"]) == before, "a refused request writes no call record"


def test_the_matrix_has_exactly_one_calling_combination():
    assert [case for case in CASES if expected(*case) is None] == [(True, True, "ACTIVE", "sample")]
