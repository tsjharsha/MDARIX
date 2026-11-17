"""Trial organizations (TO-1): one Platform Admin page for free trials, and trials kept out of the customer lists.

Every step goes through the real API with real approved trials: the one definition of a trial (backend/app/trial/
scope.py), trials left out of every main list and shown apart on the dashboard, the trial list and detail, and the
actions (extend within original end + 30 days, also on Plans & Licensing; end early through the exit-request flow;
convert; delete data now when due). Refusals by a Platform Admin are audited; other roles are refused on every route.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuditEvent, PlanDefinition, Tenant, TenantPlanAssignment
from backend.app.db.models.stage2 import OutboxEvent, SubscriptionLifecycle, TrialExitRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.trial import scope
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role
from tests.test_free_trial import _approved_trial_client, _purge_trial_business_data

BASE = "/api/v1/platform-admin/trial-organizations"
REASON = "Agreed with the trial owner on a call"


@pytest.fixture(autouse=True, scope="module")
def _clean_trial_workspaces():
    _purge_trial_business_data()
    yield
    _purge_trial_business_data()


def _trial():
    owner, approval, email = _approved_trial_client()
    return owner, uuid.UUID(approval["tenant_id"]), approval, email


def _subscription(tenant_id) -> SubscriptionLifecycle:
    with SessionLocal() as db:
        bind_system(db, "test: read the subscription")
        row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one()
        db.expunge(row)
        return row


def _move_clock(tenant_id, *, ended_days_ago: float | None = None, created_days_ago: float | None = None) -> None:
    """Age the trial: its subscription created (and started) and its end moved into the past."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: age the trial")
        row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one()
        if created_days_ago is not None:
            row.created_at = row.starts_at = now - timedelta(days=created_days_ago)
        if ended_days_ago is not None:
            row.expires_at = now - timedelta(days=ended_days_ago)
            row.grace_ends_at = None
        db.commit()


def _events(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: read the trial's trail")
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action)
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        db.expunge_all()
        return rows


