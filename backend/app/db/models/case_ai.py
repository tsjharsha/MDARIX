"""The case's one AI run (migration md42).

``case_ai_runs``: one run of the case's AI analysis in a single pass (analysis, competing explanations, challenges,
unknowns, failure chains and the investigation brief, each reusing the step before), started automatically when the
case page first opens or by a person. Each step's outcome is kept (done or failed, written by the language model or
by the rules when AI is off or unavailable, its AI run id); the steps' own results stay where they always were.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

__all__ = ["CASE_AI_RUN_STATUSES", "CASE_AI_RUN_TRIGGERS", "CaseAiRun"]

CASE_AI_RUN_STATUSES = ("QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "FAILED")
CASE_AI_RUN_TRIGGERS = ("AUTO", "MANUAL")


class CaseAiRun(Base):
    __tablename__ = "case_ai_runs"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="QUEUED")
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, server_default="MANUAL")
    as_of = mapped_column(DateTime(timezone=True), nullable=False)
    steps = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    started_at = mapped_column(DateTime(timezone=True))
    finished_at = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_case_ai_runs_investigation",
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')", name="status_known"),
        CheckConstraint("trigger IN ('AUTO', 'MANUAL')", name="trigger_known"),
        Index("ix_case_ai_runs_tenant_case", "tenant_id", "investigation_id", "requested_at"),
    )
