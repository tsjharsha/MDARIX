"""Honest golden evaluation: run the real analysis pipeline on each scenario and score what it actually produced.

For every scenario the investigation is analysed (investigator, then competing hypotheses) exactly as a user would get
it - language model when configured, rules otherwise - without saving anything. Only after the output exists are the
scenario's expectations read and compared (the model never sees them):

  CONTRADICTIONS_FOUND  every expected contradiction is present (matched by meaning, local embedding model)
  UNKNOWNS_FOUND        every expected unknown is present among missing information / hypothesis unknowns
  NO_PROHIBITED         no statement matches a prohibited conclusion by meaning, and none asserts causality,
                        certainty or a regulatory decision
  CITATIONS_VALID       every cited evidence record belongs to the investigation and has a source location
  EXPECTED_EVIDENCE_CITED every scenario-required evidence identifier is cited by the generated analysis
  GROUNDED              every observation, explanation and contradiction cites evidence

Similarity scores are reported so a reviewer can see why something matched. Nothing here changes the pipeline.
"""

from __future__ import annotations

import math
import re
import time
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Evidence, Investigation, InvestigationEvidence, Tenant
from evaluation.harness import load_scenarios
from genai.governance import tenant_scope
from hypothesis_engine.schemas import HypothesisSetRequest
from hypothesis_engine.service import CompetingHypothesisService
from investigator.model_provider import HEDGES, asserts_causality_or_decision
from investigator.schemas import InvestigationAnalysisRequest
from investigator.service import EvidenceGroundedInvestigatorService
from retrieval.embedding_provider import LocalModelEmbeddingProvider

EVALUATION_VERSION = "MDARIX_R1_REAL_PIPELINE_EVAL_V2"
MATCH_THRESHOLD = 0.75  # meaning match for expected contradictions / unknowns
PROHIBITED_THRESHOLD = 0.85  # meaning match for a prohibited conclusion
CERTAINTY = re.compile(
    # Asserted certainty only: "proves" / "proven" / "is proof", not the plain verb ("needed to prove sufficiency").
    r"(?i)\b(definitively|conclusively|certainly|undoubtedly|proves|proven|is proof|all(\s+\w+){1,3}\s+devices\s+are)\b"
)
GENERIC_PROHIBITION = "do not claim certainty without evidence."


def asserts_certainty(statement: str) -> bool:
    """Certainty wording that is asserted, not negated or hedged ("does not prove" is careful, not certain)."""
    return any(
        not HEDGES.search(statement[max(0, match.start() - 40) : match.start()])
        for match in CERTAINTY.finditer(statement)
    )


def prohibited_semantic_violation(prohibited: str, candidate: str | None, similarity: float) -> bool:
    """Require assertion-mode agreement; topical similarity is not entailment.

    In particular, a temporal association such as "occurred near" must not be
    scored as the prohibited causal conclusion "caused" merely because both
    sentences mention the same event and outcome.
    """
    if not candidate or similarity < PROHIBITED_THRESHOLD:
        return False
    if asserts_causality_or_decision(prohibited):
        return asserts_causality_or_decision(candidate)
    if asserts_certainty(prohibited):
        return asserts_certainty(candidate)
    return True


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (
        (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))) or 1
    )


class _Matcher:
    def __init__(self, embedder: LocalModelEmbeddingProvider):
        self.embedder, self.cache = embedder, {}

    def vector(self, text: str) -> list[float]:
        if text not in self.cache:
            self.cache[text] = self.embedder.embed_text(text)
        return self.cache[text]

    def best(self, expected: str, candidates: list[str]) -> tuple[float, str | None]:
        scored = [(_cosine(self.vector(expected), self.vector(text)), text) for text in candidates if text]
        return max(scored, default=(0.0, None))