def _plan_id(code_is_trial: bool) -> str:
    with SessionLocal() as db:
        query = db.query(PlanDefinition.id).filter(PlanDefinition.status == "ACTIVE")
        if code_is_trial:
            return str(query.filter(PlanDefinition.code == "FREE_TRIAL").scalar())
        found = query.filter(PlanDefinition.code == "TO1_PILOT").scalar()
        if found is not None:
            return str(found)
        now = datetime.now(timezone.utc)
        plan = PlanDefinition(
            id=uuid.uuid4(),
            code="TO1_PILOT",
            name="Pilot (test)",
            description="A pilot plan for the trial organization tests",
            version="v1",
            status="ACTIVE",
            effective_from=now,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.commit()
        return str(plan.id)


def _convert(admin, tenant_id, kind="PILOT", **changes):
    now = datetime.now(timezone.utc)
    body = {
        "kind": kind,
        "plan_id": _plan_id(False),
        "starts_at": now.isoformat(),
        "expires_at": (now + timedelta(days=90)).isoformat(),
        "reason": "Pilot agreed for the first quarter",
        **changes,
    }
    return admin.post(f"{BASE}/{tenant_id}/convert", json=body)


def _code(response) -> str:
    return response.json()["detail"]["code"]


def _tenant_business_id(tenant_id) -> str:
    with SessionLocal() as db:
        bind_system(db, "test: read the tenant")
        return db.get(Tenant, tenant_id).business_id


def _acme_tenant_id() -> uuid.UUID:
    with SessionLocal() as db:
        return db.query(Tenant.id).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").scalar()


# --------------------------------------------------------------------------------------------- step 1: the definition


def test_a_trial_is_a_trial_in_every_state_and_a_converted_one_is_a_customer():
    admin = authenticated_client()
    _, running, _, _ = _trial()
    _, ended, _, _ = _trial()
    _, archived, _, _ = _trial()
    _, converted, _, _ = _trial()
    _move_clock(ended, ended_days_ago=3)
    with SessionLocal() as db:
        bind_system(db, "test: archive a trial")
        db.get(Tenant, archived).status = "ARCHIVED"
        db.commit()
    assert _convert(admin, converted).status_code == 200
    with SessionLocal() as db:
        bind_system(db, "test: read the scope")
        for tenant_id in (running, ended, archived):
            assert scope.is_trial(db, tenant_id), tenant_id
        assert not scope.is_trial(db, converted) and scope.is_converted(db, converted)
        assert not scope.is_trial(db, _acme_tenant_id()) and not scope.was_trial(db, _acme_tenant_id())
        customer_of = dict(db.query(Tenant.id, Tenant.customer_id).filter(Tenant.id.in_([running, converted])))
        trial_only = {
            row.id
            for row in db.query(Customer.id).filter(
                Customer.id.in_(customer_of.values()), scope.trial_only_customer_clause(Customer.id)
            )
        }
        assert trial_only == {customer_of[running]}


# --------------------------------------------------------------------------------------------- step 2: main lists


def test_a_trial_never_appears_in_the_main_lists():
    admin = authenticated_client()
    _, tenant_id, approval, email = _trial()
    business_id = _tenant_business_id(tenant_id)
    accounts = admin.get("/api/v1/platform-admin/customer-accounts", params={"q": business_id, "page_size": 100})
    assert accounts.status_code == 200 and accounts.json()["total"] == 0 and accounts.json()["items"] == []
    tenants = admin.get("/api/v1/platform-admin/tenants", params={"q": business_id}).json()
    assert tenants["total"] == 0 and tenants["items"] == []
    customers = admin.get("/api/v1/platform-admin/customers", params={"q": business_id.lower()}).json()
    assert customers["total"] == 0
    csv = admin.get("/api/v1/platform-admin/customers", params={"q": business_id.lower(), "format": "csv"})
    assert csv.status_code == 200 and business_id not in csv.text
    users = admin.get("/api/v1/platform-admin/customer-users", params={"q": email}).json()
    assert all(item.get("email") != email for item in users["items"])
    admins = admin.get("/api/v1/platform-admin/customer-admins", params={"tenant_id": str(tenant_id)}).json()
    assert admins["items"] == []
    expiring = admin.get("/api/v1/platform/subscriptions/expiring").json()
    assert str(tenant_id) not in {row["tenant_id"] for row in expiring}
    renewals = admin.get("/api/v1/platform-admin/console/renewals").json()["items"]
    assert str(tenant_id) not in {row.get("tenant_id") for row in renewals}
    # The old saved view is retired, naming where trials are now.
    moved = admin.get("/api/v1/platform-admin/customers", params={"view": "TRIAL"})
    assert moved.status_code == 422 and _code(moved) == "VIEW_MOVED"
    # The tenant record by id still answers (the trial page and support use it).
    assert admin.get(f"/api/v1/platform-admin/tenants/{tenant_id}").status_code == 200
    # Totals agree with the rows: every page of the tenant directory adds up to its total, without the trial.
    every = admin.get("/api/v1/platform-admin/tenants", params={"page_size": 100}).json()
    assert every["total"] == len(every["items"]) or every["pages"] > 1
    assert str(tenant_id) not in {item["id"] for item in every["items"]}


def test_a_converted_trial_appears_in_the_main_lists_and_leaves_the_trial_list():
    admin = authenticated_client()
    owner, tenant_id, approval, _ = _trial()
    converted = _convert(admin, tenant_id, kind="PILOT")
    assert converted.status_code == 200, converted.text
    assert converted.json()["trial_converted"] is True and converted.json()["kind"] == "PILOT"
    business_id = _tenant_business_id(tenant_id)
    tenants = admin.get("/api/v1/platform-admin/tenants", params={"q": business_id}).json()
    assert [item["id"] for item in tenants["items"]] == [str(tenant_id)]
    accounts = admin.get("/api/v1/platform-admin/customer-accounts", params={"q": business_id}).json()
    assert accounts["total"] == 1
    customers = admin.get("/api/v1/platform-admin/customers", params={"q": business_id.lower()}).json()
    assert customers["total"] == 1
    listed = admin.get(BASE, params={"q": business_id, "page_size": 200}).json()
    assert str(tenant_id) not in {item["tenant_id"] for item in listed["items"]}
    former = admin.get(BASE, params={"state": "CONVERTED", "q": business_id}).json()
    assert [item["tenant_id"] for item in former["items"]] == [str(tenant_id)]
    assert former["items"][0]["conversion"]["kind"] == "PILOT"
    with SessionLocal() as db:
        bind_system(db, "test: read the plan history")
        history = (
            db.query(PlanDefinition.code, TenantPlanAssignment.status)
            .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
            .filter(TenantPlanAssignment.tenant_id == tenant_id)
            .all()
        )
        assert ("FREE_TRIAL", "SUPERSEDED") in history
        assert db.get(Customer, db.get(Tenant, tenant_id).customer_id).customer_type == "PILOT"
    assert len(_events(tenant_id, "TRIAL_CONVERTED")) == 1
    assert len(_events(tenant_id, "TRIAL_OWNER_PROMOTED")) == 1
    detail = admin.get(f"{BASE}/{tenant_id}").json()
    assert detail["state"] == "CONVERTED" and not any(action["allowed"] for action in detail["actions"].values())
    again = _convert(admin, tenant_id)
    assert again.status_code == 409 and _code(again) == "TRIAL_ALREADY_CONVERTED"


def test_a_paying_customer_cannot_be_moved_onto_the_free_trial_plan():
    admin = authenticated_client()
    tenant_id = _acme_tenant_id()
    before = len(_events(tenant_id, "TRIAL_ACTION_REFUSED"))
    now = datetime.now(timezone.utc)
    refused = admin.post(
        f"/api/v1/platform/customers/{tenant_id}/subscription",
        json={
            "plan_id": _plan_id(True),
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "reason": "Trying to put a customer on the trial",
        },
    )
    assert refused.status_code == 409 and _code(refused) == "TRIAL_PLAN_NOT_ASSIGNABLE"
    with SessionLocal() as db:
        bind_system(db, "test: read the plan")
        assert not scope.is_trial(db, tenant_id)
    assert len(_events(tenant_id, "TRIAL_ACTION_REFUSED")) == before + 1
    # Converting to the Free Trial plan is refused on the trial page too.
    _, trial_id, _, _ = _trial()
    to_trial = _convert(authenticated_client(), trial_id, plan_id=_plan_id(True))
    assert to_trial.status_code == 422 and _code(to_trial) == "TRIAL_PLAN_NOT_ASSIGNABLE"


# --------------------------------------------------------------------------------------------- step 3: totals apart


def test_the_dashboard_counts_trials_apart_from_customers():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    dashboard = admin.get("/api/v1/platform-admin/console/dashboard").json()
    assert "Free Trial" not in {row["label"] for row in dashboard["tenants_by_plan"]}
    assert {"waiting_for_review", "active", "ending_soon", "converted_this_month"} <= set(dashboard["trials"])
    assert dashboard["trials"]["active"] >= 1
    series = {key for day in dashboard["new_tenants"] for key in day if key != "date"}
    assert "trials" in series and "tenants" not in series and series <= {"customers", "trials"}
    assert dashboard["new_tenants"][-1].get("trials", 0) >= 1
    summary = admin.get(f"{BASE}/summary").json()
    assert summary == {**summary, "active": dashboard["trials"]["active"]}


# --------------------------------------------------------------------------------------------- step 4: list and detail


def test_the_trial_list_and_detail_show_dates_people_sample_and_actions():
    admin = authenticated_client()
    owner, tenant_id, approval, email = _trial()
    listed = admin.get(BASE, params={"q": email}).json()
    row = next(item for item in listed["items"] if item["tenant_id"] == str(tenant_id))
    assert row["extension"] == {"used": 0, "max": 30} and row["sample"]["status"] == "LOADED"
    assert row["state"] == "ACTIVE" and listed["counts"]["active"] >= 1
    detail = admin.get(f"{BASE}/{tenant_id}").json()
    assert detail["state"] == "ACTIVE" and detail["plan"] == "Free Trial"
    assert detail["dates"]["extension_left"] == 30 and detail["dates"]["days_left"] in (29, 30)
    assert detail["people"]["owner"]["email"] == email
    assert detail["sample"]["sample_counts"]["products"] == 3
    assert detail["actions"]["extend"]["allowed"] and detail["actions"]["end"]["allowed"]
    assert not detail["actions"]["delete_data"]["allowed"] and detail["actions"]["delete_data"]["reason"]
    assert detail["ai"]["enabled"] is False and detail["ai"]["line"] == "AI is not switched on for this trial."
    assert detail["next_step"]
    removed = owner.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
    assert removed.status_code == 200, removed.text
    assert admin.get(f"{BASE}/{tenant_id}").json()["sample"]["status"] == "REMOVED"
    # A tenant that is not a trial is not found here.
    missing = admin.get(f"{BASE}/{_acme_tenant_id()}")
    assert missing.status_code == 404 and _code(missing) == "NOT_A_TRIAL"
    bad = admin.get(BASE, params={"state": "SOMETHING"})
    assert bad.status_code == 422


# --------------------------------------------------------------------------------------------- step 5: extend


def test_extensions_stop_at_original_end_plus_30_days_and_a_refusal_is_audited():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    original = _subscription(tenant_id).expires_at
    first = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 10, "reason": REASON})
    assert first.status_code == 200, first.text and first.json()["extension_used"] == 10
    second = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 20, "reason": REASON})
    assert second.status_code == 200 and second.json()["extension_used"] == 30
    assert second.json()["extension_left"] == 0
    capped = _subscription(tenant_id)
    assert capped.expires_at == original + timedelta(days=30)
    one_more = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 1, "reason": REASON})
    assert one_more.status_code == 409 and _code(one_more) == "TRIAL_EXTENSION_LIMIT"
    assert "0 more days at most (30 in total)" in one_more.json()["detail"]["message"]
    assert _subscription(tenant_id).expires_at == capped.expires_at
    assert _subscription(tenant_id).expiry_version == capped.expiry_version
    extended = _events(tenant_id, "TRIAL_EXTENDED")
    assert [event.details["days"] for event in extended] == [10, 20]
    assert extended[-1].old_values and extended[-1].new_values and extended[-1].details["total_used"] == 30
    refused = _events(tenant_id, "TRIAL_ACTION_REFUSED")
    assert refused[-1].details == {"attempted": "EXTEND", "code": "TRIAL_EXTENSION_LIMIT"}
    short = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 1, "reason": "short"})
    assert short.status_code == 422 and _code(short) == "TRIAL_REASON_REQUIRED"


