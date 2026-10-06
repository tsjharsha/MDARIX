"""Bounded GenAI provider boundary.

No provider is contacted unless explicitly configured.  Responses are
structured and never retain hidden chain-of-thought; only a short rationale
summary is returned for human review.
"""

from __future__ import annotations
import json, os, re, time
from dataclasses import dataclass
from urllib import error as urlerror, request
import logging

CONFIG_VERSION = "genai-config-1"
PROMPT_VERSION = "mdarix-safe-prompt-1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_DEFAULT_MODEL = "llama3.2"
# OpenAI-compatible chat-completions services: address and default model. Every value can be overridden in the
# environment (MDARIX_GENAI_<NAME>_BASE_URL / _MODEL); models change often, so check the provider's list.
OPENAI_COMPATIBLE = {
    "groq": (GROQ_BASE_URL, GROQ_DEFAULT_MODEL),
    "cerebras": ("https://api.cerebras.ai/v1/chat/completions", "gpt-oss-120b"),
    # "-latest" follows Google's current Flash model, so a retired version does not break the fallback.
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-flash-latest"),
    # Free OpenRouter models come and go; check https://openrouter.ai/models?max_price=0 when this one stops answering.
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "nvidia/nemotron-3-super-120b-a12b:free"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
    # Anthropic's OpenAI-compatible endpoint; for production use under a commercial agreement (genai/policy.py).
    "anthropic": ("https://api.anthropic.com/v1/chat/completions", "claude-sonnet-5-5"),
    "ollama": (OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL),
}


def default_model(name: str) -> str | None:
    """The model a provider uses when MDARIX_GENAI_*_MODEL does not name one."""
    return OPENAI_COMPATIBLE.get(name, (None, None))[1]


# Services that no longer exist: named in MDARIX_GENAI_FALLBACKS they are skipped with a warning.
RETIRED_PROVIDERS = {"github": "GitHub Models was retired by GitHub on 30 July 2026"}
# A provider that refused us (rate or daily limit) is skipped until this time (epoch seconds), so a request does not
# wait on it every time; any other failure is skipped for a short time only. This is the process's own copy; every
# process also reads and writes the shared rest periods (genai/governance.py).
_COOLDOWN_UNTIL: dict[str, float] = {}
# Retired or misspelt fallback names already warned about, so the warning is logged once per process.
_WARNED_FALLBACKS: set[str] = set()
SENSITIVE = re.compile(r"(?i)(password|token|secret|cookie|authorization|api[_-]?key|credential)\s*[:=]\s*[^,;\n]+")
logger = logging.getLogger(__name__)


class InvalidStructuredOutput(ValueError):
    """A provider returned an empty or non-JSON response to a structured request."""


STRICT_JSON_SCHEMA_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
}


class GenAIUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class GenAIResult:
    provider: str
    model: str
    model_version: str
    output: dict
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: int
    human_review_required: bool = True


def redact_context(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"(?i)(password|token|secret|cookie|authorization|api[_-]?key|credential)", str(k))
            else redact_context(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_context(v) for v in value]
    return SENSITIVE.sub(lambda m: m.group(1) + ": [REDACTED]", str(value)) if isinstance(value, str) else value