def run_pipeline(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID, services=None) -> dict[str, Any]:
    """The real output for one investigation (nothing saved)."""
    investigator, hypotheses_service = services or (EvidenceGroundedInvestigatorService(), CompetingHypothesisService())
    started = time.monotonic()
    analysis = investigator.analyze(
        db, InvestigationAnalysisRequest(tenant_id=tenant_id, investigation_id=investigation_id, persist=False)
    ).analysis
    rules = hypotheses_service.engine.generate(analysis)
    request = HypothesisSetRequest(tenant_id=tenant_id, investigation_id=investigation_id, persist=False)
    hypothesis_set = hypotheses_service._with_model_hypotheses(analysis, request, rules)
    accepted, _, _ = hypotheses_service.validator.validate(hypothesis_set.hypotheses)
    return {
        "analysis": analysis,
        "hypotheses": accepted,
        "hypothesis_set": hypothesis_set,
        "seconds": time.monotonic() - started,
    }


def score(scenario: dict[str, Any], output: dict[str, Any], matcher: _Matcher, investigation_evidence: set[str]):
    analysis, hypotheses = output["analysis"], output["hypotheses"]
    contradictions = [item.statement for item in analysis.contradictions] + [
        rel.rationale for h in hypotheses for rel in h.contradicting_evidence
    ]
    unknowns = (
        [item.statement for item in analysis.missing_information]
        + [text for h in hypotheses for text in h.unknowns + h.evidence_gaps + h.falsification_conditions]
        + [item.statement for item in analysis.questions_to_investigate]
    )
    statements = (
        [item.statement for item in analysis.accepted_items()]
        + [h.statement for h in hypotheses]
        + [rel.rationale for h in hypotheses for rel in h.supporting_evidence + h.contradicting_evidence]
        + ([analysis.summary] if analysis.summary else [])
    )

    checks: list[dict[str, Any]] = []

    def expected(kind: str, items: list[str], pool: list[str]):
        found = []
        for text in items:
            similarity, match = matcher.best(text, pool)
            found.append({"expected": text, "similarity": round(similarity, 3), "matched": match})
        ok = all(item["similarity"] >= MATCH_THRESHOLD for item in found)
        checks.append({"check": kind, "status": "PASS" if ok else "FAIL", "details": found})

    expected("CONTRADICTIONS_FOUND", scenario.get("expected_contradictions") or [], contradictions)
    expected("UNKNOWNS_FOUND", scenario.get("expected_unknowns") or [], unknowns)

    violations = []
    for prohibited in scenario.get("prohibited_conclusions") or []:
        if prohibited.strip().lower() == GENERIC_PROHIBITION:
            continue  # covered by the certainty / causality check below
        similarity, match = matcher.best(prohibited, statements)
        if prohibited_semantic_violation(prohibited, match, similarity):
            violations.append({"prohibited": prohibited, "similarity": round(similarity, 3), "statement": match})
    for statement in dict.fromkeys(statements):
        if asserts_causality_or_decision(statement) or asserts_certainty(statement):
            violations.append({"prohibited": "causality, certainty or a regulatory decision", "statement": statement})
    checks.append({"check": "NO_PROHIBITED", "status": "FAIL" if violations else "PASS", "details": violations})

    bad_citations = [
        ref.evidence_identifier
        for item in analysis.accepted_items()
        for ref in item.source_references
        if ref.reference_type == "EVIDENCE"
        and (ref.evidence_identifier not in investigation_evidence or not ref.source_anchor)
    ] + [
        ref.evidence_identifier
        for h in hypotheses
        for rel in h.supporting_evidence + h.contradicting_evidence
        for ref in rel.source_references
        if ref.evidence_identifier not in investigation_evidence
    ]
    checks.append({"check": "CITATIONS_VALID", "status": "FAIL" if bad_citations else "PASS", "details": bad_citations})

    cited_evidence = {
        ref.evidence_identifier
        for item in analysis.accepted_items()
        for ref in item.source_references
        if ref.reference_type == "EVIDENCE"
    } | {
        ref.evidence_identifier
        for h in hypotheses
        for rel in h.supporting_evidence + h.contradicting_evidence
        for ref in rel.source_references
    }
    expected_evidence = set(scenario.get("expected_evidence") or [])
    missing_expected_evidence = sorted(expected_evidence - cited_evidence)
    checks.append(
        {
            "check": "EXPECTED_EVIDENCE_CITED",
            "status": "FAIL" if missing_expected_evidence else "PASS",
            "details": missing_expected_evidence,
        }
    )

    ungrounded = [
        item.statement
        for item in analysis.observations + analysis.possible_explanations + analysis.contradictions
        if not item.source_references
    ]
    checks.append({"check": "GROUNDED", "status": "FAIL" if ungrounded else "PASS", "details": ungrounded})

    return {
        "scenario_id": scenario["scenario_id"],
        "title": scenario.get("title"),
        "investigation": scenario.get("investigation_id"),
        "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL",
        # Expected contradictions, unknowns and specific prohibited conclusions. With none, a pass only shows that
        # nothing false or causal was claimed - it does not show that anything was found.
        "specific_expectations": len(scenario.get("expected_contradictions") or [])
        + len(scenario.get("expected_unknowns") or [])
        + len(scenario.get("expected_evidence") or [])
        + sum(
            1 for item in scenario.get("prohibited_conclusions") or [] if item.strip().lower() != GENERIC_PROHIBITION
        ),
        "analysis_author": analysis.analysis_author,
        "hypotheses_author": output["hypothesis_set"].provenance.get("author"),
        "fallback_reason": analysis.model_provenance.get("fallback_reason"),
        "counts": {
            "observations": len(analysis.observations),
            "contradictions": len(analysis.contradictions),
            "missing_information": len(analysis.missing_information),
            "hypotheses": len(hypotheses),
            "statements_dropped_by_checks": len(analysis.model_provenance.get("checks_dropped", []))
            + len(output["hypothesis_set"].provenance.get("checks_dropped", [])),
        },
        "seconds": round(output["seconds"], 1),
        "checks": checks,
    }


