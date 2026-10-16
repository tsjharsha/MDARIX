"""The Platform Admin trial overview and trial request queue with hundreds of trials (free trial launch, 20 Oct 2026).

Before 0.10.16 the overview read each trial on its own (about 32 statements per trial: 9,600 for 300 trials, over 20
seconds) and stopped answering at about 90 active trials; the request queue looked up each approved request's
workspace one by one. Both now read every trial in a fixed number of statements and return one page at a time.

The trials are seeded in a transaction that is rolled back (tests/trial_scale_seed.py), on a plan of their own that
the overview reads instead of the Free Trial plan, so other trials in the test database do not change the figures.
"""

import os
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.foundation import AuthUser, PlanDefinition
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.main import app
from backend.app.trial import citations, imports, service, story
from backend.app.trial.team import trial_request
from tests.conftest import authenticated_client
from tests.trial_scale_seed import (
    SCALE_PLAN,
    QueryCounter,
    benchmark,
    endpoint_on,
    scale_session,
    seed_trials,
    utc_now,
)


@pytest.fixture
def seeded(monkeypatch):
    """``(session, now)``: a rolled-back session, the overview reading the scale-test plan as the Free Trial plan."""
    monkeypatch.setattr(service, "FREE_TRIAL_PLAN", SCALE_PLAN)
    with scale_session() as session:
        yield session, utc_now()


def _every_trial(session, now, **filters) -> dict:
    return story.trial_overview(session, now, page_size=story.OVERVIEW_PAGE_SIZE_MAX, **filters)


def _as_read_one_by_one(session, tenant_id) -> dict:
    """What the overview showed for one trial before 0.10.16: each figure read for that trial alone, with the same
    per-trial functions (story.progress, imports.uploaded_rows, team.trial_request) and the same owner and seat rule."""
    request = trial_request(session, tenant_id)
    owner = (
        session.query(AuthUser.username, AuthUser.display_name, AuthUser.status)
        .filter(AuthUser.tenant_id == tenant_id, ~AuthUser.username.like("sample-author+%"))
        .order_by(AuthUser.created_at)
        .first()
    )
    seats = (
        session.query(AuthUser.id)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(["ACTIVE", "INVITED"]))
        .count()
    )
    return {
        "story": story.progress(session, tenant_id, story.remembered(request.profile if request else None)),
        "rows": imports.uploaded_rows(session, tenant_id),
        "users": seats,
        "owner": {"email": owner.username, "name": owner.display_name, "status": owner.status} if owner else None,
        "cited_for": citations.labels((request.profile or {}).get("citations") if request else ()),
        "feedback": story._feedback_by_tenant(session, [tenant_id]).get(tenant_id),
        "demo_request": story._demos_by_tenant(session, [tenant_id]).get(tenant_id),
    }


def test_the_overview_shows_each_trial_as_reading_it_alone_did(seeded):
    session, now = seeded
    tenant_ids = seed_trials(session, 30, "SAME", now)
    overview = _every_trial(session, now)
    by_id = {item["tenant_id"]: item for item in overview["items"]}
    assert set(by_id) == {str(tenant_id) for tenant_id in tenant_ids}
    for tenant_id in tenant_ids:
        item, expected = by_id[str(tenant_id)], _as_read_one_by_one(session, tenant_id)
        assert item["story"] == expected["story"]
        assert item["rows"]["used"] == expected["rows"] and item["users"]["used"] == expected["users"]
        assert item["owner"] == expected["owner"]
        assert item["cited_for"] == expected["cited_for"]
        assert item["feedback"] == expected["feedback"] and item["demo_request"] == expected["demo_request"]
    # The seeding varies what each trial did, so the comparison covers every kind of figure.
    items = list(by_id.values())
    assert any(item["story"]["counts"]["HIDDEN_COMPLAINTS"] for item in items)
    assert any("REPORTING_CLOCKS" in item["story"]["acted"] for item in items)  # tried before removing the sample
    assert any(item["story"]["last_activity"] for item in items) and any(item["rows"]["used"] for item in items)
    assert any(item["owner"]["status"] == "INVITED" for item in items) and any(item["feedback"] for item in items)
    assert {item["state"] for item in items} == {"ACTIVE", "ENDING_SOON", "ENDED"}

    # The figures above the table, from every trial, as before.
    active = [item for item in items if item["state"] != "ENDED"]
    summary = overview["summary"]
    assert summary["trials"] == 30 and summary["active"] == len(active) == 24
    assert summary["ending_soon"] == sum(1 for item in items if item["state"] == "ENDING_SOON") == 6
    assert summary["acted"] == sum(1 for item in active if item["story"]["acted_count"])
    assert summary["own_data"] == sum(1 for item in active if item["story"]["counts"]["YOUR_DATA"])
    assert summary["feedback"] == 5 and summary["demo_requested"] == 5
    assert summary["chapters"]["HIDDEN_COMPLAINTS"] == sum(
        1 for item in active if "HIDDEN_COMPLAINTS" in item["story"]["acted"]
    )


