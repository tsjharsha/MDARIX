"""Recorded test runs of MDARIX itself, for the validation evidence screen (E2; migration tr33).

One row per pytest JUnit XML a platform administrator uploaded: the commit and tree it ran on, when it ran, its
totals and every test case with its result and requirement markers (``validation/evidence_view.py parse_junit``).
Platform-owned (no organization): every session may read it, only system scope (a platform administrator) may add a
row, and no route changes or deletes one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.models.foundation import tz, uuid_pk

__all__ = ["ValidationTestRun"]


class ValidationTestRun(Base):
    __tablename__ = "validation_test_runs"
    __table_args__ = (Index("ix_validation_test_runs_uploaded_at", "uploaded_at"),)
    id = uuid_pk()
    commit: Mapped[str] = mapped_column(String(40), nullable=False)
    ran_at = tz()
    passed: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tests: Mapped[list] = mapped_column(JSONB, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    uploaded_at = tz(False)
