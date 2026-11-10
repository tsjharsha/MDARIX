"""The controlled Decision Brief without a database: how a version moves under quality review, the submission gate,
the author's narrative and the AI draft, the canonical fingerprint and the evidence-set fingerprint, the leading
hypothesis rule (a person's judgement, never the AI's status), the AI disclosure, the review sections, the actions a
person is offered, request validation, the composition of evidence sections, and the routes with their guards."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.db.models.reviews import BRIEF_STATUSES, QUALITY_ACTIONS
from backend.app.decision_brief import compose, rules

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
COMMENT = "The bench test of lot 7 is still missing"


# --------------------------------------------------------------------------------------------------- statuses


def test_every_status_and_action_has_a_label():
    assert set(rules.STATUS_LABELS) == set(BRIEF_STATUSES)
    assert set(rules.ACTION_LABELS) == set(QUALITY_ACTIONS)
    assert rules.REVIEW_ACTIONS == tuple(action for action in QUALITY_ACTIONS if action != "START_REVIEW")
    assert rules.status_label("approved_for_decision") == "Approved for decision"
    assert rules.status_label(None) is None


def test_how_a_version_moves_under_quality_review():
    moves = {
        (status, action): rules.status_after(status, action)
        for status in BRIEF_STATUSES
        for action in QUALITY_ACTIONS
        if rules.status_after(status, action) is not None
    }
    expected = {("READY_FOR_REVIEW", "START_REVIEW"): "UNDER_REVIEW"}
    for status in ("READY_FOR_REVIEW", "UNDER_REVIEW"):
        expected[(status, "ACCEPT_FOR_DECISION")] = "APPROVED_FOR_DECISION"
        expected[(status, "ESCALATE")] = "UNDER_REVIEW"
        for action in rules.RETURN_ACTIONS:
            expected[(status, action)] = "RETURNED"
    assert moves == expected
    # Drafts, returned, approved and superseded versions take no quality action.
    for status in ("DRAFT", "RETURNED", "APPROVED_FOR_DECISION", "SUPERSEDED"):
        assert all(rules.status_after(status, action) is None for action in QUALITY_ACTIONS)


def test_where_the_case_goes_after_a_quality_action():
    assert rules.case_state_after("ACCEPT_FOR_DECISION") == "READY_FOR_DECISION"
    for action in rules.RETURN_ACTIONS:
        assert rules.case_state_after(action) == "IN_PROGRESS"
    assert rules.case_state_after("ESCALATE") is None
    assert rules.case_state_after("START_REVIEW") is None
    assert rules.REVIEW_REQUESTS == {"RETURN_FOR_RISK_REVIEW": "RISK", "RETURN_FOR_REGULATORY_REVIEW": "REGULATORY"}


def test_a_comment_is_needed_except_to_accept():
    assert rules.comment_problem("ACCEPT_FOR_DECISION", None) is None
    assert rules.comment_problem("ACCEPT_FOR_DECISION", "Fine") is None
    for action in (*rules.RETURN_ACTIONS, "ESCALATE"):
        assert rules.comment_problem(action, None)
        assert rules.comment_problem(action, "   too   short ")
        assert rules.comment_problem(action, COMMENT) is None
    assert rules.comment_problem("ACCEPT_FOR_DECISION", "x" * (rules.COMMENT_MAX + 1))


def test_whoever_wrote_or_submitted_a_version_never_reviews_it():
    author, editor, submitter, reviewer = (str(uuid.uuid4()) for _ in range(4))
    kwargs = {"created_by": author, "submitted_by": submitter, "contributors": [editor]}
    for person in (author, editor, submitter, author.upper()):
        assert rules.sod_denied(person, **kwargs)
    assert not rules.sod_denied(reviewer, **kwargs)
    assert rules.sod_denied("", **kwargs)  # an unknown person is never allowed


# -------------------------------------------------------------------------------------------------- narrative


def test_the_narrative_reads_the_same_whatever_was_stored():
    empty = rules.normalize_narrative(None)
    assert empty == rules.empty_narrative()
    narrative = rules.normalize_narrative(
        {
            "problem_statement": "  Alarms rise  ",
            "recommended_actions": ["  Replace sensor ", "", None, "Retrain"],
            "ai_draft_text": "ignored while the draft is not used",
            "contributors": ["b", "a", "b", ""],
        }
    )
    assert narrative["problem_statement"] == "Alarms rise"
    assert narrative["recommended_actions"] == ["Replace sensor", "Retrain"]
    assert narrative["ai_draft_used"] is False and narrative["ai_draft_text"] is None
    assert narrative["contributors"] == ["a", "b"]
    assert rules.with_contributor(narrative, "c")["contributors"] == ["a", "b", "c"]


def test_only_the_fields_given_change_and_an_ai_draft_can_be_dropped():
    current = {
        **rules.empty_narrative(),
        "problem_statement": "Alarms rise",
        "ai_draft_used": True,
        "ai_draft_text": "AI text",
        "ai_draft_source": {"business_id": "BRF000001"},
    }
    merged, changed = rules.merge_narrative(current, {"proposed_conclusion": "Sensor drift is likely"})
    assert changed == ["proposed_conclusion"]
    assert merged["problem_statement"] == "Alarms rise" and merged["ai_draft_text"] == "AI text"
    same, changed = rules.merge_narrative(merged, {"problem_statement": " Alarms rise "})
    assert changed == [] and same == merged
    dropped, changed = rules.merge_narrative(merged, {"ai_draft_used": False, "recommended_actions": ["Act"]})
    assert changed == ["recommended_actions", "ai_draft_used"]
    assert dropped["ai_draft_used"] is False and dropped["ai_draft_text"] is None and dropped["ai_draft_source"] is None
    # Turning the AI draft on happens only when composing from an AI brief.
    again, changed = rules.merge_narrative(dropped, {"ai_draft_used": True})
    assert changed == [] and again["ai_draft_used"] is False


def test_the_ai_draft_text_of_a_model_written_and_a_rule_assembled_brief():
    model = {
        "ai_brief": {
            "headline": "Alarms rose after release B.",
            "sections": {
                "what_we_know": [{"statement": "12 complaints since May", "evidence": ["EV-1"]}],
                "leading_hypotheses": [{"statement": "The sensor may drift", "evidence": ["EV-2"]}],
                "next_steps": [],
            },
        },
        "executive_summary": {"text": "ignored"},
    }
    text = rules.ai_draft_text(model)
    assert text.startswith("Alarms rose after release B.")
    assert "What we know:\n- 12 complaints since May" in text
    assert "Leading hypotheses (AI interpretation):\n- The sensor may drift" in text
    assert "Possible next steps" not in text and "ignored" not in text
    assembled = {"executive_summary": {"text": "Context preserved.", "uncertainty": ["No lot data"]}}
    assert rules.ai_draft_text(assembled) == "Context preserved.\n- No lot data"
    assert rules.ai_draft_text({}) is None and rules.ai_draft_text(None) is None


# ------------------------------------------------------------------------------------------------------- gate


def _check(key: str, result: str) -> dict:
    return {"key": key, "label": key.replace("_", " ").capitalize(), "result": result, "rationale": "why"}


READY_NARRATIVE = {"problem_statement": "Alarms rise", "proposed_conclusion": "Sensor drift is likely"}


def test_the_gate_lets_a_ready_brief_through():
    checks = [
        _check("scope_complete", "PASS"),
        _check("evidence_reviewed", "PASS"),
        _check("no_blocking_request", "PASS"),
        _check("risk_review", "NOT_REQUIRED"),
        _check("regulatory_review", "PASS"),
        _check("unknowns", "PENDING"),
        _check("brief_ready", "PENDING"),
        _check("decision", "PENDING"),
    ]
    gate = rules.evaluate_gate(checks, READY_NARRATIVE)
    assert gate["can_submit"] is True and gate["blocking"] == []
    # Other pending checks warn; the brief's own check and the decision after it are never in the way.
    assert [item["key"] for item in gate["warnings"]] == ["unknowns"]


@pytest.mark.parametrize(
    ("check", "blocks"),
    [
        (_check("no_blocking_request", "BLOCKED"), True),
        (_check("risk_review", "BLOCKED"), True),
        (_check("unknowns", "BLOCKED"), True),
        (_check("scope_complete", "PENDING"), True),
        (_check("evidence_reviewed", "PENDING"), True),
        (_check("regulatory_review", "PENDING"), True),
        (_check("analysis_run", "PENDING"), False),
        (_check("risk_review", "NOT_AVAILABLE"), False),
        (_check("brief_ready", "BLOCKED"), False),
        (_check("decision", "BLOCKED"), False),
    ],
)
def test_which_checks_block_a_submission(check, blocks):
    gate = rules.evaluate_gate([check], READY_NARRATIVE)
    assert gate["can_submit"] is (not blocks)
    assert [item["key"] for item in gate["blocking"]] == ([check["key"]] if blocks else [])


def test_the_narrative_and_unreadable_records_block_a_submission():
    gate = rules.evaluate_gate([], {"problem_statement": "  "})
    assert [item["key"] for item in gate["blocking"]] == ["problem_statement", "proposed_conclusion"]
    assert all(item["result"] == "BLOCKED" for item in gate["blocking"])
    gate = rules.evaluate_gate([], READY_NARRATIVE, content_complete=False)
    assert [item["key"] for item in gate["blocking"]] == ["content_complete"]
    gate = rules.evaluate_gate([], None, check_narrative=False)
    assert gate["can_submit"] is True
    assert rules.blocked_checks([_check("risk_review", "BLOCKED"), _check("unknowns", "PENDING")]) == [
        {"key": "risk_review", "label": "Risk review"}
    ]


# ------------------------------------------------------------------------------------------------ fingerprints


def test_the_fingerprint_is_canonical():
    content = {"b": [1, 2], "a": {"y": "é", "x": None}}
    reordered = {"a": {"x": None, "y": "é"}, "b": [1, 2]}
    assert rules.content_hash(content, READY_NARRATIVE) == rules.content_hash(reordered, dict(READY_NARRATIVE))
    assert len(rules.content_hash(content, READY_NARRATIVE)) == 64
    assert rules.content_hash(content, READY_NARRATIVE) != rules.content_hash(content, {"problem_statement": "x"})
    assert rules.content_hash({"b": [2, 1]}, {}) != rules.content_hash({"b": [1, 2]}, {})
    assert rules.canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'


def test_stored_data_reads_back_with_the_same_fingerprint():
    key = uuid.uuid4()
    data = {"when": NOW, "id": key, "tags": ("x", "y"), "set": {"b", "a"}, "n": 3, "ok": True}
    plain = rules.jsonable(data)
    assert plain == {"when": NOW.isoformat(), "id": str(key), "tags": ["x", "y"], "set": ["a", "b"], "n": 3, "ok": True}
    assert rules.content_hash(data, {}) == rules.content_hash(plain, {})


def test_the_evidence_set_fingerprint():
    first, second = uuid.uuid4(), uuid.uuid4()
    items = [(first, "ACCEPTED", "SUPPORTING"), (second, "UNREVIEWED", "UNREVIEWED")]
    value = rules.evidence_set_hash(items)
    assert value == rules.evidence_set_hash(list(reversed(items)))
    assert value == rules.evidence_set_hash([(str(first).upper(), "accepted", "supporting"), (second, None, None)])
    assert value != rules.evidence_set_hash([(first, "REJECTED", "SUPPORTING"), (second, "UNREVIEWED", "UNREVIEWED")])
    assert value != rules.evidence_set_hash(items[:1])
    assert rules.evidence_set_hash([]) == rules.sha256_text("")


# ----------------------------------------------------------------------------------------------- hypotheses


def _hypothesis(business_id: str, *, human=None, ai="proposed", support=0, contradict=0) -> dict:
    return {
        "id": business_id.lower(),
        "business_id": business_id,
        "human_status": human,
        "ai_status": ai,
        "supporting_count": support,
        "contradicting_count": contradict,
    }


def test_the_ai_status_alone_never_makes_a_hypothesis_lead():
    hypotheses = [
        _hypothesis("HYP000001", ai="supported", support=9),
        _hypothesis("HYP000002", human="WEAKLY_SUPPORTED", support=5),
        _hypothesis("HYP000003", human="HYPOTHESIZED"),
    ]
    assert rules.leading_hypothesis(hypotheses) is None
    assert [item["business_id"] for item in rules.alternative_hypotheses(hypotheses, None)] == [
        "HYP000001",
        "HYP000002",
        "HYP000003",
    ]


def test_the_leading_hypothesis_is_the_best_supported_by_peoples_judgement():
    hypotheses = [
        _hypothesis("HYP000004", human="PARTIALLY_SUPPORTED", support=9),
        _hypothesis("HYP000002", human="STRONGLY_SUPPORTED", support=1, contradict=2),
        _hypothesis("HYP000003", human="STRONGLY_SUPPORTED", support=3),
        _hypothesis("HYP000001", human="STRONGLY_SUPPORTED", support=3, contradict=1),
        _hypothesis("HYP000005", human="RETIRED", support=20),
        _hypothesis("HYP000006", human="STRONGLY_SUPPORTED", ai="superseded", support=20),
    ]
    leading = rules.leading_hypothesis(hypotheses)
    assert leading["business_id"] == "HYP000003"  # strongest judgement, most support, least contradiction
    alternatives = [item["business_id"] for item in rules.alternative_hypotheses(hypotheses, leading)]
    assert alternatives == ["HYP000001", "HYP000002", "HYP000004"]  # retired and superseded are left out
    partial = [item for item in hypotheses if item["human_status"] == "PARTIALLY_SUPPORTED"]
    assert rules.leading_hypothesis(partial)["business_id"] == "HYP000004"
    tie = [_hypothesis("HYP000009", human="STRONGLY_SUPPORTED"), _hypothesis("HYP000008", human="STRONGLY_SUPPORTED")]
    assert rules.leading_hypothesis(tie)["business_id"] == "HYP000008"  # stable when everything else is equal


# ---------------------------------------------------------------------------------------------- AI disclosure


def test_the_ai_disclosure():
    assert rules.ai_statement([]) == rules.NO_AI_STATEMENT
    executions = [
        {"kind": rules.ai_kind("mdarix-controlled-hypothesis-engine"), "model": "claude-model"},
        {"kind": rules.ai_kind("MDARIX-CONTROLLED-INVESTIGATOR"), "model": "claude-model"},
    ]
    statement = rules.ai_statement(executions)
    assert statement.startswith(
        "AI assisted: 2 AI runs (Hypotheses, Investigation analysis) with claude-model in this investigation"
    )
    assert statement.endswith(rules.AI_JUDGEMENT_SENTENCE)
    assert "AI interpretation" in statement and "people made the judgements" in statement
    drafted = rules.ai_statement([], ai_draft_used=True)
    assert drafted.startswith("AI assisted: the author started the narrative from an AI draft")
    assert rules.ai_kind("something-new", "R1-Brief-v1") == "R1-Brief-v1"
    assert rules.ai_kind(None) == "AI run"


def test_risk_and_regulatory_review_sections():
    review = {"business_id": "REV000001", "status": "COMPLETED", "outcome": "NO_CHANGE_REQUIRED"}
    done = rules.review_section(review, {"result": "PASS"})
    assert done["state"] == "COMPLETED" and done["review"] == review and done["text"] is None
    requested = rules.review_section({**review, "status": "REQUESTED"}, {"result": "PENDING"})
    assert requested["state"] == "IN_PROGRESS"
    assert rules.review_section(None, {"result": "NOT_REQUIRED"})["text"] == "Not required by policy"
    assert rules.review_section(None, {"result": "PENDING"})["text"] == "Not done"
    assert rules.review_section(None, None)["state"] == "NOT_DONE"


# --------------------------------------------------------------------------------------------------- actions


def test_what_a_person_may_do_with_the_latest_version():
    base = {"can_work": True, "can_quality_review": True, "is_author": False, "case_open": True, "gate_ok": True}
    assert rules.brief_actions(status=None, **base)["can_compose"] is True
    draft = rules.brief_actions(status="DRAFT", **base)
    assert draft == {
        "can_compose": False,
        "can_edit": True,
        "can_submit": True,
        "can_start_review": False,
        "can_review": False,
    }
    assert rules.brief_actions(status="DRAFT", **{**base, "gate_ok": False})["can_submit"] is False
    ready = rules.brief_actions(status="READY_FOR_REVIEW", **base)
    assert ready["can_start_review"] and ready["can_review"] and not ready["can_compose"]
    assert not rules.brief_actions(status="READY_FOR_REVIEW", **{**base, "is_author": True})["can_review"]
    under = rules.brief_actions(status="UNDER_REVIEW", **base)
    assert under["can_review"] and not under["can_start_review"]
    for status in ("RETURNED", "APPROVED_FOR_DECISION"):
        assert rules.brief_actions(status=status, **base)["can_compose"] is True
    closed = rules.brief_actions(status="READY_FOR_REVIEW", **{**base, "case_open": False})
    assert not any(closed.values())
    viewer = rules.brief_actions(status="DRAFT", **{**base, "can_work": False, "can_quality_review": False})
    assert not any(viewer.values())


def test_request_bodies():
    assert rules.ReviewPayload(action="ACCEPT_FOR_DECISION").comment is None
    assert rules.ReviewPayload(action="RETURN_FOR_EVIDENCE", comment=f"  {COMMENT} ").comment == COMMENT
    with pytest.raises(ValidationError):
        rules.ReviewPayload(action="RETURN_FOR_EVIDENCE")
    with pytest.raises(ValidationError):
        rules.ReviewPayload(action="ESCALATE", comment="short")
    with pytest.raises(ValidationError):
        rules.ReviewPayload(action="START_REVIEW", comment=COMMENT)  # started through its own endpoint
    with pytest.raises(ValidationError):
        rules.ReviewPayload(action="APPROVE", comment=COMMENT)
    with pytest.raises(ValidationError):
        rules.DraftPayload()
    draft = rules.DraftPayload(recommended_actions=[" Replace the sensor ", ""])
    assert draft.recommended_actions == ["Replace the sensor"] and draft.model_fields_set == {"recommended_actions"}
    with pytest.raises(ValidationError):
        rules.DraftPayload(recommended_actions=["x" * (rules.ACTION_TEXT_MAX + 1)])
    with pytest.raises(ValidationError):
        rules.DraftPayload(recommended_actions=["x"] * (rules.ACTIONS_MAX + 1))
    assert rules.ComposePayload().use_ai_draft is False
    assert rules.SubmitPayload(comment="   ").comment is None


# ------------------------------------------------------------------------------------------------ composition


def _row(business_id: str, status: str, relationship: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "title": f"Evidence {business_id}",
        "review_status": status,
        "relationship": relationship,
    }


def test_the_evidence_inventory_counts_everything():
    rows = [
        _row("EVD000001", "ACCEPTED", "SUPPORTING"),
        _row("EVD000002", "ACCEPTED_WITH_LIMITATION", "CONTRADICTING"),
        _row("EVD000003", "UNREVIEWED", "UNREVIEWED"),
        _row("EVD000004", "ACCEPTED", "SUPPORTING"),
    ]
    section = compose.inventory_section(rows)
    assert section["total"] == 4 and section["truncated"] is False
    assert section["by_review_status"] == {"ACCEPTED": 2, "ACCEPTED_WITH_LIMITATION": 1, "UNREVIEWED": 1}
    assert section["by_relationship"] == {"SUPPORTING": 2, "CONTRADICTING": 1, "UNREVIEWED": 1}


def test_supporting_and_contradicting_evidence_of_the_case_and_its_hypotheses():
    rows = [_row("EVD000001", "ACCEPTED", "SUPPORTING"), _row("EVD000002", "ACCEPTED", "CONTRADICTING")]
    links = [
        {
            "relation": "support",
            "evidence_business_id": "EVD000003",
            "title": "Bench test",
            "hypothesis_business_id": "HYP000001",
            "rationale": "Drift seen",
            "linked_by": "HUMAN",
        },
        {
            "relation": "contextual",
            "evidence_business_id": "EVD000004",
            "title": "Manual",
            "hypothesis_business_id": "HYP000001",
            "rationale": None,
            "linked_by": "AI",
        },
    ]
    supporting, contradicting = compose.evidence_for_and_against(rows, links)
    assert [(item["source"], item["evidence_business_id"]) for item in supporting] == [
        ("CASE", "EVD000001"),
        ("HYPOTHESIS", "EVD000003"),
    ]
    assert supporting[1]["hypothesis_business_id"] == "HYP000001"
    assert [item["evidence_business_id"] for item in contradicting] == ["EVD000002"]


def test_evidence_for_and_against_the_leading_explanation_lists_each_piece_once():
    """0.10.72 (addendum): the sample brief listed EVD000001 and EVD000002 twice under supporting (the case's judgement
    and the leading hypothesis's link) and EVD000002 also under contradicting (its link to the alternative). Root
    cause: every hypothesis's links were merged into one list beside the case's own. Now: for and against the leading
    explanation, one entry per evidence; an alternative's links stay on the alternative."""
    from backend.app.decision_brief import compose

    rows = [
        {"business_id": "EVD000002", "title": "Inspection", "relationship": "SUPPORTING", "review_status": "ACCEPTED"},
        {"business_id": "EVD000001", "title": "Change", "relationship": "SUPPORTING", "review_status": "ACCEPTED"},
        {"business_id": "EVD000003", "title": "Trend", "relationship": "CONTEXTUAL", "review_status": "ACCEPTED"},
    ]
    link = lambda relation, evidence, hypothesis: {  # noqa: E731
        "relation": relation,
        "evidence_business_id": evidence,
        "title": evidence,
        "hypothesis_business_id": hypothesis,
        "rationale": f"{hypothesis} {relation}",
        "linked_by": "HUMAN",
    }
    links = [
        link("support", "EVD000001", "HYP000001"),
        link("support", "EVD000002", "HYP000001"),
        link("contradict", "EVD000002", "HYP000002"),
        link("contradict", "EVD000003", "HYP000002"),
    ]
    supporting, contradicting = compose.evidence_for_and_against(rows, links, "HYP000001")
    assert [item["evidence_business_id"] for item in supporting] == ["EVD000002", "EVD000001"]
    assert all(item["hypothesis_business_id"] == "HYP000001" for item in supporting)
    assert contradicting == []


# ---------------------------------------------------------------------------------------------------- routes


def test_the_routes_need_a_session_and_writes_their_permission():
    from backend.app.main import app
    from backend.app.request_context import get_request_context
    from tests.route_inventory import api_routes

    def needs_session(dependant) -> bool:
        return any(dep.call is get_request_context or needs_session(dep) for dep in dependant.dependencies)

    def guard(route) -> str | None:
        for dep in route.dependencies:
            if "require_permission" in getattr(dep.dependency, "__qualname__", ""):
                return dep.dependency
        return None

    base = "/api/v1/investigations/{investigation_id}/decision-brief"
    routes = {(method, path): route for path, route in api_routes(app) for method in route.methods}
    writes = {
        ("POST", base),
        ("PUT", base + "/draft"),
        ("POST", base + "/draft/refresh"),
        ("POST", base + "/submit"),
        ("POST", base + "/versions/{version}/start-review"),
        ("POST", base + "/versions/{version}/review"),
        ("GET", "/api/v1/decision-briefs/summary"),
        ("GET", "/api/v1/decision-briefs"),
    }
    reads = {("GET", base), ("GET", base + "/versions/{version}")}
    assert {key for key in routes if key[1].startswith(base)} | {
        key for key in routes if key[1].startswith("/api/v1/decision-briefs")
    } == writes | reads
    for key in writes | reads:
        assert needs_session(routes[key].dependant), key
    for key in writes:
        assert guard(routes[key]) is not None, key
    for key in reads:
        assert guard(routes[key]) is None, key
    ordered = [(method, path) for path, route in api_routes(app) for method in sorted(route.methods)]
    mine = ordered.index(("GET", "/api/v1/investigations/mine/summary"))
    assert all(ordered.index(key) > mine for key in reads)


def test_brief_tasks_name_their_source():
    from backend.app.workflow import router as tasks_router
    from backend.app.workflow.labels import SOURCE_LABELS

    assert SOURCE_LABELS["DecisionBriefVersion"] == "Decision brief"
    from backend.app.db.models.reviews import DecisionBriefVersion

    assert tasks_router._source_models()["DecisionBriefVersion"] is DecisionBriefVersion
