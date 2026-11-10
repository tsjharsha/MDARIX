"""W1 (0.10.94), Supplier 360 through the API on a free trial's sample, as its own user (S360-01 to -05, -07, -10 in
part, -11 requests, -14): the list, a supplier with no parts, one version only (NovaSense), the contrast with no pattern
(Precision Sensors), a lot with parts of two suppliers, a part with two suppliers, the change's before/after split, a
pattern already under investigation, the complaints paged with the basis of each link, the lots, and another
organization's supplier."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

NOVA, PRECISION = "SAMPLE-SUP-B", "SAMPLE-SUP-A"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:supplier360-cleanup")


def _session(tenant_id):
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    db = SessionLocal()
    bind_tenant(db, tenant_id)
    return db


def test_the_list_gives_each_supplier_its_parts_products_and_recent_complaints(trial):
    response = trial["user"].get("/api/v1/suppliers", params={"limit": 50})
    rows = _ok(response)
    assert response.headers["X-Total-Count"] == str(len(rows))
    by_id = {row["supplier_identifier"]: row for row in rows}
    nova, precision = by_id[NOVA], by_id[PRECISION]
    assert nova["origin"]["kind"] == "SAMPLE" and nova["parts"] == 1 and nova["versions"] == 1 and nova["products"] == 1
    assert nova["complaints_90d"] > 0 and nova["open_investigations"] >= 1
    assert precision["products"] == 3 and precision["parts"] >= 7


def test_novasense_is_on_one_version_and_says_so(trial):
    user = trial["user"]
    page = _ok(user.get(f"/api/v1/suppliers/{NOVA}"))
    assert page["supplier"]["name"].startswith("NovaSense") and page["supplier"]["origin"]["label"] == "Sample"
    (part,) = page["parts"]
    assert part["component_identifier"] == "SAMPLE-ORBIT-300-C1" and part["supplied_from"]
    assert [(u["product_identifier"], u["version_identifier"]) for u in part["used_in"]] == [
        ("SAMPLE-ORBIT-300", "Rev B")
    ]
    box = page["pattern"]
    assert box["found"] is False and box["case"] == "ONE_VERSION" and box["rule"] == "P-1"
    assert box["text"].startswith(
        "NovaSense Components (Sample) parts are in 1 product version: OrbitCare 300 Infusion Pump (Sample) Rev B."
    )
    assert "450 units released" in box["text"] and "SAMPLE-INV-001 is open on" in box["text"]
    assert box["text"].endswith("so a cross-product pattern cannot be seen.")
    assert "SAMPLE-INV-001" in [case["investigation_identifier"] for case in page["investigations"]]
    # S360-05: the change on its part, with the complaints before and after it took effect.
    (change,) = page["changes"]
    assert change["change_identifier"] == "SAMPLE-CHG-014" and change["complaints_after"] > 0
    assert change["complaints_before"] + change["complaints_after"] == page["counts"]["complaints"]
    assert any(m["kind"] == "change" and m["label"] == "SAMPLE-CHG-014" for m in page["trend"]["markers"])
    assert page["scar_note"] == "Supplier corrective action requests (SCAR): planned for a later release."
    assert any(capa["capa_identifier"] == "SAMPLE-CAPA-02" for capa in page["capas"])


def test_precision_sensors_shows_no_pattern(trial):
    page = _ok(trial["user"].get(f"/api/v1/suppliers/{PRECISION}"))
    assert page["pattern"]["found"] is False and page["pattern"]["case"] == "BELOW_RULE"
    assert "not a confirmed signal" not in page["pattern"]["text"]
    assert {v["product_identifier"] for v in page["versions"]} == {
        "SAMPLE-ORBIT-300",
        "SAMPLE-PULSE-410",
        "SAMPLE-VENTRA-250",
    }


def test_complaints_are_paged_with_the_basis_of_each_link(trial):
    user = trial["user"]
    first = user.get(f"/api/v1/suppliers/{NOVA}/complaints", params={"limit": 3})
    rows, total = _ok(first), int(first.headers["X-Total-Count"])
    assert len(rows) == 3 and total > 3 and first.headers["X-Next-Offset"] == "3"
    every = _ok(user.get(f"/api/v1/suppliers/{NOVA}/complaints"))
    assert len(every) == total
    kinds = {row["basis_kind"] for row in every}
    # Lots 003-005 name a NovaSense sensor lot in their genealogy; the basis says which one, never "caused by".
    assert "GENEALOGY" in kinds
    strong = next(row for row in every if row["basis_kind"] == "GENEALOGY")
    assert strong["basis"].startswith("On a lot whose genealogy names its Pressure Sensor (Sample) lot NS-SL-")
    assert all("cause" not in row["basis"].lower() for row in every)


def test_a_lot_with_parts_of_two_suppliers_is_on_both_pages_with_its_own_line(trial):
    user = trial["user"]
    nova = _ok(user.get(f"/api/v1/suppliers/{NOVA}/lots"))
    precision = _ok(user.get(f"/api/v1/suppliers/{PRECISION}/lots"))
    assert nova["basis"] == "GENEALOGY" and precision["basis"] == "GENEALOGY"
    lot_3 = "SAMPLE-ORBIT-300-LOT-003"
    nova_3 = next(lot for lot in nova["lots"] if lot["lot_identifier"] == lot_3)
    precision_3 = next(lot for lot in precision["lots"] if lot["lot_identifier"] == lot_3)
    assert nova_3["evidence"] == [
        "Lot genealogy: built with Pressure Sensor (Sample) lot NS-SL-2417 (Sample); NovaSense Components (Sample) is a "
        "recorded supplier of it"
    ]
    assert "Control Board (Sample) lot CB-1180" in precision_3["evidence"][0]
    assert nova_3["complaints"] == precision_3["complaints"] > 0
    assert {lot["lot_identifier"][-3:] for lot in nova["lots"]} == {"003", "004", "005", "006", "007", "008"}


def test_no_parts_two_suppliers_of_one_part_a_pattern_under_investigation_and_requests(trial):
    from backend.app.db.models.foundation import (
        Complaint,
        Component,
        ComponentSupplier,
        Investigation,
        InvestigationComplaint,
        Product,
        ProductComponent,
        ProductVersion,
        Supplier,
    )
    from backend.app.db.models.stage3 import SupplierEvidenceRequest

    user, tenant_id = trial["user"], trial["tenant_id"]
    now = datetime.now(timezone.utc)
    stamp = {"created_at": now, "updated_at": now, "source_system": "SAP S/4", "ingestion_timestamp": now}
    db = _session(tenant_id)
    try:
        empty = Supplier(tenant_id=tenant_id, supplier_identifier="T-EMPTY", name="Empty Parts Co", **stamp)
        kestrel = Supplier(tenant_id=tenant_id, supplier_identifier="T-KESTREL", name="Kestrel Sensors", **stamp)
        db.add_all([empty, kestrel])
        db.flush()
        part = Component(tenant_id=tenant_id, component_identifier="T-KS-1", name="Flow sensor", revision="1", **stamp)
        db.add(part)
        db.flush()
        db.add(ComponentSupplier(tenant_id=tenant_id, component_id=part.id, supplier_id=kestrel.id, created_at=now))
        board = (
            db.query(Component)
            .filter(Component.tenant_id == tenant_id, Component.component_identifier == "SAMPLE-ORBIT-300-C2")
            .one()
        )
        # S360-04: the OrbitCare control board now has two recorded suppliers.
        db.add(ComponentSupplier(tenant_id=tenant_id, component_id=board.id, supplier_id=kestrel.id, created_at=now))
        rev_a = (
            db.query(ProductVersion, Product)
            .join(Product, Product.id == ProductVersion.product_id)
            .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.version_identifier == "Rev A")
            .filter(Product.product_identifier.in_(["SAMPLE-ORBIT-300", "SAMPLE-PULSE-410"]))
            .all()
        )
        case = Investigation(
            tenant_id=tenant_id,
            investigation_identifier="T-INV-42",
            product_id=rev_a[0][1].id,
            investigation_question="Flow reading high on two products?",
            status="open",
            created_at=now,
            updated_at=now,
        )
        db.add(case)
        db.flush()
        for version, product in rev_a:
            db.add(
                ProductComponent(
                    tenant_id=tenant_id, product_version_id=version.id, component_id=part.id, created_at=now
                )
            )
            for n in range(2):
                complaint = Complaint(
                    tenant_id=tenant_id,
                    complaint_identifier=f"T-{product.product_identifier}-{n}",
                    product_id=product.id,
                    product_version_id=version.id,
                    description="Flow reading high (test)",
                    problem_code="FLOW_READING_HIGH",
                    event_timestamp=now - timedelta(days=5 + n),
                    status="open",
                    **stamp,
                )
                db.add(complaint)
                db.flush()
                db.add(
                    InvestigationComplaint(
                        tenant_id=tenant_id, investigation_id=case.id, complaint_id=complaint.id, created_at=now
                    )
                )
        db.add(
            SupplierEvidenceRequest(
                tenant_id=tenant_id,
                supplier_id=kestrel.id,
                investigation_id=case.id,
                requested_by="test",
                recipient="quality@kestrel.example",
                title="Calibration records for flow sensor lots",
                requested_items=["calibration"],
                status="SENT",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        empty_id, kestrel_id = str(empty.id), str(kestrel.id)
    finally:
        db.close()

    # S360-01: no parts.
    none = _ok(user.get(f"/api/v1/suppliers/{empty_id}"))
    assert none["parts"] == [] and none["counts"]["complaints"] == 0 and none["pattern"]["found"] is False
    assert none["pattern"]["text"] == "No parts are recorded for this supplier, so nothing can be linked to it."
    assert none["supplier"]["origin"] == {
        **none["supplier"]["origin"],
        "kind": "EXTERNAL",
        "label": "From SAP S/4",
    }

    # S360-02, -06, -07: one part on two products' versions, the same problem twice on each, already investigated.
    page = _ok(user.get("/api/v1/suppliers/T-KESTREL"))
    box = page["pattern"]
    assert box["found"] is True and box["case"] == "PATTERN" and box["problem"] == "FLOW_READING_HIGH"
    assert box["text"].startswith(
        "Pattern to review: flow reading high on 2 versions of 2 products that contain Kestrel"
    )
    assert "not a confirmed signal" in box["text"]
    assert [(c["ref"], c["held"]) for c in box["investigations"]] == [("T-INV-42", 4)]
    # Owner, 10 Nov 2026: the pattern names its complaints, each with its product, for "Open an investigation" to tick.
    assert sorted(c["complaint_identifier"] for c in box["complaints"]) == [
        f"T-{product}-{n}" for product in ("SAMPLE-ORBIT-300", "SAMPLE-PULSE-410") for n in range(2)
    ]
    assert len({c["product_id"] for c in box["complaints"]}) == 2
    flow = next(p for p in page["parts"] if p["component_identifier"] == "T-KS-1")
    assert {u["product_identifier"] for u in flow["used_in"]} == {"SAMPLE-ORBIT-300", "SAMPLE-PULSE-410"}
    # S360-04: both recorded suppliers of the control board are named on the part.
    board_part = next(p for p in page["parts"] if p["component_identifier"] == "SAMPLE-ORBIT-300-C2")
    assert any(name.startswith("Precision Sensors") for name in board_part["other_suppliers"])
    kestrel_lots = _ok(user.get(f"/api/v1/suppliers/{kestrel_id}/lots"))
    lot_3 = next(lot for lot in kestrel_lots["lots"] if lot["lot_identifier"].endswith("-LOT-003"))
    assert lot_3["evidence"] == [
        "Lot genealogy: built with Control Board (Sample) lot CB-1180 (Sample); Kestrel Sensors is a recorded supplier of it"
    ]
    # S360-11 (requests): the evidence request sent to the supplier.
    (request,) = page["evidence_requests"]
    assert request["title"].startswith("Calibration records") and request["investigation_identifier"] == "T-INV-42"


def test_an_unknown_or_another_organizations_supplier_is_not_found(trial):
    from sqlalchemy import text

    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    user = trial["user"]
    assert user.get("/api/v1/suppliers/NO-SUCH-SUPPLIER").status_code == 404
    with SessionLocal() as db:
        bind_system(db, "test: another organization's supplier")
        other = db.execute(
            text("SELECT id::text FROM suppliers WHERE tenant_id <> :t LIMIT 1"), {"t": str(trial["tenant_id"])}
        ).scalar()
    if other:
        for path in ("", "/complaints", "/lots"):
            response = user.get(f"/api/v1/suppliers/{other}{path}")
            assert response.status_code == 404 and other not in response.text
            assert response.json()["detail"]["code"] == "SUPPLIER_NOT_FOUND"


def test_a_pilot_is_not_offered_the_supplier_lots():
    """Owner, 10 Nov 2026: the lots sharing a supplier are a free trial's only, like a case's Lot impact. A pilot reads
    the supplier list but its lots answer 404 NOT_A_TRIAL_WORKSPACE, before the supplier is even looked up."""
    import uuid

    from tests.conftest import authenticated_client

    admin = authenticated_client()
    assert admin.get("/api/v1/suppliers").status_code == 200
    response = admin.get(f"/api/v1/suppliers/{uuid.uuid4()}/lots")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "NOT_A_TRIAL_WORKSPACE"
