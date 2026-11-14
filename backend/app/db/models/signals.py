"""Post-market signals (migration md28): a group of related complaints that a person triages and dispositions.

- ``signals``: one signal (SIG000001 per organization), where it came from (a person, the threshold rule), its product
  and version, the problem it is about, suggested and confirmed priority, triage status and disposition. A duplicate or
  merged signal keeps its row and points at the canonical signal; nothing is deleted.
- ``signal_complaints``: the complaints a signal covers, and how each was added (rule, person, merge).
- ``signal_events``: what happened to a signal (created, triaged, prioritised, dispositioned, merged ...). Never
  updated; together with ``canonical_signal_id`` it is the signal's lineage.
- ``investigation_signals``: which signals an investigation was opened for (one or several, either way round).
- ``signal_rules``: an organization's detection rule settings (the complaint threshold rule), versioned.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from backend.app.db.business_id import business_id_column

__all__ = [
    "SIGNAL_ORIGINS",
    "SIGNAL_PRIORITIES",
    "SIGNAL_STATUSES",
    "OPEN_SIGNAL_STATUSES",
    "Signal",
    "SignalComplaint",
    "SignalEvent",
    "InvestigationSignal",
    "SignalRule",
]

# NEW: detected or created, nobody has looked yet. TRIAGE: being triaged. Dispositions: MONITOR, NO_ACTION, DUPLICATE,
# MERGED, INVESTIGATION_REQUIRED, ESCALATED. INVESTIGATION_OPEN once a case exists; DECISION_RECORDED when its case's
# decision is signed; CLOSED at the end.
SIGNAL_STATUSES = (
    "NEW",
    "TRIAGE",
    "MONITOR",
    "NO_ACTION",
    "DUPLICATE",
    "MERGED",
    "INVESTIGATION_REQUIRED",
    "ESCALATED",
    "INVESTIGATION_OPEN",
    "DECISION_RECORDED",
    "CLOSED",
)
# Statuses in which a signal still collects new complaints for its problem (the rule adds to it, not a new signal).
OPEN_SIGNAL_STATUSES = ("NEW", "TRIAGE", "MONITOR", "INVESTIGATION_REQUIRED", "ESCALATED", "INVESTIGATION_OPEN")
SIGNAL_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SIGNAL_ORIGINS = ("MANUAL", "THRESHOLD_RULE", "AI_SUGGESTED", "IMPORT")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Signal(Base):
    __tablename__ = "signals"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    business_id: Mapped[str] = business_id_column()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_code: Mapped[str | None] = mapped_column(String(60))
    rule_version: Mapped[int | None] = mapped_column(Integer)
    rule_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # The grouping the signal is about: product, version (when known) and problem (problem code, else complaint type).
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    problem_key: Mapped[str | None] = mapped_column(String(160))
    complaint_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    first_event_at = mapped_column(DateTime(timezone=True))
    last_event_at = mapped_column(DateTime(timezone=True))
    highest_severity: Mapped[str | None] = mapped_column(String(40))
    serious_harm: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    suggested_priority: Mapped[str | None] = mapped_column(String(20))
    confirmed_priority: Mapped[str | None] = mapped_column(String(20))
    priority_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="NEW")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_at = mapped_column(DateTime(timezone=True))
    canonical_signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    disposition_reason: Mapped[str | None] = mapped_column(Text)
    dispositioned_by: Mapped[str | None] = mapped_column(String(255))
    dispositioned_at = mapped_column(DateTime(timezone=True))
    monitor_review_date = mapped_column(Date)
    monitor_trigger: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_signals_version_of_product",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        UniqueConstraint("tenant_id", "id", name="uq_signals_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_signals_product"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.id"],
            name="fk_signals_product_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "canonical_signal_id"], ["signals.tenant_id", "signals.id"], name="fk_signals_canonical"
        ),
        CheckConstraint(f"status IN ({_quoted(SIGNAL_STATUSES)})", name="status_known"),
        CheckConstraint(f"origin IN ({_quoted(SIGNAL_ORIGINS)})", name="origin_known"),
        CheckConstraint(
            f"suggested_priority IS NULL OR suggested_priority IN ({_quoted(SIGNAL_PRIORITIES)})",
            name="suggested_priority_known",
        ),
        CheckConstraint(
            f"confirmed_priority IS NULL OR confirmed_priority IN ({_quoted(SIGNAL_PRIORITIES)})",
            name="confirmed_priority_known",
        ),
        Index("ix_signals_tenant_status", "tenant_id", "status"),
        Index("ix_signals_tenant_problem", "tenant_id", "product_id", "product_version_id", "problem_key"),
    )


class SignalComplaint(Base):
    __tablename__ = "signal_complaints"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    added_how: Mapped[str] = mapped_column(String(20), nullable=False)  # RULE | MANUAL | MERGE
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
    added_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("tenant_id", "signal_id", "complaint_id", name="uq_signal_complaints_signal_complaint"),
        ForeignKeyConstraint(
            ["tenant_id", "signal_id"],
            ["signals.tenant_id", "signals.id"],
            name="fk_signal_complaints_signal",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_signal_complaints_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint("added_how IN ('RULE', 'MANUAL', 'MERGE')", name="added_how_known"),
        Index("ix_signal_complaints_tenant_complaint", "tenant_id", "complaint_id"),
    )


class SignalEvent(Base):
    __tablename__ = "signal_events"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_ref: Mapped[str | None] = mapped_column(String(255))
    actor_role: Mapped[str | None] = mapped_column(String(60))
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "signal_id"],
            ["signals.tenant_id", "signals.id"],
            name="fk_signal_events_signal",
            ondelete="CASCADE",
        ),
        Index("ix_signal_events_tenant_signal", "tenant_id", "signal_id"),
    )


class InvestigationSignal(Base):
    __tablename__ = "investigation_signals"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "investigation_id", "signal_id", name="uq_investigation_signals_investigation_signal"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_investigation_signals_investigation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "signal_id"],
            ["signals.tenant_id", "signals.id"],
            name="fk_investigation_signals_signal",
            ondelete="CASCADE",
        ),
        Index("ix_investigation_signals_tenant_signal", "tenant_id", "signal_id"),
    )


class SignalRule(Base):
    """An organization's settings for one detection rule. Without a row the rule runs with its defaults."""

    __tablename__ = "signal_rules"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    min_complaints: Mapped[int] = mapped_column(Integer, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_run_at = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "rule_code", name="uq_signal_rules_tenant_rule"),
        CheckConstraint("min_complaints BETWEEN 2 AND 1000", name="min_complaints_range"),
        CheckConstraint("window_days BETWEEN 1 AND 365", name="window_days_range"),
    )
