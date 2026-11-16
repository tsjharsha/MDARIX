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


MOVING_MODEL_SUFFIXES = ("-latest", ":latest")
MOVING_MODEL_NAMES = frozenset({"auto", "latest", "default"})
UNPINNED_VERSIONS = frozenset({"", "unconfigured", "latest"})
VERTEX_REGION = "asia-south1"


def moving_model(model: str | None) -> bool:
    """A name that follows whatever the provider currently serves (``-latest``, ``auto``) or names no version."""
    name = str(model or "").strip().lower()
    tail = name.rsplit("/", 1)[-1]
    return (
        not name
        or tail in MOVING_MODEL_NAMES
        or tail.endswith(MOVING_MODEL_SUFFIXES)
        or not any(character.isdigit() for character in tail)
    )


def _model_version(name: str, primary: bool) -> str:
    setting = "MDARIX_GENAI_MODEL_VERSION" if primary else f"MDARIX_GENAI_{name.upper()}_MODEL_VERSION"
    return (os.getenv(setting) or "").strip()


def pin_problems(name: str, model: str | None, primary: bool) -> list[str]:
    """Staging and production call a paid organization's provider with an exact, recorded model only (AI-R step 2;
    the trial chain may use moving names, decision T2, since each call records the model that answered)."""
    found = []
    setting = "MDARIX_GENAI_MODEL" if primary else f"MDARIX_GENAI_{name.upper()}_MODEL"
    if moving_model(model):
        found.append(f"{setting} ({model}) is a moving model name: pin an exact model id in staging and production")
    version_setting = "MDARIX_GENAI_MODEL_VERSION" if primary else f"MDARIX_GENAI_{name.upper()}_MODEL_VERSION"
    if _model_version(name, primary).lower() in UNPINNED_VERSIONS:
        found.append(f"{version_setting} must name the pinned model version in staging and production")
    return found


def chain_problems() -> list[str]:
    """The paid and trial chains stay apart: no trial-chain provider for paid organizations, no paid provider in the
    trial chain, every trial-chain name vetted (genai/vetted.py), gateways on this server only."""
    from genai.features import unknown_platform_features
    from genai.provider import trial_chain_problems, trial_only_names

    found = []
    primary = (os.getenv("MDARIX_GENAI_PROVIDER") or NO_MODEL).strip().lower()
    fallbacks = [name.strip().lower() for name in os.getenv("MDARIX_GENAI_FALLBACKS", "").split(",") if name.strip()]
    free = trial_only_names()
    for index, name in enumerate([primary, *fallbacks]):
        if name in free:
            setting = "MDARIX_GENAI_PROVIDER" if index == 0 else "MDARIX_GENAI_FALLBACKS"
            found.append(f"{setting} names {name}, a free-trial chain provider: paid organizations never use it")
    for name, reason in trial_chain_problems().items():
        found.append(f"MDARIX_AI_TRIAL_CHAIN: {name}: {reason}")
    for name in unknown_platform_features():
        found.append(f"MDARIX_AI_FEATURES names an unknown feature: {name}")
    if primary == "vertex":
        location = (os.getenv("MDARIX_GENAI_LOCATION") or VERTEX_REGION).strip()
        if location != VERTEX_REGION and _flag("MDARIX_GENAI_VERTEX_REGION_EXCEPTION") is not True:
            found.append(
                f"MDARIX_GENAI_LOCATION is {location}: production AI stays in {VERTEX_REGION} (Mumbai) unless the "
                "owner records an exception (MDARIX_GENAI_VERTEX_REGION_EXCEPTION=true)"
            )
    return found


def configuration_problems() -> list[str]:
    """Configuration that would send customer data to a provider not allowed here (empty when fine)."""
    from backend.app.runtime_env import is_production_like
    from genai.provider import OPENAI_COMPATIBLE, default_model

    if not is_production_like():
        return []
    found = chain_problems()
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
        found.extend(pin_problems(name, model, index == 0))
        if not allowed(name, model) and not (name in contracted_providers() and not is_free_model(model)):
            setting = "MDARIX_GENAI_PROVIDER" if index == 0 else "MDARIX_GENAI_FALLBACKS"
            reason = "a free model" if is_free_model(model) else "not under contract"
            found.append(
                f"{setting} uses {name} ({reason}): customer data may only go to ollama or a provider listed in "
                "MDARIX_GENAI_CONTRACTED_PROVIDERS"
            )
    return found
