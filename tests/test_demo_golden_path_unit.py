"""The demo workspace's golden path without a database: its pure helpers, and that the story it writes passes the same
rules the endpoints apply (backend/app/demo_golden_path/, backend/app/demo_story.py)."""

from datetime import datetime, timedelta, timezone

from backend.app import demo_golden_path as golden
from backend.app import demo_story as story

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def test_story_moment_counts_days_back_and_minutes_forward():
    assert golden.story_moment(NOW, 3) == NOW - timedelta(days=3)
    assert golden.story_moment(NOW, 3, 45) == NOW - timedelta(days=3) + timedelta(minutes=45)
    assert golden.story_moment(NOW, 3) < golden.story_moment(NOW, 3, 1) < golden.story_moment(NOW, 2)


def test_only_wall_clock_stamps_of_this_run_are_retimed():
    wall = NOW
    moment = NOW - timedelta(days=10)
    assert golden.retimed(None, wall, moment) is None
    assert golden.retimed(NOW - timedelta(seconds=1), wall, moment) == NOW - timedelta(seconds=1)
    assert golden.retimed(NOW, wall, moment) == moment
    assert golden.retimed(NOW + timedelta(minutes=5), wall, moment) == moment


def test_scope_two_keeps_order_and_leaves_out_the_excluded_and_late_complaints():
    ids = ["a", "b", "c", "d", "e", "f", "g", "late"]
    included, excluded = golden.scope_split(ids, excluded_index=5, late_index=7)
    assert included == ["a", "b", "c", "d", "e", "g"]
    assert excluded == ["f"]


def test_story_today_is_read_back_from_the_golden_case():
    opened = NOW - timedelta(days=61)
    assert golden.story_today(opened, 61) == NOW
    assert golden._opened_days() == 61


def test_the_golden_story_records_fit_together():
    cases = {item[0]: item for item in story.INVESTIGATIONS}
    assert cases[story.GOLDEN_CASE][1] == story.GOLDEN_PRODUCT and cases[story.GOLDEN_CASE][3] == "open"
    complaints = [item for item in story.COMPLAINTS if item[0] == story.GOLDEN_PRODUCT]
    # Seven complaints before the decision (one to be excluded) and one late complaint after it.
    assert len(complaints) == 8
    assert all(len(item) == 6 and item[5] == story.GOLDEN_PROBLEM for item in complaints)
    assert complaints[-1][3] < 6 < complaints[-2][3]
    # Complaint identifiers are positional: the earlier story keeps its numbers.
    assert all(item[0] != story.GOLDEN_PRODUCT for item in story.COMPLAINTS[:32])
    codes = {code for code, *_ in story.EVIDENCE[story.GOLDEN_CASE]}
    assert story.GOLDEN_DEFERRED_EVIDENCE <= codes
    assert {code for code, *_ in golden.EVIDENCE_REVIEWS} <= codes - story.GOLDEN_DEFERRED_EVIDENCE


def test_the_demo_team_has_one_synthetic_person_per_workflow_role():
    from backend.app.demo_workspace import DEMO_TEAM
    from backend.app.role_codes import WORKFLOW_ROLES, role_code

    roles = [role_code(role) for role, _, _ in DEMO_TEAM]
    assert set(WORKFLOW_ROLES) <= set(roles)
    assert set(golden.NEEDED_ROLES) <= set(roles)
    emails = [email for _, email, _ in DEMO_TEAM]
    assert len(set(emails)) == len(emails)
    assert all(email.endswith("@acmecare-demo.invalid") for email in emails)
    names = {role_code(role): name for role, _, name in DEMO_TEAM}
    assert (names["TRIAGE_LEAD"], names["RISK_REVIEWER"], names["REGULATORY_REVIEWER"]) == (
        "Tara Triage",
        "Rita Risk",
        "Rory Regulatory",
    )


