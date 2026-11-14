"""scripts/recovery_check.py (B6b Part D, D1): the checks run on a restored database before anyone signs in.

Scenario rows B6-53 (a broken audit chain fails the check), B6-54 (a configuration difference with no change event
after the signed snapshot is flagged) and B6-55 (an unsent outbox event older than the restore point is held, audited
and sent only after a replay). The organisations are fresh ones on the shared plane, deleted at the end.
"""

from __future__ import annotations

import hashlib
import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.db.models.foundation import AuditEvent, ConnectorConfiguration
from backend.app.db.models.stage2 import OutboxEvent, WorkerHeartbeat
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from reports import pdf

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recovery_check = _load("recovery_check")
replay_outbox = _load("replay_outbox")
requirement = pytest.mark.requirement


# ------------------------------------------------------------------------------------- no database needed


@pytest.mark.unit
def test_the_restore_point_is_a_backup_folder_name_or_a_zoned_time():
    expected = datetime(2026, 11, 13, 2, 15, tzinfo=timezone.utc)
    assert recovery_check.parse_restore_point("20261113T021500Z") == expected
    assert recovery_check.parse_restore_point("2026-11-13T07:45:00+05:30") == expected
    with pytest.raises(ValueError, match="time zone"):
        recovery_check.parse_restore_point("2026-11-13T02:15:00")


@pytest.mark.unit
def test_the_manifest_check_fails_on_a_changed_or_missing_file(tmp_path):
    (tmp_path / "control.dump.age").write_bytes(b"encrypted dump")
    digest = hashlib.sha256(b"encrypted dump").hexdigest()
    (tmp_path / "MANIFEST.sha256").write_text(f"{digest}  ./control.dump.age\n", encoding="utf-8")
    assert recovery_check.check_manifest(tmp_path)["state"] == "PASS"
    (tmp_path / "control.dump.age").write_bytes(b"changed")
    changed = recovery_check.check_manifest(tmp_path)
    assert changed["state"] == "FAIL" and changed["problems"] == ["./control.dump.age: SHA-256 differs"]
    (tmp_path / "control.dump.age").unlink()
    assert recovery_check.check_manifest(tmp_path)["problems"] == ["./control.dump.age: missing"]
    (tmp_path / "MANIFEST.sha256").unlink()
    assert recovery_check.check_manifest(tmp_path)["state"] == "FAIL"


@pytest.mark.unit
def test_any_failed_step_fails_the_check_and_a_flag_needs_an_explanation():
    assert recovery_check.overall([{"state": "PASS"}, {"state": "INFO"}]) == "PASS"
    assert recovery_check.overall([{"state": "PASS"}, {"state": "FLAG"}]) == "PASS WITH FLAGS"
    assert recovery_check.overall([{"state": "FLAG"}, {"state": "FAIL"}]) == "FAIL"


@pytest.mark.unit
def test_a_customer_summary_holds_its_own_organisation_only():
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    record = {
        "result": "PASS WITH FLAGS",
        "finished_at": "2026-11-14T10:00:00+00:00",
        "steps": [
            {
                "step": "configuration",
                "organisations": [
                    {"tenant_id": ours, "state": "PASS", "explained": ["reporting.lookback_days"]},
                    {"tenant_id": theirs, "state": "FLAG", "unexplained": [{"item": "connectors.THEIR-QMS"}]},
                ],
            },
            {"step": "outbox_hold", "per_organisation": {ours: 2, theirs: 7}},
        ],
    }

    def org(tenant_id, name, key):
        return {
            "tenant_id": tenant_id,
            "name": name,
            "key": key,
            "window_from": "2026-11-13T02:15:00+00:00",
            "window_to": "2026-11-14T10:00:00+00:00",
            "window_hours": 31.8,
        }

    record["organisations"] = [org(ours, "OrbitCare Devices", "ORBITCARE"), org(theirs, "PulseWatch", "PULSEWATCH")]
    shown = pdf.text_of(recovery_check.customer_summary(record, record["organisations"][0]))
    assert "OrbitCare Devices" in shown and "2 notification(s) held" in shown and "31.8 hours" in shown
    for other in ("PulseWatch", "PULSEWATCH", theirs, "THEIR-QMS", "7 notification"):
        assert other not in shown


