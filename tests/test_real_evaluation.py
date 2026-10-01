"""The honest golden evaluation scores the pipeline's real output, and catches what it should."""

from backend.app.db.session import SessionLocal
from evaluation.harness import load_scenarios
from evaluation.real_pipeline import _investigation_evidence, _Matcher, run_pipeline, score
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
    assert result["specific_expectations"] == 6
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
