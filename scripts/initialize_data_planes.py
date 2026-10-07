"""Create the local synthetic customer data-plane schema.

This is additive and idempotent. It uses the same versioned SQLAlchemy models
as MDARIX, so the validation databases have the business schema required for
the later route-by-route cutover.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system


PLANES = {
    "R1_TENANT_1": ("mdarix_tenant_a", 5541),
    "R1_TENANT_2": ("mdarix_tenant_b", 5542),
    "R1_TENANT_3": ("mdarix_tenant_c", 5543),
    "R1_TENANT_4": ("mdarix_tenant_d", 5544),
}

BUSINESS_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_identifier varchar(160) NOT NULL UNIQUE,
  name varchar(255) NOT NULL, description text, lifecycle_status varchar(40) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS product_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid NOT NULL REFERENCES products(id),
  version_identifier varchar(120) NOT NULL, description text, lifecycle_status varchar(40) NOT NULL DEFAULT 'active',
  release_timestamp timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(product_id, version_identifier)
);
CREATE TABLE IF NOT EXISTS components (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), component_identifier varchar(160) NOT NULL UNIQUE,
  name varchar(255) NOT NULL, revision varchar(80), status varchar(40) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS suppliers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), supplier_identifier varchar(160) NOT NULL UNIQUE,
  name varchar(255) NOT NULL, status varchar(40) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS lot_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), lot_identifier varchar(160) NOT NULL UNIQUE,
  product_version_id uuid REFERENCES product_versions(id), status varchar(40) NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS complaints (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), complaint_identifier varchar(160) NOT NULL UNIQUE,
  product_id uuid REFERENCES products(id), product_version_id uuid REFERENCES product_versions(id),
  description text, status varchar(40) NOT NULL DEFAULT 'open', source_system varchar(120), source_identifier varchar(255),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS investigations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), investigation_identifier varchar(160) NOT NULL UNIQUE,
  product_id uuid REFERENCES products(id), investigation_question text, status varchar(40) NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), evidence_identifier varchar(160) NOT NULL UNIQUE,
  investigation_id uuid REFERENCES investigations(id), evidence_type varchar(80), title varchar(255), content text,
  source_reference varchar(500), reliability_status varchar(40), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS source_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_system varchar(120) NOT NULL,
  source_record_id varchar(255) NOT NULL, source_record_version varchar(120), raw_payload jsonb,
  ingestion_timestamp timestamptz NOT NULL DEFAULT now(), UNIQUE(source_system, source_record_id, source_record_version)
);
CREATE INDEX IF NOT EXISTS ix_products_identifier ON products(product_identifier);
CREATE INDEX IF NOT EXISTS ix_complaints_product ON complaints(product_id);
CREATE INDEX IF NOT EXISTS ix_investigations_product ON investigations(product_id);
CREATE INDEX IF NOT EXISTS ix_evidence_investigation ON evidence(investigation_id);
"""


def main() -> None:
    password = os.getenv("MDARIX_DATA_PLANE_PASSWORD", "change-this-local-secret")
    for tenant_key, (database, port) in PLANES.items():
        url = f"postgresql+pg8000://mdarix_data:{password}@localhost:{port}/{database}"
        # Databases are intentionally internal-only; use docker exec networking
        # when the host does not publish their port.
        host_url = os.getenv(f"MDARIX_DATA_PLANE_{tenant_key}_URL", url)
        engine = create_engine(host_url, future=True, pool_pre_ping=True)
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        with engine.begin() as connection:
            for statement in BUSINESS_SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(text(statement))
            with SessionLocal() as control_session:
                bind_system(control_session, "initialize data planes: read the organizations they serve")
                tenant_id = control_session.query(Tenant.id).filter(Tenant.tenant_key == tenant_key).scalar()
            if tenant_id is None:
                raise RuntimeError(f"Missing control-plane tenant: {tenant_key}")
            for table in (
                "products",
                "product_versions",
                "components",
                "suppliers",
                "lot_batches",
                "complaints",
                "investigations",
                "evidence",
                "source_records",
            ):
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id uuid"))
                connection.execute(
                    text(f"UPDATE {table} SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
                    {"tenant_id": str(tenant_id)},
                )
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table}(tenant_id)"))
        print(f"INITIALIZED {tenant_key} {database}")


if __name__ == "__main__":
    main()
