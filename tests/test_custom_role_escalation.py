"""R11 (SEC-05): a custom role never makes an administrator an approver.

Administrators manage people and settings and never sign (separation of duties). Custom roles are created, activated
and assigned by administrators, and an active assignment takes precedence over the account role. Before 0.10.49 a
customer administrator could give their own account an active custom role named "Approver": the signing refusal then
no longer saw an administrator. The guards here match the ones on the account role and on additional roles: nobody
changes their own role, an administrator account keeps its administrator role, and administrator roles are given on
the account, never as custom roles.
"""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.access.permissions import DECISION_SIGN, REGULATORY_APPROVE
from backend.app.db.models.foundation import RoleAssignment, RoleDefinition
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import PASSWORD, _client_for, _tenant, _user


@pytest.fixture(scope="module")
def org():
    """One organization: the administrator under test, a second administrator and a member."""
    with SessionLocal() as db:
        bind_system(db, "test: R11 custom roles and administrators")
        tenant = _tenant(db, "R11")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "r11-admin")
        peer = _user(db, tenant, "CUSTOMER_ADMIN", "r11-peer-admin")
        member = _user(db, tenant, "Viewer", "r11-member")
        newcomer = _user(db, tenant, "Viewer", "r11-newcomer")
        db.commit()
        return {
            "admin": _client_for(db, admin),
            "admin_id": str(admin.id),
            "peer": _client_for(db, peer),
            "peer_id": str(peer.id),
            "member_id": str(member.id),
            "newcomer": _client_for(db, newcomer),
            "newcomer_id": str(newcomer.id),
            "tenant_id": tenant.id,
        }


def _active_role(client, name: str) -> str:
    """Create a custom role with this name and activate it, as an administrator can."""
    code = f"{name.upper().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    created = client.post("/api/v1/admin/identity/roles", json={"code": code, "name": name})
    assert created.status_code == 200, created.text
    role_id = created.json()["role_id"]
    activated = client.patch(f"/api/v1/admin/identity/roles/{role_id}/status", json={"status": "ACTIVE"})
    assert activated.status_code == 200, activated.text
    return role_id


def _signing_refusal(client) -> str | None:
    """The refusal code for a signature. The administrator check comes first, so no real decision is needed."""
    response = client.post(
        f"/api/v1/governance/decisions/{uuid.uuid4()}/sign",
        json={
            "decision": "APPROVE",
            "remarks": "R11 check",
            "password": PASSWORD,
            "object_version": datetime.now(timezone.utc).isoformat(),
        },
    )
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _permissions(client) -> set[str]:
    context = client.get("/api/v1/session/context")
    assert context.status_code == 200, context.text
    return set(context.json()["business_permissions"])


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def test_an_administrator_is_refused_a_signature(org):
    assert _signing_refusal(org["admin"]) == "ADMINISTRATOR_CANNOT_SIGN"


def test_an_administrator_cannot_give_themselves_a_custom_role(org):
    role_id = _active_role(org["admin"], "Approver")
    response = org["admin"].post(
        "/api/v1/admin/identity/role-assignments", json={"user_id": org["admin_id"], "role_id": role_id}
    )
    assert response.status_code == 409, response.text
    assert _code(response) == "SELF_CHANGE_NOT_ALLOWED"
    assert _signing_refusal(org["admin"]) == "ADMINISTRATOR_CANNOT_SIGN"
    assert not {DECISION_SIGN, REGULATORY_APPROVE} & _permissions(org["admin"])


def test_another_administrator_cannot_make_an_administrator_an_approver(org):
    role_id = _active_role(org["peer"], "Approver")
    response = org["peer"].post(
        "/api/v1/admin/identity/role-assignments", json={"user_id": org["admin_id"], "role_id": role_id}
    )
    assert response.status_code == 409, response.text
    assert _code(response) == "ADMINISTRATOR_ROLE_FIXED"
    assert _signing_refusal(org["admin"]) == "ADMINISTRATOR_CANNOT_SIGN"


