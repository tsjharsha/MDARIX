"""The WHIF demo database (scripts/demo_database.py) and the sample story it seeds.

The guard tests need no database. The story tests reset a ``mdarix_whif_*`` database (run them with
``POSTGRES_DB=mdarix_whif_dbtest``) and are skipped on any other, so the normal suite never drops anything.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "demo_database", Path(__file__).resolve().parents[1] / "scripts" / "demo_database.py"
)
demo_database = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(demo_database)

PASSWORD = "Whif demo password 2026!"


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        "mdarix_r1",
        "mdarix_r1_test",
        "mdarix_demo_test",
        "postgres",
        "mdarix_whif",
        "mdarix_whif_",
        "MDARIX_WHIF_DEMO",
        "xmdarix_whif_demo",
        'mdarix_whif_demo"; DROP DATABASE mdarix_r1; --',
    ],
)
def test_the_guard_refuses_every_database_but_a_whif_one(name):
    with pytest.raises(SystemExit):
        demo_database.guard(name)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["mdarix_whif_demo", "mdarix_whif_dbtest", "mdarix_whif_restore"])
def test_the_guard_accepts_whif_databases(name):
    assert demo_database.guard(name) == name


@pytest.mark.unit
@pytest.mark.parametrize("command", [["reset"], ["backup-check", "--out", "."]])
def test_the_script_refuses_another_database_before_connecting(monkeypatch, command):
    monkeypatch.setenv("POSTGRES_DB", "mdarix_r1")

    def never(*_args, **_kwargs):
        raise AssertionError("connected to a database it must refuse")

    monkeypatch.setattr(demo_database, "_admin_engine", never)
    monkeypatch.setattr(demo_database, "reset", never)
    monkeypatch.setattr(demo_database, "backup_check", never)
    assert demo_database.main(command) == 2


@pytest.mark.unit
def test_the_template_and_restore_names_are_whif_names_too():
    assert demo_database.guard(demo_database.TEMPLATE) and demo_database.guard(demo_database.RESTORE)


# ------------------------------------------------------------------------------------------------ the story


@pytest.fixture(scope="module")
def demo():
    name = os.environ.get("POSTGRES_DB", "")
    if not name.startswith(demo_database.PREFIX) or name in (demo_database.TEMPLATE, demo_database.RESTORE):
        pytest.skip("needs POSTGRES_DB=mdarix_whif_dbtest (it is dropped and created again)")
    os.environ[demo_database.PASSWORD_ENV] = PASSWORD
    try:
        first = demo_database.reset(name)
    finally:
        os.environ.pop(demo_database.PASSWORD_ENV, None)
    return first


def _db():
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    db = SessionLocal()
    bind_system(db, "test the WHIF demo story")
    return db


def _client():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    signed = client.post("/api/v1/auth/signin", json={"email": demo_database.DEMO_TRIAL_EMAIL, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    return client


@pytest.mark.db
def test_reset_is_fast_and_leaves_one_curated_trial(demo):
    from backend.app.db.models.foundation import Tenant

    assert demo["total_seconds"] < 60 and demo["accounts_active"] is True
    db = _db()
    try:
        trials = db.query(Tenant).filter(Tenant.tenant_key.like("TRIAL_%")).all()
        assert [t.display_name for t in trials] == [demo_database.DEMO_ORGANIZATION]
        assert str(trials[0].id) == demo["tenant_id"]
    finally:
        db.close()


@pytest.mark.db
def test_the_story_runs_from_intake_to_signatures(demo):
    """Intake and triage with the owner-confirmed severities, the guided investigation with its AI proposals and RCA,
    a decision in each of the five markets, signatures and a valid audit chain."""
    from backend.app.ai_review import SUBJECT_EXECUTION, review_states
    from backend.app.audit_chain import verify_tenant_chain
    from backend.app.db.models.foundation import (
        AIExecution,
        Complaint,
        FailureChain,
        Hypothesis,
        HypothesisEvidence,
        SignedApprovalRecord,
    )
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.trial import sample_ai
    from backend.app.trial.sample_calm import SAMPLE_TRIAGE_SEVERITY

    tenant_id = uuid.UUID(demo["tenant_id"])
    db = _db()
    try:
        from sqlalchemy import text

        severities = dict(
            db.execute(
                text(
                    "SELECT c.complaint_identifier, t.severity FROM triage_records t JOIN complaints c "
                    "ON c.id = t.subject_id WHERE t.tenant_id = :t"
                ),
                {"t": tenant_id},
            ).all()
        )
        for identifier, level in SAMPLE_TRIAGE_SEVERITY.items():
            if identifier in severities:
                assert severities[identifier] == level, identifier
        assert {"CRITICAL", "SERIOUS", "NEGLIGIBLE", "NOT_KNOWN"} <= set(severities.values())
        assert db.execute(text("SELECT count(*) FROM intake_events WHERE tenant_id = :t"), {"t": tenant_id}).scalar()

        # AI proposals: pre-recorded, never a real provider, all waiting for a person.
        executions = db.query(AIExecution).filter(AIExecution.tenant_id == tenant_id).all()
        assert [row.provider for row in executions] == [sample_ai.PROVIDER]
        assert review_states(db, tenant_id, SUBJECT_EXECUTION, [executions[0].id]) == {
            str(executions[0].id): "NOT_REVIEWED"
        }
        hypotheses = db.query(Hypothesis).filter(Hypothesis.tenant_id == tenant_id).all()
        assert {row.origin for row in hypotheses} == {"human", "ai"}
        assert len({row.cause_category for row in hypotheses}) >= 3
        ai = next(row for row in hypotheses if row.origin == "ai")
        relations = {
            row.relation_type for row in db.query(HypothesisEvidence).filter(HypothesisEvidence.hypothesis_id == ai.id)
        }
        assert relations == {"support", "contradict"} and ai.status == "proposed"
        methods = {row.method for row in db.query(FailureChain).filter(FailureChain.tenant_id == tenant_id)}
        assert "FIVE_WHYS" in methods

        # Markets: the US, EU/NI, India and Canada decided; Canada answers the same France event differently.
        assessed = {
            (row.market, row.conclusion)
            for row in db.query(ComplaintMarketAssessment).filter(
                ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.signed_at.isnot(None)
            )
        }
        assert {
            ("US", "REPORTABLE"),
            ("EU_NI", "REPORTABLE"),
            ("IN", "REPORTABLE"),
            ("CA", "NOT_REPORTABLE"),
        } <= assessed
        reports = {row.market for row in db.query(ReportObligation).filter(ReportObligation.tenant_id == tenant_id)}
        assert {"US", "EU_NI", "IN"} <= reports

        signed = db.query(SignedApprovalRecord).filter(SignedApprovalRecord.tenant_id == tenant_id).all()
        assert len(signed) >= 5 and all(row.content_fingerprint and row.signature_hash for row in signed)
        chain = verify_tenant_chain(db, tenant_id)
        assert chain["valid"] and chain["checked"] > 0

        # Synthetic only: every complaint is the sample's, every product says so.
        complaints = db.query(Complaint).filter(Complaint.tenant_id == tenant_id).all()
        assert complaints and {row.source_system for row in complaints} == {"MDARIX_SAMPLE"}
    finally:
        db.close()


@pytest.mark.db
def test_every_complaint_is_on_a_version_released_by_its_event(demo):
    """The "as of" rule: a complaint's version belongs to its product, was released on or before the event, and its
    lot (when named) was made of that version."""
    from sqlalchemy import text

    db = _db()
    try:
        wrong = db.execute(
            text(
                "SELECT c.complaint_identifier FROM complaints c "
                "JOIN product_versions v ON v.id = c.product_version_id "
                "LEFT JOIN lot_batches l ON l.id = c.lot_batch_id "
                "WHERE c.tenant_id = :t AND (v.product_id <> c.product_id "
                "OR v.release_timestamp > coalesce(c.event_timestamp, c.complaint_timestamp) "
                "OR (l.id IS NOT NULL AND l.product_version_id <> v.id))"
            ),
            {"t": uuid.UUID(demo["tenant_id"])},
        ).all()
        assert wrong == []
    finally:
        db.close()


@pytest.mark.db
def test_the_trial_user_sees_the_ai_proposals_labelled_on_the_case(demo):
    from backend.app.ai_review import UNREVIEWED_LABEL
    from backend.app.db.models.foundation import Investigation

    db = _db()
    try:
        case = (
            db.query(Investigation)
            .filter(
                Investigation.tenant_id == uuid.UUID(demo["tenant_id"]),
                Investigation.investigation_identifier == "SAMPLE-INV-001",
            )
            .one()
        )
    finally:
        db.close()
    client = _client()
    response = client.get(f"/api/v1/investigations/{case.id}/intelligence/observations")
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"] if isinstance(body, dict) else body
    proposals = [item for item in items if item["origin"] == "AI"]
    assert len(proposals) == 2 and {item["ai_label"] for item in proposals} == {UNREVIEWED_LABEL}
    fishbone = client.get(f"/api/v1/investigations/{case.id}/rca/fishbone")
    assert fishbone.status_code == 200, fishbone.text
    assert "PROCESS" in fishbone.text


@pytest.mark.db
def test_reset_twice_gives_the_same_start_state(demo, monkeypatch):
    """Idempotent: whatever happened in between (sign-ins, the tests above), a reset gives the same rows again."""
    name = os.environ["POSTGRES_DB"]
    monkeypatch.setenv(demo_database.PASSWORD_ENV, PASSWORD)
    first = demo_database.reset(name)
    counts = demo_database._counts(name)
    second = demo_database.reset(name)
    assert second["template_built"] is False and first["total_seconds"] < 60 and second["total_seconds"] < 60
    assert demo_database._counts(name) == counts
