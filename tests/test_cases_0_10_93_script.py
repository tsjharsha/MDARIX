"""0.10.93 (B2 step 8, spec 9.1 and 9.2): the Cases backfill lists what it would change and writes nothing; with
--apply and the typed confirmation it does exactly what it listed, per trial, audited, and a second run changes
nothing. A new trial's sample needs nothing from it (F2)."""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cases_0_10_93.py"


def _script():
    spec = importlib.util.spec_from_file_location("cases_0_10_93", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check(classification=None, signed=True, review=None):
    return SimpleNamespace(
        classification=classification, signed_at=datetime.now(timezone.utc) if signed else None, review_outcome=review
    )


@pytest.mark.unit
def test_the_state_is_read_from_the_latest_check():
    state = _script().state_for
    assert state(None, False) == "OPEN"
    assert state(_check("COMPLAINT", signed=False), True) == "OPEN"
    assert state(_check("PENDING"), False) == "PENDING"
    assert state(_check("PENDING_CONFIRM"), False) == "PENDING"
    assert state(_check("SERVICE_ONLY"), False) == "IN_REVIEW"
    assert state(_check("INQUIRY", review="AGREED"), False) == "CLOSED"
    assert state(_check("BOTH"), True) == "ESCALATED"
    assert state(_check("SERVICE_ONLY", review="RECLASSIFIED"), True) == "ESCALATED"
    # OD-3: a signed complaint with no complaint is escalated by the upgrade (None: no state of its own).
    assert state(_check("COMPLAINT"), False) is None
    assert state(_check("COMPLAINT"), False, voided=True) == "VOIDED"


@pytest.mark.unit
def test_a_country_becomes_its_code_or_is_kept_to_confirm():
    change = _script().country_change
    assert change("United States") == ("US", None)
    assert change("de") == ("DE", None)
    assert change("US") is None
    assert change("") is None
    assert change("Atlantis") == (None, "Atlantis")


@pytest.mark.unit
def test_counts_mode_prints_counts_only(capsys):
    """For the read-only production run: numbered trials and counts per kind of change, never a trial's key or
    name, a Case reference, the person who logged it or the country text someone typed."""
    script = _script()
    change = script.Change
    lines = [
        change(
            'CALL-0007: channel -> PHONE ("Phone", was kind CONTACT)', "Case channel set to PHONE from its old kind"
        ),
        change("CALL-0007: country 'Lakeside, near the clinic' kept as text", "Case country kept as text"),
        change("CALL-0007: owner -> person@example.org (who logged it)", "Case owner set to who logged it"),
        change("3 CUSTOMER_UPLOAD complaint(s): record owner -> EXTERNAL", "complaint record owner set", 3),
    ]
    found = [("acme-medical", "Acme Medical Devices Pvt Ltd", lines), ("other-org", "Other Org", [])]
    script.print_counts(found)
    out = capsys.readouterr().out
    for private in ("CALL-0007", "person@example.org", "Lakeside", "acme-medical", "Acme Medical", "Other Org"):
        assert private not in out
    assert "Trial 1 of 2: records to change" in out
    assert "Trial 2 of 2: no change" in out
    assert "     3  complaint record owner set" in out
    assert "     1  Case owner set to who logged it" in out


@pytest.mark.db
def test_the_list_names_the_changes_and_writes_nothing():
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    _user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        # The sample's calls as a 0.10.92 trial holds them: tr19's defaults, nothing backfilled.
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            _as_0_10_92(db, tenant_id)
            db.commit()
            before = {
                row.reference: (row.status, row.channel, row.owner_id, row.complaint_id, row.country)
                for row in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)
            }
            lines = _script().plan_tenant(db, tenant_id)
            db.rollback()
        text = "\n".join(lines)
        assert "SAMPLE-CALL-01: channel -> PHONE" in text
        assert "SAMPLE-CALL-01: state OPEN -> IN_REVIEW" in text
        assert "SAMPLE-CALL-02: country 'Germany' -> DE" in text
        assert "SAMPLE-CASE-11: owner -> " in text  # unsigned, still open: the person who logged it
        assert "SAMPLE-CASE-11: state" not in text  # unsigned stays OPEN
        assert "SAMPLE-CALL-02: signed complaint, no complaint: left for a person to escalate" in text
        assert "ESCALATED by the upgrade" not in text  # the sample is never escalated here
        # --counts: the same changes as counts, with no Case reference or person in the kinds.
        found = _script().counts(lines)
        assert found["Case channel set to PHONE from its old kind"] >= 1
        assert found["Case country set to its code"] >= 1
        assert sum(found.values()) >= len(lines)
        assert not any("SAMPLE-" in kind or "@" in kind for kind in found)
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            after = {
                row.reference: (row.status, row.channel, row.owner_id, row.complaint_id, row.country)
                for row in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)
            }
        assert after == before
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:cases-0-10-93-cleanup")


