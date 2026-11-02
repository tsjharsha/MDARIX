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


def test_filters_by_version_lot_problem_code_country_and_source():
    """The sample trial's complaints (backend/app/trial/sample_data.py), filtered the way Automatic insights does."""
    from tests.test_free_trial import _approved_trial_client

    user, _approval, _email = _approved_trial_client()

    def listed(**params):
        response = user.get("/api/v1/complaints", params={"page_size": 200, **params})
        assert response.status_code == 200, response.text
        return response.json()

    every = listed()
    assert every["total"] == 37
    # The filters' choices: what the complaints record, each version named with its product.
    assert {"NFF", "FLOW_ZERO_READING"} <= set(every["problem_codes"])
    assert {"US", "Germany", "France"} <= set(every["countries"])
    orbit_b = next(v for v in every["versions"] if v["label"] == "OrbitCare 300 Infusion Pump (Sample) Rev B")
    assert orbit_b["business_id"] and orbit_b["id"]

    by_version = listed(version=orbit_b["business_id"])
    assert by_version["total"] == 17 and all(row["version"] == "Rev B" for row in by_version["items"])
    assert listed(version=orbit_b["id"])["total"] == 17  # its id works too
    by_lot = listed(lot="sample-orbit-300-lot-003")  # a lot number in any case
    assert by_lot["total"] == 9 and {row["lot"] for row in by_lot["items"]} == {"SAMPLE-ORBIT-300-LOT-003"}
    assert listed(problem_code="nff")["total"] == 3
    assert {row["complaint_identifier"] for row in listed(country="Germany")["items"]} == {"SAMPLE-RV-02"}
    # Filters combine, and paging still counts what matched.
    combined = listed(version=orbit_b["business_id"], problem_code="NFF", country="US")
    assert {row["complaint_identifier"] for row in combined["items"]} == {"SAMPLE-RV-03"}
    paged = user.get("/api/v1/complaints", params={"version": orbit_b["business_id"], "page_size": 5}).json()
    assert paged["total"] == 17 and len(paged["items"]) == 5 and paged["pages"] == 4
    assert listed(source_system="MDARIX_SAMPLE")["total"] == 37 and listed(source_system="TRIAL_UPLOAD")["total"] == 0
    # The sources the complaints come from, for "Only your imported data" and "Only the sample data" (DEV-017).
    assert every["sources"] == ["MDARIX_SAMPLE"]
    own = (
        "complaint_id,product_id,description,received_date\n"
        "VAL-CMP-001,VAL-PUMP-100,Occlusion alarm with no occlusion present,2026-10-20\n"
    )
    assert user.post("/api/v1/trial/imports/complaints", content=own).status_code == 200
    assert listed()["sources"] == ["MDARIX_SAMPLE", "TRIAL_UPLOAD"]
    imported = listed(source_system="TRIAL_UPLOAD")
    assert [row["complaint_identifier"] for row in imported["items"]] == ["VAL-CMP-001"]
    assert listed(source_system="MDARIX_SAMPLE")["total"] == 37 and listed()["total"] == 38

    # Another organization's version or lot never matches there, and its list offers none of these.
    other = _client_with_role("VIEWER")
    assert other.get("/api/v1/complaints", params={"version": orbit_b["id"]}).json()["total"] == 0
    assert other.get("/api/v1/complaints", params={"lot": "SAMPLE-ORBIT-300-LOT-003"}).json()["total"] == 0
    assert orbit_b["id"] not in {v["id"] for v in other.get("/api/v1/complaints").json()["versions"]}
    assert user.get("/api/v1/complaints", params={"country": "x" * 81}).status_code == 422
