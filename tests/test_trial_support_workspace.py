"""Support access for free trials (0.10.39, NEW-1): MDARIX asks, the trial owner (only the owner) decides, and Platform
Admin reads what was granted in the read-only support workspace (backend/app/support_workspace.py), or exports it.

Everything goes through the real API: the request with its areas, MDARIX's own approval, the owner's decision (a
colleague and a Customer Administrator account in a trial are refused), every page refused without a grant and
audited, only the granted areas readable, no route that changes anything, no credential in any answer, the export
only under a Full export grant, revocation and expiry ending access at once, every step in the trial's own audit trail
(and its owner's History), and the emails to the owner.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import notifications, scheduler
from backend.app import support_access as access
from backend.app.db.models.customer_lifecycle import SupportAccessGrant
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.tenant_export import SECRET_COLUMN, run_export
from tests.route_inventory import api_routes
from tests.test_export_purge_mfa import _enrolled_client, _next_code
from tests.test_free_trial import _approved_trial_client, _purge_trial_business_data
from tests.test_support_access_customer_approval import GRANTS, _request, _start_now
from tests.test_support_access_sod import _platform_admin
from tests.test_trial_self_admin import _trial_with_colleague

SUPPORT = "/api/v1/trial/support-access"
PAGES = ("complaints", "investigations", "decisions", "imports", "team", "audit")
RECORDS_PAGES = ("complaints", "investigations", "decisions", "imports")


@pytest.fixture(autouse=True, scope="module")
def _clean_trial_workspaces():
    _purge_trial_business_data()
    yield
    _purge_trial_business_data()


def _workspace(tenant_id) -> str:
    return f"/api/v1/platform-admin/tenants/{tenant_id}/support-workspace"


def _audit(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: read the trial's audit trail")
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == uuid.UUID(str(tenant_id)), AuditEvent.action == action)
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        db.expunge_all()
        return rows


def _outbox(grant_id, event_name: str) -> list[OutboxEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: the queued notices")
        rows = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.aggregate_id == uuid.UUID(str(grant_id)), OutboxEvent.event_name == event_name)
            .all()
        )
        db.expunge_all()
        return rows


def _deliver(grant_id, event_name: str) -> None:
    """What the outbox worker does with the grant's queued notice."""
    (event,) = _outbox(grant_id, event_name)
    with SessionLocal() as db:
        bind_system(db, "test: deliver the notice")
        assert notifications.handle_event(db, event.event_name, event.payload) is True


def _asked(tenant_id, areas, *, write=False):
    """A request for the trial that MDARIX approved on its side: it waits for the trial owner. Returns its id, the
    colleague it is for (a platform administrator) and the requester."""
    requester, _ = _platform_admin()
    recipient, recipient_id = _platform_admin()
    mdarix, _ = _platform_admin()
    made = _request(requester, tenant_id, recipient_id, areas=areas, write=write, reason="Ticket 77: import question")
    assert made.status_code == 200, made.text
    grant_id = made.json()["id"]
    approved = mdarix.post(f"{GRANTS}/{grant_id}/approve", json={"reason": "Checked the ticket with the team"})
    assert approved.status_code == 200 and approved.json()["status"] == access.AWAITING_CUSTOMER
    _start_now(grant_id)
    return grant_id, recipient, requester


def _granted(owner, tenant_id, areas, *, write=False):
    grant_id, recipient, requester = _asked(tenant_id, areas, write=write)
    approved = owner.post(f"{SUPPORT}/{grant_id}/approve", json={"reason": "Yes, for the import question"})
    assert approved.status_code == 200, approved.text
    return grant_id, recipient, requester


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def test_mdarix_asks_a_trial_and_its_owner_is_emailed(monkeypatch):
    _owner, approval, owner_email = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    grant_id, _recipient, _ = _asked(tenant_id, [access.RECORDS])
    sent = []
    monkeypatch.setattr("auth.emailer.send_support_access_request", lambda to, **kw: sent.append((to, kw)) or "SENT")
    _deliver(grant_id, notifications.SUPPORT_ACCESS_AWAITING_CUSTOMER)
    assert [to for to, _ in sent] == [owner_email]
    details = sent[0][1]
    assert details["trial"] is True and details["write"] is False
    assert details["areas"] == [access.AREAS[access.RECORDS]] and details["reason"] == "Ticket 77: import question"
    assert details["expires"].endswith(" UTC")


