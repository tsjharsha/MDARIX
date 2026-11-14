"""A person accepts, edits or rejects every AI output, and only reviewed model results feed the Decision Center
(AI-R step 9, owner decision AI-D7); the decision advisory is not offered and its saved row names no rules "model"
(AI-R step 11, AI-D5). No AI service is called: the model results are written directly, as a model would have.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from backend.app.db.models.ai_records import AiOutputReview
from backend.app.db.models.foundation import AIExecution, AuditEvent, Tenant
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from decision_center.service import DecisionCenterService
from genai import provider as provider_module
from genai.features import FEATURES
from tests.conftest import authenticated_client

pytestmark = pytest.mark.db
ORCHESTRATION = "R1-Day11"


def _case():
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id, tenant_id FROM investigations WHERE investigation_identifier='INV-001'")
        ).one()


def _model_result(summary: str) -> uuid.UUID:
    """A saved analysis written by a language model (provider groq), newer than any other for the case."""
    case_id, tenant_id = _case()
    row_id = uuid.uuid4()
    with SessionLocal() as db:
        bind_system(db, "test")
        db.add(
            AIExecution(
                id=row_id,
                tenant_id=tenant_id,
                investigation_id=case_id,
                requestor_ref="test",
                provider="groq",
                model_name="openai/gpt-oss-120b",
                model_version="test-1",
                prompt_template_version="R1-MVP-P3-Investigator-v2",
                orchestration_version=ORCHESTRATION,
                context_refs={},
                evidence_refs={},
                structured_input={},
                structured_output={"summary": summary},
                validation_status="COMPLETED",
                execution_timestamp=datetime.now(timezone.utc) + timedelta(days=3650),
            )
        )
        db.commit()
    return row_id


def _latest_summary():
    case_id, tenant_id = _case()
    with SessionLocal() as db:
        bind_system(db, "test")
        found = DecisionCenterService()._latest(db, tenant_id, case_id, ORCHESTRATION)
    return found and (found["execution_id"], found["output"].get("summary"))


def _review(client, row_id, **body):
    return client.post(f"/api/v1/ai-outputs/{row_id}/review", json=body)


def test_an_unreviewed_model_result_is_not_used_and_an_accepted_one_is(monkeypatch):
    client = authenticated_client()
    row_id = _model_result("MODEL SUMMARY A")
    try:
        # Unreviewed: the Decision Center does not see it (the rules' or an older reviewed result stands).
        assert _latest_summary() is None or _latest_summary()[0] != str(row_id)
        accepted = _review(client, row_id, decision="ACCEPTED")
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["decision"] == "ACCEPTED" and accepted.json()["reviewer"]
        assert _latest_summary() == (str(row_id), "MODEL SUMMARY A")
        with SessionLocal() as db:
            bind_system(db, "test")
            event = (
                db.query(AuditEvent)
                .filter(AuditEvent.action == "AI_OUTPUT_REVIEWED", AuditEvent.entity_id == row_id)
                .one()
            )
            assert event.details["decision"] == "ACCEPTED" and len(event.details["output_sha256"]) == 64
    finally:
        # Leave it rejected, so no later test reads it as the case's analysis.
        _review(client, row_id, decision="REJECTED", reason="Test cleanup: not this case's analysis")


def test_an_edit_uses_the_persons_text_and_keeps_the_models_in_history():
    client = authenticated_client()
    row_id = _model_result("MODEL SUMMARY B")
    try:
        assert _review(client, row_id, decision="EDITED", edited_text="x").status_code == 422  # no reason
        edited = _review(
            client,
            row_id,
            decision="EDITED",
            edited_text=json.dumps({"summary": "PERSON'S SUMMARY"}),
            reason="Removed an unsupported claim",
        )
        assert edited.status_code == 200, edited.text
        assert _latest_summary() == (str(row_id), "PERSON'S SUMMARY")
        with SessionLocal() as db:
            bind_system(db, "test")
            assert db.get(AIExecution, row_id).structured_output == {"summary": "MODEL SUMMARY B"}
        history = authenticated_client().get(f"/api/v1/ai-outputs/{row_id}/reviews").json()
        assert history["state"] == "EDITED" and history["items"][0]["edited_text"]
    finally:
        _review(client, row_id, decision="REJECTED", reason="Test cleanup: not this case's analysis")


def test_a_rejected_result_is_never_used_and_reviews_are_append_only():
    client = authenticated_client()
    row_id = _model_result("MODEL SUMMARY C")
    assert _review(client, row_id, decision="REJECTED").status_code == 422  # a rejection needs a reason
    assert _review(client, row_id, decision="ACCEPTED").status_code == 200
    assert _review(client, row_id, decision="REJECTED", reason="States a root cause as fact").status_code == 200
    latest = _latest_summary()
    assert latest is None or latest[0] != str(row_id)
    with SessionLocal() as db:
        bind_system(db, "test")
        rows = db.query(AiOutputReview).filter(AiOutputReview.subject_id == str(row_id)).all()
        assert sorted(row.decision for row in rows) == ["ACCEPTED", "REJECTED"]
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("UPDATE ai_output_reviews SET reason = 'x' WHERE id = :id"), {"id": rows[0].id})
            db.flush()


def test_another_organizations_output_or_an_unknown_one_is_not_found():
    assert _review(authenticated_client(), uuid.uuid4(), decision="ACCEPTED").status_code == 404


def test_opening_a_case_page_starts_no_ai_run(monkeypatch):
    monkeypatch.setattr("backend.app.ai_settings.ai_ready", lambda db, tenant_id: True)
    case_id, _ = _case()
    path = f"/api/v1/investigations/{case_id}/ai-run"
    client = authenticated_client()
    before = client.get(path).json()["run"]
    opened = client.post(path, json={"trigger": "AUTO"})
    assert opened.status_code == 200 and opened.json() == {
        "started": False,
        "run": before,
        "reason": "ON_REQUEST_ONLY",
    }
    assert client.get(path).json()["run"] == before


class _Reply(io.BytesIO):
    headers: dict = {}

    def __init__(self):
        super().__init__(json.dumps({"choices": [{"message": {"content": "advice"}}], "usage": {}}).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_the_decision_advisory_is_not_offered_and_its_row_names_no_rules_model(monkeypatch):
    sent = []
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_API_KEY", "dev-key")
    monkeypatch.setenv("MDARIX_AI_FEATURES", ",".join(FEATURES))
    monkeypatch.delenv("MDARIX_AI_TRIAL_CHAIN", raising=False)
    monkeypatch.setattr(
        provider_module.request, "urlopen", lambda req, timeout=None: sent.append(req.full_url) or _Reply()
    )
    case_id, tenant_id = _case()
    with SessionLocal() as db:
        bind_system(db, "test")
        tenant = db.get(Tenant, tenant_id)
        saved = (tenant.ai_processing_allowed, dict(tenant.ai_features or {}))
        tenant.ai_processing_allowed, tenant.ai_features = True, dict.fromkeys(FEATURES, True)
        db.commit()
    try:
        response = authenticated_client().post(
            f"/api/v1/investigations/{case_id}/decision-advisory", json={"temporal_mode": "current"}
        )
        assert response.status_code == 200, response.text
        advisory = response.json()["advisory"]["ai_advisory"]
        assert advisory["status"] == "REFUSED" and advisory["code"] == "GENAI_FEATURE_NOT_OFFERED"
        assert sent == []
        with SessionLocal() as db:
            bind_system(db, "test")
            row = (
                db.query(AIExecution)
                .filter(AIExecution.investigation_id == case_id, AIExecution.orchestration_version.like("%Decision%"))
                .order_by(AIExecution.execution_timestamp.desc())
                .first()
            )
            assert (row.provider, row.model_name) == ("none", "none")
    finally:
        with SessionLocal() as db:
            bind_system(db, "test")
            tenant = db.get(Tenant, tenant_id)
            tenant.ai_processing_allowed, tenant.ai_features = saved
            db.commit()
