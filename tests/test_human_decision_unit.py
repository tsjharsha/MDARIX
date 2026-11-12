"""The human decision without a database: outcomes and follow-up actions with their labels, what a signing request
must hold (rationale, conditions, follow-ups, supersede reason), the brief checks (stale, tampered), the case states a
decision is taken in, the supersede rules, the refusal order behind ``can_sign``, residual unknowns, the signed
material (canonical fingerprint, signature hash, snapshot hash) and the verification checks, and the routes with their
guards."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.db.models.decision_outcomes import DECISION_OUTCOMES, FOLLOW_UP_ACTIONS
from backend.app.decision_brief import rules as brief_rules
from backend.app.human_decision import rules

pytestmark = pytest.mark.unit

RATIONALE = "The bench test reproduces the sensor drift of release B"
HASH = "a" * 64


# ----------------------------------------------------------------------------------------------------- labels


def test_every_outcome_and_follow_up_action_has_a_label_and_a_signature_code():
    assert tuple(rules.OUTCOMES) == DECISION_OUTCOMES
    assert tuple(rules.FOLLOW_UP_LABELS) == FOLLOW_UP_ACTIONS
    assert set(rules.FOLLOW_UP_ROLES) == set(FOLLOW_UP_ACTIONS)
    assert set(rules.SIGNATURE_CODES) == set(DECISION_OUTCOMES)
    # signed_approval_records.decision holds at most 12 characters, and each code maps back to one outcome.
    assert all(len(code) <= 12 for code in rules.SIGNATURE_CODES.values())
    assert {rules.OUTCOME_BY_CODE[code] for code in rules.SIGNATURE_CODES.values()} == set(DECISION_OUTCOMES)
    options = rules.outcome_options()
    assert [item["code"] for item in options] == list(DECISION_OUTCOMES)
    assert all(item["label"] and item["description"] for item in options)
    assert [item["code"] for item in rules.follow_up_options()] == list(FOLLOW_UP_ACTIONS)
    assert rules.outcome_label("accept_with_conditions") == "Accept with conditions"
    assert rules.follow_up_label("CAPA_REQUIRED") == "CAPA required"
    assert rules.outcome_label(None) is None


def test_follow_ups_land_in_the_role_queue_of_their_action():
    assert rules.default_follow_up_role("CAPA_REQUIRED") == "REVIEWER"
    assert rules.default_follow_up_role("PRODUCT_CHANGE_REQUIRED") == "REVIEWER"
    assert rules.default_follow_up_role("FIELD_ACTION_REVIEW_REQUIRED") == "REVIEWER"
    assert rules.default_follow_up_role("RISK_REASSESSMENT_REQUIRED") == "RISK_REVIEWER"
    assert rules.default_follow_up_role("REGULATORY_ACTION_REQUIRED") == "REGULATORY_REVIEWER"


def test_where_the_case_goes_after_each_outcome():
    assert rules.case_state_after("ACCEPT_CONCLUSION") == "DECIDED"
    assert rules.case_state_after("ACCEPT_WITH_CONDITIONS") == "DECIDED"
    assert rules.case_state_after("CLOSE_NO_FURTHER_ACTION") == "DECIDED"
    assert rules.case_state_after("REJECT_CONCLUSION") == "IN_PROGRESS"


def test_decision_identifiers_and_critical_cases():
    assert rules.decision_identifier("INV-2026-7", 3) == "INV-2026-7-D3"
    long = rules.decision_identifier("X" * 200, 12)
    assert len(long) == 120 and long.endswith("-D12")
    assert rules.is_critical("CRITICAL", False) and rules.is_critical("low", True)
    assert not rules.is_critical("HIGH", False)


# ---------------------------------------------------------------------------------------------------- requests


def _problem(**changes):
    values = {
        "outcome": "ACCEPT_CONCLUSION",
        "rationale": RATIONALE,
        "conditions": None,
        "follow_up_types": [],
        "supersedes_decision_id": None,
        "supersede_reason": None,
    }
    values.update(changes)
    return rules.payload_problem(**values)


def test_the_rationale_needs_20_to_5000_characters():
    assert _problem() is None
    assert "at least 20" in _problem(rationale="Too short")
    assert "at least 20" in _problem(rationale="   " + "x" * 19 + "   ")
    assert _problem(rationale="x" * 20) is None
    assert "at most 5000" in _problem(rationale="x" * 5001)


def test_conditions_go_with_accept_with_conditions_only():
    assert "conditions" in _problem(outcome="ACCEPT_WITH_CONDITIONS")
    assert "at least 10" in _problem(outcome="ACCEPT_WITH_CONDITIONS", conditions="short")
    assert _problem(outcome="ACCEPT_WITH_CONDITIONS", conditions="Retest lot 7 within 30 days") is None
    assert "at most 5000" in _problem(outcome="ACCEPT_WITH_CONDITIONS", conditions="x" * 5001)
    assert "only with" in _problem(outcome="ACCEPT_CONCLUSION", conditions="Retest lot 7 within 30 days")
    # Blank conditions are no conditions.
    assert _problem(outcome="CLOSE_NO_FURTHER_ACTION", conditions="   ") is None


def test_follow_ups_go_with_an_accepting_outcome_only():
    assert _problem(outcome="ACCEPT_CONCLUSION", follow_up_types=["CAPA_REQUIRED"]) is None
    assert (
        _problem(
            outcome="ACCEPT_WITH_CONDITIONS",
            conditions="Retest lot 7 within 30 days",
            follow_up_types=["CAPA_REQUIRED", "RISK_REASSESSMENT_REQUIRED"],
        )
        is None
    )
    assert "takes no follow-up" in _problem(outcome="REJECT_CONCLUSION", follow_up_types=["CAPA_REQUIRED"])
    assert "takes no follow-up" in _problem(outcome="CLOSE_NO_FURTHER_ACTION", follow_up_types=["CAPA_REQUIRED"])


def test_superseding_needs_a_reason_and_a_reason_needs_a_decision_to_supersede():
    earlier = uuid.uuid4()
    assert "at least 10" in _problem(supersedes_decision_id=earlier)
    assert "at least 10" in _problem(supersedes_decision_id=earlier, supersede_reason="late")
    assert _problem(supersedes_decision_id=earlier, supersede_reason="New bench results changed the picture") is None
    assert "at most 2000" in _problem(supersedes_decision_id=earlier, supersede_reason="x" * 2001)
    assert "only with" in _problem(supersede_reason="New bench results changed the picture")


def test_the_signing_request_checks_single_fields():
    body = {
        "brief_version_id": str(uuid.uuid4()),
        "brief_content_hash": HASH.upper(),
        "outcome": "ACCEPT_CONCLUSION",
        "rationale": f"  {RATIONALE}  ",
        "password": "secret",
    }
    payload = rules.SignPayload(**body)
    assert payload.brief_content_hash == HASH and payload.rationale == RATIONALE
    assert payload.follow_ups == [] and payload.residual_unknowns_acknowledged is False
    for wrong in (
        {"outcome": "RETURN"},
        {"brief_content_hash": "abc"},
        {"password": ""},
        {"mfa_code": "12"},
        {"follow_ups": [{"action_type": "SOMETHING"}]},
        {"follow_ups": [{"action_type": "CAPA_REQUIRED"}] * (rules.FOLLOW_UPS_MAX + 1)},
        {"follow_ups": [{"action_type": "CAPA_REQUIRED", "assigned_role": "CUSTOMER_ADMIN"}]},
    ):
        with pytest.raises(ValidationError):
            rules.SignPayload(**{**body, **wrong})


def test_a_follow_up_request_is_normalized():
    item = rules.FollowUpRequest(
        action_type="CAPA_REQUIRED", title="  ", assigned_role="risk reviewer", due_at=datetime(2026, 11, 5, 12, 0)
    )
    assert item.title is None and item.assigned_role == "RISK_REVIEWER"
    assert item.due_at.tzinfo is not None


def test_a_signing_refusal_never_echoes_the_password():
    """Cross-field problems are checked in the endpoint (payload_problem), so a 422 from the model only ever echoes
    the single field that is wrong: the model carries no model-level validator."""
    assert not rules.SignPayload.__pydantic_decorators__.model_validators


def test_the_return_comment_needs_10_to_5000_characters():
    brief = str(uuid.uuid4())
    assert rules.ReturnPayload(brief_version_id=brief, comment="  More bench data please  ").comment == (
        "More bench data please"
    )
    for comment in ("short", "x" * 5001):
        with pytest.raises(ValidationError):
            rules.ReturnPayload(brief_version_id=brief, comment=comment)


# ------------------------------------------------------------------------------------------------ brief and state


def test_the_brief_must_be_the_approved_unchanged_version():
    approved = brief_rules.APPROVED_FOR_DECISION
    ok = {"status": approved, "stored_hash": HASH, "sent_hash": HASH, "recomputed_hash": HASH}
    assert rules.brief_problem(**ok) is None
    assert rules.brief_problem(**{**ok, "sent_hash": HASH.upper()}) is None
    assert rules.brief_problem(**{**ok, "status": "SUPERSEDED"}) == rules.STALE_BRIEF
    assert rules.brief_problem(**{**ok, "status": "RETURNED"}) == rules.STALE_BRIEF
    assert rules.brief_problem(**{**ok, "sent_hash": "b" * 64}) == rules.STALE_BRIEF
    assert rules.brief_problem(**{**ok, "stored_hash": None}) == rules.STALE_BRIEF
    assert rules.brief_problem(**{**ok, "recomputed_hash": "c" * 64}) == rules.BRIEF_TAMPERED


def test_which_case_states_take_a_decision():
    assert rules.state_allows("READY_FOR_DECISION", False)
    assert rules.state_allows("READY_FOR_DECISION", True)
    for state in ("DECIDED", "IN_PROGRESS"):
        assert not rules.state_allows(state, False)
        assert rules.state_allows(state, True)
    for state in ("OPEN", "BRIEF_IN_REVIEW", "ON_HOLD", "CLOSED", "CANCELLED"):
        assert not rules.state_allows(state, True)
    code, message = rules.state_refusal("Brief in review")
    assert code == "CASE_NOT_READY_FOR_DECISION" and "brief in review" in message


def test_supersede_rules():
    current, other = uuid.uuid4(), uuid.uuid4()
    assert rules.supersede_problem(None, None) is None
    assert rules.supersede_problem(None, other)[0] == "SUPERSEDE_NOT_ALLOWED"
    assert rules.supersede_problem(current, None) == rules.SUPERSEDE_REQUIRED
    assert rules.supersede_problem(current, other)[0] == "SUPERSEDE_REQUIRED"
    assert rules.supersede_problem(current, current) is None
    assert rules.supersede_problem(current, str(current)) is None


def test_authors_never_decide():
    authors = ["Author-1", " editor-2 "]
    assert rules.is_author("author-1", authors) and rules.is_author("EDITOR-2", authors)
    assert not rules.is_author("approver-3", authors)
    assert rules.is_author("", authors)  # an unknown person is refused


def test_can_sign_refuses_in_the_order_the_endpoint_checks():
    allowed = {
        "administrator": False,
        "entitled": True,
        "brief": None,
        "state_ok": True,
        "state_label": "Ready for decision",
        "authority_denial": None,
        "author": False,
    }
    assert rules.sign_refusal(**allowed) is None
    everything = {
        **allowed,
        "administrator": True,
        "entitled": False,
        "brief": rules.STALE_BRIEF,
        "state_ok": False,
        "authority_denial": ("APPROVAL_AUTHORITY_DENIED", "Active role lacks approval authority"),
        "author": True,
    }
    order = [
        ("administrator", "ADMINISTRATOR_CANNOT_SIGN"),
        ("entitled", "DENIED_NOT_ENTITLED"),
        ("brief", "STALE_BRIEF"),
        ("state_ok", "CASE_NOT_READY_FOR_DECISION"),
        ("authority_denial", "APPROVAL_AUTHORITY_DENIED"),
        ("author", "SOD_DENIED"),
    ]
    values = dict(everything)
    for key, code in order:
        assert rules.sign_refusal(**values)[0] == code
        values[key] = allowed[key]
    assert rules.sign_refusal(**values) is None


# -------------------------------------------------------------------------------------------------- the brief


CONTENT = {
    "unknowns": {
        "open": [{"business_id": "UNK000001", "description": "Lot 7 not tested", "status": "open"}],
        "accepted_limitations": [
            {
                "business_id": "UNK000002",
                "description": "No field data from Japan",
                "status": "accepted_limitation",
                "resolution": "Japan is out of scope",
            }
        ],
    },
    "ai_assistance": {"executions": [{"business_id": "AIX000004"}, {"kind": "no id"}]},
    "context": {"evidence_set_hash": "e" * 64},
    "risk_review": {"state": "COMPLETED", "review": {"business_id": "REV000001", "outcome": "NO_CHANGE_REQUIRED"}},
    "regulatory_review": {"state": "NOT_REQUIRED", "review": None},
}


def test_residual_unknowns_ai_runs_and_evidence_set_come_from_the_brief():
    residual = rules.residual_unknowns(CONTENT)
    assert [(item["kind"], item["business_id"]) for item in residual] == [
        ("OPEN", "UNK000001"),
        ("ACCEPTED_LIMITATION", "UNK000002"),
    ]
    assert residual[1]["resolution"] == "Japan is out of scope"
    assert rules.residual_unknowns({}) == [] and rules.residual_unknowns(None) == []
    assert rules.ai_execution_refs(CONTENT) == ["AIX000004"]
    assert rules.evidence_set_hash(CONTENT) == "e" * 64 and rules.evidence_set_hash({}) is None
    reviews = rules.required_reviews(CONTENT)
    assert [(item["review_type"], item["outcome"]) for item in reviews] == [("RISK", "NO_CHANGE_REQUIRED")]


# ---------------------------------------------------------------------------------------------- the signature


def _material(**changes):
    values = {
        "decision_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "version": HASH,
        "outcome": "ACCEPT_WITH_CONDITIONS",
        "remarks": RATIONALE,
        "brief_version_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "evidence_set_hash": "e" * 64,
        "snapshot_hash": "f" * 64,
        "conditions": "Retest lot 7 within 30 days",
        "follow_up_actions": [{"action_type": "RISK_REASSESSMENT_REQUIRED"}, {"action_type": "CAPA_REQUIRED"}],
    }
    values.update(changes)
    return rules.signature_material(**values)


def test_the_signed_material_is_canonical():
    material = _material()
    assert material["type"] == "CASE_DECISION" and material["decision"] == "ACCEPT_WITH_CONDITIONS"
    assert material["decision_id"] == "11111111-1111-1111-1111-111111111111"
    assert material["follow_ups"] == ["CAPA_REQUIRED", "RISK_REASSESSMENT_REQUIRED"]
    # The order of follow-ups, the way ids are written and key order never change the fingerprint.
    same = _material(
        decision_id="11111111-1111-1111-1111-111111111111",
        follow_up_actions=["CAPA_REQUIRED", {"action_type": "RISK_REASSESSMENT_REQUIRED"}],
    )
    assert rules.fingerprint(same) == rules.fingerprint(material)
    assert rules.fingerprint(dict(reversed(list(material.items())))) == rules.fingerprint(material)
    assert rules.fingerprint(material) == brief_rules.sha256_text(brief_rules.canonical_json(material))
    # Everything signed changes the fingerprint.
    for change in (
        {"remarks": RATIONALE + "."},
        {"outcome": "ACCEPT_CONCLUSION"},
        {"conditions": "Retest lot 8 within 30 days"},
        {"follow_up_actions": [{"action_type": "CAPA_REQUIRED"}]},
        {"snapshot_hash": "0" * 64},
        {"evidence_set_hash": "1" * 64},
        {"brief_version_id": uuid.uuid4()},
        {"version": "b" * 64},
    ):
        assert rules.fingerprint(_material(**change)) != rules.fingerprint(material), change
    # Blank conditions are no conditions.
    assert _material(conditions="  ")["conditions"] is None


def test_the_signature_hash_binds_fingerprint_signer_and_version():
    value = rules.signature_hash("f1", "user-1", HASH)
    import hashlib

    assert value == hashlib.sha256(("f1" + "user-1" + HASH).encode()).hexdigest()
    assert rules.signature_hash("f1", "user-2", HASH) != value
    assert rules.short_fingerprint("0123456789abcdef0123") == "01234567…cdef0123"


def test_the_snapshot_hash_reads_back_the_same():
    snapshot = brief_rules.jsonable(
        {"decided_at": datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc), "brief": {"version": 2, "id": uuid.uuid4()}}
    )
    reordered = {key: snapshot[key] for key in reversed(list(snapshot))}
    assert rules.snapshot_hash(snapshot) == rules.snapshot_hash(reordered)
    assert rules.snapshot_hash({**snapshot, "outcome": "X"}) != rules.snapshot_hash(snapshot)
    assert len(rules.snapshot_hash(None)) == 64


def _signed():
    """A signature record and its decision as the endpoint writes them."""
    snapshot = {"brief": {"version": 2}, "outcome": "ACCEPT_WITH_CONDITIONS"}
    snapshot_digest = rules.snapshot_hash(snapshot)
    decision = {
        "id": "11111111-1111-1111-1111-111111111111",
        "outcome": "ACCEPT_WITH_CONDITIONS",
        "rationale": RATIONALE,
        "conditions": "Retest lot 7 within 30 days",
        "follow_up_actions": [{"action_type": "CAPA_REQUIRED", "title": "CAPA required for INV000001"}],
        "brief_version_id": "22222222-2222-2222-2222-222222222222",
        "evidence_set_hash": "e" * 64,
        "brief_content_hash": HASH,
    }
    material = rules.signature_material(
        decision_id=decision["id"],
        version=HASH,
        outcome=decision["outcome"],
        remarks=RATIONALE,
        brief_version_id=decision["brief_version_id"],
        evidence_set_hash=decision["evidence_set_hash"],
        snapshot_hash=snapshot_digest,
        conditions=decision["conditions"],
        follow_up_actions=decision["follow_up_actions"],
    )
    fingerprint = rules.fingerprint(material)
    record = {
        "decision": rules.SIGNATURE_CODES["ACCEPT_WITH_CONDITIONS"],
        "remarks": RATIONALE,
        "object_version": HASH,
        "content_fingerprint": fingerprint,
        "signature_hash": rules.signature_hash(fingerprint, "user-1", HASH),
        "signer_user_id": "user-1",
        "status": "SIGNED",
    }
    return record, decision, snapshot, snapshot_digest


def _checks(record, decision, snapshot, stored, **changes):
    values = {
        "record": record,
        "decision": decision,
        "snapshot": snapshot,
        "snapshot_found": True,
        "stored_snapshot_hash": stored,
        "brief_stored_hash": HASH,
        "brief_recomputed_hash": HASH,
    }
    values.update(changes)
    return {item["key"]: item["ok"] for item in rules.verification_checks(**values)}


def test_a_signed_decision_verifies_and_each_change_shows():
    record, decision, snapshot, stored = _signed()
    checks = rules.verification_checks(
        record=record,
        decision=decision,
        snapshot=snapshot,
        snapshot_found=True,
        stored_snapshot_hash=stored,
        brief_stored_hash=HASH,
        brief_recomputed_hash=HASH,
    )
    assert [item["key"] for item in checks] == ["fingerprint", "signature", "brief_hash", "snapshot"]
    assert all(item["ok"] for item in checks) and rules.verification_status(checks) == "VALID"
    assert [item["label"] for item in checks] == [rules.CHECK_LABELS[item["key"]] for item in checks]

    tampered_remarks = _checks({**record, "remarks": RATIONALE + " (edited)"}, decision, snapshot, stored)
    assert tampered_remarks == {"fingerprint": False, "signature": True, "brief_hash": True, "snapshot": True}
    tampered_snapshot = _checks(record, decision, {**snapshot, "outcome": "CLOSE_NO_FURTHER_ACTION"}, stored)
    assert tampered_snapshot["snapshot"] is False and tampered_snapshot["fingerprint"] is False
    rationale_changed = _checks(record, {**decision, "rationale": "Another rationale entirely"}, snapshot, stored)
    assert rationale_changed["fingerprint"] is False
    outcome_changed = _checks(record, {**decision, "outcome": "ACCEPT_CONCLUSION"}, snapshot, stored)
    assert outcome_changed["fingerprint"] is False
    conditions_changed = _checks(record, {**decision, "conditions": "No conditions at all"}, snapshot, stored)
    assert conditions_changed["fingerprint"] is False
    wrong_signer = _checks({**record, "signer_user_id": "user-2"}, decision, snapshot, stored)
    assert wrong_signer["signature"] is False and wrong_signer["fingerprint"] is True
    invalidated = _checks({**record, "status": "INVALIDATED"}, decision, snapshot, stored)
    assert invalidated["signature"] is False
    brief_changed = _checks(record, decision, snapshot, stored, brief_recomputed_hash="d" * 64)
    assert brief_changed["brief_hash"] is False and brief_changed["fingerprint"] is True
    missing = _checks(record, decision, None, stored, snapshot_found=False)
    assert missing["snapshot"] is False and missing["fingerprint"] is False
    assert rules.verification_status(None, signed=False) == "NOT_SIGNED"
    assert rules.verification_status([{"ok": True}, {"ok": False}]) == "INVALID"


def test_the_signature_meaning_names_the_brief_version_and_outcome():
    meaning = rules.signature_meaning("DBV000012", 3, "CLOSE_NO_FURTHER_ACTION")
    assert meaning == "I have reviewed Decision Brief DBV000012 version 3 and decide: Close with no further action"
    named = rules.signature_meaning("DBV000012", 3, "ACCEPT_CONCLUSION", "Asha Rao", "Leader (Quality Manager)")
    assert named == (
        "I, Asha Rao, Leader (Quality Manager), have reviewed Decision Brief DBV000012 version 3 and decide: "
        "Accept the conclusion"
    )
    assert rules.signature_meaning("DBV000012", 3, "ACCEPT_CONCLUSION", "Asha Rao").startswith("I, Asha Rao, have")


def test_the_signer_checks_read_back_authority_and_segregation_of_duties():
    def checks(**values):
        base = {"signer_user_id": "u-1", "signer_role_label": "Approver", "authority_id": "a-1", "author_refs": {"u-2"}}
        return {item["key"]: item for item in rules.signer_checks(**{**base, **values})}

    good = checks()
    assert good["authority"]["ok"] and good["separation"]["ok"]
    assert good["authority"]["label"] == "Approval authority" and good["separation"]["label"] == "Segregation of duties"
    assert checks(authority_id=None)["authority"]["ok"] is False
    assert checks(author_refs={"U-1"})["separation"]["ok"] is False  # the signer wrote the brief
    assert rules.verification_status(list(checks(author_refs={"u-1"}).values())) == "INVALID"


# ------------------------------------------------------------------------------------------------------ routes


def test_the_routes_need_a_session_and_the_queue_needs_decision_sign():
    from backend.app.access.permissions import DECISION_SIGN
    from backend.app.main import app
    from backend.app.request_context import get_request_context
    from tests.route_inventory import api_routes

    def needs_session(dependant) -> bool:
        return any(dep.call is get_request_context or needs_session(dep) for dep in dependant.dependencies)

    def guarded(route) -> bool:
        return any("require_permission" in getattr(dep.dependency, "__qualname__", "") for dep in route.dependencies)

    case = "/api/v1/investigations/{investigation_id}/decision"
    routes = {(method, path): route for path, route in api_routes(app) for method in route.methods}
    expected_guarded = {
        ("GET", "/api/v1/decisions/queue"),
        ("GET", "/api/v1/decisions/summary"),
        ("POST", case + "/return"),
    }
    # Signing is checked inside the route (as legacy signing is); the screen and the record are read by any
    # signed-in colleague of the organization.
    unguarded = {("POST", case + "/sign"), ("GET", case), ("GET", "/api/v1/decisions/{decision_id}/record")}
    for key in expected_guarded | unguarded:
        assert key in routes, key
        assert needs_session(routes[key].dependant), key
    for key in expected_guarded:
        assert guarded(routes[key]), key
    for key in unguarded:
        assert not guarded(routes[key]), key
    assert DECISION_SIGN == "decision.sign"