def test_thirty_one_days_at_once_and_the_subscriptions_route_beyond_the_cap_are_refused():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    before = _subscription(tenant_id)
    at_once = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 31, "reason": REASON})
    assert at_once.status_code == 422 and _code(at_once) == "TRIAL_EXTENSION_DAYS"
    generic = f"/api/v1/platform/customers/{tenant_id}/subscription"
    body = {"plan_id": _plan_id(True), "starts_at": before.starts_at.isoformat(), "reason": REASON}
    beyond = admin.post(generic, json={**body, "expires_at": (before.expires_at + timedelta(days=31)).isoformat()})
    assert beyond.status_code == 409 and _code(beyond) == "TRIAL_EXTENSION_LIMIT"
    grace = admin.post(
        generic,
        json={
            **body,
            "expires_at": before.expires_at.isoformat(),
            "grace_ends_at": (before.expires_at + timedelta(days=40)).isoformat(),
        },
    )
    assert grace.status_code == 409 and _code(grace) == "TRIAL_EXTENSION_LIMIT"
    moved = admin.post(
        generic,
        json={
            **body,
            "starts_at": (before.starts_at - timedelta(days=5)).isoformat(),
            "expires_at": before.expires_at.isoformat(),
        },
    )
    assert moved.status_code == 409 and _code(moved) == "TRIAL_START_FIXED"
    after = _subscription(tenant_id)
    assert (after.starts_at, after.expires_at) == (before.starts_at, before.expires_at)
    codes = [event.details["code"] for event in _events(tenant_id, "TRIAL_ACTION_REFUSED")]
    assert codes.count("TRIAL_EXTENSION_LIMIT") == 2 and "TRIAL_START_FIXED" in codes
    # Within the cap the Subscriptions route still extends a trial.
    within = admin.post(generic, json={**body, "expires_at": (before.expires_at + timedelta(days=5)).isoformat()})
    assert within.status_code == 200, within.text


