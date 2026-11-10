"""Reminders and escalation, the working calendar, absences and the event's closure (migration tr07; T-G25, T-G28 and
T-G9 of the trial, MVP G25, G28 and G9).

- ``oversight_settings``: the organization's working calendar (time zone, working weekdays, holidays) and its simple
  escalation rule (how many hours before the due time a reminder goes, and the role an overdue item escalates to).
  Without a row the defaults apply (UTC, Monday to Friday, no holidays, 24 hours, the Leader role).
- ``user_absences``: a person's absence (from, to) with the colleague who covers it. The backup receives the person's
  reminders and escalations; ownership stays, and a backup never gains a signing right.
- ``due_alerts``: one reminder or escalation of one dated item for one person, with its read state. The sweep raises
  and resolves them from the items' own records; an alert never closes or changes the item.
- ``event_closures``: one complaint's event owner, its "ready to close in the QMS" signature (with the checklist as
  signed, and the reason when items were still open) and the QMS filing reference of its event decision record.

All four are tenant-isolated (FORCE row-level security). ``source_system`` is ``MDARIX_SAMPLE`` on the sample's rows.
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

__all__ = ["ALERT_TIERS", "READY_STATES", "DueAlert", "EventClosure", "OversightSettings", "UserAbsence"]

ALERT_TIERS = ("REMINDER", "ESCALATION")
CASE_FLOWS = ("ONE_RECORD", "SERVICE_FIRST")
DELIVERIES = ("DELIVERED", "FAILED", "RETRYING")
READY_STATES = ("READY", "READY_WITH_REASON")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant():
    return mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)


def _tz(nullable: bool = True):
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class OversightSettings(Base):
    __tablename__ = "oversight_settings"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    time_zone: Mapped[str] = mapped_column(String(60), nullable=False, server_default="UTC")
    work_days = mapped_column(JSONB, nullable=False, server_default=text("'[0, 1, 2, 3, 4]'::jsonb"))
    holidays = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    reminder_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("24"))
    escalation_role: Mapped[str] = mapped_column(String(60), nullable=False, server_default="LEADER")
    swept_at = _tz()
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at = _tz(False)

    # tr19 (0.10.93, B2): the fast-track triage target in clock hours (1-24, OD-7), how Cases become complaints, and
    # the imported-backlog rule (OD-12).
    triage_fast_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4"))
    case_flow: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ONE_RECORD")
    backlog_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    backlog_target_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    # tr25 (B7): the opt-in urgent e-mail alert (off by default), the allowed sender domains, the daily e-mail limit.
    urgent_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    mail_allowed_domains = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    mail_daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("200"))

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_oversight_settings_tenant"),
        CheckConstraint("reminder_hours BETWEEN 1 AND 168", name="reminder_range"),
        CheckConstraint("triage_fast_hours BETWEEN 1 AND 24", name="fast_hours_range"),
        CheckConstraint(_in("case_flow", CASE_FLOWS), name="case_flow_known"),
        CheckConstraint("backlog_days >= 1 AND backlog_target_days >= 1", name="backlog_range"),
        CheckConstraint("mail_daily_limit BETWEEN 1 AND 5000", name="mail_limit_range"),
    )


class RecordOwnership(Base):
    """The system of record per domain (tr19, operating modes M3): MDARIX or the customer's own system. No row: a
    trial reads MDARIX, a pilot EXTERNAL."""

    __tablename__ = "record_ownership"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    owner: Mapped[str] = mapped_column(String(10), nullable=False)
    system_name: Mapped[str | None] = mapped_column(String(120))
    set_by: Mapped[str] = mapped_column(String(255), nullable=False)
    set_at = _tz(False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", name="uq_record_ownership_domain"),
        CheckConstraint("owner IN ('MDARIX', 'EXTERNAL')", name="owner_known"),
    )


class UserAbsence(Base):
    __tablename__ = "user_absences"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_on = mapped_column(Date, nullable=False)
    ends_on = mapped_column(Date, nullable=False)
    backup_id: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    cancelled_by: Mapped[str | None] = mapped_column(String(255))
    cancelled_at = _tz()

    __table_args__ = (
        CheckConstraint("starts_on <= ends_on", name="dates_ordered"),
        CheckConstraint("backup_id <> user_id", name="backup_other"),
        Index("ix_user_absences_tenant_user", "tenant_id", "user_id"),
    )


class DueAlert(Base):
    __tablename__ = "due_alerts"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    item_key: Mapped[str] = mapped_column(String(200), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(120))
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner_id: Mapped[str | None] = mapped_column(String(255))
    due_at = _tz(False)
    opens = mapped_column(JSONB)
    raised_at = _tz(False)
    read_at = _tz()
    resolved_at = _tz()
    # tr19 (A2): the channel, the attempts and the delivery result; a failed delivery never resolves the alert.
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="IN_APP")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_attempt_at = _tz()
    delivery: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DELIVERED")
    delivery_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "item_key", "tier", "recipient_id", name="uq_due_alerts_item"),
        CheckConstraint(_in("tier", ALERT_TIERS), name="tier_known"),
        CheckConstraint(_in("delivery", DELIVERIES), name="delivery_known"),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        Index("ix_due_alerts_tenant_recipient", "tenant_id", "recipient_id"),
    )


class EventClosure(Base):
    __tablename__ = "event_closures"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(255))
    owner_set_by: Mapped[str | None] = mapped_column(String(255))
    owner_set_at = _tz()
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ready_state: Mapped[str | None] = mapped_column(String(20))
    ready_reason: Mapped[str | None] = mapped_column(Text)
    checklist = mapped_column(JSONB)
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signed_by: Mapped[str | None] = mapped_column(String(255))
    signed_at = _tz()
    qms_filing_ref: Mapped[str | None] = mapped_column(String(120))
    filed_by: Mapped[str | None] = mapped_column(String(255))
    filed_at = _tz()
    source_system: Mapped[str | None] = mapped_column(String(40))
    updated_at = _tz(False)
    # tr25 (B7): MDARIX Complete closes the complaint by the Resolve and close signature; reopening needs a reason.
    closed_at = _tz()
    closed_by: Mapped[str | None] = mapped_column(String(255))
    reopened_at = _tz()
    reopened_by: Mapped[str | None] = mapped_column(String(255))
    reopen_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "complaint_id", name="uq_event_closures_complaint"),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_event_closures_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"ready_state IS NULL OR {_in('ready_state', READY_STATES)}", name="ready_known"),
        CheckConstraint(
            "ready_state IS NULL OR (signed_record_id IS NOT NULL AND signed_by IS NOT NULL AND signed_at IS NOT NULL)",
            name="ready_signed",
        ),
        CheckConstraint("ready_state <> 'READY_WITH_REASON' OR ready_reason IS NOT NULL", name="reason_given"),
        CheckConstraint(
            "closed_at IS NULL OR (closed_by IS NOT NULL AND ready_state IS NOT NULL)", name="closed_signed"
        ),
        CheckConstraint("reopened_at IS NULL OR reopen_reason IS NOT NULL", name="reopen_reason"),
    )
