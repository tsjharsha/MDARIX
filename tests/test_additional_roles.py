"""Additional workflow roles (Phase 1) against the live API: a customer administrator grants and revokes them with a
reason (audited), administrator roles and the account role are refused, other organizations' people are not found,
the person's session and the API use the union of their roles, and erasure removes them. Also the workspace
context's case resolution for deep links (/app/<view>?case=INV000147)."""

import uuid

import pytest

from backend.app.access.permissions import permissions_for_roles
from backend.app.db.models.foundation import AuditEvent, Investigation, Product, Tenant
from backend.app.db.models.workflow import UserAdditionalRole
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import GOLDEN_TENANT_KEY, golden_investigation_id
from tests.test_business_permissions import _client_with_role
from tests.test_customer_admin_account_security import _client_for, _tenant, _user

REASON = "Small team: the investigator also reviews risks"


@pytest.fixture(scope="module")
def world():
    db = SessionLocal()
    try:
        bind_system(db, "test: additional workflow roles")
        tenant = _tenant(db, "ROLES")
        other = _tenant(db, "ROLESX")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "roles-admin")
        second_admin = _user(db, tenant, "CUSTOMER_ADMIN", "roles-admin-two")
        investigator = _user(db, tenant, "Investigator", "roles-investigator")
        viewer = _user(db, tenant, "Viewer", "roles-viewer")
        leaver = _user(db, tenant, "Investigator", "roles-leaver")
        foreign = _user(db, other, "Investigator", "roles-foreign")
        db.commit()
        clients = {
            "admin": _client_for(db, admin),
            "investigator": _client_for(db, investigator),
            "viewer": _client_for(db, viewer),
        }
        db.commit()
        return {
            **clients,
            "admin_id": str(admin.id),
            "second_admin_id": str(second_admin.id),
            "investigator_id": str(investigator.id),
            "viewer_id": str(viewer.id),
            "leaver_id": str(leaver.id),
            "foreign_id": str(foreign.id),
            "tenant_id": tenant.id,
        }
    finally:
        db.close()


def _put(world, user_id, roles, reason=REASON):
    return world["admin"].put(
        f"/api/v1/admin/identity/users/{user_id}/roles", json={"additional_roles": roles, "reason": reason}
    )


def _rows(user_id):
    with SessionLocal() as db:
        bind_system(db, "test: read additional roles")
        return {
            row.role_code: row.status
            for row in db.query(UserAdditionalRole).filter(UserAdditionalRole.user_id == uuid.UUID(user_id))
        }


def _audits(user_id, action):
    with SessionLocal() as db:
        bind_system(db, "test: read role audit events")
        return [
            (row.details or {}).get("role")
            for row in db.query(AuditEvent).filter(
                AuditEvent.entity_id == uuid.UUID(user_id), AuditEvent.action == action
            )
        ]


def test_a_person_starts_with_their_account_role_only(world):
    response = world["admin"].get(f"/api/v1/admin/identity/users/{world['investigator_id']}/roles")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account_role"] == {"code": "INVESTIGATOR", "label": "Quality Investigator"}
    assert body["additional_roles"] == []
    available = [item["code"] for item in body["available_roles"]]
    assert available == ["TRIAGE_LEAD", "RISK_REVIEWER", "REGULATORY_REVIEWER", "REVIEWER", "APPROVER", "LEADER"]
    assert "CUSTOMER_ADMIN" not in available and "PLATFORM_ADMIN" not in available


