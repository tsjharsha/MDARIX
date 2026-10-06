"""Which AI providers may receive customer data.

Free tiers of hosted AI services may keep requests or use them to train models, so in staging and production only
two kinds of provider may be called:

* ``ollama``: a model running on MDARIX's own server; nothing leaves it.
* a provider named in ``MDARIX_GENAI_CONTRACTED_PROVIDERS`` (comma-separated), which an operator adds only once a
  contract covers no training on customer data, limited retention and a data processing agreement. Free models
  (OpenRouter names ending ``:free``) are refused even then.

A contracted provider must also not keep the content: an operator sets ``MDARIX_GENAI_<NAME>_ZDR=true`` once the
contract (or the provider's account setting) confirms zero data retention. Without it the provider is refused in
staging and production, unless ``MDARIX_GENAI_ACCEPT_RETENTION=true`` records that the organization accepts the
provider's limited retention (for example 30 days for abuse monitoring) under its data processing agreement.
``docs/compliance/AI_PROVIDER_REGISTER.md`` lists each provider's contract, training opt-out, retention and region.

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


def _flag(name: str) -> bool | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def zero_data_retention(provider: str) -> bool | None:
    """MDARIX_GENAI_<NAME>_ZDR: True once zero data retention is confirmed, False if it is not, None when unset."""
    return _flag(f"MDARIX_GENAI_{provider.strip().upper()}_ZDR")


def retention_accepted() -> bool:
    """MDARIX_GENAI_ACCEPT_RETENTION=true: the operator accepts a contracted provider's limited retention."""
    return _flag("MDARIX_GENAI_ACCEPT_RETENTION") is True


def retention_cleared(provider: str) -> bool:
    """A contracted provider may keep nothing (ZDR confirmed), or its retention was explicitly accepted."""
    return zero_data_retention(provider) is True or retention_accepted()


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
    if name in SELF_HOSTED:
        return True
    return name in contracted_providers() and retention_cleared(name)


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
        elif name not in SELF_HOSTED and not retention_cleared(name):
            found.append(
                f"Contracted provider {name} has no zero-data-retention confirmation: set "
                f"MDARIX_GENAI_{name.upper()}_ZDR=true once the contract confirms it, or "
                "MDARIX_GENAI_ACCEPT_RETENTION=true to accept its limited retention (docs/compliance/AI_PROVIDER_REGISTER.md)"
            )
    primary = (os.getenv("MDARIX_GENAI_PROVIDER") or NO_MODEL).strip().lower()
    fallbacks = [name.strip().lower() for name in os.getenv("MDARIX_GENAI_FALLBACKS", "").split(",") if name.strip()]
    for index, name in enumerate([primary, *fallbacks]):
        if name == NO_MODEL:
            continue
        model = _configured_model(name, index == 0) or default_model(name)
        if not allowed(name, model) and not (name in contracted_providers() and not is_free_model(model)):
            setting = "MDARIX_GENAI_PROVIDER" if index == 0 else "MDARIX_GENAI_FALLBACKS"
            reason = "a free model" if is_free_model(model) else "not under contract"
            found.append(
                f"{setting} uses {name} ({reason}): customer data may only go to ollama or a provider listed in "
                "MDARIX_GENAI_CONTRACTED_PROVIDERS"
            )
    return found
