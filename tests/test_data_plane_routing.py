import os

from fastapi.testclient import TestClient

from backend.app.main import app

# Same variable scripts/provision_day35_fixture.py uses to set fixture passwords.
FIXTURE_PASSWORD = os.environ.get("DAY35_FIXTURE_PASSWORD", "LegacyTestPassword123!")


def test_authenticated_business_reads_use_registered_tenant_data_plane():
    client = TestClient(app)
    signin = client.post(
        "/api/v1/auth/signin",
        json={"email": "r1-user-01@synthetic.invalid", "password": FIXTURE_PASSWORD},
    )
    assert signin.status_code == 200

    response = client.get("/api/v1/data-plane/products")
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == signin.json()["tenant_id"]
    assert body["records"]
    assert all(row["tenant_id"] == body["tenant_id"] for row in body["records"])


def test_business_data_plane_does_not_accept_a_caller_selected_tenant():
    client = TestClient(app)
    signin = client.post(
        "/api/v1/auth/signin",
        json={"email": "r1-user-01@synthetic.invalid", "password": FIXTURE_PASSWORD},
    )
    assert signin.status_code == 200
    response = client.get("/api/v1/data-plane/products?tenant_id=R1_TENANT_2")
    assert response.status_code == 200
    assert response.json()["tenant_id"] == signin.json()["tenant_id"]


def test_product360_investigation_workspace_and_evidence_use_data_plane():
    client = TestClient(app)
    signin = client.post(
        "/api/v1/auth/signin",
        json={"email": "r1-user-01@synthetic.invalid", "password": FIXTURE_PASSWORD},
    )
    assert signin.status_code == 200
    products = client.get("/api/v1/products").json()
    assert products
    product_id = products[0]["id"]
    assert client.get(f"/api/v1/products/{product_id}/product-360").status_code == 200
    investigations = client.get(f"/api/v1/products/{product_id}/investigations").json()
    assert investigations
    investigation_id = investigations[0]["id"]
    assert client.get(f"/api/v1/investigations/{investigation_id}/workspace").status_code == 200
    assert client.get("/api/v1/evidence").status_code == 200


def test_evidence_intelligence_processing_writes_to_tenant_data_plane():
    client = TestClient(app)
    signin = client.post(
        "/api/v1/auth/signin",
        json={"email": "r1-user-01@synthetic.invalid", "password": FIXTURE_PASSWORD},
    )
    assert signin.status_code == 200
    evidence_id = client.get("/api/v1/evidence").json()[0]["id"]
    response = client.post(f"/api/v1/evidence/{evidence_id}/process")
    assert response.status_code == 200
    assert response.json()["evidence_summary"]["provenance"]["tenant_id"] == signin.json()["tenant_id"]
