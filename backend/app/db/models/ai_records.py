"""One record per AI call, and a person's decision on each AI output (AI-R spec 4.3 and 4.4; migration tr32).

- ``ai_calls``: written by ``GenAIProvider.complete`` (``genai/call_record.py``) for every request actually sent to a
  model, answered or not. It names the feature and its risk, the hashes of the prompt and of the masked content sent
  (never that content: owner decision AI-D11), the gateway and the provider and model that actually answered, the
  organisation type and chain with the providers tried before it, tokens (with thinking), latency, the outcome, and
  the output as returned with its hash. Refused requests write no row (they are counted in ``ai_usage_monthly``).
- ``ai_output_reviews``: a person accepts, edits (with the edited text and its hash) or rejects (with a reason) an AI
  output. A later review supersedes an earlier one; nothing is deleted.

Both tables are append-only (a trigger refuses UPDATE and DELETE) and carry the forced organization row-level policy.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.models.foundation import tenant_fk, tz, uuid_pk

__all__ = ["AI_CALL_OUTCOMES", "AI_REVIEW_DECISIONS", "AiCall", "AiOutputReview"]

AI_CALL_OUTCOMES = ("ANSWERED", "FAILED", "INVALID_OUTPUT")
AI_REVIEW_DECISIONS = ("ACCEPTED", "EDITED", "REJECTED")
ORGANISATION_TYPES = ("TRIAL", "PAID")


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


class AiCall(Base):
    __tablename__ = "ai_calls"
    id = uuid_pk()
    tenant_id = tenant_fk()
    user_ref: Mapped[str | None] = mapped_column(String(255))
    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    risk: Mapped[str] = mapped_column(String(10), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(200))
    model_version: Mapped[str | None] = mapped_column(String(120))
    upstream_provider: Mapped[str | None] = mapped_column(String(80))
    upstream_model: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(80))
    configuration_version: Mapped[str] = mapped_column(String(80), nullable=False)
    retrieval_policy_version: Mapped[str | None] = mapped_column(String(80))
    organisation_type: Mapped[str] = mapped_column(String(10), nullable=False)
    chain: Mapped[str] = mapped_column(String(10), nullable=False)
    chain_position: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    records: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    thinking_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text)
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_calls_tenant_id_id"),
        CheckConstraint(f"outcome IN ({_quoted(AI_CALL_OUTCOMES)})", name="ck_ai_calls_outcome_known"),
        CheckConstraint(f"organisation_type IN ({_quoted(ORGANISATION_TYPES)})", name="ck_ai_calls_type_known"),
        CheckConstraint("chain IN ('trial', 'paid')", name="ck_ai_calls_chain_known"),
        CheckConstraint("risk IN ('LOW', 'MEDIUM')", name="ck_ai_calls_risk_allowed"),
        CheckConstraint(
            "(outcome = 'ANSWERED') = (output_sha256 IS NOT NULL)", name="ck_ai_calls_output_when_answered"
        ),
        Index("ix_ai_calls_tenant_feature_created", "tenant_id", "feature", "created_at"),
    )


class AiOutputReview(Base):
    __tablename__ = "ai_output_reviews"
    id = uuid_pk()
    tenant_id = tenant_fk()
    ai_call_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_type: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    edited_text: Mapped[str | None] = mapped_column(Text)
    edited_text_sha256: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_output_reviews_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "ai_call_id"], ["ai_calls.tenant_id", "ai_calls.id"], name="fk_ai_output_reviews_call"
        ),
        CheckConstraint(f"decision IN ({_quoted(AI_REVIEW_DECISIONS)})", name="ck_ai_output_reviews_decision_known"),
        CheckConstraint(
            "decision <> 'EDITED' OR (edited_text IS NOT NULL AND edited_text_sha256 IS NOT NULL "
            "AND reason IS NOT NULL)",
            name="ck_ai_output_reviews_edit_complete",
        ),
        CheckConstraint("decision <> 'REJECTED' OR reason IS NOT NULL", name="ck_ai_output_reviews_reject_reason"),
        Index("ix_ai_output_reviews_tenant_subject", "tenant_id", "subject_type", "subject_id", "created_at"),
        Index("ix_ai_output_reviews_tenant_call", "tenant_id", "ai_call_id"),
    )
