"""Bounded GenAI provider boundary.

No provider is contacted unless explicitly configured.  Responses are
structured and never retain hidden chain-of-thought; only a short rationale
summary is returned for human review.
"""

from __future__ import annotations
import json, os, re, threading, time
from dataclasses import dataclass, replace
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
    # Anthropic is called through its own Messages API (ANTHROPIC_MESSAGES_API below), not the OpenAI-compatible
    # shim, which Anthropic does not offer for production use. For production under a commercial agreement only
    # (genai/policy.py, docs/compliance/AI_PROVIDER_REGISTER.md).
    "anthropic": ("https://api.anthropic.com/v1/messages", "claude-sonnet-5-5"),
    # Gemini on Google Cloud Vertex AI, through Vertex's OpenAI-compatible endpoint. Its address names the Google
    # Cloud project and region (vertex_url below), and it signs in without an API key (vertex_token below).
    "vertex": (None, "google/gemini-2.5-flash"),
    "ollama": (OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL),
    # OmniRoute: a self-hosted gateway that forwards each request to the upstream providers configured in it. The model
    # name is an OmniRoute model or combo; set MDARIX_GENAI_OMNIROUTE_MODEL to the one you configured.
    "omniroute": ("http://127.0.0.1:20128/v1/chat/completions", "auto"),
    # FreeLLMAPI: a self-hosted router on the same server (loopback only) for the free-trial chain, sample data only
    # (owner decisions AI-D14a, AI-D2a). It names the upstream that answered in its X-Routed-Via header.
    "freellmapi": ("http://127.0.0.1:3011/v1/chat/completions", "auto"),
}
# The free-trial chain (MDARIX_AI_TRIAL_CHAIN, empty by default = off): the providers a Free Trial organization's
# sample-data requests may go to, in order. A paid organization never uses it (genai/vetted.py has the register).
TRIAL_CHAIN_SETTING = "MDARIX_AI_TRIAL_CHAIN"
# A trial request is a person's click on the sample (review G4): each provider gets a short wait and the whole chain
# at most TRIAL_DEADLINE_SECONDS; a provider that failed rests (REST_SECONDS) and is skipped until then, so the next
# click does not wait for it again. When every provider rests or fails, the answer is GENAI_AI_BUSY at once.
TRIAL_TIMEOUTS = {"freellmapi": 15}
TRIAL_DEFAULT_TIMEOUT = 10
TRIAL_DEADLINE_SECONDS = 20.0
# Seconds a trial-chain provider rests after each kind of failure (genai/provider.py _classify).
REST_SECONDS = {"UNAVAILABLE": 60.0, "RATE_LIMITED": 900.0, "KEY_REFUSED": 3600.0, "UPSTREAM_NOT_VETTED": 3600.0}
ORGANISATION_TRIAL = "TRIAL"
ORGANISATION_PAID = "PAID"
# Vertex AI: asia-south1 (Mumbai) keeps the processing in India. The access token comes from the metadata server of
# the Google Cloud VM, for the service account attached to it: no key is stored, and the token lasts about an hour.
VERTEX_DEFAULT_LOCATION = "asia-south1"
VERTEX_TOKEN_URL = "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token"
# Providers that sign in without an API key: a model on MDARIX's own server, or Vertex AI through the VM's identity.
KEYLESS_PROVIDERS = frozenset({"ollama", "vertex"})
_VERTEX_TOKEN: dict[str, object] = {"value": None, "expires": 0.0}


def vertex_url(project: str | None, location: str | None) -> str | None:
    """Vertex AI's chat-completions address for a Google Cloud project and region; None without a project."""
    if not project or not project.strip():
        return None
    location = (location or VERTEX_DEFAULT_LOCATION).strip()
    return (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project.strip()}"
        f"/locations/{location}/endpoints/openapi/chat/completions"
    )


def vertex_token(timeout: float) -> str:
    """An access token for Vertex AI from the VM's metadata server, reused until a minute before it expires."""
    if _VERTEX_TOKEN["value"] and time.time() < float(_VERTEX_TOKEN["expires"]):
        return str(_VERTEX_TOKEN["value"])
    req = request.Request(VERTEX_TOKEN_URL, headers={"Metadata-Flavor": "Google"})
    with request.urlopen(req, timeout=timeout) as response:
        raw = json.loads(response.read())
    token = raw.get("access_token")
    if not token:
        raise GenAIUnavailable("GENAI_PROVIDER_UNAVAILABLE: no Vertex AI access token")
    _VERTEX_TOKEN["value"] = token
    _VERTEX_TOKEN["expires"] = time.time() + max(0, int(raw.get("expires_in") or 0) - 60)
    return token