def test_only_the_trial_owner_decides_never_a_colleague_or_an_administrator_account():
    owner, approval, _, colleague, _ = _trial_with_colleague()
    tenant_id = approval["tenant_id"]
    grant_id, recipient, _ = _asked(tenant_id, [access.RECORDS])
    decision = {"reason": "Yes, for the import question"}
    for verb in ("approve", "deny", "revoke"):
        refused = colleague.post(f"{SUPPORT}/{grant_id}/{verb}", json=decision)
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "TRIAL_OWNER_REQUIRED", verb
    refused = colleague.get(f"{SUPPORT}/{grant_id}/activity")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "TRIAL_OWNER_REQUIRED"
    # A trial has no Customer Administrators; an account with that role in a trial is still not its owner.
    stray, secret = _enrolled_client("CUSTOMER_ADMIN", tenant_id)
    refused = stray.post(
        f"/api/v1/admin/support-access/{grant_id}/approve", json={**decision, "mfa_code": _next_code(secret)}
    )
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "TRIAL_OWNER_REQUIRED"
    assert recipient.get(f"{_workspace(tenant_id)}/complaints").status_code == 403
    with SessionLocal() as db:
        bind_system(db, "test: the grant")
        assert db.get(SupportAccessGrant, uuid.UUID(grant_id)).status == access.AWAITING_CUSTOMER
    approved = owner.post(f"{SUPPORT}/{grant_id}/approve", json=decision)
    assert approved.status_code == 200 and approved.json()["status"] == access.APPROVED
    assert recipient.get(f"{_workspace(tenant_id)}/complaints").status_code == 200


def test_without_a_grant_every_page_is_refused_and_the_refusal_is_in_the_trial_s_trail():
    _owner, approval, _ = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    staff, _ = _platform_admin()
    summary = staff.get(_workspace(tenant_id))
    assert summary.status_code == 200, summary.text
    assert summary.json()["grant"] is None and not any(item["open"] for item in summary.json()["sections"])
    assert summary.json()["export"] == {"open": False} and summary.json()["tenant"]["is_trial"] is True
    for page in PAGES:
        refused = staff.get(f"{_workspace(tenant_id)}/{page}")
        assert refused.status_code == 403, page
        assert refused.json()["detail"]["code"] == "CUSTOMER_APPROVAL_REQUIRED", page
    paths = [event.details["path"] for event in _audit(tenant_id, access.ACCESS_REFUSED)]
    assert paths == [f"{_workspace(tenant_id)}/{page}" for page in PAGES]
    assert staff.get(_workspace(uuid.uuid4())).status_code == 404
    workspace_user = _approved_trial_client()[0]
    assert workspace_user.get(f"{_workspace(tenant_id)}/complaints").status_code == 403  # not platform staff