def test_granting_and_revoking_roles_is_audited_and_changes_the_session(world):
    single = world["investigator"].get("/api/v1/session/context").json()
    assert single["business_permissions"] == sorted(permissions_for_roles(["Investigator"]))
    assert [role["source"] for role in single["roles"]] == ["account"]

    granted = _put(world, world["investigator_id"], ["risk_reviewer", "APPROVER", "RISK_REVIEWER"])
    assert granted.status_code == 200, granted.text
    roles = granted.json()["additional_roles"]
    assert [(role["code"], role["label"]) for role in roles] == [
        ("RISK_REVIEWER", "Risk Reviewer"),
        ("APPROVER", "Authorized Decision Maker"),
    ]
    assert all(role["granted_by_name"] == "roles-admin" and role["granted_at"] for role in roles)
    assert _rows(world["investigator_id"]) == {"RISK_REVIEWER": "ACTIVE", "APPROVER": "ACTIVE"}
    assert sorted(_audits(world["investigator_id"], "ROLE_GRANTED")) == ["APPROVER", "RISK_REVIEWER"]

    session = world["investigator"].get("/api/v1/session/context").json()
    assert session["active_role"] == single["active_role"]  # the account role is unchanged
    assert session["roles"] == [
        {"code": "INVESTIGATOR", "label": "Quality Investigator", "source": "account"},
        {"code": "RISK_REVIEWER", "label": "Risk Reviewer", "source": "additional"},
        {"code": "APPROVER", "label": "Authorized Decision Maker", "source": "additional"},
    ]
    assert session["business_permissions"] == sorted(
        permissions_for_roles(["Investigator", "RISK_REVIEWER", "APPROVER"])
    )

    revoked = _put(world, world["investigator_id"], ["APPROVER"])
    assert revoked.status_code == 200, revoked.text
    assert [role["code"] for role in revoked.json()["additional_roles"]] == ["APPROVER"]
    assert _rows(world["investigator_id"]) == {"RISK_REVIEWER": "REVOKED", "APPROVER": "ACTIVE"}
    assert _audits(world["investigator_id"], "ROLE_REVOKED") == ["RISK_REVIEWER"]

    # Granted again after a revocation: the same row becomes active again.
    again = _put(world, world["investigator_id"], ["APPROVER", "RISK_REVIEWER"])
    assert again.status_code == 200, again.text
    assert _rows(world["investigator_id"]) == {"RISK_REVIEWER": "ACTIVE", "APPROVER": "ACTIVE"}

    cleared = _put(world, world["investigator_id"], [])
    assert cleared.status_code == 200 and cleared.json()["additional_roles"] == []
    after = world["investigator"].get("/api/v1/session/context").json()
    assert after["business_permissions"] == single["business_permissions"]
    assert after["roles"] == single["roles"]


@pytest.mark.parametrize("role", ["CUSTOMER_ADMIN", "Customer Admin", "PLATFORM_ADMIN", "Administrator", "OWNER"])
def test_administrator_and_unknown_roles_are_refused(world, role):
    response = _put(world, world["investigator_id"], [role])
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"


def test_the_account_role_is_not_an_additional_role(world):
    response = _put(world, world["investigator_id"], ["Investigator"])
    assert response.status_code == 422 and response.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"


def test_an_administrator_account_cannot_hold_workflow_roles(world):
    # Administrators stay outside the case workflow, so another administrator cannot give them a workflow role.
    response = _put(world, world["second_admin_id"], ["Risk Reviewer"])
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"
    assert _rows(world["second_admin_id"]) == {}


def test_a_reason_is_required(world):
    assert _put(world, world["investigator_id"], ["APPROVER"], reason="short").status_code == 422
    assert _put(world, world["investigator_id"], ["APPROVER"], reason=" " * 12).status_code == 422


def test_another_organizations_person_is_not_found(world):
    assert world["admin"].get(f"/api/v1/admin/identity/users/{world['foreign_id']}/roles").status_code == 404
    assert _put(world, world["foreign_id"], ["APPROVER"]).status_code == 404
    assert _rows(world["foreign_id"]) == {}


def test_an_administrator_cannot_change_their_own_roles(world):
    response = _put(world, world["admin_id"], ["APPROVER"])
    assert response.status_code == 409 and response.json()["detail"]["code"] == "SELF_CHANGE_NOT_ALLOWED"


def test_business_users_cannot_manage_roles(world):
    response = world["investigator"].put(
        f"/api/v1/admin/identity/users/{world['viewer_id']}/roles",
        json={"additional_roles": ["LEADER"], "reason": REASON},
    )
    assert response.status_code == 403
    assert _rows(world["viewer_id"]) == {}