def test_the_seeded_reviews_pass_the_review_rules():
    from backend.app.case_reviews import rules as review_rules
    from backend.app.evidence_workflow.rules import review_problem

    for code, status, relationship, _, reason, limitation in golden.EVIDENCE_REVIEWS:
        assert review_problem(status, relationship, reason, limitation) is None, code
    assert {item[1] for item in golden.EVIDENCE_REVIEWS} >= {"ACCEPTED", "ACCEPTED_WITH_LIMITATION", "REJECTED"}
    assert {item[2] for item in golden.EVIDENCE_REVIEWS} >= {"SUPPORTING", "CONTRADICTING"}
    for review_type, *_, outcome, rationale, _, _ in golden.CASE_REVIEWS:
        assert review_rules.outcome_problem(review_type, outcome) is None
        assert len(rationale) >= review_rules.RATIONALE_MIN


def test_the_failure_chain_has_mixed_link_states_with_their_evidence():
    from backend.app.case_intelligence import rules as intelligence

    states = [state for _, _, state, _, _ in golden.CHAIN_LINKS]
    assert len(set(states)) >= 3 and set(states) <= set(intelligence.LINK_STATE_CODES)
    for start, end, state, code, _ in golden.CHAIN_LINKS:
        assert 0 <= start < end < len(golden.CHAIN_NODES)
        assert not intelligence.state_needs_evidence(state) or code is not None
    assert {kind for _, kind, _, _ in golden.OBSERVATIONS} <= set(intelligence.HUMAN_EPISTEMIC_TYPES)


def test_the_briefs_and_the_decision_pass_the_signing_rules():
    from backend.app.decision_brief import rules as brief_rules
    from backend.app.human_decision import rules

    for narrative in (golden.BRIEF_V1, golden.BRIEF_V2):
        assert brief_rules.narrative_problems(narrative) == []
    assert brief_rules.comment_problem("RETURN_FOR_EVIDENCE", golden.RETURN_COMMENT) is None
    assert brief_rules.comment_problem("ACCEPT_FOR_DECISION", golden.ACCEPT_COMMENT) is None
    assert (
        rules.payload_problem(
            outcome=rules.ACCEPT_WITH_CONDITIONS,
            rationale=golden.DECISION_RATIONALE,
            conditions=golden.DECISION_CONDITIONS,
            follow_up_types=["CAPA_REQUIRED"],
            supersedes_decision_id=None,
            supersede_reason=None,
        )
        is None
    )


def test_a_signature_made_with_the_signing_functions_verifies():
    """The seeding signs with exactly these functions; the verification of the signing code accepts the result."""
    from backend.app.human_decision import rules

    snapshot = {"decision_id": "d-1", "content": {"context": {"evidence_set_hash": "e" * 64}}, "outcome": "X"}
    snapshot_hash = rules.snapshot_hash(snapshot)
    follow_ups = [{"action_type": "CAPA_REQUIRED", "title": golden.CAPA_TITLE}]
    version = "b" * 64
    material = rules.signature_material(
        decision_id="d-1",
        version=version,
        outcome=rules.ACCEPT_WITH_CONDITIONS,
        remarks=golden.DECISION_RATIONALE,
        brief_version_id="brief-2",
        evidence_set_hash="e" * 64,
        snapshot_hash=snapshot_hash,
        conditions=golden.DECISION_CONDITIONS,
        follow_up_actions=follow_ups,
    )
    fingerprint = rules.fingerprint(material)
    checks = rules.verification_checks(
        record={
            "decision": rules.SIGNATURE_CODES[rules.ACCEPT_WITH_CONDITIONS],
            "remarks": golden.DECISION_RATIONALE,
            "object_version": version,
            "content_fingerprint": fingerprint,
            "signature_hash": rules.signature_hash(fingerprint, "user-ana", version),
            "signer_user_id": "user-ana",
            "status": "SIGNED",
        },
        decision={
            "id": "d-1",
            "outcome": rules.ACCEPT_WITH_CONDITIONS,
            "rationale": golden.DECISION_RATIONALE,
            "conditions": golden.DECISION_CONDITIONS,
            "follow_up_actions": follow_ups,
            "brief_version_id": "brief-2",
            "evidence_set_hash": "e" * 64,
            "brief_content_hash": version,
        },
        snapshot=snapshot,
        snapshot_found=True,
        stored_snapshot_hash=snapshot_hash,
        brief_stored_hash=version,
        brief_recomputed_hash=version,
    )
    assert rules.verification_status(checks) == "VALID"
