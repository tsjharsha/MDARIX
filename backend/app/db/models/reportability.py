"""The reportability watch (migration md41).

- ``reportability_settings``: one row per organization: the reporting windows it entered from its own procedure (name,
  markets, what starts the clock, days, calendar or work days, a note) and how far back the watch looks. Without a row
  nothing is set: the watch lists the complaints that need a decision, without due dates. Versioned.
- ``complaint_reportability``: a person's reportability decision on one complaint: REPORTED (with the report's
  reference and the day it was filed) or NOT_REPORTABLE, with the rationale, and the binding window and due date at
  the time, so a later change of the windows never rewrites whether a decision was on time. One current decision per
  complaint; a revision replaces it and both are in the audit trail. MDARIX never submits a report and never changes
  the complaint itself.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

__all__ = ["REPORTABILITY_DECISIONS", "ComplaintReportability", "ReportabilitySettings"]

REPORTABILITY_DECISIONS = ("REPORTED", "NOT_REPORTABLE")


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class ReportabilitySettings(Base):
    """An organization's reporting windows (reportability/rules.py). Without a row none is set."""

    __tablename__ = "reportability_settings"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    windows = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("365"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_reportability_settings_tenant"),
        CheckConstraint("lookback_days BETWEEN 30 AND 3650", name="lookback_days_range"),
    )


class ComplaintReportability(Base):
    """A person's reportability decision on one complaint."""

    __tablename__ = "complaint_reportability"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # REPORTED only: the report's reference (an MDR or vigilance number) and the day it was filed.
    report_reference: Mapped[str | None] = mapped_column(String(120))
    reported_on = mapped_column(Date)
    # The binding window when the person decided (its name and due date), if any.
    window_name: Mapped[str | None] = mapped_column(String(100))
    due_on = mapped_column(Date)
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "complaint_id", name="uq_complaint_reportability_complaint"),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_reportability_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint("decision IN ('REPORTED', 'NOT_REPORTABLE')", name="decision_known"),
        CheckConstraint(
            "decision <> 'REPORTED' OR (report_reference IS NOT NULL AND reported_on IS NOT NULL)",
            name="report_recorded",
        ),
    )
