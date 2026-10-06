"""Case reviews and the controlled Decision Brief (migration md32).

- ``case_reviews``: a risk or regulatory review of a case (REV000001 per organization): who asked and why, whether
  policy required it, who reviewed it under which role, the outcome and its rationale, what was assessed (risks,
  markets) and which scope version it covered. A review is never edited after completion; a new review supersedes it.
- ``decision_brief_versions``: the controlled Decision Brief (DBV000001 per organization), one row per version. A
  version is editable only while DRAFT; once submitted it is frozen (content and its SHA-256 fingerprint), and any
  further change is a new version. Status: DRAFT, READY_FOR_REVIEW, UNDER_REVIEW, RETURNED, APPROVED_FOR_DECISION,
  SUPERSEDED.
- ``brief_review_actions``: each quality-review action on a brief version (accept for decision, return, reject the
  proposed conclusion, escalate) with the reviewer's comment and role. Never updated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from backend.app.db.business_id import business_id_column

__all__ = [
    "REVIEW_TYPES",
    "REVIEW_STATUSES",
    "RISK_OUTCOMES",
    "REGULATORY_OUTCOMES",
    "BRIEF_STATUSES",
    "QUALITY_ACTIONS",
    "CaseReview",
    "DecisionBriefVersion",
    "BriefReviewAction",
]

REVIEW_TYPES = ("RISK", "REGULATORY")
REVIEW_STATUSES = ("REQUESTED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "SUPERSEDED")
RISK_OUTCOMES = (
    "NO_CHANGE_REQUIRED",
    "RISK_FILE_REASSESSMENT_REQUIRED",
    "RISK_CONTROL_REVIEW_REQUIRED",
    "ADDITIONAL_EVIDENCE_REQUIRED",
    "ESCALATE_SAFETY_CONCERN",
)
REGULATORY_OUTCOMES = (
    "NO_REPORTABILITY_CONCERN_IDENTIFIED",
    "REPORTABILITY_ASSESSMENT_COMPLETE",
    "REPORTING_REQUIRED",
    "TREND_REPORTING_REVIEW_REQUIRED",
    "ADDITIONAL_EVIDENCE_REQUIRED",
    "ESCALATE_REGULATORY",
)
BRIEF_STATUSES = ("DRAFT", "READY_FOR_REVIEW", "UNDER_REVIEW", "RETURNED", "APPROVED_FOR_DECISION", "SUPERSEDED")
QUALITY_ACTIONS = (
    "START_REVIEW",
    "ACCEPT_FOR_DECISION",
    "RETURN_FOR_EVIDENCE",
    "RETURN_FOR_ANALYSIS",
    "RETURN_FOR_RISK_REVIEW",
    "RETURN_FOR_REGULATORY_REVIEW",
    "REJECT_PROPOSED_CONCLUSION",
    "ESCALATE",
)


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


class CaseReview(Base):
    __tablename__ = "case_reviews"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    business_id: Mapped[str] = business_id_column()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="REQUESTED")
    required_by_policy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    policy_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_role: Mapped[str | None] = mapped_column(String(60))
    request_reason: Mapped[str | None] = mapped_column(Text)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewer_role: Mapped[str | None] = mapped_column(String(60))
    outcome: Mapped[str | None] = mapped_column(String(60))
    rationale: Mapped[str | None] = mapped_column(Text)
    assessed: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    scope_version: Mapped[int | None] = mapped_column(Integer)
    brief_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_at = mapped_column(DateTime(timezone=True))
    completed_at = mapped_column(DateTime(timezone=True))
    superseded_reason: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_case_reviews_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_case_reviews_investigation",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"review_type IN ({_quoted(REVIEW_TYPES)})", name="review_type_known"),
        CheckConstraint(f"status IN ({_quoted(REVIEW_STATUSES)})", name="status_known"),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_quoted(sorted(set(RISK_OUTCOMES + REGULATORY_OUTCOMES)))})",
            name="outcome_known",
        ),
        Index("ix_case_reviews_tenant_case", "tenant_id", "investigation_id"),
        Index("ix_case_reviews_tenant_status", "tenant_id", "review_type", "status"),
    )


class DecisionBriefVersion(Base):
    __tablename__ = "decision_brief_versions"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    business_id: Mapped[str] = business_id_column()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Assembled from the case's records when the version is composed or refreshed (sections, inventories, reviews).
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # What the author writes: problem statement, proposed conclusion, recommended actions, notes, AI assistance used.
    narrative: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    readiness: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    scope_version: Mapped[int | None] = mapped_column(Integer)
    source_ai_brief_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_role: Mapped[str | None] = mapped_column(String(60))
    submitted_by: Mapped[str | None] = mapped_column(String(255))
    submitted_at = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_decision_brief_versions_tenant_id_id"),
        UniqueConstraint("tenant_id", "investigation_id", "version", name="uq_decision_brief_versions_version"),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_decision_brief_versions_investigation",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_quoted(BRIEF_STATUSES)})", name="status_known"),
        Index("ix_decision_brief_versions_tenant_status", "tenant_id", "status"),
    )


class BriefReviewAction(Base):
    __tablename__ = "brief_review_actions"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    brief_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    actor_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[str | None] = mapped_column(String(60))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "brief_version_id"],
            ["decision_brief_versions.tenant_id", "decision_brief_versions.id"],
            name="fk_brief_review_actions_brief",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"action IN ({_quoted(QUALITY_ACTIONS)})", name="action_known"),
        Index("ix_brief_review_actions_tenant_brief", "tenant_id", "brief_version_id"),
    )