def test_an_ended_trial_reopens_while_its_data_is_kept_but_never_after_an_early_end():
    admin = authenticated_client()
    owner, tenant_id, _, _ = _trial()
    _move_clock(tenant_id, created_days_ago=33, ended_days_ago=3)
    reopened = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 10, "reason": REASON})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["reopened"] is True
    assert owner.get("/api/v1/trial/status").status_code == 200
    ended = admin.post(f"{BASE}/{tenant_id}/end", json={"reason": "Evaluation finished, agreed by phone"})
    assert ended.status_code == 200, ended.text
    again = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 5, "reason": REASON})
    assert again.status_code == 409 and _code(again) == "TRIAL_ENDED_EARLY"
    detail = admin.get(f"{BASE}/{tenant_id}").json()
    assert detail["state"] == "ENDED_EARLY" and not detail["actions"]["extend"]["allowed"]


# --------------------------------------------------------------------------------------------- step 6: end early


def test_mdarix_ends_a_trial_through_the_exit_request_flow_and_keeps_the_data():
    admin = authenticated_client()
    owner, tenant_id, _, _ = _trial()
    short = admin.post(f"{BASE}/{tenant_id}/end", json={"reason": "too short"})
    assert short.status_code == 422 and _code(short) == "TRIAL_REASON_REQUIRED"
    ended = admin.post(f"{BASE}/{tenant_id}/end", json={"reason": "Evaluation finished, agreed by phone"})
    assert ended.status_code == 200, ended.text
    assert ended.json()["data_deleted"] is False
    assert ended.json()["request"]["reason_code"] == "ENDED_BY_MDARIX"
    assert ended.json()["request"]["reason_label"] == "Ended by MDARIX"
    with SessionLocal() as db:
        bind_system(db, "test: read the exit request")
        row = db.query(TrialExitRequest).filter(TrialExitRequest.trial_tenant_id == tenant_id).one()
        assert row.status == "APPROVED" and row.requested_by == row.decided_by and not row.data_deleted
        assert db.get(Tenant, tenant_id).status == "ACTIVE"
        email = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == "TRIAL_REMINDER")
            .all()
        )
        assert any(event.payload.get("early") for event in email)
    assert _subscription(tenant_id).expires_at <= datetime.now(timezone.utc)
    assert len(_events(tenant_id, "TRIAL_EXIT_RAISED_BY_MDARIX")) == 1
    assert len(_events(tenant_id, "TRIAL_ENDED_EARLY")) == 1
    assert owner.get("/api/v1/trial/status").status_code == 403


