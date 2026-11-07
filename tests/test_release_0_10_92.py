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


def test_the_emdr_contact_email_is_asked_for_before_send_for_approval_and_given_beside_it(fresh):
    """1.5 (A5): the G1 contact office the eMDR file needs holds Send for approval while the report is a draft."""
    from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _reports, _sign_us

    user, _tenant_id = fresh
    complaint = _flagship(user)
    assert _sign_us(user, complaint, "REPORTABLE").status_code == 200
    (report,) = _reports(user, complaint)
    url = f"{REPORTS}/{report['id']}"

    def g1(detail: dict) -> dict:
        return next(item for part in detail["sections"] for item in part["fields"] if item["id"] == "G1")

    # The manufacturer, entered once (D3): G1 reads it, but it has no e-mail.
    given = _ok(user.put(f"{url}/once", json={"values": {"D3": "Orbit Devices, Pune, India"}}))
    assert g1(given)["value"] and g1(given)["ask"] == "CONTACT_EMAIL" and "G1" in given["mandatory"]["missing"]
    refused = user.post(f"{url}/snapshots")
    assert refused.status_code == 422 and "G1" in refused.json()["detail"]["missing"]
    # The e-mail, given beside the field, goes to the responsible party; never over one already there.
    assert user.put(f"{url}/once", json={"contact_email": "x" * 45 + "@example.invalid"}).status_code == 422
    done = _ok(user.put(f"{url}/once", json={"contact_email": "mdr@example.invalid"}))
    assert g1(done)["problem"] is None and "G1" not in done["mandatory"]["missing"]
    assert user.put(f"{url}/once", json={"contact_email": "other@example.invalid"}).status_code == 409
    # The person's own signature is never labelled as the sample's (its dates never move).
    assert _ok(user.get("/api/v1/oversight/latest-signed"))["record"]["sample"] is False
    parties = _ok(user.get("/api/v1/regulatory-reference/responsible-parties"))
    assert [item["contact_email"] for item in parties["parties"] if item["market"] == "US"] == ["mdr@example.invalid"]


def test_the_trend_names_the_supplier_change_behind_its_lots(fresh):
    """1.7 (A10): the OrbitCare 300 Rev B rise shows the change recorded against its pressure sensor."""
    user, _tenant_id = fresh
    items = _ok(user.get("/api/v1/triage/trends"))["items"]
    orbit = next(
        item
        for item in items
        if item["product_version"] and item["name"].startswith("OrbitCare 300") and item["name"].endswith("Rev B")
    )
    assert orbit["lots"] and [change["identifier"] for change in orbit["changes"]] == ["SAMPLE-CHG-014"]
    assert orbit["changes"][0]["change_type"] == "Supplier change" and "NovaSense" in orbit["changes"][0]["title"]
    # Rev A's sensor did not change: no change is shown beside its lots.
    others = [item for item in items if item["name"].startswith("OrbitCare 300") and item["name"].endswith("Rev A")]
    assert others and all(not item["changes"] for item in others)


def test_the_sample_moves_only_overnight_in_whole_days_and_its_times_of_day_never_change(fresh):
    """A1, option C (owner, 7 Nov 2026): never during the day, then by whole days, so a signed time read twice in a
    session reads the same; the sample's signed record says its dates follow the trial's day."""
    from datetime import datetime as moment
    from datetime import time

    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.db.models.stage2 import OnboardingRequest
    from backend.app.oversight.service import calendar_of
    from backend.app.trial import sample_clock

    user, tenant_id = fresh

    def signed_sample():
        with _data(tenant_id) as db:
            row = (
                db.query(ComplaintMarketAssessment)
                .filter(
                    ComplaintMarketAssessment.tenant_id == tenant_id,
                    ComplaintMarketAssessment.source_system == "MDARIX_SAMPLE",
                    ComplaintMarketAssessment.signed_at.isnot(None),
                )
                .order_by(ComplaintMarketAssessment.id)
                .first()
            )
            return row.signed_at

    with _data(tenant_id) as db:
        zone = calendar_of(db, tenant_id).tz
    day = moment.now(zone).date() - timedelta(days=3)
    nine = moment.combine(day, time(9), tzinfo=zone)
    with SessionLocal() as control:
        request = control.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).one()
        request.profile = {**request.profile, sample_clock.ANCHOR: nine.isoformat()}
        control.commit()
    before = signed_sample()

    def keep(at):
        with SessionLocal() as control, _data(tenant_id) as data:
            return sample_clock.keep_current(control, data, tenant_id, now=at)

    # Six hours later the same day: nothing moves (it moved every hour before).
    assert keep(moment.combine(day, time(15), tzinfo=zone)) == {"moved": False, "why": "CURRENT"}
    assert signed_sample() == before
    # Two days later, early in the morning: two whole days, the time of day kept, the anchor moved by the same days.
    done = keep(moment.combine(day + timedelta(days=2), time(1, 30), tzinfo=zone))
    assert done["moved"] and done["by_days"] == 2, done
    assert signed_sample() == before + timedelta(days=2)
    with SessionLocal() as control:
        request = control.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).one()
        assert moment.fromisoformat(request.profile[sample_clock.ANCHOR]) == nine + timedelta(days=2)
    # The sample's signed record says so; Records shows it on the organization's latest signed record.
    assert _ok(user.get("/api/v1/oversight/latest-signed"))["organization"]["sample"] is True
