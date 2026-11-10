"""MDARIX staff named in an organization's own records, read through the runtime role (row-level security on).

Staff accounts live in the platform's organization. An organization's session cannot read that organization, so
three lookups came back empty under the runtime role: the support-access list and decisions (who would get access,
who asked, who approved for MDARIX), the support-access activity (who used it) and the audit history (staff
actions attributed to MDARIX instead of a bare account id). Each is read apart in system scope, staff accounts only.
"""

import uuid

import pytest

from backend.app import support_access as access
from backend.app.access.authz import staff_accounts
from backend.app.access.observability import PLATFORM_ACTOR_LABEL
from backend.app.db.models.foundation import AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.runtime_role import runtime_role_requests  # noqa: F401 (fixture)
from tests.test_export_purge_mfa import _enrolled_client
from tests.test_mapping_release_self_approval import _admin, _organization
from tests.test_support_access_customer_approval import CUSTOMER, GRANTS, _request
from tests.test_support_access_sod import _platform_admin

pytestmark = pytest.mark.db


def _username(user_id) -> str:
    with SessionLocal() as db:
        bind_system(db, "test: the staff account's email")
        return db.get(AuthUser, user_id).username


def test_staff_named_in_support_access_and_audit_are_shown_to_the_organization(runtime_role_requests):  # noqa: F811
    requester, _ = _platform_admin()
    recipient, recipient_id = _platform_admin()
    mdarix, _ = _platform_admin()
    tenant = _organization()
    customer, _ = _enrolled_client("CUSTOMER_ADMIN", tenant)

    # A refused use is recorded in the organization's own trail, by the staff member.
    assert recipient.get(f"/api/v1/platform-admin/tenants/{tenant}/mappings").status_code == 403
    made = _request(requester, tenant, recipient_id, areas=[access.CONFIGURATION])
    assert made.status_code == 200, made.text
    grant_id = made.json()["id"]
    assert mdarix.post(f"{GRANTS}/{grant_id}/approve", json={"reason": "Reviewed the ticket"}).status_code == 200

    item = next(row for row in customer.get(CUSTOMER).json()["items"] if row["id"] == grant_id)
    assert item["person"] == "Platform Admin" and item["person_email"] == _username(recipient_id)
    assert item["requested_by"] == "Platform Admin" and item["approved_for_mdarix_by"] == "Platform Admin"

    history = customer.get("/api/v1/admin/audit-history").json()
    by_staff = [row for row in history if row["action"] == access.ACCESS_REFUSED]
    assert by_staff, "the refused use is in the organization's trail"
    assert all(row["actor_label"] == PLATFORM_ACTOR_LABEL and row["actor_ref"] is None for row in by_staff)
    assert str(recipient_id) not in {row["actor_ref"] for row in history}


def test_the_system_scope_lookup_returns_staff_accounts_only():
    """Another organization's account is never read through the staff lookup."""
    _, staff_id = _platform_admin()
    _, customer_admin_id = _admin(_organization())
    found = staff_accounts([staff_id, customer_admin_id, "not-an-id", None])
    assert set(found) == {str(staff_id)}
    assert found[str(staff_id)]["email"] == _username(staff_id)
    assert staff_accounts([]) == {} and staff_accounts([uuid.uuid4()]) == {}