def test_a_read_grant_opens_only_its_areas_changes_nothing_and_shows_no_credentials():
    owner, approval, owner_email = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    grant_id, recipient, requester = _granted(owner, tenant_id, [access.RECORDS, access.CONFIGURATION])
    base = _workspace(tenant_id)

    summary = recipient.get(base).json()
    assert summary["grant"]["id"] == grant_id and summary["read_only"] is True
    assert summary["grant"]["approved_by"] and summary["grant"]["expires_at"]
    assert {item["key"] for item in summary["sections"] if item["open"]} == set(RECORDS_PAGES)
    assert summary["export"] == {"open": False}
    assert summary["story"] and {"code", "title", "tried"} <= set(summary["story"][0])
    access_list = {
        item["tenant_id"]: item
        for item in recipient.get("/api/v1/platform-admin/support-workspace/access").json()["items"]
    }
    assert access_list[tenant_id]["open_for_me"] is True and access_list[tenant_id]["request"]["mine"] is True
    others = {
        item["tenant_id"]: item
        for item in requester.get("/api/v1/platform-admin/support-workspace/access").json()["items"]
    }
    assert others[tenant_id]["open_for_me"] is False  # the grant names the recipient, not the one who asked

    complaints = recipient.get(f"{base}/complaints")
    assert complaints.status_code == 200, complaints.text
    assert complaints.json()["total"] > 0 and complaints.json()["items"][0]["identifier"]  # the sample data
    for page in RECORDS_PAGES:
        answer = recipient.get(f"{base}/{page}")
        assert answer.status_code == 200, (page, answer.text)
        assert not {key for key in _keys(answer.json()) if SECRET_COLUMN.search(key)}, page
    # Areas not granted stay closed, for this colleague and anyone else.
    for page in ("team", "audit"):
        refused = recipient.get(f"{base}/{page}")
        assert refused.status_code == 403 and refused.json()["detail"]["area"] in {access.PEOPLE, access.AUDIT}
    assert requester.get(f"{base}/complaints").status_code == 403
    export = recipient.post(f"/api/v1/platform-admin/tenants/{tenant_id}/exports", json={"reason": "Not granted here"})
    assert export.status_code == 403 and export.json()["detail"]["area"] == access.DATA_EXPORT

    # Read-only, on the server: the workspace has no route that changes anything, and a change elsewhere is refused.
    methods = {method for path, route in api_routes(app) if "/support-workspace" in path for method in route.methods}
    assert methods == {"GET"}
    for page in PAGES:
        assert recipient.post(f"{base}/{page}", json={}).status_code == 405
    draft = {"code": "SUPPORT-DRAFT", "source_system": "TRACKWISE", "target_entity": "Complaint", "mapping_rules": {}}
    mappings = f"/api/v1/platform-admin/tenants/{tenant_id}/mappings"
    assert recipient.get(mappings).status_code == 200
    refused = recipient.post(mappings, json=draft)
    assert refused.status_code == 403 and refused.json()["detail"]["write"] is True
    # Platform staff have no session in the trial: their own workspace writes stay in the platform's organization.
    assert recipient.get("/api/v1/session/context").json()["tenant_id"] != tenant_id

    # Each page read is a use of the grant in the trial's own trail, shown to the owner in words.
    used = [event for event in _audit(tenant_id, access.ACCESS_USED) if event.details["grant_id"] == grant_id]
    assert {event.details["path"] for event in used} >= {f"{base}/{page}" for page in RECORDS_PAGES}
    assert all(event.details["write"] is False for event in used if "/support-workspace" in event.details["path"])
    history = owner.get(f"{SUPPORT}/{grant_id}/activity")
    assert history.status_code == 200, history.text
    what = [item["what"] for item in history.json()["items"]]
    assert what[:3] == ["MDARIX asked for access", "Approved inside MDARIX", "Access approved"]
    assert "Read the complaints" in what and "Read the decisions" in what
    # Never an account id: MDARIX staff the trial cannot read are "MDARIX support".
    assert not any(re.fullmatch(r"[0-9a-f-]{36}", str(item["who"])) for item in history.json()["items"])


def test_the_trial_s_team_and_audit_trail_open_under_their_own_areas():
    owner, approval, owner_email = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    _grant_id, recipient, _ = _granted(owner, tenant_id, [access.PEOPLE, access.AUDIT])
    base = _workspace(tenant_id)
    team = recipient.get(f"{base}/team")
    assert team.status_code == 200, team.text
    people = team.json()["items"]
    assert [person["email"] for person in people if person["is_owner"]] == [owner_email]
    assert not {key for key in _keys(team.json()) if SECRET_COLUMN.search(key)}
    assert set(people[0]) == {
        "id", "business_id", "name", "email", "role", "status", "is_owner", "uses_authenticator", "joined_at"
    }  # fmt: skip
    trail = recipient.get(f"{base}/audit")
    assert trail.status_code == 200, trail.text
    actions = [item["action"] for item in trail.json()["items"]]
    assert "SUPPORT_ACCESS_CUSTOMER_APPROVED" in actions and "SUPPORT_ACCESS_REQUESTED" in actions
    assert all(
        set(item) == {"id", "at", "who", "action", "entity_type", "reason", "support", "support_what"}
        for item in trail.json()["items"]
    )
    assert recipient.get(f"{base}/complaints").status_code == 403  # Quality records were not granted


