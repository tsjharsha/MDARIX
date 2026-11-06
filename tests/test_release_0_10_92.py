"""0.10.92 (development cycle 1, step 1) against the database, as the trial user: the fixes only a database proves.

1.1 (call intake D11, H10, C2):

- The sample's clock moves the sample and never a row the organization made: a call logged on a sample product
  hung off that product, so the hourly move re-dated its awareness and times (H10).
- Work on calls stops the clock, as a signed disposition does: a call logged, or a sample contact a person reviewed.
- C2, confirmed and left for step 2: an urgent call's provisional reporting deadline leaves Oversight once its triage
  is completed (strict expected failure, so the fix in step 2 flips it).

1.2 (A2): before the person signs anything, Records has the sample's newest signed record to show.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import Complaint, Hypothesis, Product
from backend.app.db.models.intake import IntakeEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

INTAKE = "/api/v1/intake"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def fresh():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield user, tenant_id
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:sample-clock-own-rows-cleanup")


def _data(tenant_id):
    db = SessionLocal()
    bind_tenant(db, tenant_id)
    return db


def _log(user, **extra) -> dict:
    body = {
        "kind": "CONTACT",
        "reporter_words": "Caller reports the monitor showed 99 percent while the patient looked blue.",
        "answers": {f"Q{n}": {"answer": "NO"} for n in range(1, 10)},
        **extra,
    }
    return _ok(user.post(INTAKE, json=body))


def test_the_clock_moves_the_sample_and_never_a_call_the_organization_logged(fresh):
    from backend.app.trial import sample_clock, sample_removal

    user, tenant_id = fresh
    with _data(tenant_id) as db:
        product = (
            db.query(Product).filter(Product.tenant_id == tenant_id, Product.source_system == "MDARIX_SAMPLE").first()
        )
        assert sample_clock.worked_on(db, tenant_id) is False
        # On a fresh trial the clock moves exactly what it moved before: every row of the sample's story (J2).
        assert sample_removal.plan(db, tenant_id, owned_only=True) == sample_removal.plan(db, tenant_id)
    aware = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=5)
    event = _log(user, product_id=str(product.id), received_at=aware.isoformat(), awareness_at=aware.isoformat())
    with _data(tenant_id) as db:
        mine = db.get(IntakeEvent, uuid.UUID(event["id"]))
        before = (mine.awareness_at, mine.received_at, mine.created_at)
        flagship = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == "SAMPLE-RV-11")
            .one()
        )
        flagship_id, flagship_aware = flagship.id, flagship.awareness_timestamp
        hypothesis = db.query(Hypothesis).filter(Hypothesis.tenant_id == tenant_id).first()
        hypothesis_id, hypothesis_at = hypothesis.id, hypothesis.created_at
        # Logging a call is working on the sample (D11): the hourly job leaves it alone from now on.
        assert sample_clock.worked_on(db, tenant_id) is True
        # The move itself, as the job would make it two hours later: the sample moves, the call stays as written.
        sample_clock.move(db, tenant_id, timedelta(hours=2), 0)
        db.commit()
    with _data(tenant_id) as db:
        mine = db.get(IntakeEvent, uuid.UUID(event["id"]))
        assert (mine.awareness_at, mine.received_at, mine.created_at) == before
        assert db.get(Complaint, flagship_id).awareness_timestamp == flagship_aware + timedelta(hours=2)
        # The sample author's hypotheses are the sample's own and move with it.
        assert db.get(Hypothesis, hypothesis_id).created_at == hypothesis_at + timedelta(hours=2)


def test_a_sample_contact_a_person_reviewed_stops_the_clock(fresh):
    from backend.app.trial import sample_clock

    user, tenant_id = fresh
    call = next(item for item in _ok(user.get(INTAKE))["items"] if item["reference"] == "SAMPLE-CALL-01")
    _ok(
        user.post(
            f"{INTAKE}/{call['id']}/check/review",
            json={"outcome": "AGREED", "note": "Service only: agreed with the sample author.", "password": PASSWORD},
        )
    )
    with _data(tenant_id) as db:
        assert sample_clock.worked_on(db, tenant_id) is True


@pytest.mark.xfail(strict=True, reason="C2: the provisional clock leaves Oversight after triage (step 2, D1)")
def test_an_urgent_calls_provisional_deadline_stays_after_its_triage(fresh):
    user, _tenant_id = fresh
    aware = datetime.now(timezone.utc) - timedelta(hours=2)
    event = _ok(
        user.post(
            INTAKE,
            json={
                "kind": "URGENT",
                "reporter_words": "Service agent reports a patient died during monitoring.",
                "awareness_at": aware.isoformat(),
                "awareness_zone": "America/New_York",
            },
        )
    )

    def provisional() -> list:
        items = _ok(user.get("/api/v1/oversight"))["items"]
        return [item for item in items if item["ref"] == event["reference"] and item["category"] == "REPORTING"]

    assert provisional(), "the urgent call has a provisional deadline in Oversight"
    item = next(entry for entry in _ok(user.get("/api/v1/triage"))["items"] if entry["ref"] == event["reference"])
    me = _ok(user.get("/api/v1/triage"))["people"][0]["id"]
    _ok(
        user.post(
            f"/api/v1/triage/{item['kind']}/{item['id']}/record",
            json={
                "severity": "CATASTROPHIC",
                "event_owner": me,
                "triage_owner": me,
                "immediate_action": "Monitor quarantined for evaluation.",
                "awareness_confirmed_at": item["awareness"]["at"],
            },
        )
    )
    assert provisional(), "C2: the provisional deadline left Oversight once triage was completed"


def test_records_has_the_samples_newest_signed_record_before_the_person_signs_one(fresh):
    user, _tenant_id = fresh
    found = _ok(user.get("/api/v1/oversight/latest-signed"))
    assert found["record"] is None  # the person's own: nothing signed yet
    theirs = found["organization"]
    assert theirs and theirs["signed_at_time"] and theirs["meaning_label"]
    assert theirs["signed_by"] and theirs["signed_by"] != "Signed"
    assert (theirs["complaint"] or theirs["investigation"])["ref"].startswith("SAMPLE-")
