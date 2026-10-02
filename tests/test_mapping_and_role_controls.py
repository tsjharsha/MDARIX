"""Mappings that cannot import are not released; invitations accept only roles the organization has."""

import uuid

from tests.test_business_permissions import _client_with_role


def _invite(admin, role):
    return admin.post(
        "/api/v1/admin/identity/users",
        json={
            "email": f"role-{uuid.uuid4().hex[:8]}@example.invalid",
            "display_name": "Role test",
            "company": "Test",
            "role": role,
        },
    )


def test_unknown_roles_are_refused_and_custom_roles_accepted():
    admin = _client_with_role("CUSTOMER_ADMIN")
    for role in ("SUPERUSER'; DROP TABLE auth_users;--", "Approverr", "OWNER"):
        refused = _invite(admin, role)
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "ROLE_NOT_RECOGNIZED", role
    for role in ("Investigator", "REVIEWER", "approver"):
        assert _invite(admin, role).status_code == 200, role
    name = f"Quality Lead {uuid.uuid4().hex[:4]}"
    made = admin.post("/api/v1/admin/identity/roles", json={"code": f"QL_{uuid.uuid4().hex[:6].upper()}", "name": name})
    assert made.status_code == 200, made.text
    role_id = made.json().get("role_id") or made.json().get("id")
    assert _invite(admin, name).status_code == 422  # a draft role is not yet assignable
    assert admin.patch(f"/api/v1/admin/identity/roles/{role_id}/status", json={"status": "ACTIVE"}).status_code == 200
    assert _invite(admin, name).status_code == 200


def test_a_mapping_that_cannot_import_is_never_released():
    admin = _client_with_role("CUSTOMER_ADMIN")
    made = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": f"BAD_{uuid.uuid4().hex[:8].upper()}",
            "source_system": "X",
            "target_entity": "Product",
            "mapping_rules": {"hash": {"target_field": "AuthUser.password_hash", "transform": "identity"}},
        },
    )
    assert made.status_code == 200, made.text
    blocked = admin.post(
        f"/api/v1/admin/configuration/mappings/{made.json()['mapping_id']}/release-action",
        json={"action": "REQUEST_APPROVAL", "reason": "Trying to release a bad sheet"},
    )
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "RELEASE_GATE_BLOCKED"
    assert blocked.json()["detail"]["missing_required"] == ["product_id", "product_name"]
