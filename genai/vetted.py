"""The vetted-provider register (owner decision AI-D19): which free AI services the trial chain may use.

``genai/vetted_providers.json`` has one row per provider:

* a **gateway** (``freellmapi``, ``omniroute``): self-hosted software that forwards a request to an upstream. It may
  stand in the trial chain; the upstream that actually answered is read from its reply (``upstream_from``:
  FreeLLMAPI's ``X-Routed-Via: <platform>/<model>`` header, OmniRoute's ``X-OmniRoute-Provider`` and ``X-OmniRoute-Model`` headers) and must be vetted;
* an **upstream** (``groq`` and the platforms behind the gateways): a model provider whose terms were read. It is
  usable only when commercial use is allowed, it does not train on the data (or an opt-out is confirmed) and the
  check is under ``refuse_after_days`` old (a warning from ``warn_after_days``). ``direct: true`` lets it stand in the
  trial chain itself (Groq, called without a gateway).

A reply whose upstream cannot be identified or is not usable is discarded, never shown (``UpstreamNotVetted``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

REGISTER_PATH = Path(__file__).with_name("vetted_providers.json")
TRIAL_CHAIN = "trial"
TRAINING_OK = ("no", "opt_out_confirmed")


class UpstreamNotVetted(ValueError):
    """A reply came from an upstream the register does not allow (or names none); it is discarded."""


@dataclass(frozen=True)
class Upstream:
    gateway: str
    provider: str
    model: str | None


def load(path: Path | None = None) -> dict:
    with open(path or REGISTER_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _rows(register: dict) -> dict[str, dict]:
    return {str(row.get("provider") or "").strip().lower(): row for row in register.get("providers") or []}


def _checked_on(row: dict) -> date | None:
    raw = row.get("date_checked")
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        return None


def _today(today: date | None) -> date:
    return today or datetime.now(timezone.utc).date()


def upstream_problem(row: dict | None, register: dict, today: date | None = None) -> str | None:
    """Why an upstream row may not answer now (None when it may)."""
    if row is None:
        return "not in the vetted-provider register"
    if row.get("kind") != "upstream":
        return "not an upstream provider"
    if row.get("chain") != TRIAL_CHAIN:
        return "not vetted for the trial chain"
    if row.get("commercial_use") is not True:
        return "commercial use not confirmed"
    if row.get("trains_on_data") not in TRAINING_OK:
        return "may train on the data"
    checked = _checked_on(row)
    if checked is None or not row.get("terms_link"):
        return "terms not checked"
    if (_today(today) - checked).days > int(register.get("refuse_after_days") or 365):
        return "terms check older than the refusal limit"
    return None


def stale_warning(row: dict, register: dict, today: date | None = None) -> str | None:
    checked = _checked_on(row)
    if checked and (_today(today) - checked).days > int(register.get("warn_after_days") or 183):
        return f"{row.get('provider')}: terms checked on {checked.isoformat()}, re-check due"
    return None


def chain_problem(name: str, register: dict | None = None, today: date | None = None) -> str | None:
    """Why ``name`` may not stand in ``MDARIX_AI_TRIAL_CHAIN`` (None when it may)."""
    register = register if register is not None else load()
    row = _rows(register).get(name)
    if row is None:
        return f"{name} is not in the vetted-provider register"
    if row.get("chain") != TRIAL_CHAIN:
        return f"{name} is not registered for the trial chain"
    if row.get("kind") == "gateway":
        return None
    if not row.get("direct"):
        return f"{name} is reached only through a gateway"
    problem = upstream_problem(row, register, today)
    return f"{name}: {problem}" if problem else None


def warnings(names, register: dict | None = None, today: date | None = None) -> list[str]:
    register = register if register is not None else load()
    rows = _rows(register)
    found = []
    for row in rows.values():
        if row.get("kind") == "upstream" and (row.get("provider") in names or row.get("chain") == TRIAL_CHAIN):
            warning = stale_warning(row, register, today)
            if warning and upstream_problem(row, register, today) is None:
                found.append(warning)
    return found


def _header(headers, name: str | None) -> str | None:
    """A reply header by name, whatever its case (the HTTP reply's headers, or a plain dict in tests)."""
    if not headers or not name:
        return None
    value = headers.get(name)
    if value is None and isinstance(headers, dict):
        value = next((item for key, item in headers.items() if str(key).lower() == name.lower()), None)
    return str(value) if value is not None else None


def _split(value: str | None) -> tuple[str, str | None] | None:
    text = str(value or "").strip()
    if "/" not in text:
        return None
    platform, model = text.split("/", 1)
    platform = platform.strip().lower()
    return (platform, model.strip() or None) if platform else None


def identify(gateway: str, *, headers=None, raw: dict | None = None, configured_model: str | None = None) -> Upstream:
    """The upstream that answered a reply from ``gateway``; ``UpstreamNotVetted`` when it is unknown or not usable."""
    register = load()
    rows = _rows(register)
    row = rows.get(gateway)
    if row is None:
        raise UpstreamNotVetted(f"{gateway} is not in the vetted-provider register")
    if row.get("kind") == "upstream":
        problem = upstream_problem(row, register)
        if problem:
            raise UpstreamNotVetted(f"{gateway}: {problem}")
        model = (raw or {}).get("model") or configured_model
        return Upstream(gateway, gateway, str(model) if model else None)
    source = str(row.get("upstream_from") or "")
    cache = _header(headers, row.get("cache_header"))
    if cache and cache.strip().upper() != "MISS":
        raise UpstreamNotVetted(f"{gateway} answered from its cache: the upstream is not identifiable")
    if source.startswith("header:"):
        value = _header(headers, source.split(":", 1)[1])
    elif source.startswith("headers:"):
        # Provider and model in two headers (OmniRoute: X-OmniRoute-Provider, X-OmniRoute-Model). Its body "model"
        # is the upstream's bare model name (e.g. "openai/gpt-oss-120b" from Groq), so it cannot name the provider.
        provider_header, model_header = source.split(":", 1)[1].split(",", 1)
        platform, model = _header(headers, provider_header), _header(headers, model_header)
        value = f"{platform.strip()}/{model.strip()}" if platform and model and platform.strip() else None
    elif source.startswith("body:"):
        value = (raw or {}).get(source.split(":", 1)[1])
    else:
        value = None
    found = _split(value)
    if found is None:
        # A cached or replayed reply ("cache", "idempotency") or a bare model name: the upstream is not identifiable.
        raise UpstreamNotVetted(f"{gateway} named no identifiable upstream ({str(value or '')[:60]!r})")
    platform, model = found
    upstream_row = rows.get(platform)
    problem = upstream_problem(upstream_row, register)
    if problem:
        raise UpstreamNotVetted(f"{gateway} answered through {platform}: {problem}")
    # A "models" list is an allowlist: present and empty means no model is vetted yet (review G13: fail closed).
    allowed_models = upstream_row.get("models")
    if allowed_models is not None and model not in allowed_models:
        raise UpstreamNotVetted(f"{gateway} answered through {platform} with a model not in its vetted list")
    return Upstream(gateway, platform, model)
