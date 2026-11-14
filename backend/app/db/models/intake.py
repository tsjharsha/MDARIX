"""The first contact, urgent intake and triage, and duplicates with import history (migration tr04; T-G32, T-G19,
T-G20 of the trial, MVP G32, G19 and G20).

- ``intake_events``: one occurrence as it reached the organization outside an import: a contact logged by the service
  desk (``CONTACT``), an urgent intake (``URGENT``), or an imported service record given the first-contact check from
  the second look (``SERVICE_RECORD``). It keeps the reporter's words verbatim and the separate times, each with its
  time zone (event, first knowledge by anyone acting for the manufacturer, receipt, awareness); ``created_at`` is when
  it became available in MDARIX. A contact's awareness is the time of the contact, and never moves.
- ``first_contact_checks``: the check's versions: the answers to the guide's questions, the guide's suggestion, the
  coordinator's signed classification (or an override with its reason), and the QA review of a "service only".
- ``triage_records``: the triage record of a flagged item (``subject_kind``: an intake, a complaint or a set-aside
  import row), with a manual escalation; the severity, the owners, the immediate action or why none is needed, and the
  confirmed awareness time.
- ``record_links``: a person's decision on a possible duplicate: two records linked into one event, a warning
  dismissed, or a link undone; each with its reason, and the event's awareness before and after the link.
- ``record_field_changes``: each field a re-upload changed on a record, with the import that changed it.

Design note, columns the MVP adds later (nullable): the event (G28) on intake events, triage records and links; the
customer's guide, harm-word and fault-word versions (G15); the T-table due times (G25); the communications-log entry of
each follow-up (G30). Follow-ups, the QMS-complaint task and the QA review are ``workflow_tasks`` of the intake event.
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

__all__ = [
    "CASE_STATES",
    "FIRST_CONTACT_OUTCOMES",
    "INTAKE_KINDS",
    "LINK_STATES",
    "TRIAGE_SUBJECTS",
    "CaseAddendum",
    "FirstContactCheck",
    "IntakeEvent",
    "RecordFieldChange",
    "RecordLink",
    "TriageRecord",
    "TriageRecordVersion",
]

INTAKE_KINDS = ("CONTACT", "URGENT", "SERVICE_RECORD")
FIRST_CONTACT_OUTCOMES = (
    "COMPLAINT",
    "BOTH",
    "SERVICE_ONLY",
    "PENDING",
    "PENDING_CONFIRM",
    "INQUIRY",
    "NOT_A_COMPLAINT",
)
# tr19: an incomplete draft's suggestion (an unanswered question is never Unknown); never a classification.
UNANSWERED = "UNANSWERED"
TRIAGE_SUBJECTS = ("INTAKE", "COMPLAINT", "QUARANTINE")
LINK_STATES = ("LINKED", "DISMISSED", "UNLINKED")
CASE_STATES = ("OPEN", "PENDING", "WAITING_INTERNAL", "IN_REVIEW", "CLOSED", "ESCALATED", "VOIDED")
# S-1: the service issue category (operational only); the code list and labels are in intake/case_rules.py.
ISSUE_CATEGORIES = (
    "MALFUNCTION",
    "PERFORMANCE",
    "SOFTWARE",
    "FIRMWARE",
    "HARDWARE",
    "CONNECTIVITY",
    "INSTALLATION",
    "CONFIGURATION",
    "USAGE_HELP",
    "MAINTENANCE",
    "ACCESSORIES",
    "CONSUMABLES",
    "TRAINING",
    "DELIVERY",
    "DOCUMENTATION",
    "WARRANTY",
    "OTHER",
)
ESCALATIONS = ("CREATED", "ATTACHED")
RECORD_OWNERS = ("MDARIX", "EXTERNAL")
PATIENTS = ("NONE", "ONE", "SEVERAL", "NOT_KNOWN")
TRIAGE_SPEEDS = ("FAST", "ROUTINE")
ADDENDUM_KINDS = ("STATEMENT", "WITHDRAWAL", "TECHNICIAN_FINDING", "CORRECTION_BY_REPORTER")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant():
    return mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)


def _tz(nullable: bool = True):
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class IntakeEvent(Base):
    __tablename__ = "intake_events"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    reference: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reporter_words: Mapped[str] = mapped_column(Text, nullable=False)
    reporter_type: Mapped[str | None] = mapped_column(String(40))
    reporter_site: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80))
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lot_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    requested: Mapped[str | None] = mapped_column(String(30))
    use_environment: Mapped[str | None] = mapped_column(String(30))
    user_type: Mapped[str | None] = mapped_column(String(30))
    event_at = _tz()
    event_zone: Mapped[str | None] = mapped_column(String(60))
    first_knowledge_at = _tz()
    first_knowledge_zone: Mapped[str | None] = mapped_column(String(60))
    first_knowledge_party: Mapped[str | None] = mapped_column(String(30))
    first_knowledge_basis: Mapped[str | None] = mapped_column(String(30))
    received_at = _tz()
    received_zone: Mapped[str | None] = mapped_column(String(60))
    awareness_at = _tz()
    awareness_zone: Mapped[str | None] = mapped_column(String(60))
    qms_ref: Mapped[str | None] = mapped_column(String(120))
    service_ticket: Mapped[str | None] = mapped_column(String(120))
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    updated_at = _tz(False)
    # tr19 (0.10.93, B2): the Case. Its state is set only by intake.service.set_case_status.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    request_key: Mapped[str | None] = mapped_column(String(80))
    owner_id: Mapped[str | None] = mapped_column(String(255))
    channel: Mapped[str | None] = mapped_column(String(40))
    channel_ref: Mapped[str | None] = mapped_column(String(200))
    product_text: Mapped[str | None] = mapped_column(String(200))
    lot_text: Mapped[str | None] = mapped_column(String(120))
    udi: Mapped[str | None] = mapped_column(String(120))
    software_version: Mapped[str | None] = mapped_column(String(60))
    hardware_revision: Mapped[str | None] = mapped_column(String(60))
    firmware_version: Mapped[str | None] = mapped_column(String(60))
    issue_category: Mapped[str | None] = mapped_column(String(20))
    # S-2: required before a Case signed service only is closed.
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    # ID-1: per device identifier, "Not sure", its status (confirmed / unconfirmed) and its source.
    identifiers = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    reporter_country: Mapped[str | None] = mapped_column(String(2))
    country_text: Mapped[str | None] = mapped_column(String(80))
    late_entry_reason: Mapped[str | None] = mapped_column(Text)
    no_contact_reason: Mapped[str | None] = mapped_column(Text)
    patients: Mapped[str | None] = mapped_column(String(12))
    harm_text: Mapped[str | None] = mapped_column(Text)
    troubleshooting: Mapped[str | None] = mapped_column(Text)
    service_status: Mapped[str | None] = mapped_column(String(20))
    service_status_at = _tz()
    masked = mapped_column(JSONB)
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    escalation: Mapped[str | None] = mapped_column(String(10))
    escalated_at = _tz()
    escalated_by: Mapped[str | None] = mapped_column(String(255))
    voided_at = _tz()
    voided_by: Mapped[str | None] = mapped_column(String(255))
    void_reason: Mapped[str | None] = mapped_column(Text)
    void_signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_identifier: Mapped[str | None] = mapped_column(String(255))
    last_synced_at = _tz()
    record_owner: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_intake_events_version_of_product",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        UniqueConstraint("tenant_id", "reference", name="uq_intake_events_reference"),
        UniqueConstraint("tenant_id", "id", name="uq_intake_events_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_intake_events_product"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"], ["complaints.tenant_id", "complaints.id"], name="fk_intake_events_complaint"
        ),
        CheckConstraint(_in("kind", INTAKE_KINDS), name="kind_known"),
        CheckConstraint(_in("status", CASE_STATES), name="status_known"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(f"escalation IS NULL OR {_in('escalation', ESCALATIONS)}", name="escalation_known"),
        CheckConstraint("status <> 'ESCALATED' OR complaint_id IS NOT NULL", name="escalated_complaint"),
        CheckConstraint(f"record_owner IS NULL OR {_in('record_owner', RECORD_OWNERS)}", name="record_owner_known"),
        CheckConstraint(f"patients IS NULL OR {_in('patients', PATIENTS)}", name="patients_known"),
        CheckConstraint("voided_at IS NULL OR void_reason IS NOT NULL", name="void_reason"),
        CheckConstraint(
            f"issue_category IS NULL OR {_in('issue_category', ISSUE_CATEGORIES)}", name="issue_category_known"
        ),
        Index("ix_intake_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_intake_events_tenant_status", "tenant_id", "status"),
        Index("ix_intake_events_tenant_owner", "tenant_id", "owner_id"),
        Index("ix_intake_events_tenant_complaint", "tenant_id", "complaint_id"),
        Index(
            "ix_intake_events_request_key",
            "tenant_id",
            "request_key",
            unique=True,
            postgresql_where=text("request_key IS NOT NULL"),
        ),
    )


class FirstContactCheck(Base):
    __tablename__ = "first_contact_checks"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    intake_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    guide_version: Mapped[str] = mapped_column(String(40), nullable=False)
    answers = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    unknowns: Mapped[str | None] = mapped_column(Text)
    suggestion: Mapped[str] = mapped_column(String(30), nullable=False)
    classification: Mapped[str | None] = mapped_column(String(30))
    override_reason: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    signed_by: Mapped[str | None] = mapped_column(String(255))
    signed_at = _tz()
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    review_outcome: Mapped[str | None] = mapped_column(String(20))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at = _tz()
    review_note: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    updated_at = _tz(False)
    # tr19: each recalculation of this version's suggestion (when, by whom, the answers changed, before -> after).
    history = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "intake_event_id"],
            ["intake_events.tenant_id", "intake_events.id"],
            name="fk_first_contact_checks_intake_event_id_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("intake_event_id", "version", name="uq_first_contact_checks_version"),
        CheckConstraint(_in("suggestion", (*FIRST_CONTACT_OUTCOMES, UNANSWERED)), name="suggestion"),
        CheckConstraint(
            f"classification IS NULL OR {_in('classification', FIRST_CONTACT_OUTCOMES)}", name="classification"
        ),
        CheckConstraint("classification IS NULL OR signed_at IS NOT NULL", name="signed"),
        CheckConstraint("review_outcome IS NULL OR review_outcome IN ('AGREED', 'RECLASSIFIED')", name="review_known"),
        Index("ix_first_contact_checks_tenant_event", "tenant_id", "intake_event_id"),
    )


class TriageRecord(Base):
    __tablename__ = "triage_records"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    subject_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    opened_at = _tz(False)
    target_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("24"))
    escalated_by: Mapped[str | None] = mapped_column(String(255))
    escalated_at = _tz()
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(20))
    public_health_threat: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    remedial_action: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    event_owner: Mapped[str | None] = mapped_column(String(255))
    triage_owner: Mapped[str | None] = mapped_column(String(255))
    backup_owner: Mapped[str | None] = mapped_column(String(255))
    immediate_action: Mapped[str | None] = mapped_column(Text)
    no_action_reason: Mapped[str | None] = mapped_column(Text)
    awareness_confirmed_at = _tz()
    awareness_note: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[str | None] = mapped_column(String(255))
    completed_at = _tz()
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    updated_at = _tz(False)
    # tr19 (0.10.93, B2): two speeds, versions, the floor, containment, signed exclusions, inheritance, QMS triage and
    # the acknowledgement of a fast-track item (A1).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    speed: Mapped[str | None] = mapped_column(String(10))
    due_at = _tz()
    potential_severity: Mapped[str | None] = mapped_column(String(20))
    severity_floor: Mapped[str | None] = mapped_column(String(20))
    floor_reasons = mapped_column(JSONB)
    flags_at_completion = mapped_column(JSONB)
    containment = mapped_column(JSONB)
    change_reason: Mapped[str | None] = mapped_column(Text)
    reopened_at = _tz()
    reopen_trigger: Mapped[str | None] = mapped_column(String(30))
    threat_excluded_at = _tz()
    threat_excluded_by: Mapped[str | None] = mapped_column(String(255))
    threat_exclusion_reason: Mapped[str | None] = mapped_column(Text)
    threat_signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    awareness_signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    inherited_from: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    qms_triaged_at = _tz()
    qms_owner_text: Mapped[str | None] = mapped_column(String(255))
    confirmed_by: Mapped[str | None] = mapped_column(String(255))
    confirmed_at = _tz()
    source_identifier: Mapped[str | None] = mapped_column(String(255))
    acknowledged_at = _tz()
    acknowledged_by: Mapped[str | None] = mapped_column(String(255))
    acknowledge_due_at = _tz()

    __table_args__ = (
        UniqueConstraint("tenant_id", "subject_kind", "subject_id", name="uq_triage_records_subject"),
        UniqueConstraint("tenant_id", "id", name="uq_triage_records_tenant_id_id"),
        CheckConstraint(_in("subject_kind", TRIAGE_SUBJECTS), name="subject_known"),
        CheckConstraint("target_hours BETWEEN 1 AND 168", name="target_range"),
        CheckConstraint(f"speed IS NULL OR {_in('speed', TRIAGE_SPEEDS)}", name="speed_known"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_triage_records_tenant_speed_completed", "tenant_id", "speed", "completed_at"),
    )


class TriageRecordVersion(Base):
    """Every version of a triage record (tr19): never overwritten."""

    __tablename__ = "triage_record_versions"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    triage_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot = mapped_column(JSONB, nullable=False)
    changed_fields = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    change_reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    changed_at = _tz(False)
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "triage_record_id"],
            ["triage_records.tenant_id", "triage_records.id"],
            name="fk_triage_record_versions_record",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "triage_record_id", "version", name="uq_triage_record_versions_version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class CaseAddendum(Base):
    """What was said about a Case later, and by whom (tr19); the reporter's words are never edited."""

    __tablename__ = "case_addenda"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    intake_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    said_by_role: Mapped[str] = mapped_column(String(30), nullable=False)
    said_at = _tz()
    said_zone: Mapped[str | None] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    masked = mapped_column(JSONB)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "intake_event_id"],
            ["intake_events.tenant_id", "intake_events.id"],
            name="fk_case_addenda_case",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("kind", ADDENDUM_KINDS), name="kind_known"),
        Index("ix_case_addenda_tenant_case", "tenant_id", "intake_event_id", "created_at"),
    )


