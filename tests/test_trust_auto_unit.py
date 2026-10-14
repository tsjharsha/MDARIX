"""The automatic trust check's rules (trust_engine/auto.py), without a database: what passes, what warns, what
blocks, and how each kind of saved AI result is read (only what the reader sees, never what the checks removed)."""

from __future__ import annotations

import pytest

from trust_engine import auto


def _checks(verdict: dict) -> dict[str, str]:
    return {check["check_type"]: check["status"] for check in verdict["checks"]}


def _ai(**fields) -> auto.Output:
    return auto.Output(author=auto.AI, provider="anthropic", model="claude-sonnet-5-5", **fields)


def test_a_grounded_careful_ai_result_passes():
    verdict = auto.assess(
        _ai(
            statements=["EV-1 and EV-2 both report an occlusion alarm on Rev B."],
            cited=["EV-1", "EV-2"],
            known={"EV-1", "EV-2", "EV-3"},
        )
    )
    assert verdict["status"] == auto.STATUS_PASS and verdict["policy"] == auto.POLICY
    assert set(_checks(verdict).values()) == {auto.PASS}
    assert set(_checks(verdict)) == {
        "EVIDENCE_GROUNDING",
        "RESTRICTED_CLAIMS",
        "CERTAINTY_WORDING",
        "PROVENANCE",
        "TENANT_INTEGRITY",
    }
    assert auto.LIMITATION in verdict["limitations"]


def test_an_invented_source_blocks():
    verdict = auto.assess(_ai(statements=["A record says so."], cited=["EV-1", "EV-404"], known={"EV-1"}))
    grounding = next(check for check in verdict["checks"] if check["check_type"] == "EVIDENCE_GROUNDING")
    assert verdict["status"] == auto.STATUS_BLOCKED
    assert grounding["status"] == auto.BLOCKED and grounding["details"]["missing"] == ["EV-404"]
    assert "EV-404" in grounding["message"]


@pytest.mark.parametrize(
    "statement",
    [
        "The seal change is the root cause of the leaks.",
        "The supplier change caused the leak complaints.",
        "There is a 90% probability the firmware is responsible.",
        "A recall is required for lot 7.",
        "The complaints are reportable to FDA.",
        "MDARIX approves the investigation.",
    ],
)
def test_a_stated_cause_probability_or_decision_blocks_an_ai_result(statement):
    verdict = auto.assess(_ai(statements=[statement], cited=["EV-1"], known={"EV-1"}))
    assert verdict["status"] == auto.STATUS_BLOCKED
    restricted = next(check for check in verdict["checks"] if check["check_type"] == "RESTRICTED_CLAIMS")
    assert restricted["status"] == auto.BLOCKED and restricted["details"]["examples"] == [statement]


@pytest.mark.parametrize(
    "statement",
    [
        "Whether a CAPA is required is for the quality team to decide.",
        "The records do not show whether the seal change caused the leaks.",
        "The supplier change may contribute to the leaks.",
    ],
)
def test_hedged_or_open_wording_is_not_a_claim(statement):
    assert auto.assess(_ai(statements=[statement], cited=["EV-1"], known={"EV-1"}))["status"] == auto.STATUS_PASS


def test_asserted_certainty_warns_but_does_not_block():
    verdict = auto.assess(
        _ai(statements=["EV-1 definitively shows a cracked housing."], cited=["EV-1"], known={"EV-1"})
    )
    assert verdict["status"] == auto.STATUS_LIMITED
    assert _checks(verdict)["CERTAINTY_WORDING"] == auto.WARNING


def test_an_ai_result_without_provider_or_model_blocks():
    verdict = auto.assess(
        auto.Output(author=auto.AI, statements=["EV-1 reports a leak."], cited=["EV-1"], known={"EV-1"})
    )
    assert verdict["status"] == auto.STATUS_BLOCKED and _checks(verdict)["PROVENANCE"] == auto.BLOCKED


def test_nothing_cited_is_a_limitation_not_a_pass():
    verdict = auto.assess(_ai(statements=["The complaints look alike."], cited=[], known={"EV-1"}))
    assert verdict["status"] == auto.STATUS_LIMITED and _checks(verdict)["EVIDENCE_GROUNDING"] == auto.WARNING
    assert "The result cites no records." in verdict["limitations"]


def test_rules_results_are_checked_for_grounding_and_provenance_only():
    # The rules may quote the records ("caused the alarm" in a complaint's own words); that is not an AI claim.
    rules = auto.Output(
        author=auto.RULES, statements=["EV-1: 'the pump caused the alarm'."], cited=["EV-1"], known={"EV-1"}
    )
    verdict = auto.assess(rules)
    assert verdict["status"] == auto.STATUS_PASS and verdict["author"] == auto.RULES
    assert "MDARIX rules" in next(c["message"] for c in verdict["checks"] if c["check_type"] == "PROVENANCE")
    invented = auto.assess(auto.Output(author=auto.RULES, cited=["EV-9"], known={"EV-1"}))
    assert invented["status"] == auto.STATUS_BLOCKED


def test_a_result_of_another_organization_blocks():
    verdict = auto.assess(
        _ai(statements=["EV-1 reports a leak."], cited=["EV-1"], known={"EV-1"}), tenant_matches=False
    )
    assert verdict["status"] == auto.STATUS_BLOCKED and _checks(verdict)["TENANT_INTEGRITY"] == auto.BLOCKED