# ------------------------------------------------------------------------------------------------ --apply (F1, F2)


def _as_0_10_92(db, tenant_id) -> None:
    """Set a trial's records back to how a 0.10.92 trial holds them after migration tr19: the Cases at tr19's
    defaults, the country as typed, no record owner, no triage version rows or speed."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import IntakeEvent, TriageRecord, TriageRecordVersion

    for event in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id):
        event.status, event.channel, event.owner_id, event.complaint_id = "OPEN", None, None, None
        event.record_owner, event.escalation, event.escalated_at, event.escalated_by = None, None, None, None
        if event.reference == "SAMPLE-CALL-02":
            event.country = "Germany"
    db.query(TriageRecordVersion).filter(TriageRecordVersion.tenant_id == tenant_id).delete()
    for record in db.query(TriageRecord).filter(TriageRecord.tenant_id == tenant_id):
        record.speed, record.version = None, 1
    for complaint in db.query(Complaint).filter(Complaint.tenant_id == tenant_id):
        if complaint.source_system == "MDARIX_SAMPLE":
            complaint.record_owner = None


def _own_signed_complaint_case(db, tenant_id, reference: str):
    """A Case of the trial's own, signed "complaint" before 0.10.93 and never linked, with its open QMS task."""
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
    from backend.app.intake import case_rules, service

    now = datetime.now(timezone.utc)
    event = IntakeEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        reference=reference,
        kind="CONTACT",
        reporter_words="The pump alarmed and stopped during an infusion; the nurse restarted it.",
        country="United States",
        received_at=now,
        created_by="tester",
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.flush()
    db.add(
        FirstContactCheck(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            intake_event_id=event.id,
            version=1,
            guide_version=case_rules.GUIDE_VERSION,
            answers={},
            suggestion="COMPLAINT",
            classification="COMPLAINT",
            reason="A malfunction during use.",
            signed_by="tester",
            signed_at=now,
            created_by="tester",
            created_at=now,
            updated_at=now,
        )
    )
    service.ensure_qms_task(db, tenant_id, event, "tester", now)
    db.flush()
    return event.id


def _fingerprint(db, tenant_id) -> dict:
    """What the backfill may change in one trial, plus its signed checks and signatures (never changed)."""
    from backend.app.db.models.foundation import Complaint, SignedApprovalRecord
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, TriageRecord, TriageRecordVersion

    def rows(model, *columns):
        return sorted(
            tuple(str(getattr(row, column)) for column in columns)
            for row in db.query(model).filter(model.tenant_id == tenant_id)
        )

    return {
        "cases": rows(IntakeEvent, "id", "status", "channel", "owner_id", "complaint_id", "record_owner", "country"),
        "checks": rows(FirstContactCheck, "id", "classification", "signed_at", "signed_by", "updated_at", "answers"),
        "signatures": rows(SignedApprovalRecord, "id", "status", "content_fingerprint", "signature_hash"),
        "complaints": rows(Complaint, "id", "record_owner", "status"),
        "triage": rows(TriageRecord, "id", "speed", "version"),
        "versions": rows(TriageRecordVersion, "id"),
    }


