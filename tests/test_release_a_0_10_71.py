"""0.10.71, Release A of the "Simplicity and WoW" plan: the first five minutes.

- A1: a new free trial is created on the new navigation; existing organizations keep theirs. A fresh sign-up through
  the public flow (request, approval, activation e-mail, password, authenticator) reaches the new navigation without
  anyone switching it.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from auth import emailer, totp
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE
from tests.test_free_trial import PASSWORD, _request_id

pytestmark = pytest.mark.db


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, uuid.UUID(str(tenant_id)), "test:release-a-cleanup")


@pytest.fixture()
def mail_sink(monkeypatch):
    """A test mail sink: every e-mail MDARIX would send is kept here, never sent."""
    sent: list[dict] = []

    def keep(recipient, subject, body, html_body=None, *, reply_to=None):
        sent.append({"to": recipient, "subject": subject, "text": body})
        return "SENT"

    monkeypatch.setattr(emailer, "_send_email", keep)
    return sent


def test_a_fresh_signup_through_the_public_flow_lands_on_the_new_navigation(mail_sink):
    admin = authenticated_client()
    email = f"fresh-{uuid.uuid4().hex[:10]}@example.invalid"
    # 1. The public request (the website's form): nothing but a request.
    _ok(
        TestClient(app).post(
            "/api/v1/auth/signup",
            json={"email": email, "display_name": "Fresh Quality", "organization": "Fresh Devices Ltd", **PROFILE},
        )
    )
    # 2. A platform administrator approves it; nobody touches the navigation.
    approval = _ok(admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"))
    tenant_id = approval["tenant_id"]
    try:
        # 3. The activation e-mail, from the sink: its link carries the token.
        links = [
            found.group(0)
            for message in mail_sink
            if message["to"] == email
            for found in [re.search(r"\S*/activate-account\?token=[^\s\"<>]+", message["text"])]
            if found
        ]
        assert len(links) == 1, [message["subject"] for message in mail_sink]
        link = links[0]
        token = parse_qs(urlparse(link).query)["token"][0]
        # 4. The password, then sign-in, then the authenticator.
        user = TestClient(app)
        _ok(user.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}))
        _ok(user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}))
        secret = _ok(user.post("/api/v1/auth/mfa/enroll"))["secret"]
        _ok(user.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)}))
        # 5. The first screen: the new navigation, a trial with the sample, and no administrator switched anything.
        context = _ok(user.get("/api/v1/session/context"))
        assert context["navigation"] == "new"
        # 0.10.73 (C1): the owner opens on Admin's Home, the persona theirs to change.
        assert (context["persona"], context["persona_locked"], context["persona_tabs"][0]) == ("admin", False, "home")
        status = _ok(user.get("/api/v1/trial/status"))
        assert status["is_trial"] and status["sample"]["complaints"] > 0
        with SessionLocal() as db:
            bind_system(db, "test: who set the navigation")
            from backend.app.db.models.foundation import AuditEvent

            switched = (
                db.query(AuditEvent)
                .filter(AuditEvent.entity_id == uuid.UUID(tenant_id), AuditEvent.action == "TENANT_UPDATED")
                .count()
            )
        assert switched == 0
    finally:
        _purge(tenant_id)


def test_only_new_trials_get_the_new_navigation_existing_organizations_keep_theirs():
    with SessionLocal() as db:
        bind_system(db, "test: the navigation of every organization before")
        before = {row.id: row.navigation for row in db.query(Tenant.id, Tenant.navigation)}
    admin = authenticated_client()
    email = f"nav-{uuid.uuid4().hex[:10]}@example.invalid"
    _ok(
        TestClient(app).post(
            "/api/v1/auth/signup",
            json={"email": email, "display_name": "Nav Quality", "organization": "Nav Devices Ltd", **PROFILE},
        )
    )
    approval = _ok(admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"))
    try:
        with SessionLocal() as db:
            bind_system(db, "test: the navigation of every organization after")
            after = {row.id: row.navigation for row in db.query(Tenant.id, Tenant.navigation)}
        new_id = uuid.UUID(approval["tenant_id"])
        assert after.pop(new_id) == "new"
        # Every organization that existed keeps its navigation (trials and pilots, classic or new).
        assert {key: value for key, value in after.items() if key in before} == before
    finally:
        _purge(approval["tenant_id"])


def test_an_organization_created_outside_the_trial_approval_stays_classic():
    from datetime import datetime, timezone

    from backend.app.customer_lifecycle import build_customer_tenant

    with SessionLocal() as db:
        bind_system(db, "test: a pilot's tenant")
        _, tenant = build_customer_tenant(
            db=db, tenant_key="PILOT_NAV_CHECK", name="Pilot Nav Check", status="ACTIVE", now=datetime.now(timezone.utc)
        )
        db.rollback()
    # Not set in code: the column's default applies when it is written; new since ux2navigationnew (UX2).
    assert tenant.navigation in (None, "new")


# ------------------------------------------------------------------------------------------- A2: sample-only trials

IMPORT_PREFIXES = ("/api/v1/data/import", "/api/v1/trial/imports")
# Not an import: a set-aside row dismissed with a reason brings nothing in (a sample row may be dismissed).
NOT_IMPORTS = {("POST", "/api/v1/data/import/quarantine/{row_id}/dismiss")}


def _import_routes():
    from tests.route_inventory import api_routes

    for path, route in api_routes(app):
        if not path.startswith(IMPORT_PREFIXES):
            continue
        for method in sorted(route.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            if (method, path) not in NOT_IMPORTS:
                yield method, path, route


def _set_tenant(admin, tenant_id, **changes):
    detail = _ok(admin.get(f"/api/v1/platform-admin/tenants/{tenant_id}"))
    tenant = detail.get("tenant", detail)
    return admin.patch(
        f"/api/v1/platform-admin/tenants/{tenant_id}",
        json={**changes, "reason": "Judge trial for the event (test)", "lock_version": tenant["lock_version"]},
    )


@pytest.fixture(scope="module")
def trial():
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    try:
        yield {"user": user, "tenant_id": approval["tenant_id"]}
    finally:
        _purge(approval["tenant_id"])


def test_every_import_route_refuses_a_sample_only_trial():
    from backend.app.data_import_router import refuse_sample_only

    routes = list(_import_routes())
    # The check, the import and a set-aside row's fix and re-process, and the trial's two aliases (distribution and
    # every other template is an entity of the same routes).
    assert {path for _, path, _ in routes} == {
        "/api/v1/data/import/{entity}/check",
        "/api/v1/data/import/{entity}",
        # 0.10.82 (D1.10): which template a file is; it reads the file, so it is refused like the others.
        "/api/v1/data/import/detect",
        "/api/v1/data/import/quarantine/{row_id}/reprocess",
        "/api/v1/trial/imports/{entity}/check",
        "/api/v1/trial/imports/{entity}",
    }
    for method, path, route in routes:
        assert any(dep.dependency is refuse_sample_only for dep in route.dependencies), f"{method} {path}"


def test_a_sample_only_trial_is_refused_in_plain_words_and_a_normal_trial_keeps_its_upload(trial):
    from backend.app.data_import_router import SAMPLE_ONLY_MESSAGE

    admin, user, tenant_id = authenticated_client(), trial["user"], trial["tenant_id"]
    assert _ok(user.get("/api/v1/session/context"))["sample_only"] is False
    csv = b"complaint_id,product_id,description\nOWN-1,SAMPLE-PULSE-410,Display flickers\n"
    headers = {"Content-Type": "text/csv"}
    # A normal trial checks its own file (whatever the check finds, it is not refused).
    assert user.post("/api/v1/data/import/complaints/check", content=csv, headers=headers).status_code != 403
    # The trial's own user may not set it; a platform administrator does, with a reason, audited.
    assert user.patch(
        f"/api/v1/platform-admin/tenants/{tenant_id}", json={"sample_only": True, "reason": "x" * 12, "lock_version": 1}
    ).status_code in (401, 403)
    changed = _set_tenant(admin, tenant_id, sample_only=True)
    assert changed.status_code == 200, changed.text
    assert changed.json()["updated"] == {"sample_only": True} and changed.json()["tenant"]["sample_only"] is True
    assert _ok(user.get("/api/v1/session/context"))["sample_only"] is True
    try:
        row = uuid.uuid4()
        for path in (
            "/api/v1/data/import/complaints/check",
            "/api/v1/data/import/complaints",
            "/api/v1/data/import/distribution",
            "/api/v1/trial/imports/complaints/check",
            "/api/v1/trial/imports/complaints",
        ):
            refused = user.post(path, content=csv, headers=headers)
            assert refused.status_code == 403, (path, refused.text)
            assert refused.json()["detail"] == {"code": "SAMPLE_ONLY_TRIAL", "message": SAMPLE_ONLY_MESSAGE}
        refused = user.post(f"/api/v1/data/import/quarantine/{row}/reprocess", json={"row": {"description": "x"}})
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SAMPLE_ONLY_TRIAL"
        # Reading the sample's data-quality reports stays open.
        assert user.get("/api/v1/data/import/runs").status_code == 200
        with SessionLocal() as db:
            bind_system(db, "test: the change is audited")
            from backend.app.db.models.foundation import AuditEvent

            event = (
                db.query(AuditEvent)
                .filter(AuditEvent.entity_id == uuid.UUID(tenant_id), AuditEvent.action == "TENANT_UPDATED")
                .order_by(AuditEvent.created_at.desc())
                .first()
            )
            assert event.details["after"] == {"sample_only": True} and event.details["reason"]
    finally:
        assert _set_tenant(admin, tenant_id, sample_only=False).status_code == 200
    assert user.post("/api/v1/data/import/complaints/check", content=csv, headers=headers).status_code != 403


# ------------------------------------------------------------------------------------------- A5: service work

EVENT = "/api/v1/oversight/events/SAMPLE-RV-11"


def _quality_state(view: dict) -> dict:
    """What the quality side of a complaint is: none of it may move when the service does."""
    return {
        "status_in_qms": view["event"]["status_in_qms"],
        "state": view["state"],
        "next_action": view["summary"]["next_action"],
        "checklist": [(item["code"], item["result"]) for item in view["checklist"]],
        "stages": view["stages"],
        "due": [(item["key"], item["due_at"], item["state"]) for item in view["work"]["due"]],
        "stage": view["work"]["stage"],
        "ready": view["ready"],
    }


def test_completing_the_service_leaves_the_complaint_open_and_says_so(trial):
    from backend.app.oversight.service_work import COMPLETE_LINE
    from backend.app.trial.sample_data import FLAGSHIP_SERVICE

    user = trial["user"]
    view = _ok(user.get(EVENT))
    # The sample: RV-11's service in progress under its service ticket, since its awareness, nobody named yet.
    assert view["service"]["reference"] == FLAGSHIP_SERVICE["service_reference"]
    assert view["service"]["status"] == "IN_PROGRESS" and view["service"]["owner_id"] is None
    assert view["service"]["status_at"] == view["event"]["awareness_at"] and view["service"]["header"] is None
    before = _quality_state(view)
    me = next(person["id"] for person in view["people"])
    path = f"/api/v1/oversight/events/{view['event']['complaint_id']}/service"
    assert user.put(path, json={"reference": "SVC-24-1107", "status": "SCHEDULED"}).status_code == 422
    assert user.put(path, json={"reference": "S", "status": "OPEN"}).status_code == 422
    assert user.put(path, json={"reference": "SVC", "status": "OPEN", "owner_id": "nobody"}).status_code == 422
    done = _ok(user.put(path, json={"reference": "SVC-24-1107", "status": "COMPLETE", "owner_id": me}))
    assert done["service"]["status"] == "COMPLETE" and done["service"]["owner_id"] == me
    assert done["service"]["header"] == COMPLETE_LINE == "Service complete · Quality assessment open"
    # Nothing on the quality side moved: the complaint, its assessments' clocks, its checklist, its next step.
    assert _quality_state(done) == before
    assert _quality_state(_ok(user.get(EVENT))) == before
    assert before["next_action"] is not None and before["status_in_qms"] != "Closed"


def test_the_refresh_links_the_flagship_service_once(trial):
    """scripts/refresh_trial_story.py: a trial seeded before 0.10.71 gets RV-11's service work, once (dry run first)."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial.sample_data import FLAGSHIP, seed_flagship_service

    tenant_id = uuid.UUID(trial["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == FLAGSHIP)
        saved = [(c.service_reference, c.service_status, c.service_status_at, c.service_owner) for c in row][0]
        row.update(
            {"service_reference": None, "service_status": None, "service_status_at": None, "service_owner": None}
        )
        assert seed_flagship_service(db, tenant_id, apply=False) == 1
        assert row.one().service_reference is None  # the dry run changes nothing
        assert seed_flagship_service(db, tenant_id, apply=True) == 1
        assert row.one().service_status == "IN_PROGRESS"
        assert seed_flagship_service(db, tenant_id, apply=True) == 0  # idempotent
        row.update(
            {
                "service_reference": saved[0],
                "service_status": saved[1],
                "service_status_at": saved[2],
                "service_owner": saved[3],
            }
        )
        db.commit()


# ------------------------------------------------------------------------------------------- A4: the short story

STORY = "/api/v1/trial/short-story"


def _ask_the_hospital(user, complaint_id: str, owner: str, subject: str | None = None, bind: bool = True) -> dict:
    """Step 3 as the screen does it: the hospital as a party of the complaint, then the request with its owner, kept
    with the story as its question (0.10.72, F2)."""
    from datetime import date, timedelta

    party = _ok(
        user.post(
            "/api/v1/communications/parties",
            json={
                "type": "HOSPITAL",
                "name": "Biomedical engineering, the reporting hospital (sample)",
                "complaint_id": complaint_id,
            },
        )
    )
    from datetime import datetime, timezone

    asked = _ok(
        user.post(
            "/api/v1/communications",
            json={
                "complaint_id": complaint_id,
                "party_id": party["id"],
                "direction": "SENT",
                "purpose": "INFORMATION_REQUEST",
                "subject": subject or "Did any treatment decision rely on the high SpO2 readings?",
                "channel": "EMAIL",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "owner_id": owner,
                "reply_due_on": (date.today() + timedelta(days=2)).isoformat(),
            },
        )
    )
    if bind:
        _ok(user.post(f"{STORY}/marks", json={"step": "question", "request_id": asked["id"]}))
    return asked


@pytest.fixture(scope="module")
def story_trial():
    from tests.test_free_trial import _approved_trial_client
    from tests.test_reporting_capa_api import _client

    user, approval, _ = _approved_trial_client()
    try:
        yield {"user": user, "tenant_id": approval["tenant_id"], "colleague": _client(approval["tenant_id"], "LEADER")}
    finally:
        _purge(approval["tenant_id"])


def test_the_short_story_counts_what_was_saved_not_the_screen(story_trial):
    user = story_trial["user"]
    story = _ok(user.get(STORY))
    assert story["available"] and story["complaint"]["ref"] == "SAMPLE-RV-11"
    assert [step["label"] for step in story["steps"]] == [
        "Read the call",
        "Decide the route",
        "Name the open question",
        "The intake decision summary",
    ]
    assert story["current"] == 0 and not story["started"] and not story["finished"]
    # Step 1: the reporter's words with the phrases that make it a possible complaint, and the facts beside them.
    assert [item["text"] for item in story["call"]["phrases"]] == [
        "SpO2 read 4 to 6 points high",
        "two patients",
        "No harm was reported",
        "sent for service",
    ]
    facts = {item["label"]: item["value"] for item in story["call"]["facts"]}
    assert facts["Harm"] == "None reported" and facts["Malfunction"] == "Yes" and facts["Market"].startswith("United")
    assert facts["Service"].startswith("In progress · SVC-24-1107")
    # Opening a screen saves nothing: the summary cannot be marked before its steps.
    assert user.post(f"{STORY}/marks", json={"step": "summary"}).status_code == 409
    assert user.post(f"{STORY}/marks", json={"step": "elsewhere"}).status_code == 422
    assert _ok(user.post(f"{STORY}/marks", json={"step": "read"}))["current"] == 1
    # A refresh (or another device: a new client with the same session) reads the same step.
    again = TestClient(app)
    again.cookies.set("mdarix_session", user.cookies.get("mdarix_session"))
    assert _ok(again.get(STORY))["current"] == 1

    # Step 2: the route is the triage record and the service work, both with owners.
    complaint = story["complaint"]["id"]
    me = next(person["id"] for person in _ok(user.get("/api/v1/triage"))["people"] if person["name"] != "Colleague")
    _ok(
        user.post(
            f"/api/v1/triage/COMPLAINT/{complaint}/record",
            json={
                "severity": "NEGLIGIBLE",
                "potential_severity": "MINOR",
                # B2: a fast-track triage names a backup when two people are active.
                "backup_owner": next((p["id"] for p in _ok(user.get("/api/v1/triage"))["people"] if p["id"] != me), ""),
                "event_owner": me,
                "triage_owner": me,
                "immediate_action": "Monitor out of use and sent for service (SVC-24-1107).",
            },
        )
    )
    assert _ok(user.get(STORY))["current"] == 1  # the service work has no owner yet
    service = f"/api/v1/oversight/events/{complaint}/service"
    _ok(
        user.put(
            service, json={"reference": "SVC-24-1107 (sample service ticket)", "status": "IN_PROGRESS", "owner_id": me}
        )
    )
    story = _ok(user.get(STORY))
    assert story["current"] == 2 and story["route"]["decision"] == "Complaint, with linked service work"
    assert story["route"]["source_quote"] == "its SpO2 read 4 to 6 points high on two patients"

    # Step 3: one follow-up, with owner and due date, in the communications log. The consequence stays unknown.
    _ask_the_hospital(user, complaint, me)
    story = _ok(user.get(STORY))
    assert story["current"] == 3
    assert story["question"]["asked"]["owner_name"] and story["question"]["asked"]["due_on"]
    assert story["question"]["consequence"] == "Not known until the hospital answers"

    # Step 4: the intake decision summary, seen: the story is finished.
    story = _ok(user.post(f"{STORY}/marks", json={"step": "summary"}))
    assert story["current"] == 4 and story["finished"]
    markets = {row["market"]: row for row in story["markets"]}
    assert set(markets) == {"US", "IN"} and all(row["open"] for row in markets.values())
    assert markets["US"]["deadline"] and markets["US"]["state"] == "Not assessed yet: still open"
    assert markets["IN"]["why"].startswith("Assessed because your procedure asks every market")
    assert story["service"]["owner_name"] and story["next"]["action"] and story["next"]["who"]
    # A6: who prepared, who may approve, who approved; alone in the trial it is practice approval.
    people = story["people"]
    assert people["prepared_by"] and people["approved_by"] == []
    assert people["prepared_by"][0] in people["may_approve"]


def test_each_person_has_their_own_marks_and_the_records_count_for_everyone(story_trial):
    colleague = story_trial["colleague"]
    story = _ok(colleague.get(STORY))
    # The route and the question are the organization's records: done for the colleague too. The summary is theirs
    # to see, and the call counts as read once the route is decided.
    assert [step["done"] for step in story["steps"]] == [True, True, True, False]
    assert story["current"] == 3 and story["started"] and not story["finished"]
    # With a colleague who may sign the markets, nobody approves their own practice work.
    assert story["people"]["practice"] is False and story["people"]["practice_note"] is None


def test_working_alone_the_summary_says_the_approval_is_practice(trial):
    """A6: a solo trial owner approves their own practice work; the summary says so, at the approval."""
    people = _ok(trial["user"].get(STORY))["people"]
    assert people["practice"] is True
    assert people["practice_note"] == "Practice approval: in a pilot a colleague approves this."


def test_the_decision_record_shows_who_prepared_who_may_approve_and_who_approved(trial, story_trial):
    """A6: the complaint page's decision record names the three; alone in a trial it says the approval is practice."""
    from backend.app.workflow.approvals import PRACTICE_APPROVAL

    solo = _ok(trial["user"].get(EVENT))["record_people"]
    assert solo["practice_note"] == PRACTICE_APPROVAL and solo["may_approve"]
    pair = _ok(story_trial["user"].get(EVENT))
    people = pair["record_people"]
    # The short story's triage record was completed by the owner: they prepared it; nobody approved anything yet.
    assert people["prepared_by"] and people["approved_by"] == [] and people["practice_note"] is None
    assert len(people["may_approve"]) == 2
    # The record's own fingerprint is untouched by the names beside it.
    assert set(pair["decision_record"]) == {"entries", "sha256", "version", "filed"}