def test_the_api_enforces_the_union_of_roles(world):
    refused = world["viewer"].post("/api/v1/stage3/interactions", json={"prompt": "What changed?"})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"
    assert _put(world, world["viewer_id"], ["RISK_REVIEWER"]).status_code == 200
    try:
        allowed = world["viewer"].post("/api/v1/stage3/interactions", json={"prompt": "What changed?"})
        detail = (
            allowed.json().get("detail")
            if allowed.headers.get("content-type", "").startswith("application/json")
            else None
        )
        assert not (
            allowed.status_code == 403 and isinstance(detail, dict) and detail.get("code") == "PERMISSION_DENIED"
        )
    finally:
        assert _put(world, world["viewer_id"], []).status_code == 200


def test_the_user_list_shows_role_labels(world):
    listed = world["admin"].get("/api/v1/admin/identity/users").json()
    row = next(item for item in listed if item["id"] == world["investigator_id"])
    assert row["role"] == "Investigator" and row["role_label"] == "Quality Investigator"


def test_erasure_removes_the_persons_additional_roles(world):
    assert _put(world, world["leaver_id"], ["REVIEWER"]).status_code == 200
    offboarded = world["admin"].patch(
        f"/api/v1/admin/identity/users/{world['leaver_id']}/status", json={"status": "OFFBOARDED"}
    )
    assert offboarded.status_code == 200, offboarded.text
    erased = world["admin"].post(
        f"/api/v1/admin/identity/users/{world['leaver_id']}/erase",
        json={"reason": "The person asked in writing for their data to be erased (ticket 4712)."},
    )
    assert erased.status_code == 200, erased.text
    assert erased.json()["deleted_records"].get("user_additional_roles") == 1
    assert _rows(world["leaver_id"]) == {}


# ------------------------------------------------------------------------------------------- deep links


def _golden_case():
    with SessionLocal() as db:
        bind_system(db, "test: golden case for deep links")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).one()
        case = db.query(Investigation).filter(Investigation.id == uuid.UUID(golden_investigation_id())).one()
        other = (
            db.query(Product)
            .filter(Product.tenant_id == tenant.id, Product.id != case.product_id)
            .order_by(Product.created_at)
            .first()
        )
        return case, other


def test_a_deep_link_resolves_to_the_case_and_its_product():
    case, _ = _golden_case()
    client = _client_with_role("Investigator")
    for value in (case.business_id, case.business_id.lower(), case.investigation_identifier):
        response = client.get("/api/v1/workspace/context/resolve", params={"investigation": value})
        assert response.status_code == 200, response.text
        assert response.json()["investigation_id"] == str(case.id)
        assert response.json()["investigation_business_id"] == case.business_id
        assert response.json()["product_id"] == str(case.product_id)
        assert response.json()["product_business_id"]
    missing = client.get("/api/v1/workspace/context/resolve", params={"investigation": "INV999999999"})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_another_organization_cannot_resolve_the_case(world):
    case, _ = _golden_case()
    response = world["investigator"].get(
        "/api/v1/workspace/context/resolve", params={"investigation": case.business_id}
    )
    assert response.status_code in {404, 503}
    assert str(case.id) not in response.text


def test_the_saved_context_follows_the_case_and_names_it():
    case, other = _golden_case()
    client = _client_with_role("Investigator")
    try:
        saved = client.put("/api/v1/workspace/context", json={"investigation_id": str(case.id)})
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["product_id"] == str(case.product_id)
        assert body["investigation_business_id"] == case.business_id and body["product_business_id"]
        if other is not None:
            # A product that is not the case's is replaced by the case's product.
            aligned = client.put(
                "/api/v1/workspace/context", json={"product_id": str(other.id), "investigation_id": str(case.id)}
            )
            assert aligned.status_code == 200, aligned.text
            assert aligned.json()["product_id"] == str(case.product_id)
            assert aligned.json()["investigation_id"] == str(case.id)
    finally:
        client.post("/api/v1/workspace/context/reset")
