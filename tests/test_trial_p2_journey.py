"""The trial journey fixes of 0.10.32 from the final pre-launch review.

- FUN-05: a request to move the trial data into the MVP holds the trial's deletion while it is open (with an audit
  record, the hold shown to the Platform Administrator and the MDARIX team alerted before the dates), resumes it after
  a grace period once closed, and never holds longer than its cap; without a request to move, or with data that cannot
  move, nothing is held (backend/app/trial/retention.py).
- FUN-08 / UX-24: the trial's row allowance counts the rows of the file, in the check, its message and the "used"
  figure (backend/app/trial/imports.py).
- UX-11: the sample signal's chart counts its own complaints and its related records name the supplier change.
- UX-20: the sample CAPA follows the sample case and is not overdue.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, text

from backend.app import alerts
from backend.app.db.models.foundation import Capa
from backend.app.db.models.reviews import DecisionBriefVersion
from backend.app.db.models.stage2 import SubscriptionLifecycle, TrialMvpRequest
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from backend.app.trial import retention
from tests.conftest import authenticated_client
from tests.test_free_trial import _approved_trial_client, _clean_trial_workspaces  # noqa: F401 (module fixture)

EXPECTATIONS = "Find hidden complaints across our two infusion pump lines and show CAPA effectiveness."
OWN_EXPORT = (
    "Complaint Number,Product Code,Product Name,Complaint Description,Lot #,Status\n"
    "HOLD-0001,HOLD-PUMP,Own Pump,Display flickers at start-up,HOLD-LOT-1,Open\n"
)
DAY = timedelta(days=1)


def _own_data_trial():
    """A trial whose data may move into the MVP: the sample data removed and its own data imported."""
    user, approval, _email = _approved_trial_client()
    removed = user.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
    assert removed.status_code == 200, removed.text
    imported = user.post("/api/v1/trial/imports/complaints", content=OWN_EXPORT)
    assert imported.status_code == 200, imported.text
    return user, approval


def _end_trial(tenant_id, days_ago: int) -> None:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one().expires_at = (
            datetime.now(timezone.utc) - days_ago * DAY
        )
        db.commit()
    finally:
        db.close()


def _audited(tenant_id, action: str) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM audit_events WHERE tenant_id = :t AND action = :a"),
            {"t": str(tenant_id), "a": action},
        ).scalar()


def _complaints(tenant_id) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM complaints WHERE tenant_id = :t"), {"t": str(tenant_id)}
        ).scalar()


def _purge(*tenant_ids) -> None:
    for tenant_id in tenant_ids:
        db = SessionLocal()
        try:
            retention.purge_trial(db, tenant_id, "test")
        finally:
            db.close()


def _due(tenant_id, now=None) -> list[dict]:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        return [trial for trial in retention.trials_due(db, now) if trial["tenant_id"] == str(tenant_id)]
    finally:
        db.close()


# ------------------------------------------------------------------------------------------- FUN-05


def test_the_plan_of_a_held_trial_its_grace_and_its_cap():
    ended = datetime(2026, 10, 20, tzinfo=timezone.utc)
    original, cap = ended + 30 * DAY, ended + retention.MVP_HOLD_MAX_DAYS * DAY
    asked = {"open": SimpleNamespace(id=uuid.uuid4(), status="NEW"), "closed_at": None}

    # No request, or one whose data cannot move: deleted 30 days after the trial.
    assert retention.retention_plan(ended, None, False, ended + 40 * DAY)["delete_after"] == original
    unmovable = retention.retention_plan(ended, asked, False, ended + 40 * DAY)
    assert unmovable["mvp_request"] is None and unmovable["delete_after"] == original
    # Held while the request is open: not before the hold ends.
    held = retention.retention_plan(ended, asked, True, ended + 40 * DAY)
    assert held["mvp_request"] is asked["open"] and held["delete_after"] == cap
    assert held["original_delete_after"] == original and held["hold_until"] == cap
    # Never past the cap, request open or not.
    capped = retention.retention_plan(ended, asked, True, cap + DAY)
    assert capped["mvp_request"] is None and capped["delete_after"] == original
    # Closed: a fresh grace period, never past the cap, never before the normal date.
    closed = ended + 40 * DAY
    grace = retention.MVP_HOLD_GRACE_DAYS * DAY
    assert retention.retention_plan(ended, {"open": None, "closed_at": closed}, False, closed)["delete_after"] == (
        closed + grace
    )
    late = cap - 3 * DAY
    assert retention.retention_plan(ended, {"open": None, "closed_at": late}, False, late)["delete_after"] == cap
    early = ended - 5 * DAY
    assert retention.retention_plan(ended, {"open": None, "closed_at": early}, False, ended)["delete_after"] == original


def test_a_request_to_move_the_data_holds_its_deletion_with_an_audit_record_and_an_alert(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_alert", lambda subject, body: sent.append((subject, body)) or {})
    user, approval = _own_data_trial()
    tenant_id = uuid.UUID(approval["tenant_id"])
    asked = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "move_trial_data": True})
    assert asked.status_code == 200, asked.text
    _end_trial(tenant_id, 31)
    admin = authenticated_client()
    try:
        preview = admin.get("/api/v1/platform-admin/trial-retention").json()
        assert preview["mvp_hold"] == {"max_days": 90, "grace_days": 14, "alert_days": 7}
        (trial,) = [item for item in preview["due"] if item["tenant_id"] == str(tenant_id)]
        ended = datetime.fromisoformat(trial["trial_ended_at"])
        assert trial["held_for_mvp_request"] is True and trial["legal_hold"] is False
        assert trial["mvp_request"] == {"id": asked.json()["request"]["id"], "status": "NEW"}
        assert datetime.fromisoformat(trial["original_delete_after"]) == ended + 30 * DAY
        assert datetime.fromisoformat(trial["delete_after"]) == ended + 90 * DAY

        # The run keeps it and says so in the trial's own trail. Only this trial is offered to the run, so other
        # tests' trials in the shared database are not touched.
        monkeypatch.setattr(retention, "trials_due", lambda db, now=None: [trial])
        db = SessionLocal()
        try:
            result = retention.run_retention(db, "test")
        finally:
            db.close()
        assert result["purged"] == 0 and [item["why"] for item in result["skipped"]] == ["MVP_REQUEST"]
        assert _audited(tenant_id, "TRIAL_RETENTION_SKIPPED_MVP_REQUEST") == 1
        assert _complaints(tenant_id) == 1

        # The MDARIX team is alerted once that the data is held past its normal date.
        mine = [body for _subject, body in sent if approval["tenant_business_id"] in body]
        assert len(mine) == 1 and "would be deleted on" in mine[0] and "Own Pump" not in mine[0]
        assert _audited(tenant_id, retention.HOLD_ALERTED) == 1
        db = SessionLocal()
        try:
            retention.alert_holds(db, "test")
        finally:
            db.close()
        assert len([body for _subject, body in sent if approval["tenant_business_id"] in body]) == 1

        # Platform Admin sees the hold in the trials overview and beside the MVP request.
        listed = admin.get("/api/v1/platform-admin/trials", params={"q": approval["tenant_business_id"]}).json()
        (item,) = [row for row in listed["items"] if row["tenant_id"] == str(tenant_id)]
        assert item["retention"]["held_for_mvp_request"] is True
        assert item["data_deleted_at"] == trial["delete_after"]
        requests = admin.get("/api/v1/platform-admin/mvp-requests").json()["items"]
        (request,) = [row for row in requests if row["tenant_id"] == str(tenant_id)]
        assert request["retention"]["held_for_mvp_request"] is True
        assert request["retention"]["hold_until"] == trial["hold_until"]
    finally:
        _purge(tenant_id)


def test_closing_the_request_resumes_deletion_after_a_grace_period_and_the_hold_is_capped(monkeypatch):
    monkeypatch.setattr(alerts, "send_alert", lambda subject, body: {})
    user, approval = _own_data_trial()
    tenant_id = uuid.UUID(approval["tenant_id"])
    asked = user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS, "move_trial_data": True})
    assert asked.status_code == 200, asked.text
    _end_trial(tenant_id, 31)
    admin = authenticated_client()
    path = f"/api/v1/platform-admin/mvp-requests/{asked.json()['request']['id']}/status"
    try:
        (held,) = _due(tenant_id)
        ended = datetime.fromisoformat(held["trial_ended_at"])
        assert admin.post(path, json={"status": "CLOSED"}).status_code == 200

        # Not deleted the same night: the normal schedule resumes after the grace period.
        now = datetime.now(timezone.utc)
        assert _due(tenant_id, now) == []
        (resumed,) = _due(tenant_id, now + (retention.MVP_HOLD_GRACE_DAYS * DAY) + timedelta(hours=1))
        assert resumed["held_for_mvp_request"] is False
        resume_at = datetime.fromisoformat(resumed["delete_after"])
        assert now + 13 * DAY < resume_at <= now + 14 * DAY + timedelta(minutes=5)

        # Open again: held again, but never past the cap, and the team is told before the hold ends.
        assert admin.post(path, json={"status": "NEW"}).status_code == 200
        assert _due(tenant_id)[0]["held_for_mvp_request"] is True
        (capped,) = _due(tenant_id, ended + 90 * DAY + timedelta(hours=1))
        assert capped["held_for_mvp_request"] is False
        db = SessionLocal()
        bind_system(db, "test")
        try:
            soon = retention.holds_to_alert(db, ended + 87 * DAY)
        finally:
            db.close()
        stages = {item["stage"] for item in soon if item["plan"]["tenant"].id == tenant_id}
        assert retention.ALERT_BEFORE_HOLD_ENDS in stages
    finally:
        _purge(tenant_id)


def test_nothing_is_held_without_a_request_to_move_the_data_or_with_data_that_cannot_move():
    # (a) An MVP conversation asked for without moving the data.
    user, approval, _email = _approved_trial_client()
    plain = uuid.UUID(approval["tenant_id"])
    assert user.post("/api/v1/trial/mvp-request", json={"expectations": EXPECTATIONS}).status_code == 200
    # (b) A request that says to move the data while the sample data is still there (written past the screen's and
    # the server's check): the data cannot move, so it is not held.
    _other, other_approval, _ = _approved_trial_client()
    unmovable = uuid.UUID(other_approval["tenant_id"])
    db = SessionLocal()
    bind_system(db, "test")
    now = datetime.now(timezone.utc)
    db.add(
        TrialMvpRequest(
            id=uuid.uuid4(),
            tenant_id=unmovable,
            requested_by=uuid.uuid4(),
            display_name="Test",
            email="test@example.invalid",
            organization="Trial Devices Inc",
            expectations=EXPECTATIONS,
            move_trial_data=True,
            status="NEW",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    db.close()
    for tenant_id in (plain, unmovable):
        _end_trial(tenant_id, 31)
    try:
        for tenant_id in (plain, unmovable):
            (trial,) = _due(tenant_id)
            assert trial["held_for_mvp_request"] is False and trial["mvp_request"] is None
            assert trial["delete_after"] == trial["original_delete_after"]
    finally:
        _purge(plain, unmovable)


# ------------------------------------------------------------------------------------------- FUN-08 / UX-24


def _complaints_csv(rows: int, products: int = 2) -> str:
    lines = ["complaint_id,product_id,product_name,description"]
    lines += [
        f"ROW-{number:05d},ROW-PUMP-{number % products},Row Pump {number % products},Pressure alarm during infusion"
        for number in range(rows)
    ]
    return "\n".join(lines) + "\n"


def test_the_row_allowance_counts_the_rows_of_the_file():
    user, approval, _email = _approved_trial_client()
    check = "/api/v1/trial/imports/complaints/check"

    # Exactly 5,000 rows fit, although the file also names 2 products.
    full = user.post(check, content=_complaints_csv(5000)).json()
    assert full["ready"], full["issues"]
    assert full["new_rows"] == 5000 and full["also_creates"] == {"products": 2} and full["new_records"] == 5002
    # One more does not, and the message counts rows, with thousands separators.
    over = user.post(check, content=_complaints_csv(5001)).json()
    assert not over["ready"]
    assert "This file adds 5,001 rows; your trial has 5,000 of 5,000 rows left." in [
        issue["message"] for issue in over["issues"]
    ]

    # Six rows naming a product, a version and three lots use 6 of the 5,000.
    six = "complaint_id,product_id,product_name,version,lot_id,description\n" + "".join(
        f"SIX-{number},SIX-PUMP,Six Pump,Rev A,SIX-LOT-{number % 3},Pressure alarm during infusion\n"
        for number in range(6)
    )
    checked = user.post(check, content=six).json()
    assert checked["ready"] and checked["new_rows"] == 6 and checked["new_records"] == 11
    assert user.post("/api/v1/trial/imports/complaints", content=six).status_code == 200
    assert user.get("/api/v1/trial/status").json()["usage"]["rows"] == 6
    assert user.post(check, content=_complaints_csv(1)).json()["rows_used"] == 6
    # Uploading the same rows again updates them: nothing more is used.
    again = user.post(check, content=six).json()
    assert again["ready"] and again["new_rows"] == 0 and again["updated_records"] == 6
    # Platform Admin sees the same figure.
    listed = (
        authenticated_client().get("/api/v1/platform-admin/trials", params={"q": approval["tenant_business_id"]}).json()
    )
    (item,) = [row for row in listed["items"] if row["tenant_id"] == approval["tenant_id"]]
    assert item["rows"]["used"] == 6


# ------------------------------------------------------------------------------------------- UX-11 and UX-20


def test_the_sample_signal_counts_its_own_complaints_and_names_the_supplier_change():
    user, _approval, _email = _approved_trial_client()
    signals = user.get("/api/v1/triage/signals", params={"status": "OPEN"})
    assert signals.status_code == 200, signals.text
    (orbit,) = [item for item in signals.json()["items"] if "OrbitCare" in str(item.get("title"))]
    detail = user.get(f"/api/v1/triage/signals/{orbit['id']}").json()
    assert (
        sum(row["count"] for row in detail["version_split"]) == detail["complaint_count"] == len(detail["complaints"])
    )
    assert "SAMPLE-CHG-014" in [change["identifier"] for change in detail["related"]["changes"]]


def test_the_sample_capa_follows_the_sample_case_and_is_not_overdue():
    _user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    bind_system(db, "test")
    try:
        capa = db.query(Capa).filter(Capa.tenant_id == tenant_id, Capa.capa_identifier == "SAMPLE-CAPA-02").one()
        submitted = (
            db.query(func.max(DecisionBriefVersion.submitted_at))
            .filter(DecisionBriefVersion.tenant_id == tenant_id)
            .scalar()
        )
        ends = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one().expires_at
    finally:
        db.close()
    # Opened after the sample brief was written, due after the trial, its check after the action is due.
    assert submitted is not None and capa.opened_at >= submitted
    assert capa.due_at > ends and capa.effectiveness_check_at > capa.due_at
    assert capa.status == "Open"