# ------------------------------------------------------------------------------------------- database


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "test")
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def org():
    from backend.app.trial.retention import purge_trial
    from tests.test_reporting_capa_api import _client, _organization

    tenant_id = _organization("RECOVERY")
    admin = _client(tenant_id, "CUSTOMER_ADMIN", f"Admin {uuid.uuid4().hex[:6]}")
    regulatory = _client(tenant_id, "REGULATORY_REVIEWER", f"Regulatory {uuid.uuid4().hex[:6]}")
    try:
        yield {"tenant_id": tenant_id, "admin": admin, "regulatory": regulatory}
    finally:
        with SessionLocal() as session:
            purge_trial(session, tenant_id, "test:recovery-check-cleanup")


@pytest.mark.db
@requirement("B6-53")
def test_a_broken_audit_chain_on_the_restored_copy_fails_the_recovery_check(db, org):
    from backend.app.enterprise_audit import make_audit_event

    tenant_id = org["tenant_id"]
    event = make_audit_event(tenant_id=tenant_id, actor_ref="test", action="RECOVERY_CHAIN_TEST", entity_type="Test")
    db.add(event)
    db.flush()
    db.refresh(event)
    intact = recovery_check.check_chains(db, [tenant_id])
    assert intact["state"] == "PASS" and intact["organisations"][0]["valid"] is True
    # Someone with owner access edits history in the copy (the immutability trigger normally refuses; rolled back).
    db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable"))
    db.execute(text("UPDATE audit_events SET reason = 'edited in the backup' WHERE id = :id"), {"id": event.id})
    broken = recovery_check.check_chains(db, [tenant_id])
    assert broken["state"] == "FAIL" and "do not open the system" in broken["summary"]
    assert broken["organisations"][0]["first_broken_seq"] == event.chain_seq
    assert recovery_check.overall([intact, broken]) == "FAIL"


