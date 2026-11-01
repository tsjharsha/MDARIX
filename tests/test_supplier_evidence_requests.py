"""Supplier evidence requests go only to the tenant's own suppliers, carry no links, and are rate limited."""

import uuid

from sqlalchemy import text

from backend.app.db.session import engine
from tests.test_business_permissions import _client_with_role

PATH = "/api/v1/stage3/supplier-evidence-requests"


def own_supplier(client) -> str:
    """A supplier of the client's tenant, loaded through the workspace import; returns its id."""
    identifier = f"SUP-T-{uuid.uuid4().hex[:8].upper()}"
    loaded = client.post("/api/v1/data/import/suppliers", content=f"supplier_id,supplier_name\n{identifier},Test Co\n")
    assert loaded.status_code == 200, loaded.text
    with engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT id FROM suppliers WHERE supplier_identifier = :id"), {"id": identifier}
            ).scalar()
        )


def _body(supplier_id: str, **changes) -> dict:
    return {
        "recipient": "quality@supplier.example",
        "title": "Certificate of conformance for lot KS-5521",
        "requested_items": ["Certificate of conformance", "Drift test data"],
        "supplier_id": supplier_id,
        **changes,
    }


def test_a_request_needs_one_of_your_suppliers_and_a_real_address():
    user = _client_with_role("INVESTIGATOR")
    supplier = own_supplier(user)
    made = user.post(PATH, json=_body(supplier))
    assert made.status_code == 200, made.text
    listed = next(item for item in user.get(PATH).json() if item["id"] == made.json()["id"])
    assert listed["supplier_id"] == supplier and listed["created_at"]
    assert listed["status"] in {"SENT", "PENDING_DELIVERY"}

    unknown = user.post(PATH, json=_body(str(uuid.uuid4())))
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "SUPPLIER_NOT_FOUND"
    missing = {key: value for key, value in _body(supplier).items() if key != "supplier_id"}
    assert user.post(PATH, json=missing).status_code == 422
    for recipient in ("not-an-address", "a@b", "two@one.com, three@two.com"):
        assert user.post(PATH, json=_body(supplier, recipient=recipient)).status_code == 422
    other_case = user.post(PATH, json=_body(supplier, investigation_id=str(uuid.uuid4())))
    assert other_case.status_code == 404 and other_case.json()["detail"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_links_are_refused_so_the_email_cannot_be_used_for_phishing():
    user = _client_with_role("INVESTIGATOR")
    supplier = own_supplier(user)
    assert user.post(PATH, json=_body(supplier, title="Please log in at https://evil.example")).status_code == 422
    assert user.post(PATH, json=_body(supplier, requested_items=["see www.evil.example"])).status_code == 422


def test_requests_are_rate_limited_per_person(monkeypatch):
    monkeypatch.setenv("MDARIX_SUPPLIER_REQUESTS_PER_HOUR", "1")
    user = _client_with_role("INVESTIGATOR")
    supplier = own_supplier(user)
    first = user.post(PATH, json=_body(supplier))
    second = user.post(PATH, json=_body(supplier))
    assert first.status_code in {200, 429}
    assert second.status_code == 429 and second.json()["detail"]["code"] == "SUPPLIER_REQUEST_LIMIT"


def test_the_workspace_lists_its_own_suppliers_and_capas():
    user = _client_with_role("INVESTIGATOR")
    supplier = own_supplier(user)
    listed = user.get("/api/v1/data-plane/suppliers").json()["records"]
    assert supplier in {str(row["id"]) for row in listed}
    assert user.get("/api/v1/data-plane/capas").status_code == 200


def test_a_free_trial_saves_a_supplier_request_and_never_emails_it(monkeypatch):
    """J33: a trial e-mailed any address although the guides say MDARIX sends nothing from a trial."""
    import auth.emailer
    from tests.test_free_trial import _approved_trial_client

    def must_not_send(*_args, **_kwargs):
        raise AssertionError("a free trial must not email a supplier")

    monkeypatch.setattr(auth.emailer, "send_supplier_evidence_request", must_not_send)
    user, _, _ = _approved_trial_client()
    identifier = f"SUP-TR-{uuid.uuid4().hex[:8].upper()}"
    loaded = user.post(
        "/api/v1/trial/imports/suppliers",
        content=f"supplier_id,supplier_name\n{identifier},Trial Supplier Co\n",
        headers={"Content-Type": "text/csv"},
    )
    assert loaded.status_code == 200, loaded.text
    with engine.connect() as connection:
        supplier = str(
            connection.execute(
                text("SELECT id FROM suppliers WHERE supplier_identifier = :id"), {"id": identifier}
            ).scalar()
        )
    made = user.post(PATH, json=_body(supplier))
    assert made.status_code == 200, made.text
    assert made.json()["status"] == "SAVED" and made.json()["email_delivery"] == "NOT_SENT_IN_TRIAL"