def test_the_export_needs_a_full_export_grant_and_stops_with_it():
    owner, approval, _ = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    grant_id, recipient, _ = _granted(owner, tenant_id, [access.DATA_EXPORT])
    exports = f"/api/v1/platform-admin/tenants/{tenant_id}/exports"
    assert recipient.get(_workspace(tenant_id)).json()["export"] == {"open": True}
    queued = recipient.post(exports, json={"reason": "Ticket 77: a copy for the import question"})
    assert queued.status_code == 202, queued.text
    assert run_export(queued.json()["id"])["status"] == "READY"
    download = recipient.get(f"{exports}/{queued.json()['id']}/download")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    assert _audit(tenant_id, "TENANT_EXPORT_REQUESTED") and _audit(tenant_id, "TENANT_EXPORT_DOWNLOADED")
    paths = {event.details["path"] for event in _audit(tenant_id, access.ACCESS_USED)}
    assert exports in paths and f"{exports}/{queued.json()['id']}/download" in paths

    revoked = owner.post(f"{SUPPORT}/{grant_id}/revoke", json={"reason": "The question is answered"})
    assert revoked.status_code == 200 and revoked.json()["status"] == access.REVOKED
    refused = recipient.get(f"{exports}/{queued.json()['id']}/download")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "CUSTOMER_APPROVAL_REQUIRED"
    assert recipient.post(exports, json={"reason": "Once more, after the revocation"}).status_code == 403


def test_revocation_ends_access_at_once_and_the_owner_is_told(monkeypatch):
    owner, approval, owner_email = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    grant_id, recipient, _ = _granted(owner, tenant_id, [access.RECORDS])
    sent = []
    monkeypatch.setattr("auth.emailer.send_support_access_granted", lambda to, **kw: sent.append(("granted", to, kw)))
    monkeypatch.setattr("auth.emailer.send_support_access_ended", lambda to, **kw: sent.append(("ended", to, kw)))
    _deliver(grant_id, notifications.SUPPORT_ACCESS_GRANTED)
    assert sent[0][:2] == ("granted", owner_email) and sent[0][2]["trial"] is True
    assert sent[0][2]["approved_by"] and sent[0][2]["expires"].endswith(" UTC")

    assert recipient.get(f"{_workspace(tenant_id)}/complaints").status_code == 200
    assert owner.post(f"{SUPPORT}/{grant_id}/revoke", json={"reason": "The question is answered"}).status_code == 200
    assert recipient.get(f"{_workspace(tenant_id)}/complaints").status_code == 403
    assert recipient.get(_workspace(tenant_id)).json()["grant"] is None
    assert _audit(tenant_id, "SUPPORT_ACCESS_REVOKED")[-1].details["source"] == "TRIAL_OWNER"
    (ended,) = _outbox(grant_id, notifications.SUPPORT_ACCESS_ENDED)
    assert ended.payload["ended"] == "REVOKED_BY_CUSTOMER"
    _deliver(grant_id, notifications.SUPPORT_ACCESS_ENDED)
    assert sent[1][:2] == ("ended", owner_email) and sent[1][2]["ended"] == "REVOKED_BY_CUSTOMER"
    # A confirmation that arrives after the revocation is not sent: the access it confirms is gone.
    sent.clear()
    _deliver(grant_id, notifications.SUPPORT_ACCESS_GRANTED)
    assert sent == []

    # MDARIX ending an approved access tells the owner too.
    second, recipient, _ = _granted(owner, tenant_id, [access.RECORDS])
    staff, _ = _platform_admin()
    assert staff.post(f"{GRANTS}/{second}/revoke", json={"reason": "Done with the ticket"}).status_code == 200
    assert recipient.get(f"{_workspace(tenant_id)}/complaints").status_code == 403
    assert _outbox(second, notifications.SUPPORT_ACCESS_ENDED)[0].payload["ended"] == "REVOKED_BY_MDARIX"


