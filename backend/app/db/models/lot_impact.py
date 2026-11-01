"""Distribution of lots to consignees (migration tr08; T-G5 of the trial, MVP G5).

- ``lot_distributions``: one shipment of units of a lot to a consignee (an organization: a hospital, a distributor, a
  clinic; never a person) in a country, on a day. Loaded by the Distribution import (backend/app/trial/
  business_imports.py); a re-upload of the same shipment (lot, consignee, country, ship date) updates it.

The lot impact list itself is kept with the case scope (``investigation_scope_versions.excluded_lots`` and
``lot_impact``, backend/app/db/models/case_scope.py), so its affected and excluded lots are versioned with the scope.
Tenant-isolated (FORCE row-level security). ``source_system`` is ``MDARIX_SAMPLE`` on the sample's rows.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

__all__ = ["LotDistribution"]


class LotDistribution(Base):
    __tablename__ = "lot_distributions"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    lot_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consignee: Mapped[str] = mapped_column(String(255), nullable=False)
    consignee_type: Mapped[str | None] = mapped_column(String(80))
    consignee_reference: Mapped[str | None] = mapped_column(String(120))
    # ISO 3166-1 alpha-2, upper case.
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    ship_date = mapped_column(Date, nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(40))
    created_at = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "lot_batch_id"],
            ["lot_batches.tenant_id", "lot_batches.id"],
            name="fk_lot_distributions_lot",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id", "lot_batch_id", "consignee", "country", "ship_date", name="uq_lot_distributions_shipment"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_lot_distributions_tenant_lot", "tenant_id", "lot_batch_id"),
    )