@pytest.mark.db
@requirement("B6-54")
def test_a_configuration_difference_without_a_change_event_is_flagged(db, org):
    from tests.test_reporting_capa_api import PASSWORD, REASON, SETTINGS

    tenant_id = org["tenant_id"]
    signed = org["admin"].post(
        "/api/v1/reviews/configuration/sign", json={"findings": "Configuration at go-live", "password": PASSWORD}
    )
    assert signed.status_code == 200, signed.text
    # A change made through the product, with its reason: explained by its audit event.
    settings = org["regulatory"].get(SETTINGS).json()
    saved = org["regulatory"].put(
        SETTINGS, json={"windows": settings["templates"][:1], "lookback_days": 210, "reason": REASON}
    )
    assert saved.status_code == 200, saved.text
    now = datetime.now(timezone.utc)
    explained = recovery_check.configuration_of(db, tenant_id, now + timedelta(seconds=1))
    assert explained["state"] == "PASS" and "reporting.lookback_days" in explained["explained"]
    assert explained["unexplained"] == []
    # A connector written straight into the database: no change event explains it.
    with SessionLocal() as session:
        bind_tenant(session, tenant_id)
        session.add(
            ConnectorConfiguration(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                code="QMS-UNEXPLAINED",
                connector_type="REST",
                configuration={"endpoint": "https://qms.example.invalid/api"},
                version="1",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    flagged = recovery_check.check_configuration(db, [tenant_id], datetime.now(timezone.utc) + timedelta(seconds=1))
    assert flagged["state"] == "FLAG"
    entry = flagged["organisations"][0]
    assert any(item["item"].startswith("connectors.QMS-UNEXPLAINED.") for item in entry["unexplained"])
    assert "reporting.lookback_days" in entry["explained"]


@pytest.mark.db
def test_an_organisation_without_a_signed_snapshot_is_listed_not_failed(db):
    from tests.test_reporting_capa_api import _organization

    tenant_id = _organization("NO_SNAPSHOT")
    result = recovery_check.configuration_of(db, tenant_id, datetime.now(timezone.utc))
    assert result == {"tenant_id": str(tenant_id), "state": "INFO", "note": "no signed configuration snapshot"}


def _event(db, tenant_id, occurred_at, *, published=False) -> OutboxEvent:
    row = OutboxEvent(
        tenant_id=tenant_id,
        event_name="RECOVERY_HOLD_TEST",
        aggregate_type="Test",
        payload={"to": "never-in-the-audit@example.invalid"},
        occurred_at=occurred_at,
        published_at=occurred_at if published else None,
    )
    db.add(row)
    db.flush()
    return row


def _due(db, row_id, now) -> bool:
    from outbox.worker import _due_filter

    return db.query(OutboxEvent).filter(OutboxEvent.id == row_id, *_due_filter(now)).count() == 1


@pytest.mark.db
@requirement("B6-55")
def test_an_unsent_event_older_than_the_restore_point_is_held_audited_and_sent_only_after_a_replay(db, org):
    tenant_id = org["tenant_id"]
    now = datetime.now(timezone.utc)
    point = now - timedelta(hours=1)
    pending = _event(db, tenant_id, now - timedelta(hours=2))
    sent = _event(db, tenant_id, now - timedelta(hours=2), published=True)
    db.commit()
    assert _due(db, pending.id, now)

    dry = recovery_check.hold_outbox(db, point, now, apply=False, tenant_ids=[tenant_id])
    assert dry["state"] == "FLAG" and dry["to_hold"] == 1
    db.rollback()
    assert db.get(OutboxEvent, pending.id).dead_lettered_at is None  # a dry run changes nothing

    held = recovery_check.hold_outbox(db, point, now, apply=True, tenant_ids=[tenant_id])
    db.commit()
    assert held["state"] == "PASS" and held["held"] == 1 and held["per_organisation"] == {str(tenant_id): 1}
    row = db.get(OutboxEvent, pending.id)
    assert row.dead_lettered_at is not None and row.last_error == "held after restore"
    assert db.get(OutboxEvent, sent.id).dead_lettered_at is None
    assert not _due(db, pending.id, now + timedelta(minutes=5))  # the worker never picks it up by itself
    audit = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "OUTBOX_EVENTS_HELD_AFTER_RESTORE")
        .one()
    )
    assert audit.details["count"] == 1 and audit.details["items"][0]["id"] == str(pending.id)
    assert "never-in-the-audit" not in str(audit.details) and audit.reason.startswith("held after restore")
    # Holding again holds nothing new.
    assert recovery_check.hold_outbox(db, point, now, apply=True, tenant_ids=[tenant_id])["held"] == 0
    db.rollback()

    # A person checked the mail provider's log: not sent. Only the replay puts it back in the queue.
    replay_outbox.replay(db, pending.id, "Mail provider log shows it was not sent")
    assert _due(db, pending.id, datetime.now(timezone.utc) + timedelta(seconds=1))
    bind_system(db, "test cleanup")
    db.query(OutboxEvent).filter(OutboxEvent.id.in_([pending.id, sent.id])).delete()
    db.commit()


@pytest.mark.db
@requirement("B6-55")
def test_an_unsent_event_after_the_restore_point_is_held_too_and_flagged(db, org):
    # The backup's folder time is taken before the dump reads the data: an event of those minutes may already have
    # been sent by production, so it is held like the older ones, and flagged for the person to explain.
    now = datetime.now(timezone.utc)
    later = _event(db, org["tenant_id"], now - timedelta(minutes=10))
    result = recovery_check.hold_outbox(db, now - timedelta(hours=1), now, apply=True, tenant_ids=[org["tenant_id"]])
    assert result["state"] == "FLAG" and result["after_restore_point"] == 1 and result["held"] == 1
    assert later.dead_lettered_at is not None and later.last_error == "held after restore"


@pytest.mark.db
def test_a_worker_that_ran_on_the_restored_copy_fails_the_check(db):
    now = datetime.now(timezone.utc)
    assert recovery_check.check_quiet(db, now + timedelta(days=1), now)["state"] == "PASS"
    db.add(
        WorkerHeartbeat(
            service="recovery-test", instance_id=uuid.uuid4().hex, started_at=now, updated_at=now, metrics={}
        )
    )
    db.flush()
    result = recovery_check.check_quiet(db, now - timedelta(minutes=1), now)
    assert result["state"] == "FAIL" and any(item["service"] == "recovery-test" for item in result["services"])
    # The same heartbeat seen an hour later (written while the backup was taken): flagged, not failed.
    later = recovery_check.check_quiet(db, now - timedelta(minutes=1), now + timedelta(hours=1))
    assert later["state"] == "FLAG"