class RecordLink(Base):
    __tablename__ = "record_links"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    left_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    left_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    right_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    right_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at = _tz(False)
    awareness_before = _tz()
    awareness_after = _tz()
    conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    undo_reason: Mapped[str | None] = mapped_column(Text)
    undone_by: Mapped[str | None] = mapped_column(String(255))
    undone_at = _tz()
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_at = _tz(False)

    __table_args__ = (
        CheckConstraint(_in("state", LINK_STATES), name="state_known"),
        CheckConstraint(
            f"{_in('left_kind', TRIAGE_SUBJECTS[:2])} AND {_in('right_kind', TRIAGE_SUBJECTS[:2])}",
            name="kinds_known",
        ),
        CheckConstraint("state <> 'UNLINKED' OR undo_reason IS NOT NULL", name="undo_reason"),
        Index("ix_record_links_tenant_left", "tenant_id", "left_id"),
        Index("ix_record_links_tenant_right", "tenant_id", "right_id"),
    )


class RecordFieldChange(Base):
    __tablename__ = "record_field_changes"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    entity: Mapped[str] = mapped_column(String(30), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_key: Mapped[str] = mapped_column(String(400), nullable=False)
    import_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    before: Mapped[str | None] = mapped_column(Text)
    after: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_at = _tz(False)

    __table_args__ = (
        Index("ix_record_field_changes_record", "tenant_id", "entity", "record_id"),
        Index("ix_record_field_changes_import", "import_ref"),
    )
