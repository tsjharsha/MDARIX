"""APIs behind the user workspace Overview return real, tenant-scoped data."""

from sqlalchemy import text

from backend.app.db.session import engine
from tests.conftest import authenticated_client


def _tenant_complaints(tenant_id) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("select count(*) from complaints where tenant_id = :tenant_id"), {"tenant_id": tenant_id}
        ).scalar_one()


def test_signals_list_returns_the_tenants_complaints():
    client = authenticated_client()
    tenant_id = client.get("/api/v1/auth/session").json()["tenant_id"]
    expected = min(_tenant_complaints(tenant_id), 100)
    assert expected, "the golden dataset should give this tenant complaints"
    signals = client.get("/api/v1/analytics/signals").json()
    assert signals["tenant_id"] == tenant_id
    # The list used to be silently empty because the query named a column the table does not have.
    assert len(signals["signals"]) == expected
    assert {"signal_id", "description", "severity", "status", "event_timestamp"} <= set(signals["signals"][0])


def test_command_center_counts_match_the_signal_list():
    client = authenticated_client()
    counts = client.get("/api/v1/analytics/command-center").json()["counts"]
    assert counts["complaints"] == _tenant_complaints(client.get("/api/v1/auth/session").json()["tenant_id"])


def test_api_contract_is_served_to_platform_admins_only():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    admin = authenticated_client()  # legacy fixture user holds a platform role
    contract = admin.get("/api/v1/platform-admin/api-contract")
    assert contract.status_code == 200
    assert "/api/v1/platform-admin/api-contract" in contract.json()["paths"]
    assert TestClient(app).get("/api/v1/platform-admin/api-contract").status_code == 401