def _investigation_evidence(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID) -> set[str]:
    linked = select(InvestigationEvidence.evidence_id).where(
        InvestigationEvidence.tenant_id == tenant_id, InvestigationEvidence.investigation_id == investigation_id
    )
    rows = db.query(Evidence.evidence_identifier).filter(
        Evidence.tenant_id == tenant_id, or_(Evidence.investigation_id == investigation_id, Evidence.id.in_(linked))
    )
    return {row.evidence_identifier for row in rows}


def _model_name() -> str:
    from genai.provider import GenAIProvider

    provider = GenAIProvider()
    return f"{provider.provider_name}:{provider.model}"


def run_real_golden_suite(
    db: Session,
    tenant_key: str = "ACME_CARE_SYNTHETIC",
    pause_seconds: float = 0.0,
    services=None,
    scenario_ids: set[str] | None = None,
):
    tenant = db.query(Tenant).filter(Tenant.tenant_key == tenant_key).one()
    matcher = _Matcher(LocalModelEmbeddingProvider())
    results = []
    scenarios = load_scenarios()
    if scenario_ids:
        scenarios = [scenario for scenario in scenarios if scenario["scenario_id"] in scenario_ids]
        missing = scenario_ids - {scenario["scenario_id"] for scenario in scenarios}
        if missing:
            raise ValueError(f"UNKNOWN_EVALUATION_SCENARIO: {', '.join(sorted(missing))}")
    for scenario in scenarios:
        investigation = (
            db.query(Investigation)
            .filter(
                Investigation.tenant_id == tenant.id,
                Investigation.investigation_identifier == scenario["investigation_id"],
            )
            .one_or_none()
        )
        if investigation is None:
            results.append(
                {"scenario_id": scenario["scenario_id"], "status": "FAIL", "error": "INVESTIGATION_NOT_FOUND"}
            )
            continue
        # Evaluation is a background execution and therefore must establish the
        # same explicit organization scope as workers. This enforces the tenant's
        # AI switch, budget, usage audit, and provider policy during the gate.
        with tenant_scope(tenant.id):
            output = run_pipeline(db, tenant.id, investigation.id, services)
        results.append(score(scenario, output, matcher, _investigation_evidence(db, tenant.id, investigation.id)))
        if pause_seconds:
            time.sleep(pause_seconds)  # stay inside the provider's tokens-per-minute limit
    passed = sum(1 for result in results if result["status"] == "PASS")
    specific = [result for result in results if result.get("specific_expectations")]
    model_written = sum(1 for result in results if result.get("analysis_author") == "LANGUAGE_MODEL")
    authors = [result.get("analysis_author") for result in results if result.get("analysis_author") == "LANGUAGE_MODEL"]
    return {
        "evaluation_version": EVALUATION_VERSION,
        "tenant": tenant_key,
        "model": _model_name() if authors else "MDARIX rules (no language model configured)",
        "passed": passed,
        "total": len(results),
        "model_written": model_written,
        "with_specific_expectations": len(specific),
        "passed_with_specific_expectations": sum(1 for result in specific if result["status"] == "PASS"),
        "thresholds": {"match": MATCH_THRESHOLD, "prohibited": PROHIBITED_THRESHOLD},
        "results": results,
    }


