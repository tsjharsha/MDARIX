"""Mapping Studio "Save version": the field rules it sends (a list) are saved as a draft version."""

import uuid

from tests.conftest import authenticated_client


def _active_master(platform) -> str:
    """A master mapping in ACTIVE status, made for the test (the Studio saves versions of an active master)."""
    made = platform.post(
        "/api/v1/admin/catalog/master-mappings",
        json={"code": f"MM_{uuid.uuid4().hex[:8].upper()}", "source_system": "TRACKWISE", "target_entity": "Complaint"},
    )
    assert made.status_code == 200, made.text
    master = made.json().get("id") or made.json().get("master_mapping_id")
    activated = platform.patch(f"/api/v1/admin/catalog/master-mappings/{master}/status", json={"status": "ACTIVE"})
    assert activated.status_code == 200, activated.text
    return master


def test_save_version_accepts_the_studios_field_rules():
    platform = authenticated_client()
    master = _active_master(platform)
    version = f"v-{uuid.uuid4().hex[:6]}"
    rules = [
        {
            "source_field": "complaint_number",
            "target_field": "complaint_id",
            "transform": "trim",
            "null_rule": "PRESERVE_UNKNOWN",
            "source_priority": "AUTHORITATIVE",
            "override_policy": "CUSTOMER_OVERRIDE_ALLOWED",
        }
    ]
    saved = platform.post(
        "/api/v1/admin/catalog/mapping-versions", json={"master_mapping_id": master, "version": version, "rules": rules}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "DRAFT"
    listed = platform.get("/api/v1/admin/catalog/mapping-versions").json()
    row = next(item for item in listed if item["id"] == saved.json()["id"])
    assert row["rules"] == rules  # read back exactly as the Studio shows it
    again = platform.post(
        "/api/v1/admin/catalog/mapping-versions", json={"master_mapping_id": master, "version": version, "rules": rules}
    )
    assert again.status_code == 409


def test_save_version_refuses_an_oversized_rule_list():
    platform = authenticated_client()
    too_many = [{"source_field": f"f{n}", "target_field": "x"} for n in range(501)]
    refused = platform.post(
        "/api/v1/admin/catalog/mapping-versions",
        json={"master_mapping_id": _active_master(platform), "version": "v-big", "rules": too_many},
    )
    assert refused.status_code == 422
