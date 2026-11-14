"""Bad input gets a 4xx in the API's usual shape, never a server error (the 0.10.96 trial scan found seven 500s).

- a malformed id is not found (404, ``{"detail": {"code", "message"}}``), as an unknown one;
- an offset past any real list is refused by validation (422, ``{"detail": [{"loc", "msg", ...}]}``);
- a retrieval filter by record id reads the database with typed ids (no "uuid = character varying");
- a mapping rule that is not a rule is refused by validation (422).
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import authenticated_client

pytestmark = pytest.mark.db

BAD_ID = "not-a-uuid"
HUGE_OFFSET = 10**20  # past PostgreSQL's bigint: the database itself fails on it


@pytest.fixture(scope="module")
def client():
    return authenticated_client()


def _not_found(response, code: str) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == code


def _invalid(response, field: str) -> None:
    assert response.status_code == 422, response.text
    assert any(field in error["loc"] for error in response.json()["detail"])


def test_a_product_graph_with_a_malformed_id_is_not_found(client):
    _not_found(client.get(f"/api/v1/graph/products/{BAD_ID}"), "NODE_NOT_FOUND")


def test_an_investigation_graph_with_a_malformed_id_is_not_found(client):
    _not_found(client.get(f"/api/v1/graph/investigations/{BAD_ID}"), "NODE_NOT_FOUND")


def test_a_graph_node_and_its_neighbours_with_a_malformed_id_are_not_found(client):  # sibling routes
    _not_found(client.get(f"/api/v1/graph/nodes/product/{BAD_ID}"), "NODE_NOT_FOUND")
    _not_found(client.get(f"/api/v1/graph/nodes/product/{BAD_ID}/neighbors"), "NODE_NOT_FOUND")


def test_a_products_investigations_with_a_malformed_id_are_not_found(client):
    _not_found(client.get(f"/api/v1/products/{BAD_ID}/investigations"), "PRODUCT_NOT_FOUND")
    _not_found(client.get(f"/api/v1/products/{uuid.uuid4()}/investigations"), "PRODUCT_NOT_FOUND")


def test_the_product_list_refuses_an_offset_past_any_list(client):
    _invalid(client.get("/api/v1/products", params={"offset": HUGE_OFFSET}), "offset")
    assert client.get("/api/v1/products", params={"offset": 10_000_000, "limit": 1}).status_code == 200


def test_the_supplier_list_refuses_an_offset_past_any_list(client):
    _invalid(client.get("/api/v1/suppliers", params={"offset": HUGE_OFFSET}), "offset")


def test_the_communications_log_refuses_an_offset_past_any_list(client):  # sibling route
    _invalid(client.get("/api/v1/communications", params={"offset": HUGE_OFFSET}), "offset")


@pytest.mark.parametrize("field", ["product_id", "product_version_id", "component_id", "supplier_id", "lot_id"])
def test_a_retrieval_query_filtered_by_a_record_id_runs(client, field):
    body = {"query_text": "pump alarm during infusion", "retrieval_mode": "structured", field: str(uuid.uuid4())}
    response = client.post("/api/v1/retrieval/query", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["results_count"] == 0


def test_a_retrieval_query_for_an_unknown_investigation_is_not_found(client):
    body = {"query_text": "pump alarm during infusion", "investigation_id": str(uuid.uuid4())}
    _not_found(client.post("/api/v1/retrieval/query", json=body), "INVESTIGATION_NOT_FOUND")


@pytest.mark.parametrize(
    "rule",
    [
        "Complaint.description",  # a string, not a rule
        {"target_field": 7},
        {"target_field": "Complaint.description", "transform": ["upper"]},
        {"target_field": "Complaint.description", "required": {"yes": True}},
    ],
)
def test_a_mapping_preview_with_a_malformed_rule_is_refused(client, rule):
    body = {
        "connection_id": "preview-1",
        "records": [{"text": "Alarm"}],
        "target_entity": "Complaint",
        "mapping_version": "1",
        "rules": {"text": rule},
    }
    _invalid(client.post("/api/v1/integrations/preview", json=body), "rules")
    # The organization's own mapping preview (sibling route) reads the same rules.
    admin = {"records": body["records"], "rules": body["rules"], "source_object": "x", "target_entity": "Complaint"}
    _invalid(
        client.post(
            f"/api/v1/admin/configuration/mappings/{uuid.uuid4()}/preview", json={**admin, "mapping_version": "1"}
        ),
        "rules",
    )


def test_a_well_formed_mapping_preview_still_maps(client):
    body = {
        "connection_id": "preview-1",
        "records": [{"text": " Alarm "}],
        "target_entity": "Complaint",
        "mapping_version": "1",
        "rules": {"text": {"target_field": "Complaint.description", "transform": "trim", "required": True}},
    }
    response = client.post("/api/v1/integrations/preview", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["preview"]["records"] == [{"Complaint.description": "Alarm"}]