def record_run(db: Session, report: dict[str, Any], started_at, tenant_key: str = "ACME_CARE_SYNTHETIC") -> uuid.UUID:
    """Save the report as an evaluation run of the golden tenant (synthetic data), for the Trust page."""
    import hashlib
    import json
    from datetime import datetime, timezone

    from backend.app.db.models.foundation import EvaluationRun
    from evaluation.harness import DATASET_VERSION

    tenant = db.query(Tenant).filter(Tenant.tenant_key == tenant_key).one()
    configuration = {"model": report.get("model"), "evaluation_version": EVALUATION_VERSION, **report["thresholds"]}
    now = datetime.now(timezone.utc)
    row = EvaluationRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        suite_version=EVALUATION_VERSION,
        dataset_version=DATASET_VERSION,
        release_version="MDARIX-R1",
        configuration_hash=hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest(),
        status="COMPLETED",
        results=json.loads(json.dumps(report, default=str)),
        started_at=started_at,
        completed_at=now,
        created_at=now,
    )
    db.add(row)
    db.commit()
    return row.id


def trust_summary(results: dict[str, Any], completed_at=None) -> dict[str, Any]:
    """What the Trust page shows: headline numbers and, per scenario, each check with its evidence of matching."""
    scenarios = []
    for result in results.get("results", []):
        scenarios.append(
            {
                "scenario_id": result.get("scenario_id"),
                "title": result.get("title"),
                "status": result.get("status"),
                "specific_expectations": result.get("specific_expectations", 0),
                "written_by": result.get("analysis_author"),
                "seconds": result.get("seconds"),
                "checks": [
                    {
                        "check": check["check"],
                        "status": check["status"],
                        "matches": [
                            {"expected": item.get("expected"), "similarity": item.get("similarity")}
                            for item in check.get("details") or []
                            if isinstance(item, dict) and "expected" in item
                        ],
                    }
                    for check in result.get("checks", [])
                ],
                "error": result.get("error"),
            }
        )
    return {
        "evaluation_version": results.get("evaluation_version"),
        "completed_at": completed_at.isoformat() if completed_at else results.get("generated_at"),
        "model": results.get("model"),
        "passed": results.get("passed"),
        "total": results.get("total"),
        "with_specific_expectations": results.get("with_specific_expectations"),
        "passed_with_specific_expectations": results.get("passed_with_specific_expectations"),
        "model_written": results.get("model_written"),
        "thresholds": results.get("thresholds"),
        "scenarios": scenarios,
        "data_notice": "Synthetic test scenarios only. Internal assurance, not regulatory certification.",
    }