def test_a_pending_owner_request_is_decided_in_its_own_flow_and_blocks_convert():
    admin = authenticated_client()
    owner, tenant_id, _, _ = _trial()
    asked = owner.post("/api/v1/trial/exit-request", json={"reason_code": "FINISHED", "delete_data": False})
    assert asked.status_code == 200, asked.text
    pending_id = asked.json()["request"]["id"]
    ended = admin.post(f"{BASE}/{tenant_id}/end", json={"reason": "Evaluation finished, agreed by phone"})
    assert ended.status_code == 409 and _code(ended) == "TRIAL_EXIT_PENDING"
    assert ended.json()["detail"]["request_id"] == pending_id
    convert = _convert(admin, tenant_id)
    assert convert.status_code == 409 and _code(convert) == "TRIAL_EXIT_PENDING"
    extend = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 5, "reason": REASON})
    assert extend.status_code == 409 and _code(extend) == "TRIAL_EXIT_PENDING"
    assert _subscription(tenant_id).expires_at > datetime.now(timezone.utc)
    detail = admin.get(f"{BASE}/{tenant_id}").json()
    assert detail["actions"]["end"]["pending_request_id"] == pending_id


# --------------------------------------------------------------------------------------------- step 8: delete data now


def test_delete_data_now_only_when_due_with_the_name_typed_and_never_under_a_hold():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    with SessionLocal() as db:
        name = db.get(Tenant, tenant_id).name
    _move_clock(tenant_id, created_days_ago=40, ended_days_ago=10)
    early = admin.post(f"{BASE}/{tenant_id}/delete-data", json={"confirm_name": name})
    assert early.status_code == 409 and _code(early) == "TRIAL_NOT_DUE"
    _move_clock(tenant_id, created_days_ago=61, ended_days_ago=31)
    wrong = admin.post(f"{BASE}/{tenant_id}/delete-data", json={"confirm_name": "Some other company"})
    assert wrong.status_code == 422 and _code(wrong) == "TRIAL_NAME_MISMATCH"
    with SessionLocal() as db:
        bind_system(db, "test: a legal hold")
        db.get(Tenant, tenant_id).legal_hold = True
        db.commit()
    held = admin.post(f"{BASE}/{tenant_id}/delete-data", json={"confirm_name": name})
    assert held.status_code == 409 and _code(held) == "TRIAL_LEGAL_HOLD"
    codes = [event.details["code"] for event in _events(tenant_id, "TRIAL_ACTION_REFUSED")]
    assert codes == ["TRIAL_NOT_DUE", "TRIAL_NAME_MISMATCH", "TRIAL_LEGAL_HOLD"]
    with SessionLocal() as db:
        bind_system(db, "test: lift the hold")
        assert db.get(Tenant, tenant_id).status == "ACTIVE"
        db.get(Tenant, tenant_id).legal_hold = False
        db.commit()
    deleted = admin.post(f"{BASE}/{tenant_id}/delete-data", json={"confirm_name": name.upper()})
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        bind_system(db, "test: read the tenant")
        assert db.get(Tenant, tenant_id).status == "ARCHIVED"
    assert len(_events(tenant_id, "TRIAL_DATA_DELETED_BY_ADMIN")) == 1
    assert admin.get(f"{BASE}/{tenant_id}").json()["state"] == "DATA_DELETED"
    gone = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 5, "reason": REASON})
    assert gone.status_code == 409 and _code(gone) == "TRIAL_DATA_DELETED"