# Providers in OPENAI_COMPATIBLE that speak their own Messages API instead of chat completions.
ANTHROPIC_MESSAGES_API = frozenset({"anthropic"})
ANTHROPIC_VERSION = "2023-06-01"
# Anthropic models that accept an effort setting. Short advisory answers ask for low effort, so the model's thinking
# does not use up the output allowance before the answer is written.
ANTHROPIC_EFFORT_MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7")


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


# Why no model answered, as a stable code with the sentence a user sees. Callers show the sentence and fall back to
# rules; the detailed reason (str(exc)) stays in logs and provenance.
REFUSAL_MESSAGES = {
    "GENAI_MONTHLY_BUDGET_REACHED": (
        "Your organization's monthly AI allowance is used up; an administrator can raise it."
    ),
    "GENAI_DISABLED_FOR_ORGANIZATION": (
        "AI processing is switched off for your organization; an administrator can enable it under "
        "Security › AI processing."
    ),
    "GENAI_OFF_FOR_FREE_TRIAL": ("AI is not switched on for this trial, so MDARIX answered from its rules."),
    "GENAI_PROVIDER_NOT_ALLOWED": (
        "No AI service approved for customer data is configured here, so MDARIX answered from its rules; "
        "please contact MDARIX support."
    ),
    "GENAI_INSUFFICIENT_EVIDENCE": (
        "None of your records answers this question closely enough, so MDARIX did not ask AI to guess. Rephrase "
        "the question, or ask it from an investigation."
    ),
    "GENAI_UNAVAILABLE": (
        "The AI service is not available right now, so MDARIX answered from its rules; please try again in a "
        "few minutes."
    ),
    "GENAI_FEATURE_UNKNOWN": (
        "This request names no known AI feature, so no AI was used and MDARIX answered from its rules."
    ),
    "GENAI_FEATURE_NOT_OFFERED": ("This AI feature is not offered, so MDARIX answered from its rules."),
    "GENAI_FEATURE_OFF_ON_PLATFORM": (
        "This AI feature is not switched on for this service, so MDARIX answered from its rules."
    ),
    "GENAI_FEATURE_OFF_FOR_ORGANIZATION": (
        "This AI feature is switched off for your organization; an administrator can turn it on under "
        "Security › AI processing."
    ),
    # A free trial's person whose own AI flag a Platform Administrator set INACTIVE.
    "GENAI_USER_AI_INACTIVE": "AI is not enabled for your account, so MDARIX answered from its rules.",
    # Free trials use AI on the sample data only (owner decision AI-D14a): never on the trial's own records.
    # Every trial-chain provider failed or is resting after a failure: answered at once, not after a long wait.
    "GENAI_AI_BUSY": (
        "AI is busy right now, so MDARIX answered from its rules; where the sample has a recorded AI answer it is "
        "still shown, marked as recorded. Please try again in a minute."
    ),
    "GENAI_TRIAL_SAMPLE_ONLY": (
        "AI available on paid plans. In the free trial, AI works on the sample data only, so MDARIX answered "
        "from its rules."
    ),
}


def refusal_code(reason: str) -> str:
    """The stable code for a detailed reason ("GENAI_PROVIDER_UNAVAILABLE: URLError" -> GENAI_UNAVAILABLE)."""
    head = str(reason or "").split(":", 1)[0].strip().upper()
    return head if head in REFUSAL_MESSAGES else "GENAI_UNAVAILABLE"


class GenAIUnavailable(RuntimeError):
    """No model may or can answer this request. ``reason`` is the detailed cause; ``code`` and ``user_message`` are
    the stable refusal shown to people (REFUSAL_MESSAGES)."""

    def __init__(self, reason: str = "GENAI_UNAVAILABLE"):
        super().__init__(reason)
        self.reason = str(reason)
        self.code = refusal_code(self.reason)
        self.user_message = REFUSAL_MESSAGES[self.code]

    def refusal(self) -> dict:
        """The refusal as an API answer: {status: REFUSED, code, user_message}."""
        return {"status": "REFUSED", "code": self.code, "user_message": self.user_message}


