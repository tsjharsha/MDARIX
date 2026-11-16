"""One ``ai_calls`` row per request sent to a model (AI-R 4.3; trial chain 2.4).

Written by ``GenAIProvider.complete`` in the organization's own session (the runtime role, bound to the organization,
so row-level security applies). The masked content sent is never stored, only its SHA-256 (owner decision AI-D11);
the output is stored as returned, with its hash. A refused request writes no row. When the row cannot be written the
answer is not shown: an AI output without its call record would have no audit trail.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("mdarix.genai")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash(call) -> str:
    """The request's instructions: the system text and the prompt (the template with the question)."""
    return sha256(f"{call.system or ''}\x00{call.prompt}")


def content_hash(call) -> str:
    """Everything sent, as masked and redacted: the user message (prompt, context, evidence blocks) and the system."""
    from genai.provider import user_content

    return sha256(f"{call.system or ''}\x00{user_content(call.prompt, call.context, call.evidence)}")


def _retrieval_policy(context: dict) -> str | None:
    for key in ("context_policy_version", "policy_version"):
        value = (context or {}).get(key)
        if isinstance(value, str) and value:
            return value[:80]
    grounded = (context or {}).get("grounded_context")
    return _retrieval_policy(grounded) if isinstance(grounded, dict) else None


def write(
    access,
    call,
    result,
    *,
    outcome: str,
    organisation_type: str | None = None,
    chain: str | None = None,
    attempts: list[dict] | None = None,
) -> str | None:
    """Write the call record; its id (None when there is no organization scope, in development)."""
    from backend.app.db.models.ai_records import AiCall
    from genai import governance
    from genai.provider import CONFIG_VERSION, GenAIUnavailable

    if access.tenant_id is None:
        return None
    answer = None
    if result is not None and outcome == "ANSWERED":
        raw = (result.output or {}).get("answer")
        answer = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    call_id = uuid.uuid4()
    row = AiCall(
        id=call_id,
        tenant_id=uuid.UUID(access.tenant_id),
        user_ref=access.user_id,
        feature=call.feature.key,
        risk=call.feature.risk,
        prompt_version=call.feature.prompt_version,
        prompt_sha256=prompt_hash(call),
        content_sha256=content_hash(call),
        provider=result.provider if result else None,
        model=result.model if result else None,
        model_version=result.model_version if result else None,
        upstream_provider=result.upstream_provider if result else None,
        upstream_model=result.upstream_model if result else None,
        region=result.region if result else None,
        configuration_version=CONFIG_VERSION,
        retrieval_policy_version=_retrieval_policy(call.context),
        organisation_type=(result.organisation_type if result else None) or organisation_type or "PAID",
        chain=(result.chain if result else None) or chain or "paid",
        chain_position=result.chain_position if result else None,
        attempts=list(result.attempts if result else (attempts or [])),
        records=[{key: str(value) for key, value in item.items()} for item in call.records],
        input_tokens=int(result.input_tokens) if result else int(call.input_tokens),
        output_tokens=int(result.output_tokens) if result else 0,
        thinking_tokens=int(result.thinking_tokens) if result else 0,
        latency_ms=int(result.latency_ms) if result else 0,
        outcome=outcome,
        output_text=answer,
        output_sha256=sha256(answer or "") if outcome == "ANSWERED" else None,
        created_at=datetime.now(timezone.utc),
    )
    try:
        db = governance._session(access.tenant_id)
        try:
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.exception("The AI call record could not be written")
        if outcome == "ANSWERED":
            raise GenAIUnavailable("GENAI_PROVIDER_UNAVAILABLE: call record not written") from exc
        return None
    return str(call_id)