def test_dropped_statements_are_reported_as_a_limitation():
    verdict = auto.assess(_ai(statements=["EV-1 reports a leak."], cited=["EV-1"], known={"EV-1"}, dropped=2))
    assert verdict["status"] == auto.STATUS_PASS
    assert "The feature's own checks already removed 2 statements." in verdict["limitations"]


# ------------------------------------------------------------------------------------------- reading results


def _reference(identifier: str) -> dict:
    return {
        "reference_type": "EVIDENCE",
        "evidence_identifier": identifier,
        "source_anchor": {"quote": "caused the leak"},
    }


def test_a_model_analysis_is_read_without_what_its_checks_removed():
    analysis = {
        "analysis_author": "LANGUAGE_MODEL",
        "summary": "Two records describe a leak after the seal change.",
        "observations": [{"statement": "EV-1 reports a leak.", "source_references": [_reference("EV-1")]}],
        "possible_explanations": [
            {"statement": "The seal change may contribute.", "source_references": [_reference("EV-2")]}
        ],
        "rejected_items": [
            {"statement": "The seal change caused the leaks.", "source_references": [_reference("EV-9")]}
        ],
        "model_provenance": {
            "analysis_author": "LANGUAGE_MODEL",
            "model_analysis": {"provider": "anthropic", "model": "claude-sonnet-5-5"},
            "checks_dropped": [{"reason": "CAUSAL_OR_DECISION_CLAIM"}],
        },
    }
    read = auto.read_case_output(analysis)
    assert read.author == auto.AI and (read.provider, read.model) == ("anthropic", "claude-sonnet-5-5")
    assert read.cited == ["EV-1", "EV-2"]
    assert "The seal change caused the leaks." not in read.statements
    assert "EV-1 reports a leak." in read.statements and read.dropped == 2
    read.known = {"EV-1", "EV-2"}
    assert auto.assess(read)["status"] == auto.STATUS_PASS


def test_hypotheses_and_rules_outputs_say_who_wrote_them():
    hypotheses = {
        "hypotheses": [{"statement": "A process change may contribute.", "source_references": [_reference("EV-1")]}],
        "rejected_hypotheses": [{"statement": "x", "source_references": [_reference("EV-7")]}],
        "provenance": {"author": "LANGUAGE_MODEL", "model_analysis": {"provider": "groq", "model": "m"}},
    }
    read = auto.read_case_output(hypotheses)
    assert read.author == auto.AI and read.cited == ["EV-1"] and read.dropped == 1
    unknowns = {"unknowns": [{"statement": "Lot data is missing.", "source_references": []}], "provenance": {}}
    assert auto.read_case_output(unknowns).author == auto.RULES


def test_cited_sentences_and_brief_drafts_are_read():
    summary = {
        "sentences": [{"text": "Two complaints describe an alarm.", "complaints": ["CMP1", "CMP2"]}],
        "dropped": [{"text": "x", "reason": "NO_CITATION"}],
        "model": {"provider": "anthropic", "model": "claude-sonnet-5-5"},
    }
    read = auto.read_cited_sentences(summary, cite_key="complaints")
    assert (
        read.cited == ["CMP1", "CMP2"]
        and read.statements == ["Two complaints describe an alarm."]
        and read.dropped == 1
    )
    brief = {
        "headline": "The supplier change is a lead, not a finding.",
        "sections": {"what_we_know": [{"statement": "EV-1 came first.", "evidence": ["EV-1"]}], "next_steps": []},
        "checks_dropped": [],
        "model": {"provider": "groq", "model": "m"},
    }
    read = auto.read_brief(brief)
    assert read.statements == ["The supplier change is a lead, not a finding.", "EV-1 came first."]
    assert read.cited == ["EV-1"] and read.provider == "groq"


def test_an_ask_answer_gets_the_same_verdict_from_asks_own_checks():
    clean = auto.assess_answer(
        {
            "cited": ["EV-1"],
            "unverified_citations": [],
            "causal_or_decision_wording": False,
            "certainty_wording": False,
        },
        provider="anthropic",
        model="claude-sonnet-5-5",
        model_written=True,
    )
    assert clean["status"] == auto.STATUS_PASS and clean["label"] == "Trust check passed"
    invented = auto.assess_answer(
        {"cited": ["EV-1", "EV-9"], "unverified_citations": ["EV-9"], "causal_or_decision_wording": False},
        provider="anthropic",
        model="claude-sonnet-5-5",
        model_written=True,
    )
    assert invented["status"] == auto.STATUS_BLOCKED
    causal = auto.assess_answer(
        {"cited": ["EV-1"], "unverified_citations": [], "causal_or_decision_wording": True},
        provider="anthropic",
        model="claude-sonnet-5-5",
        model_written=True,
    )
    assert causal["status"] == auto.STATUS_BLOCKED
    certain = auto.assess_answer(
        {"cited": ["EV-1"], "unverified_citations": [], "certainty_wording": True},
        provider="anthropic",
        model="claude-sonnet-5-5",
        model_written=True,
    )
    assert certain["status"] == auto.STATUS_LIMITED
    records = auto.assess_answer({}, provider="controlled", model=None, model_written=False)
    assert records["status"] == auto.STATUS_PASS and records["author"] == auto.RULES
