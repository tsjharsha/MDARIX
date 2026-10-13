"""CAPA effectiveness checks (migration md41).

``capa_effectiveness_checks``: the check of one CAPA, in rounds. A round is planned (what will show the action worked,
the day to check, and the day the measurement starts), may be re-planned with a reason while it is PLANNED, and ends
with a signed result: EFFECTIVE or NOT_EFFECTIVE, with the person's summary and the evidence they saw (the complaint
recurrence before and after the action). After a NOT_EFFECTIVE result a new round can be planned. The signature itself
is a signed approval record in the control database (object type ``CapaEffectivenessCheck``), referenced here.
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

__all__ = ["EFFECTIVENESS_STATUSES", "CapaEffectivenessCheck"]

EFFECTIVENESS_STATUSES = ("PLANNED", "EFFECTIVE", "NOT_EFFECTIVE")


class CapaEffectivenessCheck(Base):
    __tablename__ = "capa_effectiveness_checks"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PLANNED")
    criteria: Mapped[str] = mapped_column(Text, nullable=False)
    planned_on = mapped_column(Date, nullable=False)
    measured_from = mapped_column(Date, nullable=False)
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    planned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    planned_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    result_summary: Mapped[str | None] = mapped_column(Text)
    evidence = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    signature_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    signed_by: Mapped[str | None] = mapped_column(String(255))
    signer_role: Mapped[str | None] = mapped_column(String(60))
    signed_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "capa_id", "round", name="uq_capa_effectiveness_checks_round"),
        ForeignKeyConstraint(
            ["tenant_id", "capa_id"],
            ["capas.tenant_id", "capas.id"],
            name="fk_capa_effectiveness_checks_capa",
            ondelete="CASCADE",
        ),
        CheckConstraint("status IN ('PLANNED', 'EFFECTIVE', 'NOT_EFFECTIVE')", name="status_known"),
        CheckConstraint("round >= 1", name="round_positive"),
        CheckConstraint("measured_from <= planned_on", name="measured_before_check"),
        CheckConstraint(
            "status = 'PLANNED' OR (signed_by IS NOT NULL AND signed_at IS NOT NULL AND result_summary IS NOT NULL)",
            name="result_signed",
        ),
    )
