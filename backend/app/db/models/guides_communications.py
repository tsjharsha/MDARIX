"""The customer's own decision guide versions and the external communications log (migration tr06; T-G15 and T-G30 of
the trial, MVP G15 and G30).

- ``decision_guide_versions``: the organization's own version of a market's guide (version 1 is MDARIX's starter, in
  code, never stored). A version holds every question as the customer worded it (the core questions keep their id and
  the fixed conclusion logic; extra questions are recorded but never drive a conclusion), each with its clause and its
  basis in the standards catalog, its test cases and their last results. States: DRAFT, AWAITING_APPROVAL, PUBLISHED,
  SUPERSEDED, DISCARDED. A second person approves with password and authenticator code (a signed approval record);
  approval publishes it. Never edited after approval.
- ``external_parties``: a reporter, distributor, hospital or service partner, with a primary and a second contact.
- ``communication_entries``: one message sent or received, with its purpose, owner, reply due date, attempts (each
  with its time, channel, contact and outcome, and when it was logged), status (OPEN, ANSWERED, UNRESOLVED, CLOSED),
  evidence references and the QMS record it links to. ``logged_at`` against ``occurred_at`` counts S4.
- ``communication_settings``: the organization's number of unanswered attempts before a request moves on (default 3).

MDARIX sends nothing to an external contact: people send from their own mail and record it here. ``source_system`` is
``MDARIX_SAMPLE`` on the sample's rows. All four are tenant-isolated (FORCE row-level security). Design note, columns
the MVP adds later (nullable): the event (G28), G33's routing of distributor contacts, the first-contact guide on the
same versions (G32), the harm-severity scale's own versions.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
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

__all__ = [
    "COMMUNICATION_STATUSES",
    "GUIDE_STATES",
    "PARTY_TYPES",
    "CommunicationEntry",
    "CommunicationSettings",
    "DecisionGuideVersion",
    "ExternalParty",
]

GUIDE_STATES = ("DRAFT", "AWAITING_APPROVAL", "PUBLISHED", "SUPERSEDED", "DISCARDED")
PARTY_TYPES = ("REPORTER", "DISTRIBUTOR", "HOSPITAL", "SERVICE_PARTNER")
DIRECTIONS = ("SENT", "RECEIVED")
PURPOSES = ("INFORMATION_REQUEST", "UPDATE", "RESPONSE")
COMMUNICATION_STATUSES = ("OPEN", "ANSWERED", "UNRESOLVED", "CLOSED")
CONTACTS = ("PRIMARY", "SECOND")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant():
    return mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)


def _tz(nullable: bool = True):
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class DecisionGuideVersion(Base):
    __tablename__ = "decision_guide_versions"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    based_on: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    questions = mapped_column(JSONB, nullable=False)
    test_cases = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    test_results = mapped_column(JSONB)
    change_reason: Mapped[str | None] = mapped_column(Text)
    editors = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    requested_by: Mapped[str | None] = mapped_column(String(255))
    requested_at = _tz()
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at = _tz()
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    published_at = _tz()
    superseded_at = _tz()
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at = _tz(False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "market", "version", name="uq_decision_guide_versions_version"),
        UniqueConstraint("tenant_id", "code", name="uq_decision_guide_versions_code"),
        CheckConstraint(_in("state", GUIDE_STATES), name="state_known"),
        CheckConstraint("version >= 2", name="customer_version"),
        CheckConstraint(
            "state NOT IN ('PUBLISHED', 'SUPERSEDED') OR (approved_by IS NOT NULL AND signed_record_id IS NOT NULL)",
            name="published_signed",
        ),
        Index(
            "uq_decision_guide_versions_open",
            "tenant_id",
            "market",
            unique=True,
            postgresql_where=text("state IN ('DRAFT', 'AWAITING_APPROVAL')"),
        ),
        Index(
            "uq_decision_guide_versions_published",
            "tenant_id",
            "market",
            unique=True,
            postgresql_where=text("state = 'PUBLISHED'"),
        ),
    )


class ExternalParty(Base):
    __tablename__ = "external_parties"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    party_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # A reporter belongs to one complaint; a distributor, hospital or service partner to none.
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    primary_name: Mapped[str | None] = mapped_column(String(200))
    primary_details: Mapped[str | None] = mapped_column(String(300))
    second_name: Mapped[str | None] = mapped_column(String(200))
    second_details: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at = _tz(False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_external_parties_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("party_type", PARTY_TYPES), name="party_type_known"),
        Index("ix_external_parties_tenant_type", "tenant_id", "party_type"),
    )


class CommunicationEntry(Base):
    __tablename__ = "communication_entries"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    intake_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    party_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("external_parties.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(String(400), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at = _tz(False)
    logged_at = _tz(False)
    logged_by: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(255))
    reply_due_on = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="CLOSED")
    current_contact: Mapped[str] = mapped_column(String(10), nullable=False, server_default="PRIMARY")
    attempts = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    evidence = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    qms_reference: Mapped[str | None] = mapped_column(String(120))
    in_reply_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("communication_entries.id"))
    # What raised it: {"type": "MarketAssessment", "market": "US", "questions": [...]} or {"type": "IntakeEvent", ...}.
    origin = mapped_column(JSONB)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closed_at = _tz()
    closed_by: Mapped[str | None] = mapped_column(String(255))
    close_note: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str | None] = mapped_column(String(40))
    updated_at = _tz(False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_communication_entries_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("direction", DIRECTIONS), name="direction_known"),
        CheckConstraint(_in("purpose", PURPOSES), name="purpose_known"),
        CheckConstraint(_in("status", COMMUNICATION_STATUSES), name="status_known"),
        CheckConstraint(_in("current_contact", CONTACTS), name="contact_known"),
        CheckConstraint("complaint_id IS NOT NULL OR intake_event_id IS NOT NULL", name="has_subject"),
        Index("ix_communication_entries_tenant_complaint", "tenant_id", "complaint_id"),
        Index("ix_communication_entries_tenant_status", "tenant_id", "status"),
    )


class CommunicationSettings(Base):
    """The organization's settings for the communications log. Without a row the defaults apply."""

    __tablename__ = "communication_settings"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    attempts_before_escalation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at = _tz(False)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_communication_settings_tenant"),
        CheckConstraint("attempts_before_escalation BETWEEN 1 AND 10", name="attempts_range"),
    )
