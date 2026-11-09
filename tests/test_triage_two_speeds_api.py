"""0.10.93 (B2) step 3 through the API, as the trial user, with migration tr19: triage at two speeds (TR-xx), the
acknowledgement of a fast-track item and its escalation by the alert sweep (A1, B2-04), delivery tracking of alerts
(A2, B2-02, B2-03) and the downgrade of a fast-track triage only with a second person (A6, B2-05).

The tests run in order on one trial: the ones with a second person come last (a backup is then required)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, SignedApprovalRecord
from backend.app.db.models.intake import TriageRecord, TriageRecordVersion
from backend.app.db.models.oversight import DueAlert
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.oversight import service as oversight
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_intake_triage_api import INTAKE, TRIAGE, _all_no, _ok, _sign

pytestmark = pytest.mark.db

WORDS = "Clinic reports the infusion pump stopped mid-dose and restarted on its own."


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    me = _ok(user.get(TRIAGE))["people"][0]["id"]
    try:
        yield {"user": user, "tenant_id": tenant_id, "me": me, "approval": approval}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:triage-two-speeds-cleanup")


def _log(user, **extra) -> dict:
    return _ok(user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": WORDS, "answers": _all_no(), **extra}))


def _find(user, member: str) -> dict | None:
    items = _ok(user.get(TRIAGE, params={"show": "all"}))["items"]
    return next((item for item in items if member in item["members"]), None)


def _url(item: dict, action: str = "record") -> str:
    return f"{TRIAGE}/{item['kind']}/{item['id']}/{action}"


def _seen(item: dict) -> int:
    return item["record"]["version"] if item["record"] else 0


def _save(user, item: dict, me: str, **body):
    payload = {
        "severity": "SERIOUS",
        "event_owner": me,
        "triage_owner": me,
        "immediate_action": "Pump taken out of use at the clinic.",
        "containment": ["OUT_OF_USE"],
        "seen_version": _seen(item),
        **body,
    }
    return user.post(_url(item), json=payload)


def _actions(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        return db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action).all()


def _versions(tenant_id, subject_id) -> list[TriageRecordVersion]:
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        record = db.query(TriageRecord).filter(TriageRecord.subject_id == uuid.UUID(str(subject_id))).one()
        return (
            db.query(TriageRecordVersion)
            .filter(TriageRecordVersion.tenant_id == tenant_id, TriageRecordVersion.triage_record_id == record.id)
            .order_by(TriageRecordVersion.version)
            .all()
        )


def test_a_complaint_without_harm_is_routine_and_confirmed_in_one_click(trial):  # TR-25, TR-13, spec 4.7
    user, me = trial["user"], trial["me"]
    signed = _ok(_sign(user, _log(user, answers=_all_no(Q2="YES")), "COMPLAINT"))
    item = _find(user, f"COMPLAINT:{signed['complaint_id']}")
    assert item["speed"] == "ROUTINE" and item["speed_label"] == "Routine triage"
    assert item["routine_prefill"]["triage_owner"] == me  # the Case's signer, a fact (T-D12)
    assert item["routine_prefill"]["harm_now_label"] == "No health consequence"
    assert not item["acknowledgement"]["required"]
    done = _ok(user.post(_url(item, "confirm"), json={"seen_version": _seen(item)}))
    row = next(entry for entry in done["items"] if f"COMPLAINT:{signed['complaint_id']}" in entry["members"])
    assert row["record"]["completed_at"] and row["record"]["severity"] == "NEGLIGIBLE"
    assert row["record"]["containment"]["choices"] == ["NONE_NEEDED"]
    assert [v.version for v in _versions(trial["tenant_id"], signed["complaint_id"])] == [1]
    assert _actions(trial["tenant_id"], "TRIAGE_ROUTINE_CONFIRMED")


def test_an_urgent_case_is_fast_and_waits_for_a_named_acknowledgement(trial):  # TR-28, A1
    user, me = trial["user"], trial["me"]
    aware = datetime.now(timezone.utc) - timedelta(minutes=10)
    event = _ok(
        user.post(
            INTAKE,
            json={"kind": "URGENT", "reporter_words": WORDS, "awareness_at": aware.isoformat()},
        )
    )
    item = _find(user, f"INTAKE:{event['id']}")
    assert item["speed"] == "FAST" and item["triage_clock"]["target_hours"] == 4
    assert item["acknowledgement"]["required"] and not item["acknowledgement"]["done"]
    reached = datetime.fromisoformat(item["triage_clock"]["from"])  # the target counts from reaching triage
    assert datetime.fromisoformat(item["acknowledgement"]["due_at"]) == reached + timedelta(hours=1)
    assert user.post(_url(item, "confirm"), json={}).status_code == 409  # fast is never one click
    done = _ok(user.post(_url(item, "acknowledge")))
    row = next(entry for entry in done["items"] if entry["id"] == item["id"])
    assert row["acknowledgement"]["done"] and row["record"]["triage_owner"] == me
    assert row["record"]["completed_at"] is None  # acknowledged is not triaged
    assert _actions(trial["tenant_id"], "TRIAGE_ACKNOWLEDGED")


def test_an_unacknowledged_fast_item_becomes_overdue_and_reaches_the_escalation_role(trial):  # B2-04, A1, A2
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="UNKNOWN"))
    item = _find(user, f"INTAKE:{event['id']}")
    assert item["speed"] == "FAST" and "not known" in item["speed_why"]
    later = datetime.fromisoformat(item["acknowledgement"]["due_at"]) + timedelta(minutes=1)
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        oversight.sweep(db, db, tenant_id, later)
        db.commit()
        alerts = (
            db.query(DueAlert).filter(DueAlert.tenant_id == tenant_id, DueAlert.item_key == f"ack:{item['key']}").all()
        )
    escalation = [alert for alert in alerts if alert.tier == "ESCALATION"]
    assert escalation and escalation[0].recipient_id == me  # the trial's Leader: the escalation role
    assert escalation[0].delivery == "DELIVERED" and escalation[0].attempts == 1 and escalation[0].channel == "IN_APP"
    assert any(row.details["item"] == f"ack:{item['key']}" for row in _actions(tenant_id, "DUE_ITEM_ESCALATED"))


def test_a_failed_notification_keeps_the_escalation_and_a_retry_never_duplicates_it(trial, monkeypatch):  # B2-02/03
    user, tenant_id = trial["user"], trial["tenant_id"]
    event = _log(user, answers=_all_no(Q2="YES", Q5="UNKNOWN"))
    item = _find(user, f"INTAKE:{event['id']}")
    later = datetime.fromisoformat(item["acknowledgement"]["due_at"]) + timedelta(minutes=1)
    key = f"ack:{item['key']}"

    def broken(alert, now):
        raise ConnectionError("channel down")

    monkeypatch.setattr(oversight, "deliver", broken)
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        oversight.sweep(db, db, tenant_id, later)
        db.commit()
        failed = db.query(DueAlert).filter(DueAlert.tenant_id == tenant_id, DueAlert.item_key == key).all()
        assert failed and all(a.delivery == "RETRYING" and a.resolved_at is None for a in failed)
        assert "channel down" in failed[0].delivery_error
    assert any(row.details["item"] == key for row in _actions(tenant_id, "ALERT_DELIVERY_FAILED"))
    assert any(row.details["item"] == key for row in _actions(tenant_id, "DUE_ITEM_ESCALATED"))
    monkeypatch.undo()
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        oversight.sweep(db, db, tenant_id, later + timedelta(minutes=15))
        db.commit()
        again = db.query(DueAlert).filter(DueAlert.tenant_id == tenant_id, DueAlert.item_key == key).all()
    assert len(again) == len(failed)  # the same alerts, retried
    assert all(a.delivery == "DELIVERED" and a.attempts == 2 and a.delivery_error is None for a in again)


def test_not_known_yet_opens_a_follow_up_and_containment_opens_its_tasks(trial):  # TR-01, TR-29, T-D11
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="UNKNOWN"))
    item = _find(user, f"INTAKE:{event['id']}")
    _ok(_save(user, item, me, severity="NOT_KNOWN", containment=["HOLD_LOT", "FIELD_ACTION"]))
    after = _find(user, f"INTAKE:{event['id']}")
    assert after["speed"] == "FAST" and after["record"]["severity"] == "NOT_KNOWN"
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        types = {
            task.task_type
            for task in db.query(WorkflowTask).filter(
                WorkflowTask.tenant_id == tenant_id, WorkflowTask.source_entity_id == uuid.UUID(after["record"]["id"])
            )
        }
    assert types == {"TRIAGE_HARM_FOLLOW_UP", "LOT_HOLD", "FIELD_ACTION_DECISION"}
    assert len(_actions(tenant_id, "CONTAINMENT_TASK_OPENED")) >= 2


def test_an_update_is_a_new_version_with_a_reason_and_a_stale_save_is_refused(trial):  # TR-02, TR-03, TR-10, TR-24
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q5="YES"))
    item = _find(user, f"INTAKE:{event['id']}")
    assert (
        item["severity_floor"] == "SERIOUS" and item["floor_note"] == "At least Serious: a serious injury is recorded"
    )
    below = _save(user, item, me, severity="MINOR")
    assert below.status_code == 422 and below.json()["detail"]["code"] == "BELOW_FLOOR"
    _ok(_save(user, item, me, severity="SERIOUS"))
    saved = _find(user, f"INTAKE:{event['id']}")
    no_reason = _save(user, saved, me, severity="CRITICAL")
    assert no_reason.status_code == 422 and no_reason.json()["detail"]["code"] == "CHANGE_REASON_NEEDED"
    _ok(_save(user, saved, me, severity="CRITICAL", change_reason="The nurse called back: a second operation."))
    stale = _save(user, saved, me, severity="CRITICAL", change_reason="Saved from an old screen, a moment later.")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "TRIAGE_CHANGED"
    versions = _versions(tenant_id, event["id"])
    assert [v.version for v in versions] == [1, 2]
    assert versions[1].changed_fields["severity"] == {"old": "SERIOUS", "new": "CRITICAL"}
    assert versions[1].change_reason.startswith("The nurse")
    shown = _ok(user.get(_url(saved, "versions")))["items"]
    assert [entry["version"] for entry in shown] == [1, 2]


def test_a_downgrade_in_a_one_person_trial_is_signed(trial):  # A6 in the trial, TR-17
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    item = _find(user, f"INTAKE:{event['id']}")
    _ok(_save(user, item, me, severity="SERIOUS"))
    saved = _find(user, f"INTAKE:{event['id']}")
    body = {"severity": "MINOR", "change_reason": "Physician confirmed a bruise, no lasting harm."}
    unsigned = _save(user, saved, me, **body)
    assert unsigned.status_code == 422 and unsigned.json()["detail"]["code"] == "SIGNATURE_NEEDED"
    _ok(_save(user, saved, me, **body, password=PASSWORD))
    recorded = [row for row in _actions(tenant_id, "TRIAGE_RECORDED") if row.details.get("severity") == "MINOR"]
    assert recorded and recorded[-1].details["one_person"] and recorded[-1].details["signature_id"]
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        signature = db.get(SignedApprovalRecord, uuid.UUID(recorded[-1].details["signature_id"]))
        assert signature.decision_type == "TRIAGE_DOWNGRADE" and "one person" in signature.signature_meaning


def test_new_harm_reopens_a_finished_triage_on_the_fast_track(trial):  # TR-11, TR-19, T-D7
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="UNKNOWN"))
    item = _find(user, f"INTAKE:{event['id']}")
    _ok(_save(user, item, me, severity="MINOR"))
    assert _find(user, f"INTAKE:{event['id']}")["record"]["completed_at"]
    _ok(user.put(f"{INTAKE}/{event['id']}/check", json={"answers": _all_no(Q2="YES", Q5="YES"), "seen_version": 1}))
    reopened = _find(user, f"INTAKE:{event['id']}")
    assert reopened["record"]["completed_at"] is None and reopened["record"]["reopen_trigger"] == "SERIOUS_INJURY"
    assert reopened["speed"] == "FAST" and not reopened["acknowledgement"]["done"]
    assert any(row.details["trigger"] == "SERIOUS_INJURY" for row in _actions(tenant_id, "TRIAGE_REOPENED"))


def test_a_case_triaged_before_signing_hands_its_triage_to_the_complaint(trial):  # T-D8, TR-33
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    _ok(_save(user, _find(user, f"INTAKE:{event['id']}"), me, severity="MINOR"))
    signed = _ok(_sign(user, _ok(user.get(f"{INTAKE}/{event['id']}")), "COMPLAINT"))
    with SessionLocal() as db:
        bind_system(db, "test:triage-two-speeds")
        copy = db.query(TriageRecord).filter(TriageRecord.subject_id == uuid.UUID(signed["complaint_id"])).one()
        assert copy.inherited_from is not None and copy.completed_at is not None and copy.severity == "MINOR"
    assert _actions(tenant_id, "TRIAGE_INHERITED")
    open_refs = {entry["key"] for entry in _ok(user.get(TRIAGE))["items"]}
    assert f"INTAKE:{event['id']}" not in open_refs


# ------------------------------------------------------------------------------- with a second person (last)


@pytest.fixture(scope="module")
def colleague(trial):
    from tests.test_release_c1_0_10_73 import _invite

    invited, client, _ = _invite(trial["user"], "quality", "Second Reviewer")
    people = _ok(trial["user"].get(TRIAGE))["people"]
    other = next(person["id"] for person in people if person["id"] != trial["me"])
    return {"client": client, "id": other}


def test_a_backup_is_required_on_the_fast_track_with_two_people(trial, colleague):  # TR-09
    user, me = trial["user"], trial["me"]
    item = _find(user, f"INTAKE:{_log(user, answers=_all_no(Q2='YES', Q4='YES'))['id']}")
    refused = _save(user, item, me)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "BACKUP_NEEDED"
    _ok(_save(user, item, me, backup_owner=colleague["id"]))


def test_outside_the_trial_a_downgrade_needs_the_second_person_and_refusals_are_audited(
    trial, colleague, monkeypatch
):  # A6, B2-05
    from backend.app.intake import router as intake_router

    monkeypatch.setattr(intake_router, "is_trial", lambda *_: False)
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    _ok(_save(user, _find(user, f"INTAKE:{event['id']}"), me, severity="CRITICAL", backup_owner=colleague["id"]))
    saved = _find(user, f"INTAKE:{event['id']}")
    lower = {"severity": "MINOR", "backup_owner": colleague["id"], "change_reason": "Only a bruise, per the GP."}
    refused = _save(user, saved, me, **lower, password=PASSWORD)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SECOND_PERSON_NEEDED"
    task_id = refused.json()["detail"]["task_id"]
    assert _find(user, f"INTAKE:{event['id']}")["record"]["severity"] == "CRITICAL"  # nothing changed
    decide = f"{TRIAGE}/downgrades/{task_id}"
    body = {"decision": "APPROVE", "reason": "Checked the GP letter: a bruise.", "password": PASSWORD}
    same = user.post(decide, json=body)
    assert same.status_code == 403 and same.json()["detail"]["code"] == "SAME_PERSON"
    whys = [row.details.get("why") for row in _actions(tenant_id, "TRIAGE_DOWNGRADE_REFUSED")]
    assert "SECOND_PERSON" in whys and "SAME_PERSON" in whys
    _ok(colleague["client"].post(decide, json=body))
    after = _find(user, f"INTAKE:{event['id']}")
    assert after["record"]["severity"] == "MINOR" and after["record"]["version"] == 2
    recorded = [row for row in _actions(tenant_id, "TRIAGE_RECORDED") if row.details.get("approved_by")]
    assert recorded[-1].details["approved_by"] == colleague["id"] and recorded[-1].details["requested_by"] == me


def test_outside_the_trial_the_threat_is_excluded_by_another_person_signed(trial, colleague, monkeypatch):  # TR-06
    from backend.app.intake import router as intake_router

    monkeypatch.setattr(intake_router, "is_trial", lambda *_: False)
    user, tenant_id, me = trial["user"], trial["tenant_id"], trial["me"]
    event = _log(user, answers=_all_no(Q2="YES", Q4="YES"))
    _ok(
        _save(
            user,
            _find(user, f"INTAKE:{event['id']}"),
            me,
            public_health_threat=True,
            backup_owner=colleague["id"],
        )
    )
    item = _find(user, f"INTAKE:{event['id']}")
    assert item["tier"] == "THREAT"
    body = {"reason": "Single device, lot checked: no wider risk.", "password": PASSWORD}
    same = user.post(_url(item, "exclude-threat"), json=body)
    assert same.status_code == 403 and _actions(tenant_id, "TRIAGE_THREAT_EXCLUSION_REFUSED")
    _ok(colleague["client"].post(_url(item, "exclude-threat"), json=body))
    after = _find(user, f"INTAKE:{event['id']}")
    assert not after["record"]["public_health_threat"] and after["record"]["threat_excluded_at"]
    assert [v.version for v in _versions(tenant_id, event["id"])] == [1, 2]
    assert _actions(tenant_id, "TRIAGE_THREAT_EXCLUDED")
