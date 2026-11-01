"""Investigation scope and evidence review history (migration md29; excluded lots and the lot impact list, tr08).

- ``investigation_scope_versions``: every version of a case's scope (question, versions, included and excluded
  complaints with reasons, lots, markets, dates, failure modes, objectives). The latest version is the current scope;
  older ones are never changed, so a scope change keeps its before and after.
- ``evidence_review_events``: every change to how a case judges one piece of evidence (review status, relationship),
  who made it, under which role and why. Never updated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

__all__ = [
    "INVESTIGATION_STATES",
    "OPEN_INVESTIGATION_STATES",
    "EVIDENCE_REVIEW_STATUSES",
    "EVIDENCE_RELATIONSHIPS",
    "InvestigationScopeVersion",
    "EvidenceReviewEvent",
]

INVESTIGATION_STATES = (
    "OPEN",
    "IN_PROGRESS",
    "ON_HOLD",
    "BRIEF_IN_REVIEW",
    "READY_FOR_DECISION",
    "DECIDED",
    "CLOSED",
    "CANCELLED",
)
OPEN_INVESTIGATION_STATES = ("OPEN", "IN_PROGRESS", "ON_HOLD", "BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED")
EVIDENCE_REVIEW_STATUSES = (
    "UNREVIEWED",
    "ACCEPTED",
    "ACCEPTED_WITH_LIMITATION",
    "REJECTED",
    "QUARANTINED",
    "SUPERSEDED",
)
EVIDENCE_RELATIONSHIPS = ("SUPPORTING", "CONTRADICTING", "CONTEXTUAL", "UNRESOLVED", "UNRELATED", "UNREVIEWED")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class InvestigationScopeVersion(Base):
    __tablename__ = "investigation_scope_versions"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # Lists of ids (product versions, lots, failure modes), complaint ids, and [{complaint_id, reason}] exclusions.
    product_version_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    included_complaint_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    excluded_complaints: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    lot_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    markets: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    failure_mode_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    date_from = mapped_column(Date)
    date_to = mapped_column(Date)
    # tr08 (lot impact, T-G5): [{lot_id, reason}] lots a person left out of the case, and the lot impact list's
    # suspect factor and its last signed snapshot (backend/app/lot_impact/service.py); null before a factor is chosen.
    excluded_lots: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    lot_impact = mapped_column(JSONB)
    objectives: Mapped[str | None] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text)
    reviews_must_restart: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    conclusions_invalidated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_role: Mapped[str | None] = mapped_column(String(60))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "investigation_id", "version", name="uq_investigation_scope_versions_version"),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_investigation_scope_versions_investigation",
            ondelete="CASCADE",
        ),
    )


class EvidenceReviewEvent(Base):
    __tablename__ = "evidence_review_events"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # LINKED | REVIEWED
    from_review_status: Mapped[str | None] = mapped_column(String(30))
    to_review_status: Mapped[str | None] = mapped_column(String(30))
    from_relationship: Mapped[str | None] = mapped_column(String(30))
    to_relationship: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_ref: Mapped[str | None] = mapped_column(String(255))
    actor_role: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_evidence_review_events_investigation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["evidence.tenant_id", "evidence.id"],
            name="fk_evidence_review_events_evidence",
            ondelete="CASCADE",
        ),
        Index("ix_evidence_review_events_tenant_case", "tenant_id", "investigation_id"),
    )
