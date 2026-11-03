"""Authority report obligations, their approved snapshots and the complete submission record (migration tr05; T-G2b
and T-G2c of the trial, MVP G2b and G2c).

- ``report_obligations``: one report owed to one authority for one complaint (``INITIAL``), or the response to an
  authority's request for information (``RESPONSE``, with its parent). It comes from the complaint's market assessment
  (reportable, or pending with a provisional deadline), keeps the deadline it was given (a rejection never moves it),
  and holds the worksheet's entries made by a person (``entries``: value or confirmation, who and when; values from the
  records are read again each time, never stored as typed). ``state`` is G2b's: DRAFT, CORRECTION_REQUIRED (a draft
  after a rejection), APPROVED, SUBMITTED_PENDING, ACCEPTED, SUBMITTED_NO_ACK, FOLLOW_UP_DUE, COMPLETE,
  and CANCELLED (tr14: a later signed conclusion said not reportable).
- ``report_snapshots``: the worksheet frozen for approval, in versions; approved by a second person with password and
  authenticator code (a signed approval record). Never edited after approval.
- ``report_submissions``: each attempt as the person records it after submitting outside MDARIX: the route, the
  submission time, the submitted content (a note, and the file in ``report_evidence``), the differences from the
  approved snapshot, the authority's reference and the result. A rejected attempt is kept; a resubmission is a new
  attempt on the same obligation.
- ``report_evidence``: the evidence of an attempt as it arrives (the submitted content, a receipt, FDA's
  acknowledgements, the acceptance, a rejection or a bounce), each with an optional small file kept here with its
  SHA-256, so export, purge and sample removal cover it.

MDARIX never submits: nothing here is sent anywhere. Snapshots, attempts and evidence are append-only through the API
(D-10's "never deleted before the retention period ends"; in a free trial the retention period is the trial's own,
T-B5). ``source_system`` is ``MDARIX_SAMPLE`` on the sample story's rows. All four are tenant-isolated (FORCE
row-level security). Design note, columns the MVP adds later (nullable): the event (G28), G33's routing, the
emergency route and the offline approval evidence, the QMS-ready package and its filing reference, G34's time fields.
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
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

__all__ = [
    "OBLIGATION_KINDS",
    "OBLIGATION_STATES",
    "ReportEvidence",
    "ReportObligation",
    "ReportSnapshot",
    "ReportSubmission",
]

OBLIGATION_KINDS = ("INITIAL", "RESPONSE")
OBLIGATION_STATES = (
    "DRAFT",
    "CORRECTION_REQUIRED",
    "APPROVED",
    "SUBMITTED_PENDING",
    "ACCEPTED",
    "SUBMITTED_NO_ACK",
    "FOLLOW_UP_DUE",
    "COMPLETE",
    # tr14 (0.10.75): a report not yet submitted, cancelled by a later signed "not reportable" conclusion.
    "CANCELLED",
)
SNAPSHOT_STATES = ("PENDING", "APPROVED", "SUPERSEDED")
SUBMISSION_RESULTS = ("PENDING", "ACCEPTED", "REJECTED", "NO_ACK_EXPECTED")
EVIDENCE_OUTCOMES = ("CONTENT", "RECEIPT", "ACCEPTED", "REJECTED")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _tenant():
    return mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)


def _tz(nullable: bool = True):
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class ReportObligation(Base):
    __tablename__ = "report_obligations"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="INITIAL")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("report_obligations.id"))
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("complaint_market_assessments.id")
    )
    form_code: Mapped[str] = mapped_column(String(40), nullable=False)
    form_version: Mapped[str] = mapped_column(String(40), nullable=False)
    report_type: Mapped[str | None] = mapped_column(String(40))
    due_on = mapped_column(Date)
    due_provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    state: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    entries = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    request_text: Mapped[str | None] = mapped_column(Text)
    request_received_on = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    follow_up_due_on = mapped_column(Date)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _tz(False)
    updated_at = _tz(False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_report_obligations_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("kind", OBLIGATION_KINDS), name="kind_known"),
        CheckConstraint(_in("state", OBLIGATION_STATES), name="state_known"),
        CheckConstraint("kind = 'INITIAL' OR parent_id IS NOT NULL", name="response_has_parent"),
        Index("ix_report_obligations_tenant_complaint", "tenant_id", "complaint_id"),
        Index(
            "uq_report_obligations_initial",
            "tenant_id",
            "complaint_id",
            "market",
            unique=True,
            postgresql_where=text("kind = 'INITIAL'"),
        ),
    )


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    obligation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    form_version: Mapped[str] = mapped_column(String(40), nullable=False)
    fields = mapped_column(JSONB, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    preparers = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at = _tz(False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at = _tz()
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_system: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        ForeignKeyConstraint(
            ["obligation_id"], ["report_obligations.id"], name="fk_report_snapshots_obligation", ondelete="CASCADE"
        ),
        UniqueConstraint("obligation_id", "version", name="uq_report_snapshots_version"),
        CheckConstraint(_in("state", SNAPSHOT_STATES), name="state_known"),
        CheckConstraint(
            "state <> 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND signed_record_id IS NOT "
            "NULL)",
            name="approved_signed",
        ),
        Index("ix_report_snapshots_tenant_obligation", "tenant_id", "obligation_id"),
    )


class ReportSubmission(Base):
    __tablename__ = "report_submissions"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    obligation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("report_snapshots.id"))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    route: Mapped[str] = mapped_column(String(40), nullable=False)
    submitted_at = _tz(False)
    content_note: Mapped[str | None] = mapped_column(Text)
    differences = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    authority_reference: Mapped[str | None] = mapped_column(String(120))
    result: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    result_at = _tz()
    late: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at = _tz(False)
    source_system: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        ForeignKeyConstraint(
            ["obligation_id"], ["report_obligations.id"], name="fk_report_submissions_obligation", ondelete="CASCADE"
        ),
        UniqueConstraint("obligation_id", "attempt", name="uq_report_submissions_attempt"),
        CheckConstraint(_in("result", SUBMISSION_RESULTS), name="result_known"),
        Index("ix_report_submissions_tenant_obligation", "tenant_id", "obligation_id"),
    )


class ReportEvidence(Base):
    __tablename__ = "report_evidence"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = _tenant()
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(200))
    content_type: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    content = mapped_column(LargeBinary)
    received_at = _tz(False)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at = _tz(False)
    source_system: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        ForeignKeyConstraint(
            ["submission_id"], ["report_submissions.id"], name="fk_report_evidence_submission", ondelete="CASCADE"
        ),
        CheckConstraint(_in("outcome", EVIDENCE_OUTCOMES), name="outcome_known"),
        CheckConstraint("note IS NOT NULL OR content IS NOT NULL", name="note_or_file"),
        Index("ix_report_evidence_tenant_submission", "tenant_id", "submission_id"),
    )
