"""The live AI evaluation spends money on the paid model, so it runs only by hand, with a typed spend confirmation and
a token cap, and never on the free-trial chain (AI-R step 18; owner decision AI-D10; trial-chain plan 2.8)."""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ai-evaluation.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_live_evaluation_has_no_schedule_and_no_pull_request_trigger():
    # PyYAML reads the bare key "on" as True.
    triggers = _workflow().get("on", _workflow().get(True))
    assert set(triggers) == {"workflow_dispatch"}


def test_a_run_needs_the_spend_confirmation_and_a_token_cap():
    workflow = _workflow()
    inputs = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
    assert inputs["confirm_spend"]["required"] is True and inputs["confirm_spend"]["default"] == ""
    assert inputs["max_tokens"]["required"] is True
    steps = workflow["jobs"]["evaluate"]["steps"]
    first = steps[0]
    assert first["name"] == "Confirm the spend and the token cap" and '"SPEND"' in first["run"]
    env = workflow["jobs"]["evaluate"]["env"]
    assert env["MDARIX_GENAI_TENANT_MONTHLY_TOKENS"] == "${{ inputs.max_tokens }}"


def test_the_evaluation_never_uses_the_free_trial_chain():
    env = _workflow()["jobs"]["evaluate"]["env"]
    assert env["MDARIX_AI_TRIAL_CHAIN"] == "" and env["MDARIX_GENAI_FALLBACKS"] == ""