# Grounded material is sent inside delimiters, so the model can tell the request from the records: the context as
# JSON in <context>, each evidence record in <evidence id="...">. Text inside a record that looks like one of these
# tags is defused so a record cannot close its own block and pose as an instruction.
_DELIMITER_TAG = re.compile(r"(?i)<(\s*/?\s*(?:evidence|context)\b)")
_ATTRIBUTE_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]")


def _defuse(text: str) -> str:
    return _DELIMITER_TAG.sub(r"&lt;\1", text)


def _evidence_body(item: dict) -> str:
    text = item.get("text")
    if isinstance(text, str):
        header = {key: value for key, value in item.items() if key not in {"id", "text"} and value not in (None, "")}
        return (json.dumps(header, default=str) + "\n" if header else "") + text
    return json.dumps({key: value for key, value in item.items() if key != "id"}, default=str)


def user_content(prompt: str, context: dict, evidence: list[dict] | None = None) -> str:
    """The user message: the request, then the context and each evidence record in their own delimited block."""
    parts = [prompt, "", "<context>", _defuse(json.dumps(context, default=str)), "</context>"]
    for item in evidence or []:
        identifier = _ATTRIBUTE_UNSAFE.sub("", str(item.get("id") or item.get("evidence_identifier") or "unknown"))
        parts += [f'<evidence id="{identifier[:80]}">', _defuse(_evidence_body(item)), "</evidence>"]
    return "\n".join(parts)


