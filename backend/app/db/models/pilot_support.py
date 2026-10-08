"""Records added for design-partner pilots (migration md23): the erasure log, problem reports and browser errors."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column

__all__ = ["ErasureLog", "SupportProblemReport", "ClientErrorReport"]


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


class ErasureLog(Base):
    """One personal-data erasure or organization purge, kept so a restore from backup can re-apply it."""

    __tablename__ = "erasure_log"
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # PERSON_ERASED | TENANT_PURGED
    subject_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    performed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    performed_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    reapplied_at = mapped_column(DateTime(timezone=True))


class SupportProblemReport(Base):
    """A problem reported from the help menu of a signed-in screen."""

    __tablename__ = "support_problem_reports"
    business_id: Mapped[str] = business_id_column()
    id = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reporter_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    closed_at = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[str | None] = mapped_column(String(255))
    resolution: Mapped[str | None] = mapped_column(Text)


class ClientErrorReport(Base):
    """A browser-side error caught by the application's error boundary."""

    __tablename__ = "client_error_reports"
    id = _pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    stack: Mapped[str | None] = mapped_column(Text)
    component: Mapped[str | None] = mapped_column(String(200))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_id: Mapped[str | None] = mapped_column(String(64))
    release: Mapped[str | None] = mapped_column(String(80))
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