class GenAIProvider:
    def __init__(
        self,
        *,
        base_url=None,
        api_key=None,
        model=None,
        timeout_seconds=None,
        max_retries=None,
        max_input_tokens=None,
        max_output_tokens=None,
        cost_per_1k_tokens=None,
        provider_name=None,
        fallbacks=None,
    ):
        # The primary provider reads MDARIX_GENAI_*; a fallback named "x" reads MDARIX_GENAI_X_* (see fallback_chain).
        prefix = f"MDARIX_GENAI_{provider_name.upper()}_" if provider_name else "MDARIX_GENAI_"
        self.provider_name = (provider_name or os.getenv("MDARIX_GENAI_PROVIDER", "controlled")).strip().lower()
        known_url, known_model = OPENAI_COMPATIBLE.get(self.provider_name, (None, "mdarix-controlled"))
        self.base_url = base_url or os.getenv(prefix + "BASE_URL") or known_url
        self.api_key = api_key or os.getenv(prefix + "API_KEY")
        self.model = model or os.getenv(prefix + "MODEL", known_model)
        self.model_version = os.getenv(prefix + "MODEL_VERSION", "unconfigured")
        default_timeout = "120" if self.provider_name == "ollama" else "20"
        self.timeout = int(timeout_seconds or os.getenv("MDARIX_GENAI_TIMEOUT_SECONDS", default_timeout))
        self.retries = int(max_retries if max_retries is not None else os.getenv("MDARIX_GENAI_MAX_RETRIES", "2"))
        self.max_input = int(max_input_tokens or os.getenv("MDARIX_GENAI_MAX_INPUT_TOKENS", "4000"))
        self.max_output = int(max_output_tokens or os.getenv("MDARIX_GENAI_MAX_OUTPUT_TOKENS", "1000"))
        self.cost_per_1k = float(cost_per_1k_tokens or os.getenv("MDARIX_GENAI_COST_PER_1K_TOKENS", "0"))
        # Fallbacks only for the primary provider (a fallback never has fallbacks of its own).
        self.fallbacks = fallbacks if fallbacks is not None else ([] if provider_name else fallback_chain(self))

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self.api_key or self.provider_name == "ollama"))

    def health(self):
        now = time.time()
        resting_until = _resting_until()
        return {
            "configured": self.configured,
            "provider": self.provider_name if self.base_url else "controlled",
            "model": self.model,
            "configuration_version": CONFIG_VERSION,
            "human_review_required": True,
            "hidden_chain_of_thought_persisted": False,
            # Used in order when the one before is limited or down; the rule-based answer comes last.
            "fallbacks": [
                {
                    "provider": item.provider_name,
                    "model": item.model,
                    "configured": item.configured,
                    "resting": resting_until.get(item.provider_name, 0) > now,
                }
                for item in self.fallbacks
            ],
            # Named in MDARIX_GENAI_FALLBACKS but unusable (retired service or misspelt), with the reason.
            "skipped_fallbacks": unusable_fallbacks(),
        }

    @staticmethod
    def audit_details(result: GenAIResult) -> dict:
        """Safe metadata suitable for the enterprise AIExecution/audit tables."""
        return {
            "provider": result.provider,
            "model": result.model,
            "model_version": result.model_version,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "estimated_cost": result.estimated_cost,
            "latency_ms": result.latency_ms,
            "human_review_required": True,
            "hidden_chain_of_thought_persisted": False,
        }

    def complete(
        self,
        prompt: str,
        context: dict | None = None,
        *,
        system: str | None = None,
        json_output: bool = False,
        response_schema: dict | None = None,
        max_output_tokens: int | None = None,
    ) -> GenAIResult:
        """system/json_output/max_output_tokens are for structured analysis; defaults keep the plain request."""
        from genai import pii

        safe_prompt = SENSITIVE.sub(lambda m: m.group(1) + ": [REDACTED]", prompt)
        safe_context = redact_context(context or {})
        if pii.enabled():
            # Personal information never leaves for a model (genai/pii.py); identifiers of records are kept.
            safe_prompt = pii.mask_text(safe_prompt)
            safe_context = pii.mask(safe_context)
        input_tokens = max(1, (len(safe_prompt) + len(json.dumps(safe_context, default=str)) + len(system or "")) // 4)
        if input_tokens > self.max_input:
            raise GenAIUnavailable("GENAI_INPUT_TOKEN_LIMIT")
        started = time.monotonic()
        # Fallbacks stand in for a configured primary only: without one (controlled mode) no model is called.
        if not self.configured:
            return GenAIResult(
                "controlled",
                self.model,
                CONFIG_VERSION,
                {
                    "status": "PROVIDER_NOT_CONFIGURED",
                    "answer": None,
                    "limitations": ["Live GenAI provider is not configured."],
                    "human_review_required": True,
                    "causality_state": "NOT_ESTABLISHED",
                },
                input_tokens,
                0,
                0.0,
                int((time.monotonic() - started) * 1000),
            )
        from genai.policy import allowed

        chain = [
            item for item in [self, *self.fallbacks] if item.configured and allowed(item.provider_name, item.model)
        ]
        if not chain:
            # Every configured provider is forbidden here (for example a free tier in production): no model is called.
            logger.error("No AI provider may receive customer data in this environment; answering without a model")
            raise GenAIUnavailable("GENAI_PROVIDER_NOT_ALLOWED")
        from genai import governance

        # The organization's AI switch and monthly budget (raises when it may not use a model now).
        tenant_id = governance.check_allowed(input_tokens + (max_output_tokens or self.max_output))
        resting_until = _resting_until()
        resting = [item for item in chain if resting_until.get(item.provider_name, 0) > time.time()]
        # Providers that are resting are tried last, so a request still gets an answer if every provider rests.
        ordered = [item for item in chain if item not in resting] + resting
        last_error: GenAIUnavailable | None = None
        for item in ordered:
            try:
                result = item._send(
                    safe_prompt,
                    safe_context,
                    system=system,
                    json_output=json_output,
                    response_schema=response_schema,
                    max_output_tokens=max_output_tokens,
                    input_tokens=input_tokens,
                    started=started,
                    fail_fast=len(ordered) > 1,
                )
                governance.record_usage(tenant_id, result.input_tokens, result.output_tokens, result.estimated_cost)
                return result
            except GenAIUnavailable as exc:
                last_error = exc
                logger.warning("GenAI provider %s unavailable; trying the next one", item.provider_name)
        raise last_error or GenAIUnavailable("GENAI_PROVIDER_UNAVAILABLE: no provider")

    def _send(
        self,
        safe_prompt: str,
        safe_context: dict,
        *,
        system: str | None,
        json_output: bool,
        response_schema: dict | None,
        max_output_tokens: int | None,
        input_tokens: int,
        started: float,
        fail_fast: bool,
    ) -> GenAIResult:
        """One provider: the request with its retries. With other providers to fall back to (fail_fast), a rate
        limit moves on at once and the provider rests for a while instead of being waited on."""
        if self.provider_name in OPENAI_COMPATIBLE:
            body = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": safe_prompt + "\n\nAuthorized context:\n" + json.dumps(safe_context, default=str),
                    }
                ],
                "temperature": 0,
            }
            if self.provider_name == "groq":
                body["max_completion_tokens"] = max_output_tokens or self.max_output
            else:
                body["max_tokens"] = max_output_tokens or self.max_output
            if system:
                body["messages"].insert(0, {"role": "system", "content": system})
            if response_schema and self.provider_name == "groq" and self.model in STRICT_JSON_SCHEMA_MODELS:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "mdarix_investigation_analysis",
                        "strict": True,
                        "schema": response_schema,
                    },
                }
                # GPT-OSS can spend the entire completion budget on reasoning. Low, hidden reasoning leaves a
                # deterministic structured answer while retaining enough analysis for this evidence-review task.
                body["reasoning_effort"] = "low"
                body["reasoning_format"] = "hidden"
            elif json_output:
                body["response_format"] = {"type": "json_object"}
            payload = json.dumps(body).encode()
        else:
            payload = json.dumps(
                {"model": self.model, "prompt": safe_prompt, "context": safe_context, "max_tokens": self.max_output}
            ).encode()
        error = None
        for attempt in range(self.retries + 1):
            try:
                req = request.Request(
                    self.base_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "MDARIX-R1/1.0",
                    },
                )
                if self.api_key:
                    req.add_header("Authorization", f"Bearer {self.api_key}")
                with request.urlopen(req, timeout=self.timeout) as response:
                    raw = json.loads(response.read())
                if self.provider_name in OPENAI_COMPATIBLE:
                    answer = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content")
                    usage = raw.get("usage") or {}
                    output_tokens = int(usage.get("completion_tokens") or max(1, len(str(answer or "")) // 4))
                    input_tokens = int(usage.get("prompt_tokens") or input_tokens)
                else:
                    answer = raw.get("answer", raw.get("output", raw.get("text")))
                    output_tokens = min(self.max_output, max(1, len(str(answer or "")) // 4))
                if json_output:
                    if not isinstance(answer, str) or not answer.strip():
                        raise InvalidStructuredOutput("empty structured response")
                    try:
                        structured = json.loads(answer)
                    except (TypeError, ValueError) as exc:
                        raise InvalidStructuredOutput("invalid structured response") from exc
                    if not isinstance(structured, dict):
                        raise InvalidStructuredOutput("structured response is not an object")
                output = {
                    "answer": answer,
                    "limitations": ["Provider output requires human review."],
                    "human_review_required": True,
                    "causality_state": "NOT_ESTABLISHED",
                }
                return GenAIResult(
                    self.provider_name if self.provider_name != "controlled" else "external",
                    self.model,
                    self.model_version,
                    output,
                    input_tokens,
                    output_tokens,
                    ((input_tokens + output_tokens) / 1000) * self.cost_per_1k,
                    int((time.monotonic() - started) * 1000),
                )
            except Exception as exc:
                error = exc
                status = exc.code if isinstance(exc, urlerror.HTTPError) else None
                logger.warning(
                    "GenAI provider attempt failed provider=%s model=%s attempt=%s status=%s error=%s",
                    self.provider_name,
                    self.model,
                    attempt + 1,
                    status,
                    type(exc).__name__,
                )
                if fail_fast and status == 429 and not json_output:
                    _rest(
                        self.provider_name,
                        float(os.getenv("MDARIX_GENAI_RATE_LIMIT_REST_SECONDS", "900")),
                        "RATE_LIMITED",
                    )
                    break
                wait = min(2**attempt, 4)
                if status == 429 and attempt < self.retries:
                    # Rate limited: wait as long as the provider asks, within a cap that keeps requests responsive.
                    try:
                        asked = float(exc.headers.get("retry-after") or 0)
                    except (TypeError, ValueError):
                        asked = 0.0
                    wait = max(wait, min(asked, float(os.getenv("MDARIX_GENAI_MAX_RETRY_WAIT_SECONDS", "10"))))
                if attempt < self.retries:
                    time.sleep(wait)
        if fail_fast and _COOLDOWN_UNTIL.get(self.provider_name, 0) <= time.time():
            # Down rather than limited: rest briefly so the next requests go straight to a working provider.
            _rest(self.provider_name, float(os.getenv("MDARIX_GENAI_OUTAGE_REST_SECONDS", "60")), "UNAVAILABLE")
        raise GenAIUnavailable(f"GENAI_PROVIDER_UNAVAILABLE: {type(error).__name__}")


def _resting_until() -> dict[str, float]:
    """Each resting provider's end of rest (epoch seconds): this process's own, or the shared one if later."""
    from genai import governance

    merged = dict(_COOLDOWN_UNTIL)
    for name, until in governance.shared_rest_until().items():
        merged[name] = max(until, merged.get(name, 0.0))
    return merged


def _rest(name: str, seconds: float, reason: str) -> None:
    from genai import governance

    _COOLDOWN_UNTIL[name] = max(_COOLDOWN_UNTIL.get(name, 0.0), time.time() + seconds)
    governance.share_rest(name, seconds, reason)


def fallback_chain(primary: GenAIProvider) -> list[GenAIProvider]:
    """The providers named in MDARIX_GENAI_FALLBACKS (comma-separated, in order), each read from MDARIX_GENAI_<NAME>_*.

    Example: MDARIX_GENAI_FALLBACKS=cerebras,gemini,ollama with MDARIX_GENAI_CEREBRAS_API_KEY=... and so on.
    Free tiers suit demonstrations on synthetic data only: several may use the requests to improve their models.
    """
    names = [name.strip().lower() for name in os.getenv("MDARIX_GENAI_FALLBACKS", "").split(",") if name.strip()]
    for name, reason in unusable_fallbacks(names).items():
        if name not in _WARNED_FALLBACKS:
            _WARNED_FALLBACKS.add(name)
            logger.warning("GenAI fallback %s is skipped: %s", name, reason)
    return [
        GenAIProvider(
            provider_name=name,
            # A local model loads into memory on its first request, so Ollama keeps its longer default.
            timeout_seconds=os.getenv(f"MDARIX_GENAI_{name.upper()}_TIMEOUT_SECONDS")
            or (max(primary.timeout, 120) if name == "ollama" else primary.timeout),
            max_retries=int(os.getenv(f"MDARIX_GENAI_{name.upper()}_MAX_RETRIES", "1")),
            max_input_tokens=primary.max_input,
            max_output_tokens=primary.max_output,
            fallbacks=[],
        )
        for name in names
        if name != primary.provider_name and name in OPENAI_COMPATIBLE
    ]


def unusable_fallbacks(names: list[str] | None = None) -> dict[str, str]:
    """Names in MDARIX_GENAI_FALLBACKS that cannot be used, with the reason (shown in health, logged at start)."""
    if names is None:
        names = [name.strip().lower() for name in os.getenv("MDARIX_GENAI_FALLBACKS", "").split(",") if name.strip()]
    return {
        name: RETIRED_PROVIDERS.get(name, "not a supported provider name")
        for name in names
        if name not in OPENAI_COMPATIBLE
    }
