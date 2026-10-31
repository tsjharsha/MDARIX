"""Complaint disposition (migration tr02, T-G36, T-U13).

``complaint_dispositions``: how one complaint is resolved, in versions, each signed with password and authenticator
code. The branches, in the order the person answers them: ``ESCALATED_BY_TRIGGER`` (an escalation trigger is met: a
case is opened at once), ``KNOWN_ISSUE`` (the complaint joins the scope of an open case as a contributing complaint),
``SERVICE_LEVEL`` (resolved at service level: troubleshooting, the discrete correction, its result, the service ticket
and the documented no-investigation rationale, ISO 13485:2016 clause 8.2.2, with the root-cause attribution) and
``ESCALATED_BY_CHOICE`` (a case is opened by the person's choice, with a reason). ``triggers`` keeps each trigger met at
signing with the field, value and record it came from; ``answers`` the answer and rationale of each question; a signed
version is never edited: a change is a new version, and the earlier one is marked ``superseded_by``.

Design note, columns the MVP adds later (nullable): the event (G28), the T30 due time and the trigger-set version.

``decisions.root_cause_attribution`` and ``decisions.attribution_reason`` (also tr02, nullable): the case decision's
root-cause attribution, required by the signing route for new signatures; decisions signed before stay as they are.
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

__all__ = ["ATTRIBUTIONS", "DISPOSITION_BRANCHES", "ComplaintDisposition"]

DISPOSITION_BRANCHES = ("ESCALATED_BY_TRIGGER", "KNOWN_ISSUE", "SERVICE_LEVEL", "ESCALATED_BY_CHOICE")
ATTRIBUTIONS = ("DEVICE_RELATED", "USE_RELATED", "ENVIRONMENT_RELATED", "UNDETERMINED")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


class ComplaintDisposition(Base):
    __tablename__ = "complaint_dispositions"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    branch: Mapped[str] = mapped_column(String(30), nullable=False)
    triggers = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    answers = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    service_record = mapped_column(JSONB)
    attribution: Mapped[str | None] = mapped_column(String(30))
    attribution_reason: Mapped[str | None] = mapped_column(Text)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    routine_path: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    hands_on_seconds: Mapped[int | None] = mapped_column(Integer)
    change_reason: Mapped[str | None] = mapped_column(Text)
    signed_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    signed_at = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "complaint_id", "version", name="uq_complaint_dispositions_version"),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_dispositions_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(_in("branch", DISPOSITION_BRANCHES), name="branch_known"),
        CheckConstraint(f"attribution IS NULL OR {_in('attribution', ATTRIBUTIONS)}", name="attribution_known"),
        CheckConstraint(
            "branch <> 'SERVICE_LEVEL' OR (attribution IS NOT NULL AND service_record IS NOT NULL)",
            name="service_level_complete",
        ),
        CheckConstraint("attribution <> 'UNDETERMINED' OR attribution_reason IS NOT NULL", name="undetermined_reason"),
        CheckConstraint(
            "branch NOT IN ('KNOWN_ISSUE', 'ESCALATED_BY_TRIGGER', 'ESCALATED_BY_CHOICE') OR investigation_id IS NOT NULL",
            name="case_linked",
        ),
        Index("ix_complaint_dispositions_tenant_complaint", "tenant_id", "complaint_id"),
    )