@pytest.fixture
def old_trials():
    """Two trials whose records read as a 0.10.92 trial's after tr19; the first holds a signed complaint Case of its
    own, never linked (OD-3)."""
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    tenants = [uuid.UUID(_approved_trial_client()[1]["tenant_id"]) for _ in range(2)]
    try:
        for tenant_id in tenants:
            with SessionLocal() as db:
                bind_tenant(db, tenant_id)
                _as_0_10_92(db, tenant_id)
                db.commit()
        with SessionLocal() as db:
            bind_tenant(db, tenants[0])
            own = _own_signed_complaint_case(db, tenants[0], "CALL-0093")
            db.commit()
        yield tenants, own
    finally:
        for tenant_id in tenants:
            with SessionLocal() as db:
                purge_trial(db, tenant_id, "test:cases-0-10-93-cleanup")


@pytest.mark.db
def test_apply_does_exactly_what_the_list_says_audited_and_a_second_run_changes_nothing(old_trials):
    from backend.app.db.models.foundation import AuditEvent, Complaint
    from backend.app.db.models.intake import IntakeEvent, TriageRecord, TriageRecordVersion
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    script = _script()
    (tenant_id, _other), own = old_trials
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        listed = script.plan_tenant(db, tenant_id)
        db.rollback()
        before = _fingerprint(db, tenant_id)
    assert "CALL-0093: signed complaint, no complaint: ESCALATED by the upgrade" in "\n".join(listed)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        done = script.apply_tenant(db, tenant_id, batch=3)  # several batches
    assert script.counts(done) == script.counts(listed) and script.counts(done)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        after = _fingerprint(db, tenant_id)
        cases = {row.reference: row for row in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id)}
        assert cases["SAMPLE-CALL-01"].status == "IN_REVIEW" and cases["SAMPLE-CALL-01"].channel == "PHONE"
        assert cases["SAMPLE-CALL-02"].country == "DE" and cases["SAMPLE-CALL-02"].status == "OPEN"  # spec 9.3
        assert cases["SAMPLE-CALL-03"].owner_id == cases["SAMPLE-CALL-03"].created_by
        assert {row.record_owner for row in cases.values()} == {"MDARIX"}
        # OD-3: the trial's own signed complaint became a complaint owned in MDARIX; its old QMS task is not needed.
        case = cases["CALL-0093"]
        assert case.status == "ESCALATED" and case.escalation == "CREATED" and case.country == "US"
        complaint = db.get(Complaint, case.complaint_id)
        assert complaint.record_owner == "MDARIX" and complaint.source_system == "MDARIX_CASE"
        task = (
            db.query(WorkflowTask)
            .filter(WorkflowTask.tenant_id == tenant_id, WorkflowTask.source_entity_id == own)
            .one()
        )
        assert task.status == "COMPLETED" and task.completion_outcome == "NOT_NEEDED"
        records = db.query(TriageRecord).filter(TriageRecord.tenant_id == tenant_id).all()
        versioned = {
            row.triage_record_id
            for row in db.query(TriageRecordVersion).filter(TriageRecordVersion.tenant_id == tenant_id)
        }
        assert records and {row.id for row in records} <= versioned
        assert all(row.speed == "FAST" for row in records if row.completed_at is not None)
        actions = {
            row.action
            for row in db.query(AuditEvent).filter(
                AuditEvent.tenant_id == tenant_id, AuditEvent.actor_ref == script.UPGRADE_ACTOR
            )
        }
        assert {
            "CASE_FIELD_SET_BY_UPGRADE",
            "CASE_STATE_CHANGED",
            "CASE_ESCALATED",
            "CASES_UPGRADED_0_10_93",
        } <= actions
        # A second run: nothing listed, nothing done, nothing changed.
        assert not script.counts(script.plan_tenant(db, tenant_id))
        db.rollback()
        assert not script.apply_tenant(db, tenant_id)
        assert _fingerprint(db, tenant_id) == after
    # Signed checks and their signatures are never changed.
    assert after["checks"] == before["checks"] and after["signatures"] == before["signatures"]


