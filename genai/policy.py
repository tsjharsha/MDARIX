"""Which AI providers may receive customer data.

Free tiers of hosted AI services may keep requests or use them to train models, so in staging and production only
two kinds of provider may be called:

* ``ollama``: a model running on MDARIX's own server; nothing leaves it.
* a provider named in ``MDARIX_GENAI_CONTRACTED_PROVIDERS`` (comma-separated), which an operator adds only once a
  contract covers no training on customer data, limited retention and a data processing agreement. Free models
  (OpenRouter names ending ``:free``) are refused even then.

``controlled`` (no model; rule-based answers only) is always allowed. Local development and test runs may call any
configured provider, on synthetic data. The API refuses to start when its configuration breaks this rule
(``backend/app/config_check.py``), and ``GenAIProvider.complete`` skips any provider it forbids, so customer data
never reaches one by accident.
"""

from __future__ import annotations

import os

SELF_HOSTED = frozenset({"ollama"})
NO_MODEL = "controlled"


def contracted_providers() -> frozenset[str]:
    return frozenset(
        name.strip().lower() for name in os.getenv("MDARIX_GENAI_CONTRACTED_PROVIDERS", "").split(",") if name.strip()
    )


def is_free_model(model: str | None) -> bool:
    return str(model or "").strip().lower().endswith(":free")


def allowed(provider: str, model: str | None = None) -> bool:
    """True when ``provider`` (with ``model``) may receive customer data in this environment."""
    from backend.app.runtime_env import is_production_like

    name = (provider or NO_MODEL).strip().lower()
    if name == NO_MODEL or not is_production_like():
        return True
    if is_free_model(model):
        return False
    return name in SELF_HOSTED or name in contracted_providers()


def _configured_model(name: str, primary: bool) -> str | None:
    if primary:
        return os.getenv("MDARIX_GENAI_MODEL")
    return os.getenv(f"MDARIX_GENAI_{name.upper()}_MODEL")


def configuration_problems() -> list[str]:
    """Configuration that would send customer data to a provider not allowed here (empty when fine)."""
    from backend.app.runtime_env import is_production_like
    from genai.provider import OPENAI_COMPATIBLE, default_model

    if not is_production_like():
        return []
    found = []
    for name in sorted(contracted_providers()):
        if name not in OPENAI_COMPATIBLE:
            found.append(f"MDARIX_GENAI_CONTRACTED_PROVIDERS names an unknown provider: {name}")
    primary = (os.getenv("MDARIX_GENAI_PROVIDER") or NO_MODEL).strip().lower()
    fallbacks = [name.strip().lower() for name in os.getenv("MDARIX_GENAI_FALLBACKS", "").split(",") if name.strip()]
    for index, name in enumerate([primary, *fallbacks]):
        if name == NO_MODEL:
            continue
        model = _configured_model(name, index == 0) or default_model(name)
        if not allowed(name, model):
            setting = "MDARIX_GENAI_PROVIDER" if index == 0 else "MDARIX_GENAI_FALLBACKS"
            reason = "a free model" if is_free_model(model) else "not under contract"
            found.append(
                f"{setting} uses {name} ({reason}): customer data may only go to ollama or a provider listed in "
                "MDARIX_GENAI_CONTRACTED_PROVIDERS"
            )
    return found
