"""History of people's judgements on a case's intelligence (migration md30).

AI output stays exactly as the AI produced it (``ai_executions``). What people decide about it, and what they add by
hand when AI is off or wrong, lives on the domain rows (hypotheses, hypothesis_evidence, unknowns, failure chains,
observations) and each change is recorded here: which object, what changed, why, by whom and under which role.
Never updated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

__all__ = ["HYPOTHESIS_HUMAN_STATUSES", "LINK_STATES", "EPISTEMIC_TYPES", "IntelligenceEvent"]

HYPOTHESIS_HUMAN_STATUSES = (
    "PROPOSED",
    "HYPOTHESIZED",
    "PARTIALLY_SUPPORTED",
    "STRONGLY_SUPPORTED",
    "WEAKLY_SUPPORTED",
    "CONTRADICTED",
    "RETIRED",
)
LINK_STATES = ("SUPPORTED", "PARTIALLY_SUPPORTED", "HYPOTHESIZED", "UNKNOWN", "CONTRADICTED")
EPISTEMIC_TYPES = ("FACT", "SOURCE_ASSERTION", "DERIVED_OBSERVATION", "AI_INTERPRETATION")


class IntelligenceEvent(Base):
    __tablename__ = "intelligence_events"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # HYPOTHESIS, HYPOTHESIS_EVIDENCE, UNKNOWN, FAILURE_CHAIN, FAILURE_CHAIN_LINK, OBSERVATION
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(60))
    to_value: Mapped[str | None] = mapped_column(String(60))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_ref: Mapped[str | None] = mapped_column(String(255))
    actor_role: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_intelligence_events_investigation",
            ondelete="CASCADE",
        ),
        Index("ix_intelligence_events_tenant_case", "tenant_id", "investigation_id"),
        Index("ix_intelligence_events_tenant_object", "tenant_id", "object_type", "object_id"),
    )