@pytest.mark.db
def test_a_case_past_to_check_is_never_touched(old_trials):
    """A Case 0.10.93 itself moved (here closed, with no channel, owner or record owner) is left exactly as it is."""
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    script = _script()
    (tenant_id, _other), _own = old_trials
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        closed = (
            db.query(IntakeEvent)
            .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == "SAMPLE-CALL-04")
            .one()
        )
        closed.status, closed.resolution_summary = "CLOSED", "Answered the caller's question about the loan pump."
        db.commit()
        text = "\n".join(script.plan_tenant(db, tenant_id))
        db.rollback()
        assert "SAMPLE-CALL-04" not in text
        script.apply_tenant(db, tenant_id)
        db.refresh(closed)
        assert (closed.status, closed.channel, closed.owner_id, closed.record_owner) == ("CLOSED", None, None, None)


@pytest.mark.db
def test_one_trial_never_touches_another_trials_rows(old_trials):
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    script = _script()
    (first, second), _own = old_trials
    with SessionLocal() as db:
        bind_tenant(db, second)
        untouched = _fingerprint(db, second)
    with SessionLocal() as db:
        bind_tenant(db, first)
        assert script.apply_tenant(db, first)
        # A session bound to the first trial is refused for the second: one trial per tenant-bound session.
        for run in (script.plan_tenant, script.apply_tenant):
            with pytest.raises(ValueError, match="bound to the trial"):
                run(db, second)
        db.rollback()
    with SessionLocal() as db:
        bind_tenant(db, second)
        assert _fingerprint(db, second) == untouched
        assert script.counts(script.plan_tenant(db, second))  # still all to do
        db.rollback()


@pytest.mark.db
def test_apply_is_refused_without_the_typed_confirmation(old_trials, capsys):
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant

    script = _script()
    (tenant_id, _other), _own = old_trials
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        before = _fingerprint(db, tenant_id)
    assert script.main(["--apply"], ask=lambda _prompt: "yes") == 2
    out = capsys.readouterr().out
    assert "Refused: the confirmation was not typed" in out
    assert "CALL-0093" not in out and "SAMPLE-" not in out  # --apply prints counts only
    with pytest.raises(SystemExit):
        script.main(["--apply", "--dry-run"])
    assert script.main(["--dry-run", "--counts"]) == 0
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert _fingerprint(db, tenant_id) == before


@pytest.mark.db
def test_a_new_trial_needs_nothing_from_the_backfill_and_keeps_its_duplicate_pair():
    """F2: the sample of a trial created by 0.10.93 reads correctly from the start: its calls have their channel,
    owner and record owner, SAMPLE-CALL-01 (signed service only) is in QA review, and its triage records have their
    version rows. The Case's country code still pairs SAMPLE-CALL-02 with SAMPLE-RT-05 ("Germany")."""
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.intake import service
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    tenant_id = uuid.UUID(_approved_trial_client()[1]["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            lines = _script().plan_tenant(db, tenant_id)
            assert not _script().counts(lines), "\n".join(lines)
            call = (
                db.query(IntakeEvent)
                .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == "SAMPLE-CALL-01")
                .one()
            )
            assert call.status == "IN_REVIEW"
            pairs = [{item["left"]["ref"], item["right"]["ref"]} for item in service.duplicates(db, tenant_id)]
            assert {"SAMPLE-CALL-02", "SAMPLE-RT-05"} in pairs
            db.rollback()
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:cases-0-10-93-cleanup")
