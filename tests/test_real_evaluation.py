"""The honest golden evaluation scores the pipeline's real output, and catches what it should."""

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


def test_citations_outside_the_investigation_fail():
    output, _ = _vs001_output()
    result = score(VS001, output, _Matcher(LocalModelEmbeddingProvider()), set())  # none belong to it
    assert _check(result, "CITATIONS_VALID")["status"] == "FAIL"


def test_required_expected_evidence_must_be_cited():
    output, evidence = _vs001_output()
    scenario = {**VS001, "expected_evidence": ["EV-NOT-CITED"]}
    result = score(scenario, output, _Matcher(LocalModelEmbeddingProvider()), evidence)
    assert _check(result, "EXPECTED_EVIDENCE_CITED")["status"] == "FAIL"
    assert _check(result, "EXPECTED_EVIDENCE_CITED")["details"] == ["EV-NOT-CITED"]


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


def test_careful_wording_is_not_mistaken_for_certainty():
    from evaluation.real_pipeline import asserts_certainty

    assert asserts_certainty("The data proves the capacitor failed.")
    assert asserts_certainty("All Rev D devices are affected.")
    assert not asserts_certainty("Absence of data does not prove lack of effect, only that evidence is missing.")
    assert not asserts_certainty("It cannot be proven from these records.")
    assert not asserts_certainty("Its brevity limits the detail needed to prove sufficiency.")
    assert asserts_certainty("This is proof that the lot was defective.")


def test_temporal_association_is_not_mistaken_for_prohibited_causality():
    from evaluation.real_pipeline import prohibited_semantic_violation

    prohibited = "The packaging label change caused the shutdown increase."
    association = "Label revision occurred near an increase in shutdown complaints."
    assert not prohibited_semantic_violation(prohibited, association, 0.918)
    assert prohibited_semantic_violation(prohibited, prohibited, 1.0)
