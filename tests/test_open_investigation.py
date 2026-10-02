"""Opening an investigation for one of the tenant's own products, with the complaints that prompted it."""

import uuid

from backend.app.db.models.foundation import Complaint, Product, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_business_permissions import _client_with_role


def _product_with_complaints():
    with SessionLocal() as db:
        bind_system(db, "test: pick a product")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        for product in db.query(Product).filter(Product.tenant_id == tenant.id):
            complaints = [row[0] for row in db.query(Complaint.id).filter(Complaint.product_id == product.id).limit(3)]
            other = (
                db.query(Complaint.id)
                .filter(Complaint.tenant_id == tenant.id, Complaint.product_id != product.id)
                .first()
            )
            if complaints and other:
                return str(product.id), [str(c) for c in complaints], str(other[0])
    raise AssertionError("the golden dataset has products with complaints")


def test_an_investigator_opens_a_case_and_works_on_it():
    product_id, complaints, _ = _product_with_complaints()
    user = _client_with_role("INVESTIGATOR")
    made = user.post(
        "/api/v1/investigations",
        json={
            "product_id": product_id,
            "investigation_question": "Why did alarms rise after the latest release?",
            "complaint_ids": complaints,
        },
    )
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["investigation_identifier"].startswith("INV-") and body["complaints_linked"] == len(complaints)
    assert body["owner_ref"]  # assigned to the person who opened it
    assert user.get(f"/api/v1/investigations/{body['id']}/workspace").status_code == 200
    listed = user.get("/api/v1/data-plane/investigations?limit=500").json()["records"]
    assert any(row["id"] == body["id"] and row["owner_ref"] == body["owner_ref"] for row in listed)


def test_opening_a_case_is_checked():
    product_id, _, other_complaint = _product_with_complaints()
    question = "A question long enough to be accepted"
    assert (
        _client_with_role("VIEWER")
        .post("/api/v1/investigations", json={"product_id": product_id, "investigation_question": question})
        .status_code
        == 403
    )
    user = _client_with_role("INVESTIGATOR")
    foreign = user.post(
        "/api/v1/investigations", json={"product_id": str(uuid.uuid4()), "investigation_question": question}
    )
    assert foreign.status_code == 404
    wrong = user.post(
        "/api/v1/investigations",
        json={"product_id": product_id, "investigation_question": question, "complaint_ids": [other_complaint]},
    )
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "COMPLAINT_NOT_FOR_PRODUCT"
    identifier = f"INV-TEST-{uuid.uuid4().hex[:6].upper()}"
    first = user.post(
        "/api/v1/investigations",
        json={"product_id": product_id, "investigation_question": question, "investigation_identifier": identifier},
    )
    assert first.status_code == 201
    again = user.post(
        "/api/v1/investigations",
        json={"product_id": product_id, "investigation_question": question, "investigation_identifier": identifier},
    )
    assert again.status_code == 409
    short = user.post("/api/v1/investigations", json={"product_id": product_id, "investigation_question": "Why?"})
    assert short.status_code == 422