def _strip_code_fence(answer: str) -> str:
    """Some models wrap a JSON reply in a Markdown code fence; the JSON inside is the reply."""
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


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
    # Per-call facts (AI-R 4.3, trial chain 2.4): the gateway is ``provider``; the upstream is who actually answered.
    upstream_provider: str | None = None
    upstream_model: str | None = None
    region: str | None = None
    thinking_tokens: int = 0
    organisation_type: str | None = None
    chain: str | None = None
    chain_position: int | None = None
    attempts: tuple = ()
    call_id: str | None = None


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
        if self.provider_name == "vertex" and not self.base_url:
            self.base_url = vertex_url(os.getenv(prefix + "PROJECT"), os.getenv(prefix + "LOCATION"))
        self.api_key = api_key or os.getenv(prefix + "API_KEY")
        self.model = model or os.getenv(prefix + "MODEL", known_model)
        self.model_version = os.getenv(prefix + "MODEL_VERSION", "unconfigured")
        default_timeout = "120" if self.provider_name == "ollama" else "20"
        # An empty setting (the production template leaves MDARIX_GENAI_COST_PER_1K_TOKENS empty) means the default.
        self.timeout = int(timeout_seconds or os.getenv("MDARIX_GENAI_TIMEOUT_SECONDS") or default_timeout)
        self.retries = int(max_retries if max_retries is not None else os.getenv("MDARIX_GENAI_MAX_RETRIES") or "2")
        self.max_input = int(max_input_tokens or os.getenv("MDARIX_GENAI_MAX_INPUT_TOKENS") or "4000")
        self.max_output = int(max_output_tokens or os.getenv("MDARIX_GENAI_MAX_OUTPUT_TOKENS") or "1000")
        self.cost_per_1k = float(cost_per_1k_tokens or os.getenv("MDARIX_GENAI_COST_PER_1K_TOKENS") or "0")
        # Fallbacks only for the primary provider (a fallback never has fallbacks of its own).
        self.fallbacks = fallbacks if fallbacks is not None else ([] if provider_name else fallback_chain(self))

    @property
    def configured(self) -> bool:
        return bool(self.base_url and (self.api_key or self.provider_name in KEYLESS_PROVIDERS))

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
        feature: str | None = None,
        records: list[dict] | None = None,
        user_text: str | None = None,
        system: str | None = None,
        json_output: bool = False,
        response_schema: dict | None = None,
        max_output_tokens: int | None = None,
        evidence: list[dict] | None = None,
    ) -> GenAIResult:
        """system/json_output/max_output_tokens are for structured analysis; defaults keep the plain request.

        ``feature`` (``genai/features.py``) is required: a request without a known feature is refused before anything
        else. ``evidence`` (records with an ``id`` and ``text`` or fields) is sent in delimited ``<evidence id="...">``
        blocks after the context (``user_content``), masked and redacted like the context. ``records`` lists every
        record whose content is in the prompt, context or evidence (``{"table", "id"}``, plus ``evidence_id`` naming
        its evidence block): a Free Trial organization's request is sent only when each is unedited sample data
        (``genai/sample_gate.py``). ``user_text`` is free text the person typed (the Ask question).

        Order (every refusal comes before any network code): feature known -> nothing configured = no AI -> feature
        on the platform list -> the organization's switches and budget (its type: trial or paid) -> trial: the
        sample-data gate and the trial chain; paid: the paid provider and its fallbacks. A paid organization never
        reaches the trial chain, and a trial organization never reaches the paid provider."""
        from genai import features, pii

        item = features.known(feature)
        if not item.offered:
            # Not offered at all (AI-D5): refused before anything else, whatever the switches say.
            raise GenAIUnavailable(f"GENAI_FEATURE_NOT_OFFERED: {item.key}")
        safe_prompt = SENSITIVE.sub(lambda m: m.group(1) + ": [REDACTED]", prompt)
        safe_context = redact_context(context or {})
        safe_evidence = redact_context(list(evidence or []))
        if pii.enabled():
            # Personal information never leaves for a model (genai/pii.py); identifiers of records are kept.
            safe_prompt = pii.mask_text(safe_prompt)
            safe_context = pii.mask(safe_context)
            safe_evidence = pii.mask(safe_evidence)
        sizes = len(safe_prompt) + len(json.dumps(safe_context, default=str)) + len(system or "")
        input_tokens = max(1, (sizes + len(json.dumps(safe_evidence, default=str))) // 4)
        if input_tokens > self.max_input:
            raise GenAIUnavailable("GENAI_INPUT_TOKEN_LIMIT")
        started = time.monotonic()
        trial_names = trial_chain_names()
        # Fallbacks stand in for a configured primary only: with no paid provider and no trial chain (controlled
        # mode) no model is called and nothing is read.
        if not self.configured and not trial_names:
            return self._controlled(input_tokens, started)
        features.check_platform(item)
        from genai.policy import allowed

        paid_chain = [
            provider
            for provider in [self, *self.fallbacks]
            if provider.configured and allowed(provider.provider_name, provider.model) and _paid_may_use(provider)
        ]
        if self.configured and not paid_chain and not trial_names:
            # Every configured provider is forbidden here (for example a free tier in production): no model is called.
            logger.error("No AI provider may receive customer data in this environment; answering without a model")
            raise GenAIUnavailable("GENAI_PROVIDER_NOT_ALLOWED")
        from genai import governance

        # The organization's switches, its feature switch and its budget; also whether it is a free trial.
        access = governance.check_allowed(
            input_tokens + (max_output_tokens or self.max_output), feature=item.key, trial_chain_on=bool(trial_names)
        )
        call = _Call(
            feature=item,
            prompt=safe_prompt,
            context=safe_context,
            evidence=safe_evidence,
            system=system,
            json_output=json_output,
            response_schema=response_schema,
            max_output_tokens=max_output_tokens,
            input_tokens=input_tokens,
            started=started,
            records=list(records or []),
        )
        if access.trial:
            return self._complete_trial(access, call, user_text)
        if not self.configured:
            return self._controlled(input_tokens, started)
        if not paid_chain:
            logger.error("No AI provider may receive this organization's data here; answering without a model")
            raise GenAIUnavailable("GENAI_PROVIDER_NOT_ALLOWED")
        resting_until = _resting_until()
        resting = [provider for provider in paid_chain if resting_until.get(provider.provider_name, 0) > time.time()]
        # Providers that are resting are tried last, so a request still gets an answer if every provider rests.
        ordered = [provider for provider in paid_chain if provider not in resting] + resting
        last_error: GenAIUnavailable | None = None
        attempts: list[dict] = []
        for position, provider in enumerate(ordered, start=1):
            try:
                result = provider._send(
                    safe_prompt,
                    safe_context,
                    evidence=safe_evidence,
                    system=system,
                    json_output=json_output,
                    response_schema=response_schema,
                    max_output_tokens=max_output_tokens,
                    input_tokens=input_tokens,
                    started=started,
                    fail_fast=len(ordered) > 1,
                )
            except GenAIUnavailable as exc:
                last_error = exc
                attempts.append({"provider": provider.provider_name, "outcome": exc.reason[:120]})
                logger.warning("GenAI provider %s unavailable; trying the next one", provider.provider_name)
                continue
            result = replace(
                result,
                organisation_type=ORGANISATION_PAID,
                chain="paid",
                chain_position=position,
                attempts=tuple(attempts),
            )
            return _finish(access, call, result)
        _record_failure(access, call, attempts, ORGANISATION_PAID, "paid")
        raise last_error or GenAIUnavailable("GENAI_PROVIDER_UNAVAILABLE: no provider")

    def _controlled(self, input_tokens: int, started: float) -> GenAIResult:
        return GenAIResult(
            "controlled",
            self.model,
            CONFIG_VERSION,
            {
                "status": "PROVIDER_NOT_CONFIGURED",
                "answer": None,
                "limitations": ["No AI service is set up here, so no AI was used."],
                "human_review_required": True,
                "causality_state": "NOT_ESTABLISHED",
            },
            input_tokens,
            0,
            0.0,
            int((time.monotonic() - started) * 1000),
        )

    def _complete_trial(self, access, call: "_Call", user_text: str | None) -> GenAIResult:
        """A Free Trial organization: sample data only, through the trial chain, with the failover rules."""
        from genai import governance, sample_gate

        # Before any network code: every record in the request must be unedited sample data of this organization.
        sample_gate.check(access.tenant_id, records=call.records, evidence=call.evidence, user_text=user_text)
        chain = trial_chain(self)
        if not chain:
            governance.count_refusal(access.tenant_id)
            raise GenAIUnavailable("GENAI_PROVIDER_NOT_ALLOWED: no usable provider in the trial chain")
        # Resting providers are skipped, not tried last (review G4): one that just failed would only fail again.
        resting_until = _resting_until()
        ordered = [provider for provider in chain if resting_until.get(provider.provider_name, 0) <= time.time()]
        if not ordered:
            governance.count_refusal(access.tenant_id)
            raise GenAIUnavailable("GENAI_AI_BUSY: every trial provider is resting after a failure")
        deadline = time.monotonic() + TRIAL_DEADLINE_SECONDS
        attempts: list[dict] = []
        for provider in ordered:
            position = chain.index(provider) + 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                attempts.append({"provider": provider.provider_name, "outcome": "DEADLINE"})
                break
            try:
                result = provider._send_once(call, timeout=min(float(provider.timeout), remaining))
            except _Failover as exc:
                attempts.append({"provider": provider.provider_name, "outcome": exc.kind, "status": exc.status})
                logger.warning(
                    "Trial AI provider %s failed (%s); %s",
                    provider.provider_name,
                    exc.kind,
                    "stopping" if exc.stop else "trying the next one",
                )
                if exc.stop:
                    break
                _after_failure(provider.provider_name, exc.kind)
                continue
            result = replace(
                result,
                organisation_type=ORGANISATION_TRIAL,
                chain="trial",
                chain_position=position,
                attempts=tuple(attempts),
            )
            return _finish(access, call, result)
        _record_failure(access, call, attempts, ORGANISATION_TRIAL, "trial")
        raise GenAIUnavailable(f"GENAI_AI_BUSY: trial chain ({len(attempts)} tried)")

    def _payload(
        self,
        content: str,
        *,
        system: str | None,
        json_output: bool,
        response_schema: dict | None,
        max_output_tokens: int | None,
        safe_prompt: str,
        safe_context: dict,
        evidence: list[dict] | None,
    ) -> bytes:
        if self.provider_name in ANTHROPIC_MESSAGES_API:
            # Anthropic Messages API: the system prompt is a top-level field, and current models refuse sampling
            # parameters such as temperature, so none is sent.
            body = {
                "model": self.model,
                "max_tokens": max_output_tokens or self.max_output,
                "messages": [{"role": "user", "content": content}],
            }
            if system:
                body["system"] = system
            if self.model.startswith(ANTHROPIC_EFFORT_MODELS):
                body["output_config"] = {"effort": "low"}
            return json.dumps(body).encode()
        if self.provider_name in OPENAI_COMPATIBLE:
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0,
            }
            if self.provider_name == "groq":
                body["max_completion_tokens"] = max_output_tokens or self.max_output
            else:
                body["max_tokens"] = max_output_tokens or self.max_output
            if system:
                body["messages"].insert(0, {"role": "system", "content": system})
            if self.provider_name == "vertex":
                # Gemini Flash may spend the output allowance on thinking; a low effort leaves room for the answer.
                body["reasoning_effort"] = (os.getenv("MDARIX_GENAI_VERTEX_REASONING_EFFORT") or "low").strip().lower()
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
            return json.dumps(body).encode()
        context = {**safe_context, "evidence": evidence} if evidence else safe_context
        return json.dumps(
            {"model": self.model, "prompt": safe_prompt, "context": context, "max_tokens": self.max_output}
        ).encode()

    def _open(self, payload: bytes, timeout: float):
        """One HTTP request: the parsed reply and its headers."""
        req = request.Request(
            self.base_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MDARIX-R1/1.0",
            },
        )
        if self.provider_name in ANTHROPIC_MESSAGES_API:
            req.add_header("x-api-key", self.api_key or "")
            req.add_header("anthropic-version", ANTHROPIC_VERSION)
        elif self.provider_name == "vertex" and not self.api_key:
            req.add_header("Authorization", f"Bearer {vertex_token(timeout)}")
        elif self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        with request.urlopen(req, timeout=timeout) as response:
            raw = json.loads(response.read())
            headers = getattr(response, "headers", None)
        return raw, headers

    def _parse(self, raw: dict, *, json_output: bool, input_tokens: int, started: float) -> GenAIResult:
        """The reply as a result; ``InvalidStructuredOutput`` when a structured request got no JSON object."""
        thinking = 0
        if self.provider_name in ANTHROPIC_MESSAGES_API:
            if raw.get("stop_reason") == "refusal":
                raise InvalidStructuredOutput("the model declined the request")
            texts = [
                block.get("text") or ""
                for block in raw.get("content") or []
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            answer = "".join(texts) or None
            usage = raw.get("usage") or {}
            output_tokens = int(usage.get("output_tokens") or max(1, len(str(answer or "")) // 4))
            input_tokens = int(usage.get("input_tokens") or input_tokens)
        elif self.provider_name in OPENAI_COMPATIBLE:
            answer = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content")
            usage = raw.get("usage") or {}
            output_tokens = int(usage.get("completion_tokens") or max(1, len(str(answer or "")) // 4))
            input_tokens = int(usage.get("prompt_tokens") or input_tokens)
            details = usage.get("completion_tokens_details") or {}
            thinking = int((details.get("reasoning_tokens") if isinstance(details, dict) else 0) or 0)
        else:
            answer = raw.get("answer", raw.get("output", raw.get("text")))
            output_tokens = min(self.max_output, max(1, len(str(answer or "")) // 4))
        if json_output:
            if not isinstance(answer, str) or not answer.strip():
                raise InvalidStructuredOutput("empty structured response")
            answer = _strip_code_fence(answer)
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
            upstream_provider=self.provider_name,
            upstream_model=str(raw.get("model") or self.model) if isinstance(raw, dict) else self.model,
            region=provider_region(self),
            thinking_tokens=thinking,
        )

    def _send_once(self, call: "_Call", *, timeout: float) -> GenAIResult:
        """One trial-chain attempt, no retries (the next provider is the retry). Raises ``_Failover`` with the
        failure's kind: the caller moves on, or stops for a request that would fail everywhere (400, 413)."""
        from genai import vetted

        content = user_content(call.prompt, call.context, call.evidence)
        payload = self._payload(
            content,
            system=call.system,
            json_output=call.json_output,
            response_schema=call.response_schema,
            max_output_tokens=call.max_output_tokens,
            safe_prompt=call.prompt,
            safe_context=call.context,
            evidence=call.evidence,
        )
        try:
            raw, headers = self._open(payload, timeout)
        except urlerror.HTTPError as exc:
            raise _Failover.from_status(exc.code) from exc
        except GenAIUnavailable as exc:
            raise _Failover("UNAVAILABLE") from exc
        except (urlerror.URLError, OSError, ValueError) as exc:
            # Connection refused, DNS failure, timeout (an OSError) or an unreadable reply.
            raise _Failover("UNAVAILABLE") from exc
        try:
            upstream = vetted.identify(self.provider_name, headers=headers, raw=raw, configured_model=self.model)
        except vetted.UpstreamNotVetted as exc:
            # The answer is discarded unread: it came from (or may have come from) a provider not vetted.
            logger.error("Trial AI reply discarded: %s", exc)
            raise _Failover("UPSTREAM_NOT_VETTED") from exc
        try:
            result = self._parse(
                raw, json_output=call.json_output, input_tokens=call.input_tokens, started=call.started
            )
        except InvalidStructuredOutput as exc:
            raise _Failover("INVALID_OUTPUT") from exc
        return replace(
            result,
            upstream_provider=upstream.provider,
            upstream_model=upstream.model,
            region=vetted_region(upstream.provider),
        )

    def _send(
        self,
        safe_prompt: str,
        safe_context: dict,
        *,
        evidence: list[dict] | None = None,
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
        content = user_content(safe_prompt, safe_context, evidence)
        payload = self._payload(
            content,
            system=system,
            json_output=json_output,
            response_schema=response_schema,
            max_output_tokens=max_output_tokens,
            safe_prompt=safe_prompt,
            safe_context=safe_context,
            evidence=evidence,
        )
        error = None
        for attempt in range(self.retries + 1):
            try:
                raw, _headers = self._open(payload, self.timeout)
                return self._parse(raw, json_output=json_output, input_tokens=input_tokens, started=started)
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
        reason = "GENAI_PROVIDER_UNAVAILABLE"
        if isinstance(error, InvalidStructuredOutput):
            reason = "GENAI_PROVIDER_UNAVAILABLE: INVALID_OUTPUT"
        raise GenAIUnavailable(f"{reason}: {type(error).__name__}")


@dataclass(frozen=True)
class _Call:
    """One request as it is sent: masked, redacted and sized."""

    feature: object
    prompt: str
    context: dict
    evidence: list
    system: str | None
    json_output: bool
    response_schema: dict | None
    max_output_tokens: int | None
    input_tokens: int
    started: float
    records: list


class _Failover(Exception):
    """A trial-chain attempt failed; ``kind`` decides what happens next (``REST_SECONDS``; ``stop`` ends the chain)."""

    def __init__(self, kind: str, status: int | None = None, stop: bool = False):
        super().__init__(kind)
        self.kind = kind
        self.status = status
        self.stop = stop

    @classmethod
    def from_status(cls, status: int) -> "_Failover":
        if status == 429:
            return cls("RATE_LIMITED", status)
        if status in (401, 403):
            return cls("KEY_REFUSED", status)
        if status in (400, 413):
            # Our request is wrong or too big: it would fail at every provider, so the rules answer at once.
            return cls("REQUEST_REFUSED", status, stop=True)
        return cls("UNAVAILABLE", status)


# When this process last alerted about a trial provider being down (UNAVAILABLE), by provider name.
_DOWN_ALERTED_AT: dict[str, float] = {}
DOWN_ALERT_SECONDS = 3600.0


def _after_failure(name: str, kind: str) -> None:
    """Rest a failed trial provider for its kind of failure; tell the operators about a key or upstream problem, and
    (at most once an hour per process) about a provider that is down (review G10: a down gateway was silent)."""
    seconds = REST_SECONDS.get(kind)
    if seconds:
        _rest(name, seconds, kind)
    if kind in ("KEY_REFUSED", "UPSTREAM_NOT_VETTED"):
        advice = "Check its key, or the upstreams configured in it against the vetted-provider register."
    elif kind == "UNAVAILABLE" and time.time() - _DOWN_ALERTED_AT.get(name, 0.0) >= DOWN_ALERT_SECONDS:
        # shortcut: once an hour per process (each worker may alert once); share it across processes if that is noisy.
        _DOWN_ALERTED_AT[name] = time.time()
        advice = "It did not answer: check that the gateway runs on the server and the forwarders are healthy."
    else:
        return
    body = f"Trial AI provider {name} failed with {kind}; it rests for {int(seconds or 0)} seconds. {advice}"
    _alert_beside_the_request(body)


def _alert_beside_the_request(body: str) -> None:
    """Sent in its own thread: a person's click does not wait for the alert channel (webhook up to 10 s)."""
    threading.Thread(target=_send_provider_alert, args=(body,), daemon=True).start()


def _send_provider_alert(body: str) -> None:
    try:
        from backend.app.alerts import send_alert

        send_alert("Trial AI provider problem", body)
    except Exception:
        logger.exception("Trial AI provider alert could not be sent")


def _finish(access, call: _Call, result: GenAIResult) -> GenAIResult:
    """An answered request: count its tokens and write its call record (genai/call_record.py)."""
    from genai import call_record, governance

    governance.record_usage(access.tenant_id, result.input_tokens, result.output_tokens, result.estimated_cost)
    call_id = call_record.write(access, call, result, outcome="ANSWERED")
    return replace(result, call_id=call_id) if call_id else result


def _record_failure(access, call: _Call, attempts: list[dict], organisation_type: str, chain: str) -> None:
    """Every provider failed after a request was sent: the call record says FAILED (or INVALID_OUTPUT), no output."""
    from genai import call_record

    if not attempts:
        return
    invalid = all("INVALID_OUTPUT" in str(item.get("outcome")) for item in attempts)
    call_record.write(
        access,
        call,
        None,
        outcome="INVALID_OUTPUT" if invalid else "FAILED",
        organisation_type=organisation_type,
        chain=chain,
        attempts=attempts,
    )


def provider_region(provider: GenAIProvider) -> str | None:
    """Where a provider processes the request, when its address says so (Vertex names its region)."""
    if provider.provider_name == "vertex" and provider.base_url:
        match = re.match(r"https://([a-z0-9-]+)-aiplatform\.googleapis\.com/", provider.base_url)
        return match.group(1) if match else None
    return None


def vetted_region(name: str) -> str | None:
    from genai import vetted

    for row in vetted.load().get("providers") or []:
        if str(row.get("provider") or "").lower() == name:
            return row.get("region")
    return None


def trial_chain_names() -> list[str]:
    """``MDARIX_AI_TRIAL_CHAIN`` as written (comma-separated, in order); empty = no AI for free trials."""
    return [name.strip().lower() for name in os.getenv(TRIAL_CHAIN_SETTING, "").split(",") if name.strip()]


def paid_provider_names() -> set[str]:
    """Providers for paid organizations only: never in the trial chain (keeps paid keys away from trial traffic)."""
    from genai.policy import contracted_providers

    return {"vertex", "anthropic", *contracted_providers()}


def trial_only_names() -> set[str]:
    """Providers registered for the trial chain (genai/vetted_providers.json): never for a paid organization."""
    from genai import vetted

    return {
        str(row.get("provider") or "").lower()
        for row in vetted.load().get("providers") or []
        if row.get("chain") == vetted.TRIAL_CHAIN
    }


def _paid_may_use(provider: GenAIProvider) -> bool:
    """In staging and production a paid organization's request never goes to a trial-chain provider."""
    from backend.app.runtime_env import is_production_like

    return not (is_production_like() and provider.provider_name in trial_only_names())


def is_loopback(url: str | None) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url or "").hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def trial_chain_problems(names: list[str] | None = None) -> dict[str, str]:
    """Names in ``MDARIX_AI_TRIAL_CHAIN`` that may not be used, with the reason."""
    from backend.app.runtime_env import is_production_like
    from genai import vetted

    names = trial_chain_names() if names is None else names
    register = vetted.load()
    paid = paid_provider_names()
    found = {}
    for name in names:
        if name in paid:
            found[name] = "a paid provider may not stand in the trial chain"
            continue
        if name not in OPENAI_COMPATIBLE:
            found[name] = "not a supported provider name"
            continue
        problem = vetted.chain_problem(name, register)
        if problem:
            found[name] = problem
            continue
        if is_production_like() and name in ("freellmapi", "omniroute"):
            url = os.getenv(f"MDARIX_GENAI_{name.upper()}_BASE_URL") or OPENAI_COMPATIBLE[name][0]
            if not is_loopback(url):
                found[name] = "its address must be on this server (127.0.0.1)"
    return found


def trial_chain(primary: GenAIProvider) -> list[GenAIProvider]:
    """The usable trial-chain providers, in order: vetted, configured, and (in staging and production) on loopback."""
    names = trial_chain_names()
    problems = trial_chain_problems(names)
    for name, reason in problems.items():
        if name not in _WARNED_FALLBACKS:
            _WARNED_FALLBACKS.add(name)
            logger.warning("Trial AI provider %s is skipped: %s", name, reason)
    chain = []
    for name in dict.fromkeys(names):
        if name in problems:
            continue
        provider = GenAIProvider(
            provider_name=name,
            timeout_seconds=os.getenv(f"MDARIX_GENAI_{name.upper()}_TIMEOUT_SECONDS")
            or TRIAL_TIMEOUTS.get(name, TRIAL_DEFAULT_TIMEOUT),
            max_retries=0,
            max_input_tokens=primary.max_input,
            max_output_tokens=primary.max_output,
            fallbacks=[],
        )
        if provider.configured:
            chain.append(provider)
    return chain


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
