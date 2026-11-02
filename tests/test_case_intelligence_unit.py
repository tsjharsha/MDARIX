"""Case intelligence without a database: hypothesis statuses, evidence relations, unknown statuses and failure chain
link states (validation and labels), how hypotheses are named (AI interpretation, judged by, added by), observation
kinds, the readiness rules that depend on people's work, and the routes with their guards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.case_intelligence import rules
from backend.app.case_intelligence.rules import (
    AdoptChainPayload,
    FailureChainCreatePayload,
    HypothesisCreatePayload,
    HypothesisEvidencePayload,
    HypothesisStatusPayload,
    LinkStatePayload,
    ObservationCreatePayload,
    RetractPayload,
    UnknownCreatePayload,
    UnknownStatusPayload,
)
from backend.app.case_workflow import readiness

pytestmark = pytest.mark.unit

REASON = "The service report contradicts the complaint date"
EVIDENCE = "6f1c1b8e-0d7e-4c1e-9d55-0d4f6b0d8f11"


# ------------------------------------------------------------------------------------------------- hypotheses


def test_a_person_judges_a_hypothesis_with_a_known_status_and_a_reason():
    judged = HypothesisStatusPayload(human_status=" partially_supported ", reason=f"  {REASON}  ")
    assert judged.human_status == "PARTIALLY_SUPPORTED" and judged.reason == REASON
    assert set(rules.HUMAN_STATUSES) == {
        "PROPOSED",
        "HYPOTHESIZED",
        "PARTIALLY_SUPPORTED",
        "STRONGLY_SUPPORTED",
        "WEAKLY_SUPPORTED",
        "CONTRADICTED",
        "RETIRED",
    }
    for body in (
        {"human_status": "CONFIRMED", "reason": REASON},
        {"human_status": "ROOT_CAUSE", "reason": REASON},
        {"human_status": "", "reason": REASON},
        {"human_status": "RETIRED", "reason": "too short"},
        {"human_status": "RETIRED", "reason": "          x"},
        {"human_status": "RETIRED"},
    ):
        with pytest.raises(ValidationError):
            HypothesisStatusPayload(**body)


def test_a_hypothesis_a_person_adds_needs_a_statement():
    made = HypothesisCreatePayload(statement="  Tubing supplier change raised occlusion alarms  ", rationale="  ")
    assert made.statement == "Tubing supplier change raised occlusion alarms" and made.rationale is None
    for body in ({"statement": "too short"}, {"statement": "          x"}, {"statement": "x" * 2001}):
        with pytest.raises(ValidationError):
            HypothesisCreatePayload(**body)


def test_hypothesis_labels_and_what_each_hypothesis_is_called():
    assert rules.human_status_label("STRONGLY_SUPPORTED") == "Strongly supported"
    assert rules.human_status_label(None) is None
    assert rules.ai_status_label("mixed_evidence") == "Mixed evidence"
    assert rules.ai_status_label("SUPERSEDED") == "Replaced by a newer AI run"
    assert rules.ai_status_label("something_new") == "Something new"
    assert rules.origin_code("ai") == "AI" and rules.origin_code("system") == "SYSTEM"
    assert rules.origin_code("human") == "HUMAN"
    # Until a person judges it, an AI (or rule-written) hypothesis is the AI's interpretation.
    assert rules.kind_label("ai", None) == "AI interpretation"
    assert rules.kind_label("system", None, judged_by_name="Ann") == "AI interpretation"
    assert rules.kind_label("ai", "WEAKLY_SUPPORTED", judged_by_name="Ann Lee") == "Judged by Ann Lee"
    assert rules.kind_label("system", "RETIRED") == "Judged by a colleague"
    # A person's own hypothesis says who added it, judged or not.
    assert rules.kind_label("human", "PROPOSED", created_by_name="Raj", judged_by_name="Ann") == "Added by Raj"
    assert rules.kind_label("human", None) == "Added by a colleague"
    assert rules.counts_toward_case("mixed_evidence", None) and rules.counts_toward_case("proposed", "CONTRADICTED")
    assert not rules.counts_toward_case("superseded", None) and not rules.counts_toward_case("proposed", "RETIRED")


def test_evidence_relations_of_a_hypothesis():
    linked = HypothesisEvidencePayload(evidence_id=EVIDENCE, relation="contradicting", rationale=REASON)
    assert linked.relation == "CONTRADICTING" and rules.relation_type(linked.relation) == "contradict"
    assert [rules.relation_type(item) for item in rules.RELATIONS] == [
        "support",
        "contradict",
        "contextual",
        "unresolved",
    ]
    assert rules.relation_bucket("support") == "supporting" and rules.relation_bucket("contradict") == "contradicting"
    assert rules.relation_bucket("contextual") == "contextual" and rules.relation_bucket("whatever") == "unresolved"
    assert rules.link_is_human("human") and not rules.link_is_human("system") and not rules.link_is_human("ai")
    for body in (
        {"evidence_id": EVIDENCE, "relation": "PROVES", "rationale": REASON},
        {"evidence_id": EVIDENCE, "relation": "SUPPORTING", "rationale": "short"},
        {"evidence_id": "not-a-uuid", "relation": "SUPPORTING", "rationale": REASON},
    ):
        with pytest.raises(ValidationError):
            HypothesisEvidencePayload(**body)
    assert RetractPayload(reason=REASON).reason == REASON
    with pytest.raises(ValidationError):
        RetractPayload(reason="short")


# --------------------------------------------------------------------------------------------------- unknowns


def test_unknown_statuses_and_their_reasons():
    moved = UnknownStatusPayload(status="Accepted_Limitation", reason=REASON)
    assert moved.status == "accepted_limitation"
    assert rules.RESOLUTION_STATUSES == {"resolved", "accepted_limitation", "superseded"}
    assert UnknownStatusPayload(status="SUPERSEDED", reason=REASON).status == "superseded"
    for body in (
        {"status": "closed", "reason": REASON},
        {"status": "superseded", "reason": "short"},
        {"status": "resolved", "reason": "short"},
        {"status": "resolved"},
    ):
        with pytest.raises(ValidationError):
            UnknownStatusPayload(**body)
    assert rules.unknown_locked("superseded") and not rules.unknown_locked("open")
    # Set aside as no longer relevant only while open or in progress; nothing leaves superseded; answers reopen.
    assert rules.unknown_transition_allowed("open", "superseded")
    assert rules.unknown_transition_allowed("in_progress", "superseded")
    assert not rules.unknown_transition_allowed("resolved", "superseded")
    assert not rules.unknown_transition_allowed("accepted_limitation", "superseded")
    assert not rules.unknown_transition_allowed("superseded", "open")
    assert not rules.unknown_transition_allowed("open", "open")
    assert rules.unknown_transition_allowed("resolved", "open")
    assert rules.unknown_transition_allowed("accepted_limitation", "open")
    assert rules.unknown_status_label("superseded") == "No longer relevant"
    assert rules.unknown_status_label("in_progress") == "In progress"
    assert rules.unknown_status_label("accepted_limitation") == "Accepted as a limitation"
    assert rules.origin_label("human") == "Person" and rules.origin_label("ai") == "AI"
    assert rules.origin_label(None) == "System" and rules.plain_origin("system") == "SYSTEM"
    made = UnknownCreatePayload(description="Was lot KS-5521 sterilized?", category=" ", evidence_needed=None)
    assert made.category is None and made.hypothesis_id is None
    with pytest.raises(ValidationError):
        UnknownCreatePayload(description="short")


# --------------------------------------------------------------------------------------------- failure chains


def _chain(**overrides) -> dict:
    body = {
        "name": "Supplier change to alarms",
        "nodes": ["Tubing supplier changed", "Wall thickness varies", "Occlusion alarms rise"],
        "links": [
            {"from_index": 0, "to_index": 1, "state": "hypothesized"},
            {"from_index": 1, "to_index": 2, "state": "PARTIALLY_SUPPORTED", "evidence_id": EVIDENCE},
        ],
    }
    return {**body, **overrides}


def test_failure_chain_link_states_never_claim_proven_causality():
    assert rules.LINK_STATE_CODES == ("SUPPORTED", "PARTIALLY_SUPPORTED", "HYPOTHESIZED", "UNKNOWN", "CONTRADICTED")
    assert not any("CONFIRM" in state or "PROVEN" in state for state in rules.LINK_STATE_CODES)
    assert not any("confirm" in label.lower() or "cause" in label.lower() for label in rules.LINK_STATE_LABELS.values())
    for state in ("CONFIRMED", "ESTABLISHED_FACT", "ROOT_CAUSE", ""):
        with pytest.raises(ValidationError):
            LinkStatePayload(state=state, reason=REASON)
    with pytest.raises(ValidationError):
        LinkStatePayload(state="SUPPORTED", reason="short")
    assert LinkStatePayload(state="unknown", reason=REASON).state == "UNKNOWN"
    # Links stored before md30 keep their meaning; anything else is unknown.
    assert rules.link_state("established_fact") == "SUPPORTED" and rules.link_state("hypothesized") == "HYPOTHESIZED"
    assert rules.link_state("contradicted") == "CONTRADICTED" and rules.link_state("CONFIRMED") == "UNKNOWN"
    assert rules.link_state_label("PARTIALLY_SUPPORTED") == "Partially supported"


def test_an_adopted_ai_link_keeps_the_ai_epistemic_status():
    assert rules.ai_link_state("OBSERVED_SOURCE_SUPPORTED") == "SUPPORTED"
    assert rules.ai_link_state("DETERMINISTICALLY_DERIVED") == "PARTIALLY_SUPPORTED"
    assert rules.ai_link_state("HYPOTHESIZED") == "HYPOTHESIZED"
    assert rules.ai_link_state("CONTRADICTED") == "CONTRADICTED"
    assert rules.ai_link_state("UNKNOWN_GAP") == "UNKNOWN"
    for anything in ("CONFIRMED", "CAUSAL", "", None):
        assert rules.ai_link_state(anything) == "UNKNOWN"
    adopt = AdoptChainPayload(ai_execution_id=EVIDENCE, ai_chain_id=" 9B2C4F6A-0000-4000-8000-000000000001 ")
    assert adopt.ai_chain_id == "9b2c4f6a-0000-4000-8000-000000000001"
    assert rules.chain_origin("ai_adopted") == "AI_ADOPTED" and rules.chain_origin("human") == "HUMAN"
    assert rules.chain_origin("system") == "SYSTEM" and rules.chain_origin(None) == "SYSTEM"


def test_a_failure_chain_a_person_builds():
    made = FailureChainCreatePayload(**_chain(name="  Supplier   change "))
    assert made.name == "Supplier change" and [link.state for link in made.links] == [
        "HYPOTHESIZED",
        "PARTIALLY_SUPPORTED",
    ]
    for body in (
        _chain(name="ab"),
        _chain(nodes=["Only one step"]),
        _chain(nodes=[f"Step {index}" for index in range(21)]),
        _chain(nodes=["A", "Two", "Three"]),
        _chain(links=[]),
        _chain(nodes=["Supplier changed", "x" * 256]),
        _chain(links=[{"from_index": 0, "to_index": 3, "state": "UNKNOWN"}]),
        _chain(links=[{"from_index": 1, "to_index": 1, "state": "UNKNOWN"}]),
        _chain(
            links=[
                {"from_index": 0, "to_index": 1, "state": "HYPOTHESIZED"},
                {"from_index": 0, "to_index": 1, "state": "UNKNOWN"},
            ]
        ),
        _chain(links=[{"from_index": 0, "to_index": 1, "state": "CONFIRMED"}]),
        # A (partially) supported link names the evidence it rests on.
        _chain(links=[{"from_index": 0, "to_index": 1, "state": "SUPPORTED"}]),
        _chain(links=[{"from_index": 0, "to_index": 1, "state": "partially_supported"}]),
    ):
        with pytest.raises(ValidationError):
            FailureChainCreatePayload(**body)
    long_step = FailureChainCreatePayload(**_chain(nodes=["Supplier changed", "x" * 255, "Alarms"]))
    assert len(long_step.nodes[1]) == 255
    assert rules.state_needs_evidence("SUPPORTED") and rules.state_needs_evidence("PARTIALLY_SUPPORTED")
    assert not rules.state_needs_evidence("HYPOTHESIZED") and not rules.state_needs_evidence("UNKNOWN")


# ----------------------------------------------------------------------------------------------- observations


def test_people_record_facts_assertions_and_derived_observations_but_never_ai_interpretations():
    for kind in ("fact", "SOURCE_ASSERTION", "derived_observation"):
        made = ObservationCreatePayload(evidence_id=EVIDENCE, statement="Alarm at 4 psi", epistemic_type=kind)
        assert made.epistemic_type in rules.HUMAN_EPISTEMIC_TYPES
    for body in (
        {"evidence_id": EVIDENCE, "statement": "Alarm at 4 psi", "epistemic_type": "AI_INTERPRETATION"},
        {"evidence_id": EVIDENCE, "statement": "Alarm at 4 psi", "epistemic_type": "OPINION"},
        {"evidence_id": EVIDENCE, "statement": "abc", "epistemic_type": "FACT"},
    ):
        with pytest.raises(ValidationError):
            ObservationCreatePayload(**body)
    assert [rules.epistemic_label(code) for code in ("FACT", "SOURCE_ASSERTION", "DERIVED_OBSERVATION")] == [
        "Fact",
        "Source assertion",
        "Derived observation",
    ]
    assert rules.epistemic_label("AI_INTERPRETATION") == "AI interpretation"
    assert (rules.HUMAN_OBSERVATION_TYPE, rules.HUMAN_EXTRACTION_METHOD) == ("HUMAN_OBSERVATION", "HUMAN")


def test_observations_without_a_recorded_kind_are_read_as_md30_labelled_them():
    assert rules.observation_kind(None, "STRUCTURED_EXTRACTION", "DETERMINISTIC") == "FACT"
    assert rules.observation_kind(None, "STRUCTURED_EXTRACTION", "GENAI") == "SOURCE_ASSERTION"
    assert rules.observation_kind(None, "EXPLICIT_SOURCE_STATEMENT", "GENAI") == "SOURCE_ASSERTION"
    assert rules.observation_kind(None, "AI_EXTRACTED_OBSERVATION", "GENAI") == "AI_INTERPRETATION"
    assert rules.observation_kind(None, "DETERMINISTIC_DERIVATION", "DETERMINISTIC") == "DERIVED_OBSERVATION"
    assert rules.observation_kind("FACT", "AI_EXTRACTED_OBSERVATION", "GENAI") == "FACT"
    assert (
        rules.observation_origin(None, "GENAI") == "AI" and rules.observation_origin(None, "DETERMINISTIC") == "SYSTEM"
    )
    assert rules.observation_origin("HUMAN", "HUMAN") == "HUMAN" and rules.observation_origin(None, "HUMAN") == "HUMAN"


def test_history_names():
    assert rules.audit_action(rules.EVENT_STATUS_CHANGED) == "INTELLIGENCE_STATUS_CHANGED"
    assert rules.event_label("EVIDENCE_RETRACTED") == "Evidence link withdrawn"
    assert rules.event_label("SOMETHING_ELSE") == "Something else" and rules.event_label(None) is None


# -------------------------------------------------------------------------------------------------- readiness


def _facts(**overrides) -> dict:
    facts = {
        "workflow_state": "IN_PROGRESS",
        "question": True,
        "scope": {"version": 1, "question": True, "included": 1},
        "evidence": {"total": 1, "unreviewed": 0},
        "requests": {"open": 0, "blocking": 0},
        "unknowns": {"total": 0, "open": 0},
        "analysis_run": False,
        "people_analysis": 0,
        "hypotheses": 1,
        "contradictions": {"total": 0, "undocumented": []},
        "brief": {"latest_version": None},
        "decision": {"count": 0, "signed": 0},
    }
    return {**facts, **overrides}


def _check(result: dict, key: str) -> dict:
    (found,) = [check for check in result["checks"] if check["key"] == key]
    return found


def _step(result: dict, key: str) -> dict:
    (found,) = [step for step in result["steps"] if step["key"] == key]
    return found


def test_ai_is_never_required_for_the_analysis():
    nothing = readiness.evaluate(_facts())
    assert _check(nothing, "analysis_run")["result"] == "PENDING"
    assert "record observations and hypotheses yourself" in _check(nothing, "analysis_run")["rationale"]
    people = readiness.evaluate(_facts(people_analysis=3))
    assert _check(people, "analysis_run")["result"] == "PASS" and _step(people, "analysis")["status"] == "DONE"
    assert _check(people, "analysis_run")["rationale"] == "People recorded 3 observations and hypotheses"
    # Even when the AI analysis could not be read, people's own work counts.
    unreadable = readiness.evaluate(_facts(analysis_run=None, people_analysis=1))
    assert _check(unreadable, "analysis_run")["result"] == "PASS"
    ai = readiness.evaluate(_facts(analysis_run=True))
    assert _check(ai, "analysis_run") == {
        "key": "analysis_run",
        "label": "Analysis has been run",
        "result": "PASS",
        "rationale": "An analysis has been run",
    }


def test_contradicting_evidence_must_be_judged_by_a_person():
    check = _check(readiness.evaluate(_facts()), "contradictions_documented")
    assert check["result"] == "PASS" and check["rationale"] == "No hypothesis has contradicting evidence"
    assert check["label"] == "Contradicting evidence is judged"
    pending = _check(
        readiness.evaluate(_facts(contradictions={"total": 2, "undocumented": ["HYP000002"]})),
        "contradictions_documented",
    )
    assert pending["result"] == "PENDING"
    assert pending["rationale"] == "Judge 1 hypothesis with contradicting evidence: HYP000002"
    many = [f"HYP00000{index}" for index in range(1, 8)]
    named = _check(
        readiness.evaluate(_facts(contradictions={"total": 7, "undocumented": many})), "contradictions_documented"
    )
    assert named["rationale"].endswith("HYP000005 and 2 more") and "HYP000006" not in named["rationale"]
    judged = _check(
        readiness.evaluate(_facts(contradictions={"total": 2, "undocumented": []})), "contradictions_documented"
    )
    assert judged["result"] == "PASS"
    assert judged["rationale"] == "All 2 hypotheses with contradicting evidence are judged"
    unreadable = _check(readiness.evaluate(_facts(contradictions=None)), "contradictions_documented")
    assert unreadable["result"] == "PENDING" and unreadable["rationale"] == readiness.UNREADABLE


def test_unknowns_in_progress_are_open_and_accepted_limitations_are_answered():
    assert readiness.unknown_is_open("open") and readiness.unknown_is_open("in_progress")
    assert not readiness.unknown_is_open("resolved") and not readiness.unknown_is_open("accepted_limitation")
    assert not readiness.unknown_is_open("superseded")
    pending = readiness.evaluate(_facts(unknowns={"total": 3, "open": 2}))
    assert _check(pending, "unknowns")["result"] == "PENDING"
    assert _check(pending, "unknowns")["rationale"] == "2 open unknowns still to answer"
    assert _check(readiness.evaluate(_facts(unknowns={"total": 3, "open": 0})), "unknowns")["result"] == "PASS"


# ------------------------------------------------------------------------------------------------------ routes

PREFIX = "/api/v1/investigations/{investigation_id}/intelligence"
WRITES = {
    ("POST", f"{PREFIX}/hypotheses"),
    ("POST", f"{PREFIX}/hypotheses/{{hypothesis_id}}/status"),
    ("POST", f"{PREFIX}/hypotheses/{{hypothesis_id}}/evidence"),
    ("POST", f"{PREFIX}/hypotheses/{{hypothesis_id}}/evidence/{{link_id}}/retract"),
    ("POST", f"{PREFIX}/unknowns"),
    ("POST", f"{PREFIX}/unknowns/{{unknown_id}}/status"),
    ("POST", f"{PREFIX}/failure-chains"),
    ("POST", f"{PREFIX}/failure-chains/adopt"),
    ("POST", f"{PREFIX}/failure-chains/{{chain_id}}/links/{{link_id}}/state"),
    ("POST", f"{PREFIX}/observations"),
}
READS = {
    ("GET", f"{PREFIX}/{name}")
    for name in ("hypotheses", "contradictions", "unknowns", "failure-chains", "observations", "history")
}


def test_the_intelligence_routes_are_registered_guarded_and_need_a_session():
    from backend.app.main import app
    from backend.app.request_context import get_request_context
    from tests.route_inventory import api_routes

    def needs_session(dependant) -> bool:
        return any(dep.call is get_request_context or needs_session(dep) for dep in dependant.dependencies)

    routes = {(method, path): route for path, route in api_routes(app) for method in route.methods}
    assert WRITES | READS <= set(routes)
    assert {key for key in routes if key[1].startswith(PREFIX)} == WRITES | READS  # no deletes, nothing else
    for key in WRITES | READS:
        assert needs_session(routes[key].dependant), key
    for key in WRITES:
        guards = [getattr(dep.dependency, "__qualname__", "") for dep in routes[key].dependencies]
        assert any("require_permission" in guard for guard in guards), key
    ordered = [(method, path) for path, route in api_routes(app) for method in sorted(route.methods)]
    mine = ordered.index(("GET", "/api/v1/investigations/mine/summary"))
    assert all(ordered.index(key) > mine for key in READS)