# --------------------------------------------------------------------------------------------- step 9: permissions


def test_only_a_platform_admin_reaches_any_trial_organization_route_and_nothing_changes():
    owner, tenant_id, _, _ = _trial()
    before = _subscription(tenant_id)
    routes = [
        ("get", f"{BASE}/summary", None),
        ("get", BASE, None),
        ("get", f"{BASE}/{tenant_id}", None),
        ("post", f"{BASE}/{tenant_id}/extend", {"days": 5, "reason": REASON}),
        ("post", f"{BASE}/{tenant_id}/end", {"reason": REASON}),
        (
            "post",
            f"{BASE}/{tenant_id}/convert",
            {
                "kind": "PILOT",
                "plan_id": _plan_id(False),
                "starts_at": "2026-12-01T00:00:00Z",
                "expires_at": "2027-03-01T00:00:00Z",
                "reason": REASON,
            },
        ),  # noqa: E501
        ("post", f"{BASE}/{tenant_id}/delete-data", {"confirm_name": "x"}),
    ]
    # A generic "Admin" is stored as the canonical PLATFORM_ADMIN (AuthUser role validator), so it is no separate case.
    callers = {
        "customer admin": _client_with_role("CUSTOMER_ADMIN"),
        "leader": _client_with_role("Leader"),
        "trial owner": owner,
    }
    for label, caller in callers.items():
        for method, path, body in routes:
            response = getattr(caller, method)(path, **({"json": body} if body else {}))
            assert response.status_code == 403, f"{label} {method} {path}: {response.status_code}"
    anonymous = TestClient(app)
    for method, path, body in routes:
        response = getattr(anonymous, method)(path, **({"json": body} if body else {}))
        assert response.status_code == 401, f"anonymous {method} {path}: {response.status_code}"
    after = _subscription(tenant_id)
    assert (after.expires_at, after.expiry_version, after.plan_id) == (
        before.expires_at,
        before.expiry_version,
        before.plan_id,
    )
    assert _events(tenant_id, "TRIAL_ACTION_REFUSED") == []


def test_an_actor_named_in_the_body_is_ignored():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    someone = str(uuid.uuid4())
    response = admin.post(
        f"{BASE}/{tenant_id}/extend",
        json={"days": 3, "reason": REASON, "actor_id": someone, "requested_by": someone, "admin_id": someone},
    )
    assert response.status_code == 200, response.text
    event = _events(tenant_id, "TRIAL_EXTENDED")[-1]
    assert event.actor_ref != someone and someone not in str(event.details)


# --------------------------------------------------------------------------------------------- review fixes


