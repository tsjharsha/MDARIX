import uuid

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.models.foundation import tenant_fk, tz, uuid_pk


class RegulatoryDocument(Base):
    """Durable tenant-owned regulatory document identity and lifecycle."""

    __tablename__ = "regulatory_documents"
    id = uuid_pk()
    tenant_id = tenant_fk()
    document_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_identifier", name="uq_regulatory_document_tenant_identifier"),
        Index("ix_regulatory_documents_tenant_status", "tenant_id", "status"),
    )


class RegulatoryDocumentVersion(Base):
    """Immutable snapshot of a generated or edited regulatory document."""

    __tablename__ = "regulatory_document_versions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "version", name="uq_regulatory_document_version"),
        Index("ix_regulatory_document_versions_tenant_document", "tenant_id", "document_id", "version"),
    )