def test_an_assignment_made_before_the_fix_does_not_make_an_administrator_an_approver(org):
    """An administrator who gave themselves "Approver" before 0.10.49 still holds that assignment row: it must have
    no effect, and it cannot be switched back on once switched off."""
    role_id = _active_role(org["peer"], "Approver")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: an assignment made before the R11 fix")
        row = RoleAssignment(
            id=uuid.uuid4(),
            tenant_id=org["tenant_id"],
            user_id=uuid.UUID(org["admin_id"]),
            role_id=uuid.UUID(role_id),
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        assignment_id = str(row.id)
    assert _signing_refusal(org["admin"]) == "ADMINISTRATOR_CANNOT_SIGN"
    assert not {DECISION_SIGN, REGULATORY_APPROVE} & _permissions(org["admin"])
    # It grants nothing, so the administration screens do not list it as access.
    access = org["peer"].get(f"/api/v1/admin/identity/users/{org['admin_id']}/effective-access")
    assert access.status_code == 200, access.text
    assert access.json()["roles"] == []
    # Switching it off is always allowed (it removes access); switching it on again is not.
    path = f"/api/v1/admin/identity/role-assignments/{assignment_id}/status"
    assert org["admin"].patch(path, json={"status": "RETIRED"}).status_code == 200
    again = org["admin"].patch(path, json={"status": "ACTIVE"})
    assert again.status_code == 409, again.text
    assert _code(again) == "SELF_CHANGE_NOT_ALLOWED"


@pytest.mark.parametrize("name", ["Platform Administrator", "Admin", "Customer Administrator"])
def test_a_custom_role_never_carries_an_administrator_role(org, name):
    created = org["admin"].post(
        "/api/v1/admin/identity/roles", json={"code": f"R11_{uuid.uuid4().hex[:6]}", "name": name}
    )
    assert created.status_code == 422, created.text
    assert _code(created) == "ADMINISTRATOR_ROLE_NOT_ASSIGNABLE"
    by_code = org["admin"].post("/api/v1/admin/identity/roles", json={"code": name.upper(), "name": "Helpdesk"})
    assert by_code.status_code == 422, by_code.text


def test_an_assigned_role_cannot_be_renamed_to_an_administrator_role(org):
    role_id = _active_role(org["admin"], "Complaint Intake")
    assigned = org["admin"].post(
        "/api/v1/admin/identity/role-assignments", json={"user_id": org["member_id"], "role_id": role_id}
    )
    assert assigned.status_code == 200, assigned.text
    renamed = org["admin"].patch(f"/api/v1/admin/control-plane/roles/{role_id}", json={"values": {"name": "Admin"}})
    assert renamed.status_code == 422, renamed.text
    assert _code(renamed) == "ADMINISTRATOR_ROLE_NOT_ASSIGNABLE"


def test_a_role_named_like_an_administrator_before_the_fix_grants_nothing(org):
    """A custom role named "Admin" and given to a member before 0.10.49 read as the platform role (every business
    permission); it is ignored, so the member keeps their account role's permissions (a Viewer's: none)."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: an administrator-named role made before the R11 fix")
        role = RoleDefinition(
            id=uuid.uuid4(),
            tenant_id=org["tenant_id"],
            code=f"ADMIN_{uuid.uuid4().hex[:6]}",
            name="Admin",
            version="v1",
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        db.add(role)
        db.flush()
        db.add(
            RoleAssignment(
                id=uuid.uuid4(),
                tenant_id=org["tenant_id"],
                user_id=uuid.UUID(org["newcomer_id"]),
                role_id=role.id,
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    assert _permissions(org["newcomer"]) == set()


def test_a_member_can_still_be_given_a_custom_role(org):
    role_id = _active_role(org["admin"], "Complaint Clerk")
    response = org["admin"].post(
        "/api/v1/admin/identity/role-assignments", json={"user_id": org["member_id"], "role_id": role_id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACTIVE"