def test_plans_and_licensing_never_reopens_a_trial_ended_early_nor_converts_one_with_a_pending_request():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    before = _subscription(tenant_id)
    assert (
        admin.post(f"{BASE}/{tenant_id}/end", json={"reason": "Evaluation finished, agreed by phone"}).status_code
        == 200
    )
    generic = f"/api/v1/platform/customers/{tenant_id}/subscription"
    reopen = admin.post(
        generic,
        json={
            "plan_id": _plan_id(True),
            "starts_at": before.starts_at.isoformat(),
            "expires_at": (before.expires_at + timedelta(days=5)).isoformat(),
            "reason": REASON,
        },
    )
    assert reopen.status_code == 409 and _code(reopen) == "TRIAL_ENDED_EARLY"
    assert _subscription(tenant_id).expires_at <= datetime.now(timezone.utc)

    owner, pending_id, _, _ = _trial()
    asked = owner.post("/api/v1/trial/exit-request", json={"reason_code": "FINISHED", "delete_data": False})
    assert asked.status_code == 200
    now = datetime.now(timezone.utc)
    convert = admin.post(
        f"/api/v1/platform/customers/{pending_id}/subscription",
        json={
            "plan_id": _plan_id(False),
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(days=90)).isoformat(),
            "reason": REASON,
        },
    )
    assert convert.status_code == 409 and _code(convert) == "TRIAL_EXIT_PENDING"
    with SessionLocal() as db:
        bind_system(db, "test: still a trial")
        assert scope.is_trial(db, pending_id)


def test_a_date_without_a_time_zone_is_read_as_utc_not_a_server_error():
    admin = authenticated_client()
    _, tenant_id, _, _ = _trial()
    before = _subscription(tenant_id)
    naive = (before.expires_at + timedelta(days=40)).replace(tzinfo=None).isoformat()
    response = admin.post(
        f"/api/v1/platform/customers/{tenant_id}/subscription",
        json={
            "plan_id": _plan_id(True),
            "starts_at": before.starts_at.replace(tzinfo=None).isoformat(),
            "expires_at": naive,
            "reason": REASON,
        },
    )
    assert response.status_code == 409 and _code(response) == "TRIAL_EXTENSION_LIMIT"
    bad = _convert(admin, tenant_id, starts_at="2026-12-01T00:00:00")
    assert bad.status_code == 422 and _code(bad) == "INVALID_DATE"
    assert _events(tenant_id, "TRIAL_ACTION_REFUSED")[-1].details["code"] == "INVALID_DATE"


# --------------------------------------------------------------------------------------------- run 2: grace period


