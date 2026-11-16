"""One fake for every AI-service test (trial-chain plan N8): the trial gateways' addresses, their replies and the
recording ``urlopen`` that stands in for the network. No test that uses it can reach a real AI service, FreeLLMAPI,
OmniRoute or Groq: every request is recorded and answered here, or refused as "connection refused".
"""

from __future__ import annotations

import io
import json
from datetime import date
from urllib import error as urlerror

from genai import provider as provider_module

FREELLMAPI = "http://127.0.0.1:3011/v1/chat/completions"
OMNIROUTE = "http://127.0.0.1:20128/v1/chat/completions"
GROQ = provider_module.GROQ_BASE_URL

# How each gateway names the upstream that answered: FreeLLMAPI in one header, OmniRoute in two (its published source,
# release v3.8.54; never called).
FREELLMAPI_CEREBRAS = {"x-routed-via": "cerebras/gpt-oss-120b"}
OMNI_CEREBRAS = {"X-OmniRoute-Provider": "cerebras", "X-OmniRoute-Model": "m-2", "X-OmniRoute-Cache": "MISS"}


class Reply(io.BytesIO):
    """A provider's HTTP reply: a JSON body and its headers."""

    def __init__(self, body: dict, headers: dict | None = None):
        super().__init__(json.dumps(body).encode())
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def answer(text: str = "From the sample records.", model: str = "m-1") -> dict:
    """An OpenAI-style chat completion carrying ``text``."""
    return {"choices": [{"message": {"content": text}}], "model": model, "usage": {"prompt_tokens": 5}}


def http_error(url: str, status: int) -> urlerror.HTTPError:
    return urlerror.HTTPError(url, status, "error", {}, io.BytesIO(b"{}"))


def register(**overrides) -> dict:
    """A vetted-provider register with every trial provider checked today (the shipped one vets no upstream yet).
    ``overrides`` change one provider's row, e.g. ``register(cerebras={"commercial_use": False})``."""
    upstream = {
        "kind": "upstream",
        "chain": "trial",
        "terms_link": "https://example.invalid/terms",
        "date_checked": date.today().isoformat(),
        "region": "US",
        "commercial_use": True,
        "trains_on_data": "no",
        "checked_by": "test",
    }
    rows = [
        {"provider": "freellmapi", "kind": "gateway", "chain": "trial", "upstream_from": "header:x-routed-via"},
        {
            "provider": "omniroute",
            "kind": "gateway",
            "chain": "trial",
            "upstream_from": "headers:x-omniroute-provider,x-omniroute-model",
            "cache_header": "x-omniroute-cache",
        },
        {**upstream, "provider": "groq", "direct": True},
        {**upstream, "provider": "cerebras"},
        {**upstream, "provider": "mistral", "commercial_use": False},
    ]
    for name, change in overrides.items():
        rows = [{**row, **change} if row["provider"] == name else row for row in rows]
    return {"version": 1, "warn_after_days": 183, "refuse_after_days": 365, "providers": rows}


def install(monkeypatch, default=None) -> dict:
    """Replace the network with a recorder. Returns ``{"sent": [urls], "replies": {url: Reply | Exception}}``: a URL
    in ``replies`` gets that reply (an exception is raised), any other URL ``default()`` when given, else a refused
    connection."""
    state: dict = {"sent": [], "replies": {}}

    def urlopen(req, timeout=None):
        url = req.full_url
        state["sent"].append(url)
        reply = state["replies"].get(url)
        if reply is None and default is not None:
            reply = default()
        if reply is None:
            raise urlerror.URLError("connection refused")
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(provider_module.request, "urlopen", urlopen)
    return state
