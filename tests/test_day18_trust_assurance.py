from fastapi.testclient import TestClient
from backend.app.main import app
from tests.conftest import authenticated_client, golden_investigation_id


def test_assurance_persists_profile_and_checks():
    client = authenticated_client(app)
    # Create a real investigator execution in the golden tenant instead of
    # relying on an execution id that only existed in one local database.
    investigation_id = golden_investigation_id()
    analysis = client.post(f"/api/v1/investigations/{investigation_id}/analysis", json={"investigation_id": investigation_id})
    assert analysis.status_code == 200
    EXECUTION = analysis.json()["ai_execution_id"]
    response = client.post(f"/api/v1/ai-executions/{EXECUTION}/assurance", json={"output_type": "AI_INVESTIGATOR"})
    assert response.status_code == 200
    body = response.json()
    assert body["trust_policy_version"] == "MDARIX_AI_TRUST_POLICY_R1_V1"
    assert body["configuration_hash"] and len(body["configuration_hash"]) == 64
    assert len(body["checks"]) >= 5
    assert body["human_review_required"] is True

def test_foreign_execution_is_not_available():
    response = authenticated_client(app).get("/api/v1/ai-executions/00000000-0000-0000-0000-000000000000/assurance")
    assert response.status_code == 404