def test_expiry_ends_access_at_once_and_is_recorded_and_told(monkeypatch):
    owner, approval, owner_email = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    grant_id, recipient, _ = _granted(owner, tenant_id, [access.RECORDS])
    assert recipient.get(f"{_workspace(tenant_id)}/complaints").status_code == 200
    with SessionLocal() as db:
        bind_system(db, "test: the window passes")
        row = db.get(SupportAccessGrant, uuid.UUID(grant_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    # Refused at once, before anything has closed it.
    refused = recipient.get(f"{_workspace(tenant_id)}/complaints")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "CUSTOMER_APPROVAL_REQUIRED"

    job = next(job for job in scheduler.JOBS if job.name == "support-access-expiry")
    assert job.roles == scheduler.PLATFORM_JOBS
    with SessionLocal() as db:
        bind_system(db, "test: the scheduled job")
        assert job.run(db, {})["closed"] >= 1
        db.commit()
    with SessionLocal() as db:
        bind_system(db, "test: the grant")
        assert db.get(SupportAccessGrant, uuid.UUID(grant_id)).status == access.EXPIRED
    (expired,) = [event for event in _audit(tenant_id, access.ACCESS_EXPIRED) if str(event.entity_id) == grant_id]
    assert expired.actor_ref == "system:support-access-expiry"
    (ended,) = _outbox(grant_id, notifications.SUPPORT_ACCESS_ENDED)
    assert ended.payload["ended"] == "EXPIRED"
    sent = []
    monkeypatch.setattr("auth.emailer.send_support_access_ended", lambda to, **kw: sent.append((to, kw)))
    _deliver(grant_id, notifications.SUPPORT_ACCESS_ENDED)
    assert sent[0][0] == owner_email and sent[0][1]["ended"] == "EXPIRED"
    what = [item["what"] for item in owner.get(f"{SUPPORT}/{grant_id}/activity").json()["items"]]
    assert what[-1] == "Access ended on its own"
    # Nothing more to close, and nothing told twice.
    with SessionLocal() as db:
        bind_system(db, "test: the scheduled job again")
        job.run(db, {})
        db.commit()
    assert len(_outbox(grant_id, notifications.SUPPORT_ACCESS_ENDED)) == 1


def test_the_support_emails_name_the_trial_owner_s_place_and_escape_what_they_show(monkeypatch):
    from auth import emailer

    pages = []
    monkeypatch.setattr(
        emailer, "_send_email", lambda to, subject, text, page, **kw: pages.append((subject, text, page))
    )
    common = {"organization": "Orbit <Medical>", "person": "Ravi Support"}
    emailer.send_support_access_request(
        "owner@example.invalid",
        **common,
        areas=[access.AREAS[access.RECORDS]],
        write=False,
        expires="21 October 2026, 10:00 UTC",
        reason="Ticket 77",
        trial=True,
    )
    emailer.send_support_access_granted(
        "owner@example.invalid",
        **common,
        areas=[access.AREAS[access.RECORDS]],
        write=False,
        expires="21 October 2026, 10:00 UTC",
        approved_by="Asha Rao",
        trial=True,
    )
    emailer.send_support_access_ended(
        "owner@example.invalid", **common, ended="EXPIRED", when="21 October 2026, 10:00 UTC", trial=True
    )
    request, granted, ended = pages
    assert "Nothing is opened until you approve it" in request[1] and "Getting started › Team" in request[1]
    assert "free trial of Orbit <Medical>" in request[1]
    assert "Orbit &lt;Medical&gt;" in request[2] and "Orbit <Medical>" not in request[2]
    assert granted[0] == "Support access to Orbit <Medical> is approved" and "Asha Rao approved" in granted[1]
    assert "read only" in granted[1] and "If you did not approve this, revoke it now" in granted[1]
    assert ended[0] == "Support access to Orbit <Medical> has ended" and "Its time ran out." in ended[1]
    for subject, text, _page in pages:
        assert "—" not in text and "MVP" not in text, subject
    # A customer's administrators keep their own wording and place.
    pages.clear()
    emailer.send_support_access_request(
        "admin@example.invalid", **common, areas=[], write=True, expires="x", reason="y", trial=False
    )
    assert "one of your administrators approves it" in pages[0][1] and "/app/customer-admin" in pages[0][1]
    assert re.search(r"as an administrator of Orbit <Medical>", pages[0][1])
