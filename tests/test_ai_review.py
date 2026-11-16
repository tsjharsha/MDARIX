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


def _model_observations(row_id, count: int) -> tuple[uuid.UUID, list[tuple[uuid.UUID, str]]]:
    """``count`` observations one model extraction (``row_id``) proposed on the case's evidence."""
    from backend.app.db.models.evidence_intelligence import EvidenceObservation

    case_id, tenant_id = _case()
    made = [(uuid.uuid4(), f"MODEL OBSERVATION {uuid.uuid4().hex[:8]}") for _ in range(count)]
    with SessionLocal() as db:
        bind_system(db, "test")
        evidence_id = db.execute(
            text("SELECT id FROM evidence WHERE tenant_id = :t LIMIT 1"), {"t": tenant_id}
        ).scalar()
        for observation_id, statement in made:
            db.add(
                EvidenceObservation(
                    id=observation_id,
                    tenant_id=tenant_id,
                    evidence_id=evidence_id,
                    investigation_id=case_id,
                    statement=statement,
                    observation_type="EXPLICIT_SOURCE_STATEMENT",
                    extraction_method="GENAI",
                    ai_execution_id=row_id,
                )
            )
        db.commit()
    return case_id, made


def _brief_facts(case_id) -> list[str]:
    from backend.app.db.models.foundation import Investigation
    from backend.app.decision_brief import compose

    with SessionLocal() as db:
        bind_system(db, "test")
        return [item["statement"] for item in compose.facts_section(db, db.get(Investigation, case_id), [])]


def test_each_observation_a_model_proposed_is_reviewed_on_its_own_before_it_feeds_the_brief():
    client = authenticated_client()
    row_id = _model_result("MODEL EXTRACTION")
    case_id, made = _model_observations(row_id, 3)
    (accepted, accepted_text), (edited, edited_text), (rejected, rejected_text) = made
    statements = {text_ for _, text_ in made}
    try:
        assert not statements & set(_brief_facts(case_id)), "an unreviewed observation never feeds the brief"
        listed = client.get(f"/api/v1/investigations/{case_id}/intelligence/observations?page_size=200")
        assert listed.status_code == 200, listed.text
        mine = {item["id"]: item for item in listed.json()["items"] if item["statement"] in statements}
        assert len(mine) == 3
        assert {item["ai_label"] for item in mine.values()} == {"AI proposal, not reviewed"}
        assert {item["ai_review_state"] for item in mine.values()} == {"NOT_REVIEWED"}
        # Accepting the extraction run as a whole does not make its observations evidence.
        assert _review(client, row_id, decision="ACCEPTED").status_code == 200
        assert not statements & set(_brief_facts(case_id))
        # One by one: accept one, edit one, reject one.
        assert _review(client, accepted, decision="ACCEPTED").status_code == 200
        person = "The person's own reading of the evidence."
        assert (
            _review(client, edited, decision="EDITED", edited_text=person, reason="Model overstated it").status_code
            == 200
        )
        assert _review(client, rejected, decision="REJECTED", reason="Not in the source document").status_code == 200
        facts = _brief_facts(case_id)
        assert accepted_text in facts and person in facts
        assert edited_text not in facts and rejected_text not in facts
        states = {
            item["id"]: (item["ai_review_state"], item["ai_label"])
            for item in client.get(f"/api/v1/investigations/{case_id}/intelligence/observations?page_size=200").json()[
                "items"
            ]
            if item["id"] in mine
        }
        assert states == {
            str(accepted): ("ACCEPTED", None),
            str(edited): ("EDITED", None),
            str(rejected): ("REJECTED", None),
        }
        history = client.get(f"/api/v1/ai-outputs/{edited}/reviews").json()
        assert history["state"] == "EDITED" and history["items"][0]["subject_type"] == "evidence_observation"
    finally:
        _review(client, row_id, decision="REJECTED", reason="Test cleanup: not this case's extraction")
        for observation_id, _ in made:
            _review(client, observation_id, decision="REJECTED", reason="Test cleanup: not this case's extraction")


