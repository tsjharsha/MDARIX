"""Complaint review (migration md40): the second look at records that may be hidden complaints, and the
organization's settings for it and for the complaint backlog.

- ``complaint_settings``: one row per organization: the target number of days within which a complaint should be in
  a signal or a case (the backlog board), and the words that mark a record as a possible complaint (the second look).
  Without a row the defaults apply. Versioned, like the signal rule settings.
- ``complaint_second_looks``: a person's decision on one record the second look flagged (cancelled, logged as an
  inquiry or service record, or a recurring No Fault Found / User Error): it is a complaint (CONFIRMED) or it is not
  (DISMISSED), with the reason. One current decision per record; a revised decision replaces it and the change is in
  the audit trail. MDARIX never changes the record itself: the source system stays the record of truth.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
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

__all__ = ["SECOND_LOOK_DECISIONS", "ComplaintSecondLook", "ComplaintSettings"]

SECOND_LOOK_DECISIONS = ("CONFIRMED", "DISMISSED")


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class ComplaintSettings(Base):
    """An organization's complaint review settings. Without a row the defaults apply (complaint_review/rules.py)."""

    __tablename__ = "complaint_settings"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    backlog_target_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    # Null: the default word list. Otherwise the organization's own list.
    second_look_words = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_complaint_settings_tenant"),
        CheckConstraint("backlog_target_days BETWEEN 1 AND 365", name="backlog_target_days_range"),
    )


class ComplaintSecondLook(Base):
    """A person's decision on a record the second look flagged."""

    __tablename__ = "complaint_second_looks"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # What the second look showed when the person decided: its reasons and signs.
    flagged = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "complaint_id", name="uq_complaint_second_looks_complaint"),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_second_looks_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint("decision IN ('CONFIRMED', 'DISMISSED')", name="decision_known"),
    )
