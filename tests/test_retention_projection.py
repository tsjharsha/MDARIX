"""DEV-05 (0.10.86): one retention projection for every channel.

The trial status (Getting started), the trial-ended error, the trial e-mails, the Platform Admin trials overview, the
trial requests queue, the MVP requests and the purge job all read ``retention.retention_plan`` now. Before 0.10.86 the
trial requests queue said "expires + 30 days" (no grace, no hold) and the trial-ended page said "end + 30 days" (no
hold); none of them knew a legal hold, and the purge job deleted from a list read at its start."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.db.models.foundation import Tenant
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.trial import retention
from backend.app.trial.service import long_moment, trial_end_dates
from tests.conftest import authenticated_client
from tests.test_free_trial import _approved_trial_client
from tests.test_trial_p2_journey import EXPECTATIONS, OWN_EXPORT, _complaints, _purge

DAY = timedelta(days=1)
ENDED = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------------- the projection, on fixed clocks


@pytest.mark.unit
def test_the_projection_for_each_case_on_a_fixed_clock():
    plan = retention.retention_plan
    asked = {"open": SimpleNamespace(id=uuid.uuid4(), status="NEW"), "closed_at": None}
    # Ordinary expiry, and an early exit (the end moved to the exit): 30 days after the end.
    ordinary = plan(ENDED, None, False, ENDED + DAY)
    assert ordinary["earliest_deletion"] == ENDED + 30 * DAY and ordinary["hold"] is None
    assert ordinary["policy_version"] == retention.POLICY_VERSION
    # Grace counts: the effective end is the end of the grace extension.
    grace = SimpleNamespace(expires_at=ENDED, grace_ends_at=ENDED + 7 * DAY)
    assert retention.effective_end(grace) == ENDED + 7 * DAY
    assert retention.effective_end(SimpleNamespace(expires_at=ENDED, grace_ends_at=None)) == ENDED
    # An open request to move the data, the data movable: held to the maximum hold, then the maximum is the end.
    held = plan(ENDED, asked, True, ENDED + 40 * DAY)
    assert held["hold"] == retention.MVP_REQUEST_HOLD and held["earliest_deletion"] == ENDED + 90 * DAY
    past = plan(ENDED, asked, True, ENDED + 91 * DAY)
    assert past["hold"] is None and past["earliest_deletion"] == ENDED + 30 * DAY
    # The same request when the data cannot move: no hold.
    assert plan(ENDED, asked, False, ENDED + 40 * DAY)["hold"] is None
    # A closed request: 14 days after it closed, never after the maximum hold.
    closed = plan(ENDED, {"open": None, "closed_at": ENDED + 50 * DAY}, False, ENDED + 50 * DAY)
    assert closed["earliest_deletion"] == ENDED + 64 * DAY
    late = plan(ENDED, {"open": None, "closed_at": ENDED + 85 * DAY}, False, ENDED + 85 * DAY)
    assert late["earliest_deletion"] == ENDED + 90 * DAY
    # A legal hold: no date at all, whatever else applies; the internal 30-day mark stays for the purge job's audit.
    for requests, movable in ((None, False), (asked, True)):
        legal = plan(ENDED, requests, movable, ENDED + 40 * DAY, legal_hold=True)
        assert legal["earliest_deletion"] is None and legal["hold"] == retention.LEGAL_HOLD
        assert retention.deletion_words(legal) == "no date while a legal hold applies"
        assert retention.plan_view(legal)["earliest_deletion"] is None
        assert retention.plan_view(legal)["hold_reason"].startswith("Kept under a legal hold")


# ------------------------------------------------------------------------------------------ every channel agrees


def _subscription(db, tenant_id) -> SubscriptionLifecycle:
    return db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one()


class _Mail:
    def __init__(self):
        self.sent = []

    def send_trial_ended(self, recipient, **details):
        self.sent.append(details["delete_on"])

    send_trial_reminder = send_trial_ended


def _channels(user, admin, approval, email, tenant_id) -> dict:
    """The deletion date as each channel gives it (ISO, or the words of the page and the e-mail)."""
    from backend.app import notifications

    business_id = approval["tenant_business_id"]
    status = user.get("/api/v1/trial/status").json()
    (overview,) = [
        row
        for row in admin.get("/api/v1/platform-admin/trials", params={"q": business_id}).json()["items"]
        if row["tenant_id"] == str(tenant_id)
    ]
    (queued,) = [
        row
        for row in admin.get("/api/v1/platform-admin/trial-requests", params={"q": email}).json()["items"]
        if row["tenant_id"] == str(tenant_id)
    ]
    mvp = [
        row["retention"]
        for row in admin.get("/api/v1/platform-admin/mvp-requests").json()["items"]
        if row["tenant_id"] == str(tenant_id)
    ]
    mail = _Mail()
    with SessionLocal() as db:
        bind_system(db, "test: retention channels")
        subscription = _subscription(db, tenant_id)
        notifications._trial_reminder(db, {"subscription_id": str(subscription.id), "stage": "ENDED"}, mail)
        ended_page = trial_end_dates(db, tenant_id)[1]
    return {
        "status": status["data_deleted_at"],
        "status_hold": status["data_hold"],
        "overview": overview["data_deleted_at"],
        "overview_hold": overview["retention"]["hold"],
        "requests_queue": queued["data_delete_after"],
        "mvp_requests": mvp[0]["earliest_deletion"] if mvp else "none",
        "ended_page": ended_page,
        "email": mail.sent[0],
    }


@pytest.mark.db
def test_every_channel_gives_the_same_date_with_grace_and_a_migration_hold_and_none_under_a_legal_hold(monkeypatch):
    user, approval, email = _approved_trial_client()
    # The data may move into the pilot: the sample removed and the organization's own data imported.
    assert user.post("/api/v1/trial/sample-data/removal", json={"confirm": True}).status_code == 200
    own = user.post("/api/v1/trial/imports/complaints", params={"date_column": "none"}, content=OWN_EXPORT)
    assert own.status_code == 200, own.text
    tenant_id = uuid.UUID(approval["tenant_id"])
    asked = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "move_trial_data": True})
    assert asked.status_code == 200, asked.text
    admin = authenticated_client()
    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            bind_system(db, "test: retention channels")
            subscription = _subscription(db, tenant_id)
            # Ended yesterday, in a grace extension of five more days: the effective end is the grace's end.
            subscription.expires_at, subscription.grace_ends_at = now - DAY, now + 5 * DAY
            db.commit()
            end = now + 5 * DAY
        expected = (end + retention.MVP_HOLD_MAX_DAYS * DAY).isoformat()  # held for the open request
        seen = _channels(user, admin, approval, email, tenant_id)
        assert seen == {
            "status": expected,
            "status_hold": "MVP_REQUEST",
            "overview": expected,
            "overview_hold": "MVP_REQUEST",
            "requests_queue": expected,
            "mvp_requests": expected,
            "ended_page": long_moment(datetime.fromisoformat(expected)),
            "email": long_moment(datetime.fromisoformat(expected)),
        }, seen

        # A legal hold: no channel invents a date, every one says why.
        with SessionLocal() as db:
            bind_system(db, "test: retention channels")
            tenant = db.get(Tenant, tenant_id)
            tenant.legal_hold, tenant.legal_hold_reason, tenant.legal_hold_set_at = True, "Test hold", now
            db.commit()
        held = _channels(user, admin, approval, email, tenant_id)
        words = "no date while a legal hold applies"
        assert held == {
            "status": None,
            "status_hold": "LEGAL_HOLD",
            "overview": None,
            "overview_hold": "LEGAL_HOLD",
            "requests_queue": None,
            "mvp_requests": None,
            "ended_page": words,
            "email": words,
        }, held

        # Held data survives the purge job, even a year after the trial ended (only this trial is offered to it).
        with SessionLocal() as db:
            bind_system(db, "test: retention channels")
            subscription = _subscription(db, tenant_id)
            subscription.expires_at, subscription.grace_ends_at = now - 400 * DAY, None
            db.commit()
        real = retention.trials_due
        monkeypatch.setattr(
            retention, "trials_due", lambda db, now=None: [t for t in real(db, now) if t["tenant_id"] == str(tenant_id)]
        )
        with SessionLocal() as db:
            result = retention.run_retention(db, "test")
        mine = [item for item in result["skipped"] if item["tenant_id"] == str(tenant_id)]
        assert [item["why"] for item in mine] == ["LEGAL_HOLD"] and _complaints(tenant_id) == 1
    finally:
        with SessionLocal() as db:
            bind_system(db, "test: retention cleanup")
            db.get(Tenant, tenant_id).legal_hold = False
            db.commit()
        _purge(tenant_id)


@pytest.mark.db
def test_the_purge_job_checks_again_before_it_deletes_and_a_second_run_is_safe(monkeypatch):
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: retention job")
        _subscription(db, tenant_id).expires_at = now - 31 * DAY
        db.commit()
        stale = [item for item in retention.trials_due(db, now) if item["tenant_id"] == str(tenant_id)]
    assert len(stale) == 1 and _complaints(tenant_id) > 0
    # Meanwhile an administrator extends the trial's grace: the list the job read is out of date.
    with SessionLocal() as db:
        bind_system(db, "test: retention job")
        _subscription(db, tenant_id).grace_ends_at = now + 10 * DAY
        db.commit()
    monkeypatch.setattr(retention, "trials_due", lambda db, now=None: stale)
    with SessionLocal() as db:
        result = retention.run_retention(db, "test", now)
    assert result["purged"] == 0 and [item["why"] for item in result["skipped"]] == ["NO_LONGER_DUE"]
    assert _complaints(tenant_id) > 0  # deleted from the stale list before 0.10.86

    # Due again (no grace): deleted, with its evidence; the next run finds nothing more to do.
    with SessionLocal() as db:
        bind_system(db, "test: retention job")
        _subscription(db, tenant_id).grace_ends_at = None
        db.commit()
    with SessionLocal() as db:
        first = retention.run_retention(db, "test", now)
    assert first["purged"] == 1 and first["trials"][0]["status"] == "ARCHIVED"
    assert first["trials"][0]["deleted_records"]["complaints"] > 0 and _complaints(tenant_id) == 0
    with SessionLocal() as db:
        second = retention.run_retention(db, "test", now)
        assert retention.plans(db, now, [tenant_id]) == []  # archived: no deletion date any more
    # The same (stale) list again: the trial is found gone, nothing is deleted twice, nothing fails.
    assert second["purged"] == 0 and second["failed"] == []
    assert [item["why"] for item in second["skipped"]] == ["NO_LONGER_DUE"]
