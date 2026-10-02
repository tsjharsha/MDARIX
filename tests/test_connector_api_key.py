"""A connector keeps the customer system's API key encrypted: never returned, bound to its connector, removable."""

import uuid
from types import SimpleNamespace

import pytest

from access_control.connector_secrets import open_sealed, seal
from backend.app.access.common import _connector_credential
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role


def _connector(admin) -> str:
    created = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={
            "code": f"key-{uuid.uuid4().hex[:6]}",
            "connector_type": "REST",
            "configuration": {"endpoint": "http://127.0.0.1:8101", "source_object": "complaints"},
        },
    )
    assert created.status_code == 200, created.text
    return created.json()["connector_id"]


def test_the_api_key_is_stored_encrypted_and_never_shown_again():
    admin = authenticated_client()
    connector_id = _connector(admin)
    key = "sk_trackwise_" + uuid.uuid4().hex
    saved = admin.put(f"/api/v1/admin/configuration/connectors/{connector_id}/api-key", json={"api_key": key})
    assert saved.status_code == 200, saved.text
    assert saved.json() == {"connector_id": connector_id, "has_api_key": True, "api_key_ends_with": key[-4:]}
    listed = next(
        item for item in admin.get("/api/v1/admin/configuration/connectors").json() if item["id"] == connector_id
    )
    assert listed["has_api_key"] and listed["api_key_ends_with"] == key[-4:]
    assert key not in str(listed)
    removed = admin.delete(f"/api/v1/admin/configuration/connectors/{connector_id}/api-key")
    assert removed.status_code == 200 and removed.json()["has_api_key"] is False
    assert admin.delete(f"/api/v1/admin/configuration/connectors/{connector_id}/api-key").status_code == 404


def test_only_administrators_of_the_tenant_can_set_a_key():
    admin = authenticated_client()
    connector_id = _connector(admin)
    investigator = _client_with_role("Investigator")
    refused = investigator.put(
        f"/api/v1/admin/configuration/connectors/{connector_id}/api-key", json={"api_key": "sk_abcdefgh123"}
    )
    assert refused.status_code in {401, 403}
    unknown = admin.put(
        f"/api/v1/admin/configuration/connectors/{uuid.uuid4()}/api-key", json={"api_key": "sk_abcdefgh123"}
    )
    assert unknown.status_code == 404
    spaces = admin.put(
        f"/api/v1/admin/configuration/connectors/{connector_id}/api-key", json={"api_key": "has spaces in it"}
    )
    assert spaces.status_code == 422


def test_a_sealed_key_only_opens_for_its_own_connector():
    tenant, connector, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sealed = seal("sk_secret_value_1", tenant, connector)
    assert "sk_secret" not in sealed
    assert open_sealed(sealed, tenant, connector) == "sk_secret_value_1"
    with pytest.raises(Exception):
        open_sealed(sealed, tenant, other)
    stored = SimpleNamespace(credential_encrypted=sealed, tenant_id=tenant, id=connector)
    assert _connector_credential({"credential_ref": "MDARIX_CONNECTOR_SECRET_UNUSED"}, stored) == "sk_secret_value_1"
    moved = SimpleNamespace(credential_encrypted=sealed, tenant_id=tenant, id=other)
    with pytest.raises(ValueError, match="CONNECTOR_CREDENTIAL_UNREADABLE"):
        _connector_credential({}, moved)