@pytest.mark.db
def test_schema_and_row_level_security_are_compared_with_the_source(db):
    from backend.app.db.data_plane import schema_head

    facts = recovery_check.database_facts(db)
    assert recovery_check.check_schema(facts, schema_head())["state"] == "PASS"
    assert recovery_check.check_schema(facts, "not_the_head")["state"] == "FAIL"
    assert recovery_check.check_security(facts, dict(facts))["state"] == "PASS"
    assert recovery_check.check_security(facts, None)["state"] == "FLAG"  # not compared is never a pass
    assert recovery_check.check_counts(facts, None)["state"] == "FLAG"
    fewer = {**facts, "policies": facts["policies"] + 1}
    assert recovery_check.check_security(facts, fewer)["state"] == "FAIL"
    assert recovery_check.check_counts(facts, dict(facts))["state"] == "PASS"
    source = {**facts, "row_counts": {**facts["row_counts"], "tenants": facts["row_counts"]["tenants"] + 3}}
    differs = recovery_check.check_counts(facts, source)
    assert differs["state"] == "FLAG" and differs["differences"][0]["table"] == "tenants"


@pytest.mark.db
def test_the_script_refuses_a_database_the_operator_did_not_name(capsys):
    assert recovery_check.main(["--database", "not_this_database", "--restore-point", "20261113T021500Z"]) == 1
    assert "Refused" in capsys.readouterr().err


@pytest.mark.unit
def test_the_clock_step_keeps_the_clock_checks_own_state(monkeypatch):
    from backend.app import clock_check

    def measured(_connection=None):
        return {"state": clock_check.DEGRADED, "limit_seconds": 1.0, "database_offset_seconds": 2.5}

    monkeypatch.setattr(clock_check, "check", measured)
    result = recovery_check.check_clock()
    assert result["state"] == "FAIL" and result["clock_state"] == clock_check.DEGRADED
    assert result["database_offset_seconds"] == 2.5


@pytest.mark.db
def test_holding_needs_the_restored_copy_confirmation(db, capsys):
    current = db.execute(text("SELECT current_database()")).scalar()
    with pytest.raises(SystemExit) as stopped:
        recovery_check.main(["--database", current, "--restore-point", "20261113T021500Z"])
    assert stopped.value.code == 2 and "--restored-copy" in capsys.readouterr().err


@pytest.mark.db
def test_a_dry_run_writes_the_record_and_one_summary_per_organisation_and_changes_nothing(org, tmp_path):
    tenant_id = org["tenant_id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        bind_system(session, "test")
        pending = _event(session, tenant_id, now - timedelta(hours=2))
        session.commit()
        pending_id = pending.id

    def no_clock():
        return recovery_check.step("clock", "PASS", "not measured in this test")

    try:
        record = recovery_check.run(restore_point=now - timedelta(hours=1), apply=False, clock=no_clock)
        assert record["outbox_hold_applied"] is False
        hold = next(item for item in record["steps"] if item["step"] == "outbox_hold")
        assert hold["state"] == "FLAG" and hold["per_organisation"][str(tenant_id)] == 1
        names = {item["step"] for item in record["steps"]}
        assert {"worker_stopped", "schema_head", "audit_chain", "configuration", "dedicated_databases"} <= names
        written = recovery_check.write_record(record, tmp_path)
        assert written[0].suffix == ".json" and written[1].suffix == ".pdf"
        assert len(written) == 2 + len(record["organisations"])
        ours = next(org_ for org_ in record["organisations"] if org_["tenant_id"] == str(tenant_id))
        summary = next(path for path in written[2:] if ours["key"] in path.name)
        shown = pdf.text_of(summary.read_bytes())
        assert "1 notification(s) held" in shown
        assert not any(other["key"] in shown for other in record["organisations"] if other["key"] != ours["key"])
        with SessionLocal() as session:
            bind_system(session, "test")
            assert session.get(OutboxEvent, pending_id).dead_lettered_at is None  # the dry run changed nothing
    finally:
        with SessionLocal() as session:
            bind_system(session, "test cleanup")
            session.query(OutboxEvent).filter(OutboxEvent.id == pending_id).delete()
            session.commit()
