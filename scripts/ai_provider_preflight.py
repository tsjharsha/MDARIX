"""Is this server ready to run the golden evaluation with the contracted AI provider? A check of settings only.

    python scripts/ai_provider_preflight.py

Run it on staging once the provider contract is signed and its settings are in place (docs/runbooks/AI_PROVIDERS.md).
It reads the MDARIX_GENAI_* settings of this environment and the release files under evaluation/, sends nothing to any
provider and changes nothing. Each line says what passed, what did not and what to do; the exit code is 0 only when
the provider settings are ready for `scripts/run_real_evaluation.py --gate --require-model --switch-ai-on
--release-record`. The four bars of the AI release gate are listed last (backend/app/ai_release_gate.py).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS, FAIL = "PASS", "FAIL"
EVALUATION = "python scripts/run_real_evaluation.py --pause 5 --gate --require-model --switch-ai-on --release-record"


def checks() -> list[tuple[str, str, str]]:
    """(status, what, detail) for each provider setting, in the order to fix them."""
    from genai.policy import NO_MODEL, allowed, configuration_problems, contracted_providers, retention_cleared
    from genai.provider import OPENAI_COMPATIBLE, GenAIProvider

    found: list[tuple[str, str, str]] = []
    name = (os.getenv("MDARIX_GENAI_PROVIDER") or NO_MODEL).strip().lower()
    if name == NO_MODEL:
        found.append(
            (FAIL, "Provider chosen", "MDARIX_GENAI_PROVIDER is not set: every AI feature answers from rules.")
        )
        return found
    if name not in OPENAI_COMPATIBLE:
        found.append((FAIL, "Provider chosen", f"MDARIX_GENAI_PROVIDER={name} is not a provider MDARIX knows."))
        return found
    provider = GenAIProvider()
    found.append((PASS, "Provider chosen", f"{name} {provider.model}"))
    if name == "vertex":
        # Vertex AI signs in as the VM's service account (genai/provider.py vertex_token): no key, only the project.
        found.append(
            (PASS, "Credentials", f"Vertex AI at {provider.base_url}, signed in as the VM's service account.")
            if provider.configured
            else (
                FAIL,
                "Credentials",
                "Set MDARIX_GENAI_PROJECT to the Google Cloud project (and _LOCATION if not asia-south1).",
            )
        )
    else:
        found.append(
            (PASS, "Credentials", "An API key is set (never shown).")
            if provider.configured
            else (FAIL, "Credentials", f"Set MDARIX_GENAI_API_KEY for {name}.")
        )
    contracted = name in contracted_providers()
    found.append(
        (PASS, "Under contract", f"{name} is listed in MDARIX_GENAI_CONTRACTED_PROVIDERS.")
        if contracted
        else (FAIL, "Under contract", f"Add {name} to MDARIX_GENAI_CONTRACTED_PROVIDERS once the contract is signed.")
    )
    cleared = retention_cleared(name)
    found.append(
        (PASS, "Data retention", "Zero data retention confirmed, or limited retention accepted.")
        if cleared
        else (
            FAIL,
            "Data retention",
            f"Set MDARIX_GENAI_{name.upper()}_ZDR=true once the contract confirms zero data retention "
            "(or MDARIX_GENAI_ACCEPT_RETENTION=true to accept its limited retention).",
        )
    )
    found.append(
        (PASS, "Allowed by the provider policy", "Customer data may be sent to it.")
        if allowed(name, provider.model)
        else (FAIL, "Allowed by the provider policy", "The policy refuses this provider or model (a free model?).")
    )
    try:
        cost = float(os.getenv("MDARIX_GENAI_COST_PER_1K_TOKENS", "0") or 0)
    except ValueError:
        cost = 0.0
    found.append(
        (PASS, "Cost per 1,000 tokens", f"{cost} (budgets and alerts use it)")
        if cost > 0
        else (FAIL, "Cost per 1,000 tokens", "Set MDARIX_GENAI_COST_PER_1K_TOKENS from the contract's price.")
    )
    for problem in configuration_problems():
        found.append((FAIL, "Production configuration", problem))
    return found


def main() -> int:
    from backend.app.ai_release_gate import status

    results = checks()
    width = max(len(what) for _, what, _ in results)
    print("Provider settings")
    for state, what, detail in results:
        print(f"  {state:<5} {what:<{width}}  {detail}")
    ready = all(state == PASS for state, _, _ in results)
    gate = status()
    print(f"\nAI release gate: {gate['met']} of {gate['total']} bars met")
    for bar in gate["bars"]:
        print(f"  {'MET ' if bar['status'] == 'MET' else 'OPEN'}  {bar['title']}: {bar['detail']}")
    if ready:
        print(f"\nReady. Next, on staging: {EVALUATION}")
    else:
        print("\nNot ready: fix each FAIL above, then run this again.")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
