"""Per-market reportability assessment, complaint classification and signer training (migration tr01).

- ``complaint_market_assessments`` (T-G15S, T-G15H): one market's seriousness and causation assessment of one
  complaint, in versions. A version is saved as a draft (``conclusion`` empty: the answers, the harm level and the
  suggestion so far) and becomes a signed conclusion (REPORTABLE or NOT_REPORTABLE) with password and authenticator
  code; the signature is a signed approval record, referenced here. A signed version is never edited: a change is a new
  version, and the earlier one is marked ``superseded_by``. When the organization has reported outside MDARIX, the
  filing reference and date are recorded on the signed version. Design note, columns the MVP adds later (nullable):
  the guide version of the G15 engine, the event (G28), the source-register rows, re-confirmation and reassessment
  (T10, T11), and the conclusion "not reportable on current evidence".
- ``complaint_classifications`` (T-G39): use environment and user type of a complaint for trend analysis, proposed then
  confirmed by a person under the written coding criteria, in versions. Its screens arrive with the disposition
  (0.10.52); the table lands now (dark). Design note: the MVP adds nullable columns for the contact (G32) and the event
  (G28).
- ``signer_training_records`` (T-G40P): a person's training on one version of a document a signature relies on (in a
  free trial a practice acknowledgement). Design note: the MVP keeps the table for the customer's entered records and
  adds the complaint-handling procedure as a document code.

``source_system`` is ``MDARIX_SAMPLE`` on rows of the trial's sample story, so sample removal and the story's counts
tell them from the organization's own. All three are tenant-isolated (FORCE row-level security).
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
    "ASSESSMENT_CONCLUSIONS",
    "ASSESSMENT_MARKETS",
    "CLASSIFICATION_STATES",
    "USER_TYPES",
    "USE_ENVIRONMENTS",
    "ComplaintClassification",
    "ComplaintMarketAssessment",
    "SignerTrainingRecord",
]

ASSESSMENT_MARKETS = ("US", "EU_NI", "GB", "IN", "CA")
ASSESSMENT_SUGGESTIONS = ("REPORTABLE", "PENDING_INFORMATION", "NOT_REPORTABLE")
ASSESSMENT_CONCLUSIONS = ("REPORTABLE", "NOT_REPORTABLE")
USE_ENVIRONMENTS = (
    "HOSPITAL_WARD",
    "INTENSIVE_CARE_UNIT",
    "OPERATING_THEATRE",
    "HOME",
    "AMBULANCE",
    "CLINIC",
    "OTHER",
    "UNKNOWN",
)
USER_TYPES = ("HEALTHCARE_PROFESSIONAL", "LAY_USER", "PATIENT", "SERVICE_ENGINEER", "OTHER", "UNKNOWN")
CLASSIFICATION_STATES = ("PROPOSED", "CONFIRMED")


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def _now():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ComplaintMarketAssessment(Base):
    __tablename__ = "complaint_market_assessments"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    question_set: Mapped[str] = mapped_column(String(40), nullable=False)
    answers = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    harm_level: Mapped[str | None] = mapped_column(String(20))
    harm_code: Mapped[str | None] = mapped_column(String(60))
    harm_level_reason: Mapped[str | None] = mapped_column(Text)
    scale_version: Mapped[str] = mapped_column(String(40), nullable=False)
    # The written reason for an answer that disagrees with the scale (markets.disagreement).
    scale_disagreement_reason: Mapped[str | None] = mapped_column(Text)
    suggested_conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(30))
    override_reason: Mapped[str | None] = mapped_column(Text)
    # Why a re-signed conclusion changes (owner decision OD-4, tr18): asked when it supersedes a signed version.
    change_reason: Mapped[str | None] = mapped_column(Text)
    report_type: Mapped[str | None] = mapped_column(String(40))
    window_name: Mapped[str | None] = mapped_column(String(160))
    due_on = mapped_column(Date)
    filing_reference: Mapped[str | None] = mapped_column(String(120))
    filed_on = mapped_column(Date)
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content_fingerprint: Mapped[str | None] = mapped_column(String(64))
    signed_by: Mapped[str | None] = mapped_column(String(255))
    signed_at = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # B4 (tr27): the floor in force on the awareness day, the rules that applied, how the due date was counted. Empty
    # on rows signed before the rule register (never backfilled) and while MDARIX_RULE_REGISTER is off.
    floor_code: Mapped[str | None] = mapped_column(String(40))
    rules_applied = mapped_column(JSONB)
    date_calc = mapped_column(JSONB)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _now()
    updated_at = _now()

    __table_args__ = (
        # DB-1 (tr23).
        UniqueConstraint("tenant_id", "id", name="uq_complaint_market_assessments_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "complaint_id", "market", "version", name="uq_complaint_market_assessments_version"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_market_assessments_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("market", ASSESSMENT_MARKETS), name="market_known"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(_in("suggested_conclusion", ASSESSMENT_SUGGESTIONS), name="suggestion_known"),
        CheckConstraint(f"conclusion IS NULL OR {_in('conclusion', ASSESSMENT_CONCLUSIONS)}", name="conclusion_known"),
        CheckConstraint(
            "conclusion IS NULL OR (signed_record_id IS NOT NULL AND signed_by IS NOT NULL AND signed_at IS NOT NULL)",
            name="conclusion_signed",
        ),
        CheckConstraint("filed_on IS NULL OR conclusion = 'REPORTABLE'", name="filed_when_reportable"),
        Index("ix_complaint_market_assessments_tenant_complaint", "tenant_id", "complaint_id"),
    )


class ComplaintClassification(Base):
    __tablename__ = "complaint_classifications"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    use_environment: Mapped[str] = mapped_column(String(30), nullable=False, server_default="UNKNOWN")
    use_environment_text: Mapped[str | None] = mapped_column(String(200))
    user_type: Mapped[str] = mapped_column(String(30), nullable=False, server_default="UNKNOWN")
    user_type_text: Mapped[str | None] = mapped_column(String(200))
    # The values as the source (sample data or the import) gave them, kept beside the coded value.
    source_values = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PROPOSED")
    coding_criteria_version: Mapped[str] = mapped_column(String(40), nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(255))
    confirmed_at = mapped_column(DateTime(timezone=True))
    signed_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    change_reason: Mapped[str | None] = mapped_column(Text)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = _now()

    __table_args__ = (
        UniqueConstraint("tenant_id", "complaint_id", "version", name="uq_complaint_classifications_version"),
        ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_classifications_complaint",
            ondelete="CASCADE",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(_in("use_environment", USE_ENVIRONMENTS), name="use_environment_known"),
        CheckConstraint(_in("user_type", USER_TYPES), name="user_type_known"),
        CheckConstraint(_in("state", CLASSIFICATION_STATES), name="state_known"),
        CheckConstraint(
            "use_environment <> 'OTHER' OR use_environment_text IS NOT NULL", name="other_environment_text"
        ),
        CheckConstraint("user_type <> 'OTHER' OR user_type_text IS NOT NULL", name="other_user_type_text"),
        CheckConstraint(
            "state <> 'CONFIRMED' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="confirmed_by_someone",
        ),
    )


class SignerTrainingRecord(Base):
    __tablename__ = "signer_training_records"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_code: Mapped[str] = mapped_column(String(60), nullable=False)
    document_version: Mapped[str] = mapped_column(String(60), nullable=False)
    trained_at = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(200), nullable=False)
    trainer: Mapped[str | None] = mapped_column(String(255))
    evidence = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_at = _now()

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "document_code", "document_version", name="uq_signer_training_records_version"
        ),
        Index("ix_signer_training_records_document", "tenant_id", "document_code", "document_version"),
    )
