"""W1 (0.10.94), spec 6.5 and P360-12 / S360-15: Product 360 and Supplier 360 measured on a 5,000-complaint trial,
against the spec's budget (p95 under 1 s a read) and the approved read target (500 ms). Opt-in, local only:

    MDARIX_TRIAL_LOAD_MEASURE=1 python -m pytest tests/test_product_supplier_load_measure.py -s

The same synthetic export as DEV-13 (tests/test_trial_load_measure.py: five products, two versions, forty lots, five
countries) is imported into a new trial beside its sample; one part supplied by the sample's Precision Sensors is then
linked to every imported version, so that supplier's page covers all 5,000 complaints. Each read is asked
MDARIX_TRIAL_LOAD_REPEAT times (10 by default), in-process, with its queries counted. Timings are reported, not
asserted; the test asserts only that every read answered without an error.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from tests.test_trial_load_measure import _complaints_csv, _save, _series

pytestmark = pytest.mark.skipif(
    not os.getenv("MDARIX_TRIAL_LOAD_MEASURE"), reason="set MDARIX_TRIAL_LOAD_MEASURE=1 to measure (W1, spec 6.5)"
)

BUDGET_MS = 1000  # spec 6.5: p95 under 1 s a read


def _link_a_part_to_every_imported_version(tenant_id) -> None:
    from backend.app.db.models.foundation import (
        Component,
        ComponentSupplier,
        Product,
        ProductComponent,
        ProductVersion,
        Supplier,
    )
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        supplier = (
            db.query(Supplier)
            .filter(Supplier.tenant_id == tenant_id, Supplier.supplier_identifier == "SAMPLE-SUP-A")
            .one()
        )
        part = Component(
            tenant_id=tenant_id,
            component_identifier="LOAD-SENSOR",
            name="Occlusion sensor (load)",
            revision="1",
            source_system="CSV_IMPORT",
            created_at=now,
            updated_at=now,
        )
        db.add(part)
        db.flush()
        db.add(ComponentSupplier(tenant_id=tenant_id, component_id=part.id, supplier_id=supplier.id, created_at=now))
        versions = (
            db.query(ProductVersion)
            .join(Product, (Product.tenant_id == ProductVersion.tenant_id) & (Product.id == ProductVersion.product_id))
            .filter(ProductVersion.tenant_id == tenant_id, Product.product_identifier.like("LOAD-PUMP-%"))
            .all()
        )
        assert versions, "the import made no product versions"
        for version in versions:
            db.add(
                ProductComponent(
                    tenant_id=tenant_id, product_version_id=version.id, component_id=part.id, created_at=now
                )
            )
        db.commit()


def test_measure_product_and_supplier_360_on_5000_complaints():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    report: dict = {"topology": "one Python process, FastAPI TestClient in-process, local PostgreSQL 16 in Docker"}
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        query = "?date_format=ISO&on_problems=skip&personal_data=refuse&file_name=load-5000.csv"
        imported = user.post(
            f"/api/v1/data/import/complaints{query}",
            content=_complaints_csv(5000),
            headers={"Content-Type": "text/csv"},
        )
        assert imported.status_code == 200, imported.text[:500]
        _link_a_part_to_every_imported_version(tenant_id)
        product = "LOAD-PUMP-0"
        reads = [
            "/api/v1/products?counts=1&limit=100",
            f"/api/v1/products/{product}/product-360?light=1",
            f"/api/v1/products/{product}/product-360?light=1&version_id=Rev%20B",
            f"/api/v1/products/{product}/links?version=Rev%20B",
            f"/api/v1/products/{product}/links",
            f"/api/v1/products/{product}/links?version=Rev%20B&kind=complaints&limit=20",
            f"/api/v1/products/{product}/links?version=Rev%20B&kind=investigations&limit=20",
            "/api/v1/suppliers?limit=100",
            "/api/v1/suppliers/SAMPLE-SUP-A",
            "/api/v1/suppliers/SAMPLE-SUP-A/complaints?limit=20",
            "/api/v1/suppliers/SAMPLE-SUP-A/lots",
            "/api/v1/suppliers/SAMPLE-SUP-B",
        ]
        report["reads_5000"] = []
        for path in reads:
            item = _series(user, "GET", path, target=BUDGET_MS)
            item["path"] = path
            item["meets_500ms"] = item["p95_ms"] <= 500
            report["reads_5000"].append(item)
            _save(report)
        page = user.get("/api/v1/suppliers/SAMPLE-SUP-A").json()
        report["supplier_a_complaints"] = page["counts"]["complaints"]
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:w1-load-measure-cleanup")
        print(json.dumps(report, indent=2))
        _save(report)
    assert all(item["server_errors"] == 0 for item in report["reads_5000"])
