"""Copy the deterministic synthetic business slice into each data plane.

Only synthetic tenant records are copied. Control-plane identity, memberships,
secrets, audit, mappings, and subscriptions remain in the control database.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.db.models.foundation import Complaint, Evidence, Investigation, Product, ProductVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system

PLANES = {
    "R1_TENANT_1": ("mdarix_tenant_a", 5541),
    "R1_TENANT_2": ("mdarix_tenant_b", 5542),
    "R1_TENANT_3": ("mdarix_tenant_c", 5543),
    "R1_TENANT_4": ("mdarix_tenant_d", 5544),
}


def main() -> None:
    password = os.getenv("MDARIX_DATA_PLANE_PASSWORD", "change-this-local-secret")
    migrated = {}
    with SessionLocal() as source:
        bind_system(source, "copy synthetic business data to the organization databases")
        from backend.app.db.models.foundation import Tenant

        tenants = {t.tenant_key: t for t in source.query(Tenant).filter(Tenant.tenant_key.in_(PLANES)).all()}
        for tenant_key, (database, port) in PLANES.items():
            tenant = tenants[tenant_key]
            target = create_engine(
                f"postgresql+pg8000://mdarix_data:{password}@localhost:{port}/{database}", future=True
            )
            products = source.query(Product).filter(Product.tenant_id == tenant.id).all()
            product_ids = {p.id for p in products}
            versions = (
                source.query(ProductVersion)
                .filter(ProductVersion.tenant_id == tenant.id, ProductVersion.product_id.in_(product_ids or {None}))
                .all()
            )
            investigations = (
                source.query(Investigation)
                .filter(Investigation.tenant_id == tenant.id, Investigation.product_id.in_(product_ids or {None}))
                .all()
            )
            investigation_ids = {i.id for i in investigations}
            complaints = (
                source.query(Complaint)
                .filter(Complaint.tenant_id == tenant.id, Complaint.product_id.in_(product_ids or {None}))
                .all()
            )
            evidence = (
                source.query(Evidence)
                .filter(Evidence.tenant_id == tenant.id, Evidence.investigation_id.in_(investigation_ids or {None}))
                .all()
            )
            with target.begin() as db:
                if not products:
                    now = datetime.now(timezone.utc)
                    product_id = uuid.uuid4()
                    version_id = uuid.uuid4()
                    investigation_id = uuid.uuid4()
                    complaint_id = uuid.uuid4()
                    evidence_id = uuid.uuid4()
                    identifier = f"{tenant_key}-PRODUCT-CANARY"
                    db.execute(
                        text(
                            "INSERT INTO products (id, product_identifier, name, description, lifecycle_status, created_at, updated_at) VALUES (:id,:identifier,:name,:description,'active',:now,:now) ON CONFLICT (product_identifier) DO NOTHING"
                        ),
                        {
                            "id": product_id,
                            "identifier": identifier,
                            "name": f"{tenant_key} Synthetic Product",
                            "description": "Synthetic MVP data-plane canary",
                            "now": now,
                        },
                    )
                    db.execute(
                        text(
                            "INSERT INTO product_versions (id, product_id, version_identifier, description, lifecycle_status, created_at, updated_at) VALUES (:id,:product,'VALIDATION-1',:description,'active',:now,:now) ON CONFLICT (product_id, version_identifier) DO NOTHING"
                        ),
                        {
                            "id": version_id,
                            "product": product_id,
                            "description": "Synthetic validation version",
                            "now": now,
                        },
                    )
                    db.execute(
                        text(
                            "INSERT INTO investigations (id, investigation_identifier, product_id, investigation_question, status, created_at, updated_at) VALUES (:id,:identifier,:product,:question,'open',:now,:now) ON CONFLICT (investigation_identifier) DO NOTHING"
                        ),
                        {
                            "id": investigation_id,
                            "identifier": f"{tenant_key}-INVESTIGATION-CANARY",
                            "product": product_id,
                            "question": "Synthetic tenant-scoped validation investigation",
                            "now": now,
                        },
                    )
                    db.execute(
                        text(
                            "INSERT INTO complaints (id, complaint_identifier, product_id, product_version_id, description, status, source_system, source_identifier, created_at, updated_at) VALUES (:id,:identifier,:product,:version,:description,'open','VALIDATION',:source,:now,:now) ON CONFLICT (complaint_identifier) DO NOTHING"
                        ),
                        {
                            "id": complaint_id,
                            "identifier": f"{tenant_key}-COMPLAINT-CANARY",
                            "product": product_id,
                            "version": version_id,
                            "description": "Synthetic validation complaint; not customer data",
                            "source": f"{tenant_key}-SOURCE-001",
                            "now": now,
                        },
                    )
                    db.execute(
                        text(
                            "INSERT INTO evidence (id, evidence_identifier, investigation_id, evidence_type, title, content, source_reference, reliability_status, created_at, updated_at) VALUES (:id,:identifier,:investigation,'synthetic','Validation evidence',:content,:source,'reviewed',:now,:now) ON CONFLICT (evidence_identifier) DO NOTHING"
                        ),
                        {
                            "id": evidence_id,
                            "identifier": f"{tenant_key}-EVIDENCE-CANARY",
                            "investigation": investigation_id,
                            "content": "Synthetic evidence for data-plane validation only.",
                            "source": f"{tenant_key}-COMPLAINT-CANARY",
                            "now": now,
                        },
                    )
                    products = [object()]
                    versions = [object()]
                    investigations = [object()]
                    complaints = [object()]
                    evidence = [object()]
                for p in products:
                    if not hasattr(p, "product_identifier"):
                        continue
                    db.execute(
                        text(
                            "INSERT INTO products (id, product_identifier, name, description, lifecycle_status, created_at, updated_at) VALUES (:id,:identifier,:name,:description,:status,:created,:updated) ON CONFLICT (product_identifier) DO NOTHING"
                        ),
                        {
                            "id": p.id,
                            "identifier": p.product_identifier,
                            "name": p.name,
                            "description": p.description,
                            "status": p.lifecycle_status,
                            "created": p.created_at,
                            "updated": p.updated_at,
                        },
                    )
                for v in versions:
                    if not hasattr(v, "version_identifier"):
                        continue
                    db.execute(
                        text(
                            "INSERT INTO product_versions (id, product_id, version_identifier, description, lifecycle_status, release_timestamp, created_at, updated_at) VALUES (:id,:product,:version,:description,:status,:release,:created,:updated) ON CONFLICT (product_id, version_identifier) DO NOTHING"
                        ),
                        {
                            "id": v.id,
                            "product": v.product_id,
                            "version": v.version_identifier,
                            "description": v.description,
                            "status": v.lifecycle_status,
                            "release": v.release_timestamp,
                            "created": v.created_at,
                            "updated": v.updated_at,
                        },
                    )
                for i in investigations:
                    if not hasattr(i, "investigation_identifier"):
                        continue
                    db.execute(
                        text(
                            "INSERT INTO investigations (id, investigation_identifier, product_id, investigation_question, status, created_at, updated_at) VALUES (:id,:identifier,:product,:question,:status,:created,:updated) ON CONFLICT (investigation_identifier) DO NOTHING"
                        ),
                        {
                            "id": i.id,
                            "identifier": i.investigation_identifier,
                            "product": i.product_id,
                            "question": i.investigation_question,
                            "status": i.status,
                            "created": i.created_at,
                            "updated": i.updated_at,
                        },
                    )
                for c in complaints:
                    if not hasattr(c, "complaint_identifier"):
                        continue
                    db.execute(
                        text(
                            "INSERT INTO complaints (id, complaint_identifier, product_id, product_version_id, description, status, source_system, source_identifier, created_at, updated_at) VALUES (:id,:identifier,:product,:version,:description,:status,:source,:source_id,:created,:updated) ON CONFLICT (complaint_identifier) DO NOTHING"
                        ),
                        {
                            "id": c.id,
                            "identifier": c.complaint_identifier,
                            "product": c.product_id,
                            "version": c.product_version_id,
                            "description": c.description,
                            "status": c.status,
                            "source": c.source_system,
                            "source_id": c.source_identifier,
                            "created": c.created_at,
                            "updated": c.updated_at,
                        },
                    )
                for e in evidence:
                    if not hasattr(e, "evidence_identifier"):
                        continue
                    db.execute(
                        text(
                            "INSERT INTO evidence (id, evidence_identifier, investigation_id, evidence_type, title, content, source_reference, reliability_status, created_at, updated_at) VALUES (:id,:identifier,:investigation,:type,:title,:content,:source,:reliability,:created,:updated) ON CONFLICT (evidence_identifier) DO NOTHING"
                        ),
                        {
                            "id": e.id,
                            "identifier": e.evidence_identifier,
                            "investigation": e.investigation_id,
                            "type": e.evidence_type,
                            "title": e.title,
                            "content": e.content,
                            "source": e.source_reference,
                            "reliability": e.reliability_status,
                            "created": e.created_at,
                            "updated": e.updated_at,
                        },
                    )
            migrated[tenant_key] = {
                "products": len(products),
                "versions": len(versions),
                "investigations": len(investigations),
                "complaints": len(complaints),
                "evidence": len(evidence),
            }
    print(migrated)


if __name__ == "__main__":
    main()
