"""Platform staff reach an organization's data only under support access its administrators approved (ADR-015).

One organization, its Customer Administrator, and three platform administrators: a requester, the colleague who
would get access, and a third who approves the request for MDARIX. Every step goes through the real API: the
refusal before any grant (audited in the organization's trail), the request with its areas, MDARIX's approval and
the email it queues, the customer's decision with an authenticator code, read-only enforcement, every use recorded
and shown to the customer, revocation, and what stays open without a grant (staff accountability, continuity).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from backend.app import support_access as access
from backend.app.db.models.customer_lifecycle import SupportAccessGrant
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_export_purge_mfa import _enrolled_client, _next_code
from tests.test_mapping_release_self_approval import _admin, _organization
from tests.test_support_access_sod import _platform_admin

GRANTS = "/api/v1/platform-admin/support-access"
CUSTOMER = "/api/v1/admin/support-access"


def _audit(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: read the organization's audit trail")
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == uuid.UUID(str(tenant_id)), AuditEvent.action == action)
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        db.expunge_all()
        return rows


def _grant_row(grant_id) -> SupportAccessGrant:
    with SessionLocal() as db:
        bind_system(db, "test: read the grant")
        row = db.get(SupportAccessGrant, uuid.UUID(str(grant_id)))
        db.expunge(row)
        return row


def _request(requester, tenant, recipient_id, *, areas, write=False, reason="Ticket 4711: products missing"):
    starts = datetime.now(timezone.utc) + timedelta(seconds=1)
    return requester.post(
        GRANTS,
        json={
            "tenant_id": tenant,
            "platform_user_id": str(recipient_id),
            "scope": {"areas": areas, "write": write},
            "reason": reason,
            "starts_at": starts.isoformat(),
            "expires_at": (starts + timedelta(hours=2)).isoformat(),
        },
    )


def _start_now(grant_id) -> None:
    """The window starts a second after the request (a request may not start in the past): begin it now."""
    with SessionLocal() as db:
        bind_system(db, "test: start the window")
        row = db.get(SupportAccessGrant, uuid.UUID(str(grant_id)))
        row.starts_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()


def test_customer_data_opens_only_after_the_customer_approves_and_every_use_is_theirs_to_see():
    requester, _ = _platform_admin()
    recipient, recipient_id = _platform_admin()
    mdarix, _ = _platform_admin()
    tenant = _organization()
    customer, secret = _enrolled_client("CUSTOMER_ADMIN", tenant)
    mappings = f"/api/v1/platform-admin/tenants/{tenant}/mappings"

    # No grant: refused, and the refusal is in the organization's own trail.
    refused = recipient.get(mappings)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "CUSTOMER_APPROVAL_REQUIRED"
    assert refused.json()["detail"]["area"] == access.CONFIGURATION
    assert _audit(tenant, access.ACCESS_REFUSED)[-1].details["path"] == mappings

    # A request names known areas only.
    bad = _request(requester, tenant, recipient_id, areas=["EVERYTHING"])
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "SUPPORT_SCOPE_INVALID"
    made = _request(requester, tenant, recipient_id, areas=[access.CONFIGURATION])
    assert made.status_code == 200, made.text
    grant_id = made.json()["id"]
    assert made.json()["scope"] == {"areas": [access.CONFIGURATION], "write": False}
    assert customer.get(CUSTOMER).json()["items"] == []  # still inside MDARIX: not the customer's yet

    # MDARIX approves (a third administrator): the request goes to the customer, who is emailed; nothing opens.
    approved = mdarix.post(f"{GRANTS}/{grant_id}/approve", json={"reason": "Reviewed the ticket with the team"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == access.AWAITING_CUSTOMER
    with SessionLocal() as db:
        bind_system(db, "test: the queued email")
        queued = db.query(OutboxEvent).filter(OutboxEvent.aggregate_id == uuid.UUID(grant_id)).one()
        assert queued.event_name == "SUPPORT_ACCESS_AWAITING_CUSTOMER"
    _start_now(grant_id)
    assert recipient.get(mappings).status_code == 403

    # The customer sees the request in their words, and decides with their authenticator.
    listing = customer.get(CUSTOMER).json()
    assert listing["awaiting_decision"] == 1
    item = listing["items"][0]
    assert item["id"] == grant_id and item["can_approve"] and item["can_deny"]
    assert [area["code"] for area in item["areas"]] == [access.CONFIGURATION] and item["write"] is False
    assert recipient.get(CUSTOMER).json()["detail"]["code"] == "CUSTOMER_ADMIN_REQUIRED"  # staff never decide
    without_code = customer.post(f"{CUSTOMER}/{grant_id}/approve", json={"reason": "Yes, for ticket 4711"})
    assert without_code.status_code == 403
    decided = customer.post(
        f"{CUSTOMER}/{grant_id}/approve", json={"reason": "Yes, for ticket 4711", "mfa_code": _next_code(secret)}
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == access.APPROVED and decided.json()["can_revoke"]
    assert _grant_row(grant_id).customer_decided_by is not None

    # Open: read-only, for this colleague only, every use in the customer's trail.
    assert recipient.get(mappings).status_code == 200
    assert requester.get(mappings).status_code == 403  # the grant is for the recipient, not the requester
    draft = {"code": "SUPPORT-DRAFT", "source_system": "TRACKWISE", "target_entity": "Complaint", "mapping_rules": {}}
    assert recipient.post(mappings, json=draft).status_code == 403  # read-only
    used = _audit(tenant, access.ACCESS_USED)
    assert used and used[-1].details["grant_id"] == grant_id and used[-1].details["area"] == access.CONFIGURATION
    other_area = recipient.get(f"/api/v1/platform-admin/tenants/{tenant}/ai-settings")
    assert other_area.status_code == 200  # AI settings are Configuration too
    assert (
        recipient.post(
            f"/api/v1/platform-admin/tenants/{tenant}/exports", json={"reason": "Not granted: a full export"}
        ).status_code
        == 403
    )

    history = customer.get(f"{CUSTOMER}/{grant_id}/activity").json()["items"]
    actions = [entry["action"] for entry in history]
    assert actions[:3] == ["SUPPORT_ACCESS_REQUESTED", "SUPPORT_ACCESS_APPROVED", "SUPPORT_ACCESS_CUSTOMER_APPROVED"]
    assert actions.count(access.ACCESS_USED) >= 2
    assert customer.get(CUSTOMER).json()["items"][0]["uses"] >= 2

    # Revoked by the customer: closed at once.
    revoked = customer.post(f"{CUSTOMER}/{grant_id}/revoke", json={"reason": "Ticket 4711 is solved"})
    assert revoked.status_code == 200 and revoked.json()["status"] == access.REVOKED
    assert recipient.get(mappings).status_code == 403
    assert customer.post(f"{CUSTOMER}/{grant_id}/revoke", json={"reason": "Ticket 4711 is solved"}).status_code == 409


def test_the_customer_can_deny_and_a_denied_request_never_opens():
    requester, _ = _platform_admin()
    recipient, recipient_id = _platform_admin()
    mdarix, _ = _platform_admin()
    tenant = _organization()
    customer, _ = _admin(tenant)
    grant_id = _request(requester, tenant, recipient_id, areas=[access.AUDIT]).json()["id"]
    assert (
        mdarix.post(f"{GRANTS}/{grant_id}/approve", json={"reason": "Reviewed the ticket with the team"}).status_code
        == 200
    )
    _start_now(grant_id)
    denied = customer.post(f"{CUSTOMER}/{grant_id}/deny", json={"reason": "Not needed for this ticket"})
    assert denied.status_code == 200 and denied.json()["status"] == access.DENIED
    assert customer.post(f"{CUSTOMER}/{grant_id}/approve", json={"reason": "Changed my mind now"}).status_code == 409
    full = recipient.get(f"/api/v1/platform-admin/tenants/{tenant}/audit").json()
    assert full["complete"] is False


def test_without_audit_access_staff_see_what_staff_did_and_never_the_customer_s_own_events():
    requester, _ = _platform_admin()
    recipient, recipient_id = _platform_admin()
    mdarix, _ = _platform_admin()
    tenant = _organization()
    customer, _ = _admin(tenant)
    grant_id = _request(requester, tenant, recipient_id, areas=[access.CONFIGURATION]).json()["id"]
    mdarix.post(f"{GRANTS}/{grant_id}/approve", json={"reason": "Reviewed the ticket with the team"})
    customer.post(
        f"{CUSTOMER}/{grant_id}/deny", json={"reason": "Not needed for this ticket"}
    )  # the customer's own event

    shown = recipient.get(f"/api/v1/platform-admin/tenants/{tenant}/audit").json()
    actions = {item["action"] for item in shown["items"]}
    assert "SUPPORT_ACCESS_REQUESTED" in actions and "SUPPORT_ACCESS_APPROVED" in actions  # staff accountability
    assert "SUPPORT_ACCESS_DENIED" not in actions and shown["complete"] is False
    # Each row names the person who acted (the trial history shows names, not account ids).
    requested = next(item for item in shown["items"] if item["action"] == "SUPPORT_ACCESS_REQUESTED")
    assert requested["actor_name"] and requested["actor_name"] != requested["actor_ref"]
    console = recipient.get(
        "/api/v1/platform-admin/console/audit", params={"tenant_id": tenant, "page_size": 200}
    ).json()
    assert "SUPPORT_ACCESS_DENIED" not in {item["action"] for item in console["items"]}
    denied_event = _audit(tenant, "SUPPORT_ACCESS_DENIED")[-1]
    one = recipient.get(f"/api/v1/platform-admin/audit-events/{denied_event.id}")
    assert one.status_code == 403 and one.json()["detail"]["code"] == "CUSTOMER_APPROVAL_REQUIRED"
    staff_event = _audit(tenant, "SUPPORT_ACCESS_REQUESTED")[-1]
    assert recipient.get(f"/api/v1/platform-admin/audit-events/{staff_event.id}").status_code == 200


def test_people_of_an_organization_need_people_access_except_its_only_administrator():
    _, _ = _platform_admin()
    staff, _ = _platform_admin()
    tenant = _organization()
    _, admin_id = _admin(tenant)
    _, member_id = _admin(tenant)
    with SessionLocal() as db:
        bind_system(db, "test: one administrator, one member")
        db.execute(text("UPDATE auth_users SET role = 'INVESTIGATOR' WHERE id = :u"), {"u": member_id})
        db.commit()
    reset = {"reason": "Lost their phone and recovery codes"}
    member = staff.post(f"/api/v1/platform-admin/users/{member_id}/mfa-reset", json=reset)
    assert member.status_code == 403 and member.json()["detail"]["area"] == access.PEOPLE
    # The organization's only active Customer Administrator: nobody inside could help, so MDARIX may (continuity).
    assert staff.post(f"/api/v1/platform-admin/users/{admin_id}/mfa-reset", json=reset).status_code == 200
    listing = staff.get("/api/v1/platform-admin/customer-users", params={"tenant_id": tenant}).json()
    assert listing["items"] == [] and listing["withheld"] >= 1


def test_repeated_reads_of_the_same_page_count_once_and_every_change_counts():
    """Paging through a list (or the audit trail itself) is one use; each change is recorded on its own."""
    from backend.app.db.models.foundation import AuthUser
    from tests.support_grants import grant_support_access, legacy_platform_admin_id

    tenant = _organization()
    staff_id = legacy_platform_admin_id()
    grant_support_access(tenant, staff_id, areas=(access.CONFIGURATION,), write=True)
    with SessionLocal() as db:
        bind_system(db, "test: support access uses")
        staff = db.get(AuthUser, staff_id)
        for _ in range(3):
            access.require_customer_approved_access(db, staff, uuid.UUID(tenant), access.CONFIGURATION)
        for _ in range(2):
            access.require_customer_approved_access(db, staff, uuid.UUID(tenant), access.CONFIGURATION, write=True)
    used = _audit(tenant, access.ACCESS_USED)
    assert [row.details["write"] for row in used] == [False, True, True]
