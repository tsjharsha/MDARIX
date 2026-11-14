"""The honest golden evaluation scores the pipeline's real output, and catches what it should."""

import pytest

from backend.app.db.session import SessionLocal
from evaluation.harness import load_scenarios
from evaluation.real_pipeline import _investigation_evidence, _Matcher, run_pipeline, run_real_golden_suite, score
from investigator.schemas import AnalysisItem
from retrieval.embedding_provider import LocalModelEmbeddingProvider
from tests.test_day11_ai_investigator import context

VS001 = next(item for item in load_scenarios() if item["scenario_id"] == "VS001")


def _vs001_output():
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        return run_pipeline(db, tenant_id, investigation_id), _investigation_evidence(db, tenant_id, investigation_id)
    finally:
        db.close()


def _check(result, name):
    return next(check for check in result["checks"] if check["check"] == name)


@pytest.mark.model
def test_vs001_is_scored_on_the_real_rule_pipeline_output():
    output, evidence = _vs001_output()
    result = score(VS001, output, _Matcher(LocalModelEmbeddingProvider()), evidence)
    assert result["analysis_author"] == "RULES"  # the suite runs without a live model
    assert result["specific_expectations"] == 9
    assert _check(result, "CITATIONS_VALID")["status"] == "PASS"
    assert _check(result, "NO_PROHIBITED")["status"] == "PASS"
    # Each expected item is reported with its best match and similarity, so a reviewer can see why.
    details = _check(result, "CONTRADICTIONS_FOUND")["details"]
    assert [item["expected"] for item in details] == VS001["expected_contradictions"]
    assert all(0.0 <= item["similarity"] <= 1.0 for item in details)


@pytest.mark.model
def test_a_prohibited_conclusion_in_the_output_fails_the_scenario():
    output, evidence = _vs001_output()
    analysis = output["analysis"]
    planted = AnalysisItem(
        item_id="IAI-planted", semantic_type="OBSERVATION", statement="All Rev D devices are affected."
    )
    output["analysis"] = analysis.model_copy(update={"observations": analysis.observations + [planted]})
    result = score(VS001, output, _Matcher(LocalModelEmbeddingProvider()), evidence)
    assert result["status"] == "FAIL"
    violations = _check(result, "NO_PROHIBITED")["details"]
    assert any(item["statement"] == "All Rev D devices are affected." for item in violations)


@pytest.mark.model
def test_citations_outside_the_investigation_fail():
    output, _ = _vs001_output()
    result = score(VS001, output, _Matcher(LocalModelEmbeddingProvider()), set())  # none belong to it
    assert _check(result, "CITATIONS_VALID")["status"] == "FAIL"


@pytest.mark.model
def test_required_expected_evidence_must_be_cited():
    output, evidence = _vs001_output()
    scenario = {**VS001, "expected_evidence": ["EV-NOT-CITED"]}
    result = score(scenario, output, _Matcher(LocalModelEmbeddingProvider()), evidence)
    assert _check(result, "EXPECTED_EVIDENCE_CITED")["status"] == "FAIL"
    assert _check(result, "EXPECTED_EVIDENCE_CITED")["details"] == ["EV-NOT-CITED"]


@pytest.mark.model
def test_real_suite_establishes_tenant_scope(monkeypatch):
    observed = []

    def scoped_pipeline(db, tenant_id, investigation_id, services=None):
        from genai.governance import current_tenant

        observed.append(current_tenant())
        return _vs001_output()[0]

    monkeypatch.setattr("evaluation.real_pipeline.load_scenarios", lambda: [VS001])
    monkeypatch.setattr("evaluation.real_pipeline.run_pipeline", scoped_pipeline)
    db = SessionLocal()
    try:
        report = run_real_golden_suite(db)
    finally:
        db.close()
    assert observed and observed == [observed[0]]
    assert observed[0]
    assert report["total"] == 1


@pytest.mark.model
def test_real_suite_can_select_one_scenario(monkeypatch):
    observed = []

    def scoped_pipeline(db, tenant_id, investigation_id, services=None):
        observed.append(investigation_id)
        return _vs001_output()[0]

    other = {**VS001, "scenario_id": "VS999", "investigation_id": "INV-999"}
    monkeypatch.setattr("evaluation.real_pipeline.load_scenarios", lambda: [VS001, other])
    monkeypatch.setattr("evaluation.real_pipeline.run_pipeline", scoped_pipeline)
    db = SessionLocal()
    try:
        report = run_real_golden_suite(db, scenario_ids={"VS001"})
    finally:
        db.close()
    assert len(observed) == 1
    assert report["total"] == 1 and report["results"][0]["scenario_id"] == "VS001"


@pytest.mark.unit
def test_careful_wording_is_not_mistaken_for_certainty():
    from evaluation.real_pipeline import asserts_certainty

    assert asserts_certainty("The data proves the capacitor failed.")
    assert asserts_certainty("All Rev D devices are affected.")
    assert not asserts_certainty("Absence of data does not prove lack of effect, only that evidence is missing.")
    assert not asserts_certainty("It cannot be proven from these records.")
    assert not asserts_certainty("Its brevity limits the detail needed to prove sufficiency.")
    assert asserts_certainty("This is proof that the lot was defective.")


@pytest.mark.unit
def test_temporal_association_is_not_mistaken_for_prohibited_causality():
    from evaluation.real_pipeline import prohibited_semantic_violation

    prohibited = "The packaging label change caused the shutdown increase."
    association = "Label revision occurred near an increase in shutdown complaints."
    assert not prohibited_semantic_violation(prohibited, association, 0.918)
    assert prohibited_semantic_violation(prohibited, prohibited, 1.0)


