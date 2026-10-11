"""Data & Configuration: master reference data, customer product configuration, and wizard mappings."""

import uuid

import pytest

from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


def test_reference_data_lists_the_seeded_master_values(platform):
    response = platform.get("/api/v1/platform-admin/reference-data")
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {
        "value_sets",
        "countries",
        "units",
        "timezones",
        "jurisdictions",
        "data_quality_rules",
        "reference_resolution_rules",
    }
    assert data["countries"] and data["units"] and data["value_sets"]
    severity = next(item for item in data["value_sets"] if item["code"] == "COMPLAINT_SEVERITY")
    assert severity["values"] >= 1
    items = platform.get("/api/v1/platform-admin/reference-data/value-sets/complaint_severity").json()
    assert items["code"] == "COMPLAINT_SEVERITY" and len(items["items"]) == severity["values"]
    assert all(item["label"] for item in items["items"])
    assert platform.get("/api/v1/platform-admin/reference-data/value-sets/NO_SUCH_SET").status_code == 404


@pytest.mark.parametrize(
    "path", ["/api/v1/platform-admin/reference-data", "/api/v1/platform-admin/reference-data/value-sets/X"]
)
def test_reference_data_is_for_platform_administrators_only(path):
    assert _client_with_role("CUSTOMER_ADMIN").get(path).status_code == 403


def test_a_platform_administrator_edits_a_tenant_product(platform):
    code = f"PDC{uuid.uuid4().hex[:6].upper()}"
    tenant = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Product Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    ).json()
    from tests.support_grants import grant_for

    grant_for(platform, tenant["id"], areas=("CONFIGURATION",))  # Configuration, with changes, approved
    created = platform.post(
        "/api/v1/platform/product-configuration/products",
        json={"tenant_id": tenant["id"], "product_identifier": f"P-{code}", "name": "Infusion Pump"},
    )
    assert created.status_code == 200, created.text
    product_id = created.json()["id"]
    edited = platform.patch(
        f"/api/v1/platform/product-configuration/{tenant['id']}/products/{product_id}",
        json={"name": "Infusion Pump 2", "product_family": "Pumps", "manufacturer_context": "Acme"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["product_identifier"] == f"P-{code}"
    config = platform.get(f"/api/v1/platform/product-configuration/{tenant['id']}").json()
    product = next(item for item in config["products"] if item["id"] == product_id)
    assert (product["name"], product["family"], product["manufacturer"]) == ("Infusion Pump 2", "Pumps", "Acme")
    # Only known fields and a valid status; the identifier is not editable here.
    assert (
        platform.patch(
            f"/api/v1/platform/product-configuration/{tenant['id']}/products/{product_id}",
            json={"lifecycle_status": "deleted"},
        ).status_code
        == 422
    )
    assert (
        platform.patch(
            f"/api/v1/platform/product-configuration/{tenant['id']}/products/{product_id}", json={}
        ).status_code
        == 422
    )
    other = platform.patch(
        f"/api/v1/platform/product-configuration/{uuid.uuid4()}/products/{product_id}", json={"name": "Wrong tenant"}
    )
    assert other.status_code == 404
    denied = _client_with_role("CUSTOMER_ADMIN").patch(
        f"/api/v1/platform/product-configuration/{tenant['id']}/products/{product_id}", json={"name": "No"}
    )
    assert denied.status_code == 403


def test_a_wizard_mapping_lists_one_row_per_field_rule(platform):
    code = f"WIZ_{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": code,
            "source_system": "TRACKWISE",
            "target_entity": "COMPLAINT",
            "mapping_rules": {
                "rules": [
                    {"kind": "field", "source_field": "complaint_id", "target_field": "complaint_number"},
                    {"kind": "field", "source_field": "event_date", "target_field": "event_date"},
                ]
            },
        },
    )
    assert created.status_code == 200, created.text
    rows = [
        row for row in platform.get("/api/v1/admin/configuration/data-mappings").json() if row["mapping_code"] == code
    ]
    # Previously the whole list became one row whose target was "[object Object],[object Object]".
    assert [(row["source_field"], row["target_field"]) for row in rows] == [
        ("complaint_id", "complaint_number"),
        ("event_date", "event_date"),
    ]