def test_an_observation_a_person_wrote_is_not_an_ai_output():
    from backend.app.db.models.evidence_intelligence import EvidenceObservation

    case_id, tenant_id = _case()
    human = uuid.uuid4()
    with SessionLocal() as db:
        bind_system(db, "test")
        evidence_id = db.execute(
            text("SELECT id FROM evidence WHERE tenant_id = :t LIMIT 1"), {"t": tenant_id}
        ).scalar()
        db.add(
            EvidenceObservation(
                id=human,
                tenant_id=tenant_id,
                evidence_id=evidence_id,
                investigation_id=case_id,
                statement="Written by the investigator.",
                observation_type="EXPLICIT_SOURCE_STATEMENT",
                extraction_method="HUMAN",
            )
        )
        db.commit()
    response = _review(authenticated_client(), human, decision="ACCEPTED")
    assert response.status_code == 404 and response.json()["detail"]["code"] == "AI_OUTPUT_NOT_FOUND"


def test_a_case_ai_run_step_the_model_wrote_carries_its_review_state():
    from backend.app.case_ai import runner
    from backend.app.db.models.case_ai import CaseAiRun

    client = authenticated_client()
    row_id = _model_result("MODEL RUN STEP")
    case_id, tenant_id = _case()
    run = CaseAiRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case_id,
        status="COMPLETED",
        trigger="MANUAL",
        as_of=datetime.now(timezone.utc),
        requested_by="test",
        steps=[
            {"step": "ANALYSIS", "status": "DONE", "author": "AI", "ai_execution_id": str(row_id)},
            {"step": "UNKNOWNS", "status": "DONE", "author": "RULES", "ai_execution_id": None},
        ],
    )

    def steps():
        with SessionLocal() as db:
            bind_system(db, "test")
            return {item["step"]: item for item in runner.view(run, db)["steps"]}

    try:
        assert steps()["ANALYSIS"]["review_state"] == "NOT_REVIEWED"
        assert "review_state" not in steps()["UNKNOWNS"], "a step the rules wrote needs no review"
        assert _review(client, row_id, decision="ACCEPTED").status_code == 200
        assert steps()["ANALYSIS"]["review_state"] == "ACCEPTED"
    finally:
        _review(client, row_id, decision="REJECTED", reason="Test cleanup: not this case's analysis")


def test_a_second_look_explanation_carries_its_review_state():
    from backend.app.complaint_review import explain

    client = authenticated_client()
    _, tenant_id = _case()
    complaint_id = str(uuid.uuid4())
    row_id = uuid.uuid4()
    with SessionLocal() as db:
        bind_system(db, "test")
        db.add(
            AIExecution(
                id=row_id,
                tenant_id=tenant_id,
                requestor_ref="test",
                provider=explain.PROVIDER,
                model_name="test-model",
                model_version="1",
                prompt_template_version=explain.VERSION,
                orchestration_version=explain.VERSION,
                context_refs={"complaint_id": complaint_id},
                evidence_refs={},
                structured_input={},
                structured_output={"sentences": [{"text": "It names an injury.", "quotes": []}]},
                validation_status="VALIDATED",
                execution_timestamp=datetime.now(timezone.utc),
            )
        )
        db.commit()

    def state():
        with SessionLocal() as db:
            bind_system(db, "test")
            return explain.latest(db, tenant_id, [complaint_id])[complaint_id]["ai"]["review_state"]

    assert state() == "NOT_REVIEWED"
    assert (
        _review(client, row_id, decision="EDITED", edited_text="It names a burn.", reason="Be precise").status_code
        == 200
    )
    assert state() == "EDITED"


def test_the_case_record_labels_a_model_result_until_a_person_reviews_it():
    from reports.content import investigation_record

    client = authenticated_client()
    row_id = _model_result("MODEL SUMMARY LABEL")
    case_id, tenant_id = _case()

    def label():
        with SessionLocal() as db:
            bind_system(db, "test")
            rows = investigation_record(db, tenant_id, case_id)["ai_executions"]
            return next(item["ai_label"] for item in rows if item["id"] == str(row_id))

    try:
        assert label() == "AI proposal, not reviewed"
        assert _review(client, row_id, decision="ACCEPTED").status_code == 200
        assert label() is None
    finally:
        _review(client, row_id, decision="REJECTED", reason="Test cleanup: not this case's analysis")


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