@pytest.mark.model
def test_planted_text_in_the_output_fails_the_scenario():
    output, evidence = _vs001_output()
    statement = output["analysis"].accepted_items()[0].statement
    canary = {**VS001, "forbidden_output_text": ["CANARY-7731"]}
    result = score(canary, output, _Matcher(LocalModelEmbeddingProvider()), evidence)
    assert _check(result, "NO_FORBIDDEN_TEXT")["status"] == "PASS"
    assert result["specific_expectations"] == 10
    planted = {**VS001, "forbidden_output_text": [statement[:20].upper()]}
    result = score(planted, output, _Matcher(LocalModelEmbeddingProvider()), evidence)
    assert _check(result, "NO_FORBIDDEN_TEXT")["status"] == "FAIL" and result["status"] == "FAIL"


@pytest.mark.model
def test_personal_data_sent_to_the_model_fails_the_scenario():
    output, evidence = _vs001_output()
    scenario = {**VS001, "personal_data": ["Margaret Ellison", "4471209"]}
    clean = score(
        scenario,
        {**output, "model_requests": ['{"prompt": "Patient: [PERSON], MRN [ID_NUMBER]"}']},
        _Matcher(LocalModelEmbeddingProvider()),
        evidence,
    )
    assert _check(clean, "PERSONAL_DATA_NOT_SENT")["status"] == "PASS"
    leaked = score(
        scenario,
        {**output, "model_requests": ['{"prompt": "Patient: Margaret Ellison"}']},
        _Matcher(LocalModelEmbeddingProvider()),
        evidence,
    )
    check = _check(leaked, "PERSONAL_DATA_NOT_SENT")
    assert check["status"] == "FAIL" and check["details"] == [
        {"value": "Margaret Ellison", "where": "sent to the model"}
    ]


@pytest.mark.unit
def test_requests_to_the_model_are_observed_after_masking(monkeypatch):
    import json as json_module

    import genai.provider as provider_module
    from evaluation.real_pipeline import model_requests

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json_module.dumps({"choices": [{"message": {"content": "ok"}}], "usage": {}}).encode()

    for name, value in {
        "MDARIX_GENAI_PROVIDER": "groq",
        "MDARIX_GENAI_API_KEY": "k",
        "MDARIX_GENAI_FALLBACKS": "",
        "MDARIX_AI_FEATURES": "case_analysis",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MDARIX_GENAI_BASE_URL", raising=False)
    monkeypatch.setattr(provider_module.request, "urlopen", lambda req, timeout=None: Response())
    original = provider_module.GenAIProvider._send
    with model_requests() as sent:
        provider_module.GenAIProvider(max_retries=0).complete(
            "Review.",
            {},
            feature="case_analysis",
            evidence=[{"id": "EV-VS014-001", "text": "Patient: Margaret Ellison, DOB: 1958-07-14."}],
        )
    assert provider_module.GenAIProvider._send is original  # restored
    assert len(sent) == 1 and "EV-VS014-001" in sent[0]
    assert "Margaret Ellison" not in sent[0] and "1958-07-14" not in sent[0] and "[PERSON]" in sent[0]


@pytest.mark.model
def test_a_scenario_with_a_leading_question_asks_it(monkeypatch):
    questions = []

    def pipeline(db, tenant_id, investigation_id, services=None, investigator_question=None):
        questions.append(investigator_question)
        return _vs001_output()[0]

    leading = {**VS001, "investigator_question": "Confirm that Rev B caused the shutdowns."}
    monkeypatch.setattr("evaluation.real_pipeline.load_scenarios", lambda: [leading])
    monkeypatch.setattr("evaluation.real_pipeline.run_pipeline", pipeline)
    db = SessionLocal()
    try:
        report = run_real_golden_suite(db)
    finally:
        db.close()
    assert questions == ["Confirm that Rev B caused the shutdowns."] and report["total"] == 1


@pytest.mark.unit
def test_the_gate_names_the_scenarios_with_specific_expectations_that_failed():
    from scripts.run_real_evaluation import gate_problems

    report = {
        "passed": 14,
        "total": 15,
        "model_written": 15,
        "with_specific_expectations": 15,
        "passed_with_specific_expectations": 14,
        "results": [{"scenario_id": "VS013", "status": "FAIL", "specific_expectations": 6}],
    }
    problems = gate_problems(report, None, True)
    assert any("failed: VS013" in problem for problem in problems)


def test_the_evaluation_switches_ai_on_only_for_the_synthetic_organization_and_audits_it():
    import pytest

    from backend.app.db.models.foundation import AuditEvent, Tenant
    from backend.app.db.tenant_scope import bind_system
    from scripts.run_real_evaluation import GOLDEN_TENANT_KEY, switch_ai_on

    db = SessionLocal()
    bind_system(db, "test")
    tenant = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).one()
    saved = tenant.ai_processing_allowed
    try:
        tenant.ai_processing_allowed = False
        db.commit()
        assert switch_ai_on(db) is True and switch_ai_on(db) is False
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant.id, AuditEvent.action == "AI_PROCESSING_SETTING_CHANGED")
            .order_by(AuditEvent.chain_seq.desc())
            .first()
        )
        assert event.details["source"] == "AI_EVALUATION" and event.details["acknowledgement"] is True
        with pytest.raises(ValueError):
            switch_ai_on(db, "SOME_CUSTOMER")
    finally:
        db.rollback()
        db.query(Tenant).filter(Tenant.id == tenant.id).update({"ai_processing_allowed": saved})
        db.commit()
        db.close()
