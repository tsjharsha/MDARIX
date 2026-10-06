from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column
from backend.app.db.models.foundation import tenant_fk, tz, uuid_pk


class ReportJob(Base):
    """Durable tenant-scoped report job and artifact metadata."""

    __tablename__ = "report_jobs"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    report_code: Mapped[str] = mapped_column(String(80), nullable=False)
    output_format: Mapped[str] = mapped_column(String(12), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    hidden_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="QUEUED")
    attempts: Mapped[int] = mapped_column(nullable=False, server_default="0")
    artifact_path: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(120))
    report_version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="1.0")
    last_error: Mapped[str | None] = mapped_column(String(120))
    created_at = tz(False)
    updated_at = tz(False)
