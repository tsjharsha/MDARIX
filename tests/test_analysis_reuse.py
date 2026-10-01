"""Unknowns and failure chains build on the hypotheses and challenges already shown, instead of regenerating them."""

from backend.app.db.models.foundation import AIExecution
from backend.app.db.session import SessionLocal
from challenger.schemas import ChallengeRequest
from challenger.service import ChallengerService
from failure_chain.service import UnknownsFailureChainService
from hypothesis_engine.engine import PROVIDER as HYPOTHESIS_PROVIDER
from hypothesis_engine.schemas import HypothesisSetRequest
from hypothesis_engine.service import CompetingHypothesisService
from investigator.model_provider import parse_json_reply
from investigator.provider import PROVIDER as INVESTIGATOR_PROVIDER
from investigator.schemas import InvestigationAnalysisRequest
from investigator.service import EvidenceGroundedInvestigatorService
from tests.test_day11_ai_investigator import context
from unknowns.schemas import UnknownRequest


def _hypothesis_runs(db, tenant_id, investigation_id) -> int:
    return (
        db.query(AIExecution)
        .filter_by(tenant_id=tenant_id, investigation_id=investigation_id, provider=HYPOTHESIS_PROVIDER)
        .count()
    )


def test_unknowns_reuse_the_current_hypotheses_and_challenges():
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        challenges = ChallengerService().generate(
            db, ChallengeRequest(tenant_id=tenant_id, investigation_id=investigation_id)
        )
        before = _hypothesis_runs(db, tenant_id, investigation_id)
        service = UnknownsFailureChainService()
        hypotheses, challenge_set = service._inputs(
            db, UnknownRequest(tenant_id=tenant_id, investigation_id=investigation_id)
        )
        assert challenge_set.challenge_set_id == challenges.challenge_set.challenge_set_id
        assert hypotheses.hypothesis_set_id == challenge_set.source_hypothesis_set_id
        assert _hypothesis_runs(db, tenant_id, investigation_id) == before  # nothing regenerated
    finally:
        db.close()


def test_a_different_view_regenerates_and_the_same_view_reuses():
    tenant_id, investigation_id = context()
    request = UnknownRequest(
        tenant_id=tenant_id, investigation_id=investigation_id, temporal_mode="known", as_of="2026-03-01T00:00:00Z"
    )
    db = SessionLocal()
    try:
        before = _hypothesis_runs(db, tenant_id, investigation_id)
        first, _ = UnknownsFailureChainService()._inputs(db, request)  # the latest set is for another view
        assert _hypothesis_runs(db, tenant_id, investigation_id) == before + 1
        again, _ = UnknownsFailureChainService()._inputs(db, request)
        assert again.hypothesis_set_id == first.hypothesis_set_id
        assert _hypothesis_runs(db, tenant_id, investigation_id) == before + 1
    finally:
        db.close()


def test_model_text_uses_plain_hyphens_and_spaces():
    parsed = parse_json_reply('{"statement": "LOT‑010 uses Rev B – see EV‑VS001‑003"}')
    assert parsed["statement"] == "LOT-010 uses Rev B - see EV-VS001-003"


def test_hypotheses_build_on_the_analysis_on_screen():
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        shown = EvidenceGroundedInvestigatorService().analyze(
            db, InvestigationAnalysisRequest(tenant_id=tenant_id, investigation_id=investigation_id)
        )
        runs = db.query(AIExecution).filter_by(investigation_id=investigation_id, provider=INVESTIGATOR_PROVIDER)
        before = runs.count()
        result = CompetingHypothesisService().generate(
            db,
            HypothesisSetRequest(
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                source_analysis_id=shown.analysis.analysis_id,
                persist=False,
            ),
        )
        assert result.hypothesis_set.source_analysis_id == shown.analysis.analysis_id
        assert runs.count() == before  # the analysis was not run again
        # An analysis for another point in time is not reused.
        other = CompetingHypothesisService().generate(
            db,
            HypothesisSetRequest(
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                source_analysis_id=shown.analysis.analysis_id,
                temporal_mode="known",
                as_of="2026-03-01T00:00:00Z",
                persist=False,
            ),
        )
        assert other.hypothesis_set.source_analysis_id != shown.analysis.analysis_id
    finally:
        db.close()
