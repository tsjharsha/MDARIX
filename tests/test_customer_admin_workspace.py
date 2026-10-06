"""A customer administrator in the workspace: an Investigator's rights in their own organization, nothing more.

They read and work on investigations and evidence, use Ask and export; they cannot sign a decision, approve a
regulatory document, use the platform console, or see another organization's records.
"""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.access.permissions import (
    AI_RUN,
    DATA_EXPORT,
    RECORDS_WRITE,
    REGULATORY_APPROVE,
    permissions_for_role,
)
from backend.app.db.models.foundation import Decision, HumanReview, Investigation, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import GOLDEN_TENANT_KEY, golden_investigation_id
from tests.test_customer_admin_account_security import PASSWORD, _client_for, _tenant, _user


@pytest.fixture(scope="module")
def admins():
    """A customer administrator of the golden organization, and one of a separate organization."""
    with SessionLocal() as db:
        bind_system(db, "test: customer administrators of two organizations")
        golden = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).one()
        own = _user(db, golden, "CUSTOMER_ADMIN", "ws-admin")
        foreign = _user(db, _tenant(db, "WS"), "CUSTOMER_ADMIN", "ws-foreign-admin")
        db.commit()
        return {
            "own": _client_for(db, own),
            "own_id": str(own.id),
            "golden_tenant": str(golden.id),
            "foreign": _client_for(db, foreign),
            "foreign_tenant": str(foreign.tenant_id),
        }


def test_the_role_has_investigator_rights_and_no_approval():
    assert permissions_for_role("CUSTOMER_ADMIN") == permissions_for_role("Investigator")
    assert permissions_for_role("CUSTOMER_ADMIN") == {RECORDS_WRITE, AI_RUN, DATA_EXPORT}
    assert REGULATORY_APPROVE not in permissions_for_role("CUSTOMER_ADMIN")


def test_the_session_offers_the_workspace_and_the_administration(admins):
    context = admins["own"].get("/api/v1/session/context")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["business_permissions"] == sorted({RECORDS_WRITE, AI_RUN, DATA_EXPORT})
    assert {"investigations", "evidence", "customer-admin"} <= set(body["allowed_menu"])
    assert "admin" not in body["allowed_menu"]


def test_a_customer_admin_reads_their_own_organizations_investigations(admins):
    investigation_id = golden_investigation_id()
    listed = admins["own"].get("/api/v1/data-plane/investigations")
    assert listed.status_code == 200, listed.text
    assert listed.json()["tenant_id"] == admins["golden_tenant"]
    assert investigation_id in {str(row["id"]) for row in listed.json()["records"]}
    workspace = admins["own"].get(f"/api/v1/investigations/{investigation_id}/workspace")
    assert workspace.status_code == 200, workspace.text


def test_a_customer_admin_passes_the_work_permission_check(admins):
    response = admins["own"].post(f"/api/v1/investigations/{golden_investigation_id()}/analysis", json={})
    assert not (response.status_code == 403 and response.json()["detail"].get("code") == "PERMISSION_DENIED")


def test_another_organizations_admin_sees_none_of_it(admins):
    investigation_id = golden_investigation_id()
    listed = admins["foreign"].get("/api/v1/data-plane/investigations")
    if listed.status_code == 200:
        assert listed.json()["tenant_id"] == admins["foreign_tenant"]
        assert investigation_id not in {str(row["id"]) for row in listed.json()["records"]}
    else:
        assert listed.status_code in {403, 404, 503}
    workspace = admins["foreign"].get(f"/api/v1/investigations/{investigation_id}/workspace")
    assert workspace.status_code in {403, 404}, workspace.text


def test_a_customer_admin_cannot_use_the_platform_console(admins):
    for method, path in (
        ("GET", "/api/v1/platform-admin/customer-admins"),
        ("GET", "/api/v1/platform-admin/customers"),
        ("POST", f"/api/v1/platform-admin/users/{uuid.uuid4()}/activation-link"),
    ):
        response = admins["own"].request(method, path)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"


@pytest.fixture
def decision():
    with SessionLocal() as db:
        bind_system(db, "test: a decision awaiting signature")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).one()
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        now = datetime.now(timezone.utc)
        row = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            decision_identifier=f"CA-WS-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Customer administrator signature check",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone-else",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        yield row
        db.query(HumanReview).filter(HumanReview.decision_id == row.id).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.id == row.id).delete(synchronize_session=False)
        db.commit()


def test_a_customer_admin_cannot_sign_a_decision(admins, decision):
    response = admins["own"].post(
        f"/api/v1/governance/decisions/{decision.id}/sign",
        json={
            "decision": "APPROVE",
            "remarks": "Looks right",
            "password": PASSWORD,
            "object_version": decision.updated_at.isoformat(),
        },
    )
    assert response.status_code == 403, response.text
    # Administrators never sign, whatever approval authority exists (separation of duties).
    assert response.json()["detail"]["code"] == "ADMINISTRATOR_CANNOT_SIGN"
