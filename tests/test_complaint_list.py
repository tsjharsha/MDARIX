"""The complaint list: every product's complaints for the signed-in organization, searchable and paged."""

import uuid

from tests.test_business_permissions import _client_with_role


def test_lists_search_filter_and_page():
    user = _client_with_role("VIEWER")  # reading needs no write permission
    first = user.get("/api/v1/complaints", params={"page_size": 5})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] >= len(body["items"]) and len(body["items"]) <= 5 and body["pages"] >= 1
    item = body["items"][0]
    assert {"complaint_identifier", "product_name", "status", "investigations"} <= set(item)
    found = user.get("/api/v1/complaints", params={"q": item["complaint_identifier"]}).json()
    assert any(row["id"] == item["id"] for row in found["items"])
    by_product = user.get("/api/v1/complaints", params={"product_id": item["product_id"]}).json()
    assert all(row["product_id"] == item["product_id"] for row in by_product["items"])
    by_status = user.get("/api/v1/complaints", params={"status": item["status"]}).json()
    assert all(row["status"].lower() == item["status"].lower() for row in by_status["items"])


def test_search_text_is_literal_and_inputs_are_bounded():
    user = _client_with_role("VIEWER")
    assert user.get("/api/v1/complaints", params={"q": "%"}).json()["total"] == 0  # % is not a wildcard
    assert user.get("/api/v1/complaints", params={"page_size": 1000}).status_code == 422
    assert user.get("/api/v1/complaints", params={"product_id": "not-a-uuid"}).status_code == 422
    assert user.get("/api/v1/complaints", params={"product_id": str(uuid.uuid4())}).json()["total"] == 0