def _overview_statements(session, now) -> int:
    with QueryCounter() as counter:
        story.trial_overview(session, now)
    return counter.count


def test_the_overview_reads_every_trial_in_the_same_few_statements(seeded):
    """Guards against reading trial by trial again: 5 or 120 trials, the overview sends the same statements."""
    session, now = seeded
    seed_trials(session, 5, "FEW", now)
    few = _overview_statements(session, now)
    plan = session.query(PlanDefinition).filter(PlanDefinition.code == SCALE_PLAN).one()
    seed_trials(session, 115, "MANY", now, plan=plan)
    many = _overview_statements(session, now)
    assert many == few, f"{few} statements for 5 trials, {many} for 120: something is read trial by trial"
    # The trials, their requests, feedback, demos, chapter counts, last activity, people and uploads, plus the
    # session's own transaction statements: a fixed handful.
    assert many <= 14, many


def test_the_overview_pages_filters_and_sorts_on_the_server(seeded):
    session, now = seeded
    tenant_ids = seed_trials(session, 120, "PAGE", now)
    first = story.trial_overview(session, now)
    assert len(first["items"]) == 50 and first["page"] == 1 and first["page_size"] == 50
    assert first["total"] == 120 and first["pages"] == 3
    pages = [story.trial_overview(session, now, page=number)["items"] for number in (1, 2, 3)]
    assert [len(items) for items in pages] == [50, 50, 20]
    seen = [item["tenant_id"] for items in pages for item in items]
    assert len(seen) == len(set(seen)) == 120 and set(seen) == {str(tenant_id) for tenant_id in tenant_ids}
    # Every trial on a page carries its people and uploads; a page past the end shows the last one.
    assert all(item["owner"] and item["users"]["used"] >= 1 for items in pages for item in items)
    assert story.trial_overview(session, now, page=9)["page"] == 3
    assert story.trial_overview(session, now, page_size=1000)["page_size"] == 200

    # By default the trials that need a person come first, across all pages: ending soon and not engaged, then the
    # least progress, then the fewest days left; ended trials last.
    ranks = [story._attention_rank(item) for items in pages for item in items]
    assert ranks == sorted(ranks) and pages[0][0]["state"] == "ENDING_SOON" and pages[2][-1]["state"] == "ENDED"
    attention = first["attention"]
    assert len(attention) == 5 and all(item["state"] != "ENDED" and item["owner"] for item in attention)
    assert [item["tenant_id"] for item in attention] == [
        item["tenant_id"] for items in pages for item in items if item["state"] != "ENDED"
    ][:5]

    # A column heading sorts every page; filters keep the summary for every trial.
    by_name = story.trial_overview(session, now, sort="name", order="desc", page_size=200)["items"]
    assert [item["name"] for item in by_name] == sorted((item["name"] for item in by_name), reverse=True)
    by_story = story.trial_overview(session, now, sort="story", page_size=200)["items"]
    assert [item["story"]["acted_count"] for item in by_story] == sorted(
        item["story"]["acted_count"] for item in by_story
    )
    ended = story.trial_overview(session, now, state="ENDED", page_size=200)
    assert ended["total"] == 24 and {item["state"] for item in ended["items"]} == {"ENDED"}
    assert ended["summary"] == first["summary"] and ended["attention"] == first["attention"]
    one = story.trial_overview(session, now, q="page devices 0042")
    assert [item["name"] for item in one["items"]] == ["PAGE Devices 0042"] and one["total"] == 1
    owner = one["items"][0]["owner"]["email"]
    assert [item["tenant_id"] for item in story.trial_overview(session, now, q=owner.upper())["items"]] == [
        one["items"][0]["tenant_id"]
    ]
    assert story.trial_overview(session, now, q="no such trial")["items"] == []


def test_the_overview_endpoint_takes_pages_and_filters_for_the_platform_admin_only(seeded):
    session, now = seeded
    seed_trials(session, 60, "API", now)
    admin = authenticated_client()
    with endpoint_on(session):
        body = admin.get("/api/v1/platform-admin/trials?page=2&page_size=25&state=active&sort=name").json()
        assert body["page"] == 2 and body["page_size"] == 25 and body["total"] == 36 and body["pages"] == 2
        assert {item["state"] for item in body["items"]} == {"ACTIVE"}
        assert body["summary"]["trials"] == 60 and len(body["items"]) == 11
        invalid = admin.get("/api/v1/platform-admin/trials?state=SOMETIMES")
        assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "INVALID_TRIAL_STATE"
        assert TestClient(app).get("/api/v1/platform-admin/trials").status_code == 401


