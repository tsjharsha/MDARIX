"""Regulatory reference data (G2a): each product's registrations per market, the responsible party in each market,
the IMDRF codes by release, and the organization's own codes mapped to them (backend/app/regulatory_reference.py)."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

from .foundation import tenant_fk, tz, uuid_pk

__all__ = ["ImdrfCode", "ImdrfCodeMapping", "MarketResponsibleParty", "ProductRegistration"]

MARKETS = ("US", "EU", "GB", "NI", "CA", "IN", "AU")
PARTY_ROLES = (
    "MANUFACTURER",
    "IMPORTER",
    "AUTHORISED_REPRESENTATIVE",
    "UK_RESPONSIBLE_PERSON",
    "SPONSOR",
    "LICENCE_HOLDER",
)
ANNEXES = ("A", "B", "C", "D", "E", "F", "G")
MAPPING_STATES = ("PROPOSED", "APPROVED", "REJECTED")


def _in(column: str, values) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


class ProductRegistration(Base):
    """One registration of a product in one market: FDA product code with 510(k)/PMA, the EU or UK identifier with
    its notified or approved body, the Health Canada licence, the CDSCO licence or the ARTG entry."""

    __tablename__ = "product_registrations"
    id = uuid_pk()
    tenant_id = tenant_fk()
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    market: Mapped[str] = mapped_column(String(4), nullable=False)
    registration_type: Mapped[str] = mapped_column(String(40), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(120), nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(20))
    body_name: Mapped[str | None] = mapped_column(String(200))
    body_number: Mapped[str | None] = mapped_column(String(20))
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"], ondelete="CASCADE"),
        UniqueConstraint("tenant_id", "product_id", "market", "registration_number", name="uq_product_registration"),
        CheckConstraint(_in("market", MARKETS), name="product_registration_market_known"),
        Index("ix_product_registrations_product", "tenant_id", "product_id"),
    )


class MarketResponsibleParty(Base):
    """Who answers for the organization in a market, in which legal role, and how to reach them."""

    __tablename__ = "market_responsible_parties"
    id = uuid_pk()
    tenant_id = tenant_fk()
    market: Mapped[str] = mapped_column(String(4), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    organisation: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "market", "role", name="uq_market_responsible_party"),
        CheckConstraint(_in("market", MARKETS), name="responsible_party_market_known"),
        CheckConstraint(_in("role", PARTY_ROLES), name="responsible_party_role_known"),
    )


class ImdrfCode(Base):
    """An IMDRF adverse event term, as published in one annex of one release (reference data for every
    organization; loaded from IMDRF's own files by scripts/load_imdrf_annex.py, never typed in)."""

    __tablename__ = "imdrf_codes"
    id = uuid_pk()
    release: Mapped[str] = mapped_column(String(20), nullable=False)
    annex: Mapped[str] = mapped_column(String(1), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    term: Mapped[str] = mapped_column(String(300), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    parent_code: Mapped[str | None] = mapped_column(String(20))
    loaded_at = tz(False)
    __table_args__ = (
        UniqueConstraint("release", "annex", "code", name="uq_imdrf_code"),
        CheckConstraint(_in("annex", ANNEXES), name="imdrf_code_annex_known"),
    )


class ImdrfCodeMapping(Base):
    """One link from the organization's own code to an IMDRF code (many-to-many): proposed by one person, approved
    or rejected by another with regulatory approval rights."""

    __tablename__ = "imdrf_code_mappings"
    id = uuid_pk()
    tenant_id = tenant_fk()
    customer_system: Mapped[str] = mapped_column(String(80), nullable=False)
    customer_code: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_term: Mapped[str | None] = mapped_column(String(300))
    release: Mapped[str] = mapped_column(String(20), nullable=False)
    annex: Mapped[str] = mapped_column(String(1), nullable=False)
    imdrf_code: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PROPOSED")
    proposed_by: Mapped[str] = mapped_column(String(120), nullable=False)
    proposed_at = tz(False)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at = tz()
    review_note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "customer_system", "customer_code", "release", "annex", "imdrf_code", name="uq_imdrf_mapping"
        ),
        CheckConstraint(_in("status", MAPPING_STATES), name="imdrf_mapping_status_known"),
        Index("ix_imdrf_mappings_code", "tenant_id", "customer_system", "customer_code"),
    )
