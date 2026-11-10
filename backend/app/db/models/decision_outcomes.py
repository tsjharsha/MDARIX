"""What follows a signed human decision (migration md33).

- ``decision_follow_ups``: each follow-up action the decision maker chose while signing (CAPA, product change, field
  action review, risk reassessment, regulatory action), FUP000001 per organization, with its owner, task and status.
- ``impact_assessments``: evidence that reached a case after its decision was signed (IMP000001 per organization). A
  person assesses whether it changes the decision; the signed decision itself is never changed. A material impact
  reopens the case so a new decision can supersede the old one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column

__all__ = [
    "DECISION_OUTCOMES",
    "FIELD_ACTION_KINDS",
    "FOLLOW_UP_ACTIONS",
    "FOLLOW_UP_STATUSES",
    "IMPACT_CONCLUSIONS",
    "DecisionFollowUp",
    "ImpactAssessment",
]

# Outcomes a decision maker signs. Returning a case for more work is not a signed outcome; it sends the brief back.
DECISION_OUTCOMES = ("ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS", "REJECT_CONCLUSION", "CLOSE_NO_FURTHER_ACTION")
FOLLOW_UP_ACTIONS = (
    "CAPA_REQUIRED",
    "PRODUCT_CHANGE_REQUIRED",
    "FIELD_ACTION_REVIEW_REQUIRED",
    "RISK_REASSESSMENT_REQUIRED",
    "REGULATORY_ACTION_REQUIRED",
)
FOLLOW_UP_STATUSES = ("OPEN", "IN_PROGRESS", "DONE", "CANCELLED")
# B5 (tr26): the kind of a field action recorded on its follow-up.
FIELD_ACTION_KINDS = ("CORRECTION", "REMOVAL", "ADVISORY_NOTICE", "SOFTWARE_UPDATE", "OTHER")
IMPACT_CONCLUSIONS = ("NO_IMPACT", "MATERIAL_IMPACT")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


class DecisionFollowUp(Base):
    __tablename__ = "decision_follow_ups"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    business_id: Mapped[str] = business_id_column()
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assigned_role: Mapped[str | None] = mapped_column(String(60))
    due_at = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    capa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    completion_note: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[str | None] = mapped_column(String(255))
    completed_at = mapped_column(DateTime(timezone=True))
    # B5 (tr26): a field action or product change recorded lightly (reference, kind, effective date, lots/versions).
    action_reference: Mapped[str | None] = mapped_column(String(120))
    action_kind: Mapped[str | None] = mapped_column(String(30))
    action_effective_on = mapped_column(Date)
    action_scope = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "decision_id"],
            ["decisions.tenant_id", "decisions.id"],
            name="fk_decision_follow_ups_decision",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"action_type IN ({_quoted(FOLLOW_UP_ACTIONS)})", name="action_type_known"),
        CheckConstraint(f"status IN ({_quoted(FOLLOW_UP_STATUSES)})", name="status_known"),
        CheckConstraint(
            f"action_kind IS NULL OR action_kind IN ({_quoted(FIELD_ACTION_KINDS)})", name="action_kind_known"
        ),
        Index("ix_decision_follow_ups_tenant_case", "tenant_id", "investigation_id"),
    )


class ImpactAssessment(Base):
    __tablename__ = "impact_assessments"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    business_id: Mapped[str] = business_id_column()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)  # EVIDENCE_LINKED | EVIDENCE_REVIEWED | ...
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    conclusion: Mapped[str | None] = mapped_column(String(20))
    rationale: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[str | None] = mapped_column(String(255))
    assessed_role: Mapped[str | None] = mapped_column(String(60))
    assessed_at = mapped_column(DateTime(timezone=True))
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_impact_assessments_investigation",
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('OPEN', 'COMPLETED')", name="status_known"),
        CheckConstraint(
            f"conclusion IS NULL OR conclusion IN ({_quoted(IMPACT_CONCLUSIONS)})", name="conclusion_known"
        ),
        Index("ix_impact_assessments_tenant_case", "tenant_id", "investigation_id"),
    )