def _give_grace(tenant_id, *, ended_days_ago: float, grace_days_left: float) -> None:
    """The trial ended, then Plans & Licensing gave it a grace period that is still running."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: a grace period")
        row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one()
        row.created_at = row.starts_at = now - timedelta(days=30 + ended_days_ago)
        row.expires_at = now - timedelta(days=ended_days_ago)
        row.grace_ends_at = now + timedelta(days=grace_days_left)
        db.commit()


def test_a_trial_in_its_grace_period_shows_as_running_and_can_be_ended_early():
    from backend.app.trial import admin_actions

    admin = authenticated_client()
    owner, tenant_id, _, email = _trial()
    with SessionLocal() as db:
        before = admin_actions.summary(db)
    _give_grace(tenant_id, ended_days_ago=2, grace_days_left=5)
    # Its users can still sign in, so the page shows it running, counting the days to the grace end.
    assert owner.get("/api/v1/trial/status").status_code == 200
    detail = admin.get(f"{BASE}/{tenant_id}").json()
    assert detail["state"] == "ENDING_SOON" and detail["dates"]["days_left"] == 5
    assert detail["dates"]["in_grace"] is True and detail["dates"]["grace_ends_at"]
    assert detail["dates"]["deletion"] is None
    assert detail["actions"]["end"]["allowed"], detail["actions"]["end"]
    row = next(item for item in admin.get(BASE, params={"q": email}).json()["items"])
    assert row["tenant_id"] == str(tenant_id) and row["state"] == "ENDING_SOON" and row["in_grace"] is True
    with SessionLocal() as db:
        after = admin_actions.summary(db)
    assert after["active"] == before["active"] and after["ending_soon"] == before["ending_soon"] + 1
    assert after["ended_data_kept"] == before["ended_data_kept"]
    # An extension counts from the grace end, never shortening the users' time.
    grace_end = _subscription(tenant_id).grace_ends_at
    extended = admin.post(f"{BASE}/{tenant_id}/extend", json={"days": 3, "reason": REASON})
    assert extended.status_code == 200, extended.text
    assert extended.json()["reopened"] is False
    assert _subscription(tenant_id).expires_at == grace_end + timedelta(days=3)
    # End early is no longer refused as "already ended".
    _give_grace(tenant_id, ended_days_ago=2, grace_days_left=5)
    ended = admin.post(f"{BASE}/{tenant_id}/end", json={"reason": "Evaluation finished, agreed by phone"})
    assert ended.status_code == 200, ended.text
    finished = admin.get(f"{BASE}/{tenant_id}").json()
    assert finished["state"] == "ENDED_EARLY" and finished["dates"]["in_grace"] is False
    assert owner.get("/api/v1/trial/status").status_code == 403


# --------------------------------------------------------------------------------- run 2: the list at scale


@pytest.fixture
def scaled(monkeypatch):
    """``(session, now)``: a rolled-back session in which the scale-test plan stands for the Free Trial plan, so the
    other trials in the test database do not count."""
    from backend.app.trial import admin_actions, service
    from tests.trial_scale_seed import SCALE_PLAN, scale_session, utc_now

    for module in (service, scope, admin_actions):
        monkeypatch.setattr(module, "FREE_TRIAL_PLAN", SCALE_PLAN)
    with scale_session() as session:
        yield session, utc_now()


def _end_early(session, tenant_ids, now) -> None:
    for tenant_id in tenant_ids:
        session.add(
            TrialExitRequest(
                id=uuid.uuid4(),
                trial_tenant_id=tenant_id,
                organization="Scale trial",
                reason_code="ENDED_BY_MDARIX",
                reason="Ended for the paging test",
                delete_data=False,
                status="APPROVED",
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()


def test_the_ended_early_filter_pages_and_sorts_on_the_server(scaled):
    from backend.app.trial import admin_actions
    from tests.trial_scale_seed import seed_trials

    session, now = scaled
    tenant_ids = seed_trials(session, 45, "EARLY", now)
    ended = tenant_ids[::5]  # trial n ends three days ago when n % 5 == 0: 9 trials
    _end_early(session, ended[:7], now)
    _end_early(session, tenant_ids[1:2], now)  # still running (an approved request on a running trial)
    pages = [
        admin_actions.trial_list(session, state="ENDED_EARLY", page=number, page_size=3, sort="name", order="desc")
        for number in (1, 2, 3)
    ]
    assert [len(page["items"]) for page in pages] == [3, 3, 1]
    assert {(page["total"], page["pages"], page["page_size"]) for page in pages} == {(7, 3, 3)}
    names = [item["name"] for page in pages for item in page["items"]]
    assert names == sorted(names, reverse=True) and len(set(names)) == 7
    assert {item["tenant_id"] for page in pages for item in page["items"]} == {str(t) for t in ended[:7]}
    assert {item["state"] for page in pages for item in page["items"]} == {"ENDED_EARLY"}
    # A page past the end shows the last one; a search narrows within the ended-early trials.
    assert admin_actions.trial_list(session, state="ENDED_EARLY", page=9, page_size=3)["page"] == 3
    one = admin_actions.trial_list(session, state="ENDED_EARLY", q=names[0])
    assert [item["name"] for item in one["items"]] == [names[0]] and one["total"] == 1


def _list_statements(session, now, **filters) -> int:
    from backend.app.trial import admin_actions
    from tests.trial_scale_seed import QueryCounter

    with QueryCounter() as counter:
        admin_actions.trial_list(session, now=now, **filters)
    return counter.count


def test_the_trial_list_reads_5_or_45_trials_in_the_same_statements(scaled):
    """Guards against reading trial by trial: the list (and its ended-early filter) sends the same statements for 5
    trials as for 45."""
    from backend.app.db.models.foundation import PlanDefinition
    from tests.trial_scale_seed import SCALE_PLAN, seed_trials

    session, now = scaled
    few_ids = seed_trials(session, 5, "FEW", now)
    _end_early(session, few_ids[:1], now)
    few = _list_statements(session, now)
    few_early = _list_statements(session, now, state="ENDED_EARLY")
    plan = session.query(PlanDefinition).filter(PlanDefinition.code == SCALE_PLAN).one()
    many_ids = seed_trials(session, 40, "MANY", now, plan=plan)
    _end_early(session, many_ids[::5], now)
    many = _list_statements(session, now)
    many_early = _list_statements(session, now, state="ENDED_EARLY")
    assert many == few, f"{few} statements for 5 trials, {many} for 45: something is read trial by trial"
    assert many_early == few_early, f"ended early: {few_early} statements for 5 trials, {many_early} for 45"