# ------------------------------------------------------------------------------------------- the request queue


def _requests(session, tag: str, count: int, now, approved_tenants=()) -> list:
    rows = []
    for number in range(count):
        tenant_id = approved_tenants[number] if number < len(approved_tenants) else None
        rows.append(
            OnboardingRequest(
                id=uuid.uuid4(),
                email=f"queue-{tag.lower()}-{number:03d}-{uuid.uuid4().hex[:6]}@example.invalid",
                display_name=f"Requester {number:03d}",
                organization=f"{tag} Queue {number:03d}",
                status="APPROVED" if tenant_id else "DECLINED" if number % 4 == 3 else "PENDING_REVIEW",
                profile={},
                tenant_id=tenant_id,
                created_at=now - timedelta(minutes=number),
                updated_at=now,
            )
        )
    session.add_all(rows)
    session.flush()
    return rows


def _queue_statements(session, tag: str) -> int:
    with QueryCounter() as counter:
        service.request_queue(session, q=tag, status="APPROVED")
    return counter.count


def test_the_request_queue_reads_any_page_in_the_same_few_statements(seeded):
    session, now = seeded
    few = seed_trials(session, 3, "QFEW", now)
    tag = f"qbound{uuid.uuid4().hex[:6]}"
    _requests(session, tag, 3, now, few)
    with_three = _queue_statements(session, tag)
    plan = session.query(PlanDefinition).filter(PlanDefinition.code == SCALE_PLAN).one()
    more = seed_trials(session, 47, "QMANY", now, plan=plan)
    _requests(session, f"{tag}b", 47, now, more)
    with_fifty = _queue_statements(session, tag)
    assert with_fifty == with_three <= 6, (with_three, with_fifty)


