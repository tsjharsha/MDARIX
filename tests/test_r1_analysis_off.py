"""RCA-D13: while no AI model answers for the organization, the R1 analysis routes run no keyword rule.

The rules behind the analysis (investigator/provider.py) match words written for the sample data ("novacap", "rev b",
"shutdown"). With AI off, unavailable or a free trial, the routes answer "AI analysis is off for this organization"
and neither run nor return an analysis. With AI answering they work as before.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import ai_settings
from backend.app.investigations import router
from investigator.provider import ControlledInvestigatorProvider
from investigator.schemas import InvestigationAnalysisRequest

pytestmark = pytest.mark.unit

CTX = SimpleNamespace(tenant_id=uuid.uuid4())
CASE = uuid.uuid4()


@pytest.fixture
def rules(monkeypatch):
    """The keyword rules and the service that runs them, watched: neither may be called while AI is off."""
    provider = MagicMock(side_effect=AssertionError("keyword rules ran"))
    monkeypatch.setattr(ControlledInvestigatorProvider, "analyze", provider)
    service = MagicMock()
    monkeypatch.setattr(router, "investigator_service", service)
    return provider, service


def _off_state(response) -> None:
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "analysis": None,
        "persisted": False,
        "state": "AI_OFF",
        "message": "AI analysis is off for this organization.",
    }


def test_every_analysis_route_answers_off_and_runs_no_keyword_rule(monkeypatch, rules):
    provider, service = rules
    monkeypatch.setattr(router, "ai_ready", lambda control, tenant_id: False)
    request = InvestigationAnalysisRequest(investigation_id=CASE)

    _off_state(router.create_investigation_analysis(CASE, request, data_db=None, control=None, ctx=CTX))
    _off_state(router.get_latest_investigation_analysis(CASE, request=None, data_db=None, control=None, ctx=CTX))
    _off_state(router.get_investigation_analysis(CASE, uuid.uuid4(), data_db=None, control=None, ctx=CTX))

    provider.assert_not_called()
    assert service.method_calls == []


def test_with_ai_answering_the_analysis_runs_as_before(monkeypatch, rules):
    _, service = rules
    seen = []
    monkeypatch.setattr(router, "ai_ready", lambda control, tenant_id: seen.append(tenant_id) or True)
    monkeypatch.setattr(router, "with_evidence_business_ids", lambda db, result: result)
    request = InvestigationAnalysisRequest(investigation_id=CASE)

    result = router.create_investigation_analysis(CASE, request, data_db="data", control="control", ctx=CTX)

    assert seen == [CTX.tenant_id]
    assert result is service.analyze.return_value
    db, scoped = service.analyze.call_args.args
    assert db == "data" and scoped.tenant_id == CTX.tenant_id and scoped.investigation_id == CASE


@pytest.mark.parametrize(
    ("models", "switched_on", "trial", "ready"),
    [
        ([], True, False, False),  # provider "controlled": no model on this server
        ([{"provider": "p", "model": "m"}], False, False, False),  # the organization switched AI off
        ([{"provider": "p", "model": "m"}], True, True, False),  # a free trial, whatever the switch says
        ([{"provider": "p", "model": "m"}], True, False, True),  # AI answers: the analysis runs
    ],
)
def test_the_gate_is_the_organizations_ai_status(monkeypatch, models, switched_on, trial, ready):
    monkeypatch.setattr(ai_settings, "_models_in_use", lambda: models)
    monkeypatch.setattr(ai_settings.governance, "is_free_trial", lambda db, tenant_id: trial)
    usage = {"ai_processing_allowed": switched_on, "monthly_token_budget": 1000, "tokens_used": 0}
    monkeypatch.setattr(ai_settings.governance, "usage", lambda db, tenant_id: usage)
    assert ai_settings.ai_ready(None, CTX.tenant_id) is ready


# ------------------------------------------------------------------- the case AI run and the hypotheses (follow-up)


@pytest.mark.parametrize("trigger", ["AUTO", "MANUAL"])
def test_the_case_ai_run_starts_nothing_while_ai_is_off_whoever_asks(monkeypatch, trigger):
    from backend.app.case_ai import router as case_ai_router

    monkeypatch.setattr(ai_settings, "ai_ready", lambda control, tenant_id: False)
    monkeypatch.setattr(case_ai_router.runner, "latest", lambda db, tenant_id, case_id: None)
    monkeypatch.setattr(case_ai_router, "_has_analysis", lambda db, tenant_id, case_id: False)
    db, background = MagicMock(), MagicMock()
    ctx = SimpleNamespace(tenant_id=str(CTX.tenant_id), user_id="person", correlation_id="c")

    answer = case_ai_router.start_run(
        CASE, case_ai_router.RunRequest(trigger=trigger), background, db=db, control=None, ctx=ctx
    )

    assert answer == {
        "started": False,
        "run": None,
        "reason": "AI_NOT_READY",
        "state": "AI_OFF",
        "message": "AI analysis is off for this organization.",
    }
    db.add.assert_not_called()
    db.commit.assert_not_called()
    background.add_task.assert_not_called()


@pytest.mark.parametrize("source", [None, uuid.uuid4()])
def test_hypotheses_run_no_analysis_while_ai_is_off(monkeypatch, rules, source):
    """Without a saved analysis to build on (none named, or the one named cannot be read), nothing runs."""
    from investigator.service import InvestigatorError

    provider, _ = rules
    analysis = MagicMock()
    analysis.analyze.side_effect = AssertionError("keyword analysis ran")
    analysis.get.side_effect = InvestigatorError("ANALYSIS_NOT_FOUND", "not found")
    monkeypatch.setattr(router.hypothesis_service, "investigator_service", analysis)
    monkeypatch.setattr(router, "ai_ready", lambda control, tenant_id: False)
    request = router.HypothesisSetRequest(investigation_id=CASE, source_analysis_id=source)

    response = router.create_hypotheses(CASE, request, data_db=None, control=None, ctx=CTX)

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "hypothesis_set": None,
        "persisted": False,
        "state": "AI_OFF",
        "message": "AI analysis is off for this organization.",
    }
    analysis.analyze.assert_not_called()
    provider.assert_not_called()


def test_with_ai_answering_the_hypotheses_may_run_the_analysis(monkeypatch):
    service = MagicMock()
    monkeypatch.setattr(router, "hypothesis_service", service)
    monkeypatch.setattr(router, "ai_ready", lambda control, tenant_id: True)
    monkeypatch.setattr(router, "with_hypothesis_business_ids", lambda db, tenant_id, result: result)
    request = router.HypothesisSetRequest(investigation_id=CASE)

    result = router.create_hypotheses(CASE, request, data_db="data", control="control", ctx=CTX)

    assert result is service.generate.return_value
    assert service.generate.call_args.kwargs == {"run_analysis": True}


# ------------------------------------------------- the challenges and the unknowns / failure-chain routes (last two)

OFF = {"persisted": False, "state": "AI_OFF", "message": "AI analysis is off for this organization."}


def _ctx():
    return SimpleNamespace(tenant_id=str(CTX.tenant_id), user_id="person", correlation_id="c")


@pytest.fixture
def no_saved_set(monkeypatch, rules):
    """No saved hypothesis set or challenges for the case; generating one would run the (watched) keyword analysis."""
    from hypothesis_engine.service import CompetingHypothesisService
    from challenger.service import ChallengerService
    from investigator.service import EvidenceGroundedInvestigatorService

    analyze = MagicMock(side_effect=AssertionError("keyword analysis ran"))
    monkeypatch.setattr(EvidenceGroundedInvestigatorService, "analyze", analyze)
    monkeypatch.setattr(CompetingHypothesisService, "latest", lambda self, db, tenant_id, case_id: None)
    monkeypatch.setattr(ChallengerService, "latest", lambda self, db, tenant_id, case_id: None)
    return rules[0], analyze


def test_challenges_generate_no_hypotheses_while_ai_is_off(monkeypatch, no_saved_set):
    from backend.app import challenger_router
    from challenger.schemas import ChallengeRequest
    from challenger.service import ChallengerService

    provider, analyze = no_saved_set
    monkeypatch.setattr(challenger_router, "service", ChallengerService())
    monkeypatch.setattr(challenger_router, "ai_ready", lambda control, tenant_id: False)
    db = MagicMock()

    response = challenger_router.create_challenges(
        CASE,
        None,
        ChallengeRequest(investigation_id=CASE, hypothesis_set_id=uuid.uuid4()),
        db=db,
        control=None,
        ctx=_ctx(),
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {"challenge_set": None, **OFF}
    analyze.assert_not_called()
    provider.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(("route", "key"), [("create_unknowns", "unknown_set"), ("create_chains", "failure_chain_set")])
def test_unknowns_and_failure_chains_generate_nothing_while_ai_is_off(monkeypatch, no_saved_set, route, key):
    from backend.app import unknowns_failure_chain_router as chain_router
    from failure_chain.schemas import FailureChainRequest
    from failure_chain.service import UnknownsFailureChainService
    from unknowns.schemas import UnknownRequest

    provider, analyze = no_saved_set
    monkeypatch.setattr(chain_router, "service", UnknownsFailureChainService())
    monkeypatch.setattr(chain_router, "ai_ready", lambda control, tenant_id: False)
    data = (UnknownRequest if route == "create_unknowns" else FailureChainRequest)(investigation_id=CASE)
    db = MagicMock()

    response = getattr(chain_router, route)(CASE, None, data, db=db, control=None, ctx=_ctx())

    assert response.status_code == 200
    assert json.loads(response.body) == {key: None, **OFF}
    analyze.assert_not_called()
    provider.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("ready", [True, False])
@pytest.mark.parametrize("route", ["challenges", "create_unknowns", "create_chains"])
def test_the_routes_pass_the_organizations_ai_status_to_the_service(monkeypatch, route, ready):
    """AI answering: the services may generate as before (run_analysis=True); AI off: only saved sets (False)."""
    from backend.app import challenger_router
    from backend.app import unknowns_failure_chain_router as chain_router
    from challenger.schemas import ChallengeRequest
    from failure_chain.schemas import FailureChainRequest
    from unknowns.schemas import UnknownRequest

    service = MagicMock()
    if route == "challenges":
        module, call, method = challenger_router, challenger_router.create_challenges, service.generate
        data = ChallengeRequest(investigation_id=CASE)
        monkeypatch.setattr(module, "with_evidence_business_ids", lambda db, result: result)
    else:
        module, call = chain_router, getattr(chain_router, route)
        method = service.unknowns if route == "create_unknowns" else service.chains
        data = (UnknownRequest if route == "create_unknowns" else FailureChainRequest)(investigation_id=CASE)
        monkeypatch.setattr(module, "with_unknown_business_ids", lambda db, tenant_id, result: result)
        monkeypatch.setattr(module, "with_failure_chain_business_ids", lambda db, tenant_id, result: result)
    monkeypatch.setattr(module, "service", service)
    monkeypatch.setattr(module, "make_audit_event", MagicMock(), raising=False)
    monkeypatch.setattr(module, "ai_ready", lambda control, tenant_id: ready)

    result = call(CASE, None, data, db=MagicMock(), control="control", ctx=_ctx())

    assert result is method.return_value
    assert method.call_args.kwargs == {"run_analysis": ready}
