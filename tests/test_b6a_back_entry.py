"""B6a Part A, G18b/c (B6-07..B6-09): back-entry after an outage. Entered more than 24 h after Received needs a
late-entry reason (just under 24 h needs none; owner, 11 Nov: Received, not awareness); the reason is stored, audited and shown; the clock counts from awareness, so a back-entered
Case can be overdue at once; possible duplicates (a complaint, an e-mail to check) are found before saving; another
organization's records are never offered; switched off, today's behaviour."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.data_plane import open_tenant_data_session
from backend.app.db.models.foundation import AuditEvent, Complaint, LotBatch
from backend.app.db.models.intake import InboundMessage
from backend.app.db.session import SessionLocal
from tests.test_free_trial import _approved_trial_client

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.db, pytest.mark.requirement("B6-07", "B6-08", "B6-09")]

INTAKE = "/api/v1/intake"
WORDS = "Caller reports the pump alarmed twice during the night shift."


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b6a-back-entry-cleanup")


def _contact(user, hours_ago: float, **extra):
    received = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).replace(tzinfo=None, microsecond=0)
    body = {"kind": "CONTACT", "reporter_words": WORDS, "received_at": received.isoformat(), "received_zone": "UTC"}
    return user.post(INTAKE, json={**body, **extra})


def test_more_than_24_hours_after_received_needs_a_reason(trial):  # B6-07 (owner, 11 Nov: from Received)
    user = trial["user"]
    within = _contact(user, 23.9)
    assert within.status_code == 200, within.text
    assert within.json()["late_entry_reason"] is None
    refused = _contact(user, 24.1)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "LATE_ENTRY_REASON_NEEDED"
    assert _contact(user, 25, late_entry_reason="outage").status_code == 422  # under 10 characters


def test_a_call_logged_as_it_arrives_is_not_late_though_a_distributor_knew_days_before(trial):  # B6-07, B6-08
    knew = (datetime.now(timezone.utc) - timedelta(days=3)).replace(tzinfo=None, microsecond=0)
    saved = _contact(
        trial["user"],
        0.1,
        first_knowledge_at=knew.isoformat(),
        first_knowledge_zone="UTC",
        first_knowledge_basis="ACTS_FOR_MANUFACTURER",
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["late_entry_reason"] is None
    # The clock still counts from awareness: the distributor's knowledge three days ago.
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.intake.service import event_awareness

    with open_tenant_data_session(trial["tenant_id"]) as data:
        event = data.get(IntakeEvent, uuid.UUID(saved.json()["id"]))
        aware = event_awareness(event, None)["at"]
    assert abs(aware - knew.replace(tzinfo=timezone.utc)) < timedelta(seconds=1)


def test_the_reason_is_stored_audited_and_shown(trial):  # B6-07
    reason = "MDARIX unavailable 10:00-14:00; entered from manual log row 3"
    saved = _contact(trial["user"], 25, late_entry_reason=reason)
    assert saved.status_code == 200, saved.text
    case = saved.json()
    assert case["late_entry_reason"] == reason
    assert trial["user"].get(f"{INTAKE}/{case['id']}").json()["late_entry_reason"] == reason
    with open_tenant_data_session(trial["tenant_id"]) as data:
        (event,) = data.query(AuditEvent).filter(
            AuditEvent.tenant_id == trial["tenant_id"],
            AuditEvent.action == "INTAKE_LOGGED",
            AuditEvent.entity_id == uuid.UUID(case["id"]),
        )
    assert event.details["late_entry_reason"] == reason


def test_the_clock_counts_from_awareness_never_from_entry(trial):  # B6-08
    aware = datetime.now(timezone.utc) - timedelta(days=60)
    saved = trial["user"].post(
        INTAKE,
        json={
            "kind": "URGENT",
            "reporter_words": "Service agent reports a patient burned by the warming plate.",
            "awareness_at": aware.isoformat(),
            "awareness_zone": "UTC",
            "late_entry_reason": "Paper log from the outage on the weekend, row 7",
        },
    )
    assert saved.status_code == 200, saved.text
    ref = saved.json()["reference"]
    items = {item["ref"]: item for item in trial["user"].get("/api/v1/triage").json()["items"]}
    item = items[ref]
    assert abs(datetime.fromisoformat(item["awareness"]["at"]) - aware) < timedelta(seconds=1)
    # The reporting deadline counts from awareness 60 days ago: overdue at once, though the Case was entered now.
    assert item["deadlines"] and datetime.fromisoformat(item["deadlines"][0]["due_at"]) < datetime.now(timezone.utc)


def _sample_complaint(tenant_id):
    with open_tenant_data_session(tenant_id) as data:
        row = (
            data.query(Complaint, LotBatch.lot_identifier)
            .join(LotBatch, LotBatch.id == Complaint.lot_batch_id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.product_id.isnot(None), Complaint.country.isnot(None))
            .filter(Complaint.event_timestamp.isnot(None))
            .first()
        )
        complaint, lot = row
        return {
            "id": str(complaint.id),
            "product_id": str(complaint.product_id),
            "lot": lot,
            "country": complaint.country,
            "event_on": complaint.event_timestamp.date().isoformat(),
        }


def test_possible_duplicates_before_saving_a_back_entry(trial, monkeypatch):  # B6-09
    monkeypatch.setenv("MDARIX_EMAIL_INTAKE", "on")  # e-mails to check are compared only while intake is on
    user = trial["user"]
    known = _sample_complaint(trial["tenant_id"])
    query = {key: known[key] for key in ("product_id", "lot", "country", "event_on")}
    found = user.get(f"{INTAKE}/possible-duplicates", params=query)
    assert found.status_code == 200, found.text
    hits = {(hit["kind"], hit["id"]) for hit in found.json()["items"]}
    assert ("COMPLAINT", known["id"]) in hits
    # Another lot: not this complaint.
    other_lot = user.get(f"{INTAKE}/possible-duplicates", params={**query, "lot": "NO-SUCH-LOT"}).json()["items"]
    assert known["id"] not in {hit["id"] for hit in other_lot}
    # An e-mail to check that names the product and lot, from the caller's site, received meanwhile.
    now = datetime.now(timezone.utc)
    with open_tenant_data_session(trial["tenant_id"]) as data:
        message_id = uuid.uuid4()
        message = InboundMessage(
            id=message_id,
            tenant_id=trial["tenant_id"],
            message_id=f"<b6a-{uuid.uuid4().hex}@example.invalid>",
            subject_masked="Pump alarm",
            from_domain="example.invalid",
            received_at=now,
            created_at=now,
            state="NEW",
            draft={
                "words": "The pump alarmed",
                "identifiers": {
                    "product": {"id": known["product_id"], "text": "pump"},
                    "lot": {"text": known["lot"]},
                },
                "site": {"text": "City Hospital Pune"},
            },
        )
        data.add(message)
        data.commit()
    by_site = user.get(f"{INTAKE}/possible-duplicates", params={**query, "site": "City Hospital Pune"}).json()["items"]
    assert ("EMAIL", str(message_id)) in {(hit["kind"], hit["id"]) for hit in by_site}
    # Another organization is never offered this organization's records.
    other, approval, _ = _approved_trial_client()
    try:
        theirs = other.get(f"{INTAKE}/possible-duplicates", params={**query, "site": "City Hospital Pune"}).json()
        assert not {hit["id"] for hit in theirs["items"]} & {known["id"], str(message_id)}
    finally:
        from backend.app.trial.retention import purge_trial

        with SessionLocal() as db:
            purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:b6a-back-entry-other")


def test_the_switch_off_on_off(trial, monkeypatch):  # B6-46
    user = trial["user"]
    known = _sample_complaint(trial["tenant_id"])
    for state in ("off", "on", "off"):
        monkeypatch.setenv("MDARIX_B6_LATE_ENTRY", state)
        on = state == "on"
        assert (_contact(user, 30).status_code == 422) is on  # off: no reason asked (today's behaviour)
        found = user.get(f"{INTAKE}/possible-duplicates", params={"product_id": known["product_id"]})
        assert found.status_code == (200 if on else 404)
        assert user.get("/api/v1/session/context").json()["b6"]["late_entry"] is on


def test_possible_duplicates_needs_a_role_and_takes_the_lots_product(trial):  # review findings 1, 7
    from tests.test_reporting_capa_api import _client

    known = _sample_complaint(trial["tenant_id"])
    viewer = _client(trial["tenant_id"], "VIEWER")
    assert viewer.get(f"{INTAKE}/possible-duplicates", params={"product_id": known["product_id"]}).status_code == 403
    by_lot = trial["user"].get(
        f"{INTAKE}/possible-duplicates", params={k: known[k] for k in ("lot", "country", "event_on")}
    )
    assert by_lot.status_code == 200 and known["id"] in {hit["id"] for hit in by_lot.json()["items"]}


def test_the_late_entry_reason_is_masked(trial):  # review finding 2
    saved = _contact(trial["user"], 30, late_entry_reason="Paper log kept by jane.doe@example.com during the outage")
    assert saved.status_code == 200, saved.text
    assert "jane.doe@example.com" not in (saved.json()["late_entry_reason"] or "")