def test_the_request_queue_pages_filters_counts_and_shows_each_workspace(seeded):
    session, now = seeded
    trials = seed_trials(session, 12, "QUEUE", now)
    tag = f"queue{uuid.uuid4().hex[:6]}"
    rows = _requests(session, tag, 130, now, trials)
    everything = service.request_queue(session, q=tag)
    assert everything["counts"] == {"PENDING_REVIEW": 89, "APPROVED": 12, "DECLINED": 29}
    assert everything["total"] == 130 and everything["pages"] == 3 and len(everything["items"]) == 50
    # Newest first, every page, no request twice.
    pages = [service.request_queue(session, q=tag, page=number)["items"] for number in (1, 2, 3)]
    listed = [item["id"] for items in pages for item in items]
    assert listed == [str(row.id) for row in rows] and len(set(listed)) == 130
    pending = service.request_queue(session, q=tag, status="PENDING_REVIEW", page_size=500)
    assert pending["page_size"] == 200 and pending["total"] == 89 and pending["counts"] == everything["counts"]
    assert {item["status"] for item in pending["items"]} == {"PENDING_REVIEW"}
    by_company = service.request_queue(session, q=tag, sort="organization", order="desc")["items"]
    assert by_company[0]["organization"] == f"{tag} Queue 129"

    # Each approved request shows its trial workspace, end date and owner as reading it alone does.
    approved = service.request_queue(session, q=tag, status="APPROVED")["items"]
    assert len(approved) == 12
    for item in approved:
        row = session.get(OnboardingRequest, uuid.UUID(item["id"]))
        subscription = service.trial_subscription(session, row.tenant_id)
        assert item["tenant_id"] == str(row.tenant_id) and item["tenant_key"]
        assert item["trial_expires_at"] == subscription.expires_at.isoformat()
        assert item["owner_status"] is None  # the seeded owners have other addresses than these requests
    # Once the requester has an account in the workspace, its status shows (INVITED until they activate).
    owned = session.get(OnboardingRequest, uuid.UUID(approved[0]["id"]))
    person = AuthUser(
        id=uuid.uuid4(),
        tenant_id=owned.tenant_id,
        username=owned.email,
        display_name="Requester",
        company="Queue",
        password_hash="!",
        role="Leader",
        status="INVITED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    session.add(person)
    session.flush()
    shown = {item["id"]: item for item in service.request_queue(session, q=tag, status="APPROVED")["items"]}
    assert shown[str(owned.id)]["owner_status"] == "INVITED"
    assert service.serialize_request(session, owned) == shown[str(owned.id)]


def test_the_request_queue_endpoint_takes_pages_and_filters(seeded):
    session, now = seeded
    tag = f"qapi{uuid.uuid4().hex[:6]}"
    _requests(session, tag, 8, now)
    admin = authenticated_client()
    with endpoint_on(session):
        body = admin.get(f"/api/v1/platform-admin/trial-requests?q={tag}&status=declined&page_size=1").json()
        assert body["total"] == 2 and body["pages"] == 2 and len(body["items"]) == 1
        assert body["counts"] == {"PENDING_REVIEW": 6, "APPROVED": 0, "DECLINED": 2}
        invalid = admin.get("/api/v1/platform-admin/trial-requests?status=MAYBE")
        assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "INVALID_REQUEST_STATUS"
        assert TestClient(app).get("/api/v1/platform-admin/trial-requests").status_code == 401


def _ask_to_end(session, tenant_ids, now) -> None:
    """One exit request per trial, by its owner: pending, declined or approved (with its data deleted) in turn."""
    from backend.app.db.models.stage2 import TrialExitRequest

    for number, tenant_id in enumerate(tenant_ids):
        owner = (
            session.query(AuthUser.id)
            .filter(AuthUser.tenant_id == tenant_id, ~AuthUser.username.like("sample-author+%"))
            .order_by(AuthUser.created_at)
            .first()
        )
        status = ("PENDING", "DECLINED", "APPROVED")[number % 3]
        session.add(
            TrialExitRequest(
                id=uuid.uuid4(),
                trial_tenant_id=tenant_id,
                organization=f"Exit {number}",
                requested_by=owner.id if owner else None,
                reason_code="FINISHED",
                delete_data=status == "APPROVED",
                status=status,
                data_deleted=status == "APPROVED",
                created_at=now - timedelta(minutes=number),
                updated_at=now,
            )
        )
    session.flush()


def _exit_request_alone(session, item) -> dict:
    """What the exit requests panel showed for one request before 0.10.17, each figure read for it alone."""
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.stage2 import TrialExitRequest
    from backend.app.trial import early_exit

    row = session.get(TrialExitRequest, uuid.UUID(item["id"]))
    tenant = session.get(Tenant, row.trial_tenant_id)
    person = session.get(AuthUser, row.requested_by) if row.requested_by else None
    on_trial = service.trial_subscription(session, row.trial_tenant_id) is not None
    return {
        "tenant_business_id": tenant.business_id if tenant else None,
        "tenant_status": tenant.status if tenant else None,
        "requested_by": (person.display_name or person.username) if person and not row.data_deleted else None,
        "days_left": early_exit.days_left(session, row.trial_tenant_id) if on_trial else None,
    }


def test_the_exit_requests_panel_reads_every_request_in_the_same_few_statements(seeded):
    """Platform Admin › Trials › exit requests: 5 or 45 requests, the same statements (before 0.10.17 each request
    cost four: its organization, the person who asked and its subscription twice), and the same figures as reading
    each request alone."""
    from backend.app.trial import early_exit

    session, now = seeded
    _ask_to_end(session, seed_trials(session, 5, "XFEW", now), now)
    with QueryCounter() as few:
        early_exit.overview(session)
    plan = session.query(PlanDefinition).filter(PlanDefinition.code == SCALE_PLAN).one()
    _ask_to_end(session, seed_trials(session, 40, "XMANY", now, plan=plan), now)
    with QueryCounter() as many:
        items = early_exit.overview(session)
    # The requests, their organizations, the people who asked and the trials' subscriptions.
    assert many.count == few.count <= 4, (few.count, many.count)

    seeded_items = [item for item in items if item["organization"].startswith("Exit ")]
    assert len(seeded_items) >= 45
    assert [item["status"] for item in items] == sorted(
        (item["status"] for item in items), key=lambda status: status != "PENDING"
    )
    for item in seeded_items:
        expected = _exit_request_alone(session, item)
        assert {key: item[key] for key in expected} == expected, item
    shown = {item["status"]: item for item in seeded_items}
    assert shown["PENDING"]["requested_by"] and shown["PENDING"]["days_left"] is not None
    assert shown["APPROVED"]["requested_by"] is None  # the people were deleted with the data


@pytest.mark.skipif(not os.getenv("MDARIX_TRIAL_SCALE_BENCH"), reason="set MDARIX_TRIAL_SCALE_BENCH=1 to measure")
def test_benchmark_the_trial_overview_and_request_queue():
    """Statements and milliseconds per endpoint for 25, 100 and 300 trials (``-s`` shows them)."""
    for row in benchmark():
        print(row)
