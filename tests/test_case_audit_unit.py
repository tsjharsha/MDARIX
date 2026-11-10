"""The pure rules of a case's trust and audit views (backend/app/case_audit/rules.py): timeline items merged,
deduplicated, sorted, filtered and paged; titles; safe details and actors; "known then" partitioning and statuses as
of a moment; AI run kinds, guardrails and context hashes; legacy signature checks; the audit chain summary; the CSV
rows of an export."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.case_audit import rules

pytestmark = pytest.mark.unit

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
TASK = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
PERSON = "33333333-3333-4333-8333-333333333333"


def _item(at, category="TASK", event="TASK_COMPLETED", *, match=(TASK,), source="domain", key=None, **values):
    return rules.item(
        at=at,
        category=category,
        event=event,
        title=values.pop("title", event),
        match=match,
        source=source,
        key=key,
        **values,
    )


# ----------------------------------------------------------------------------------------- merge and dedupe


def test_an_audit_event_repeating_a_history_row_is_dropped():
    domain = _item(T0)
    audit = _item(T0 + timedelta(seconds=2), source="audit", key="audit:1")
    merged = rules.merge([[domain], [audit]])
    assert len(merged) == 1 and merged[0]["_source"] == "domain"


def test_an_audit_event_outside_the_window_or_about_another_record_is_kept():
    domain = _item(T0)
    late = _item(T0 + timedelta(seconds=rules.DEDUPE_WINDOW_SECONDS + 5), source="audit", key="audit:1")
    elsewhere = _item(T0, match=(OTHER,), source="audit", key="audit:2")
    other_code = _item(T0, event="TASK_ASSIGNED", source="audit", key="audit:3")
    assert len(rules.merge([[domain, late, elsewhere, other_code]])) == 4


def test_an_alias_code_counts_as_the_same_change():
    domain = _item(T0, category="BRIEF", event="BRIEF_SUBMITTED", aliases=("BRIEF_RESUBMITTED",))
    audit = _item(T0, category="BRIEF", event="BRIEF_RESUBMITTED", source="audit", key="audit:9")
    assert [entry["event"] for entry in rules.merge([[domain, audit]])] == ["BRIEF_SUBMITTED"]


def test_the_same_audit_event_read_from_two_planes_appears_once():
    first = _item(T0, event="INVESTIGATION_OPENED", category="CASE", source="audit", key="audit:7")
    second = dict(first)
    assert len(rules.dedupe([first, second])) == 1


def test_items_are_oldest_first_and_in_flow_order_at_the_same_moment():
    decision = _item(T0, category="DECISION", event="CASE_DECISION_SIGNED", match=(OTHER,))
    signal = _item(T0, category="SIGNAL", event="SIGNAL_CREATED", match=(OTHER,))
    earlier = _item(T0 - timedelta(days=1), category="AUDIT", event="X", match=())
    undated = _item(None, category="CASE", event="Y", match=())
    ordered = rules.sort_items([decision, signal, earlier, undated])
    assert [entry["event"] for entry in ordered] == ["Y", "X", "SIGNAL_CREATED", "CASE_DECISION_SIGNED"]


def test_filters_paging_and_counts():
    items = [
        _item(T0, category="AI", event="AI_RUN_RECORDED", actor={"name": "Ada Lovelace", "role_label": None}),
        _item(T0 + timedelta(hours=1), category="DECISION", event="CASE_DECISION_SIGNED", actor={"name": "Bo"}),
        _item(T0 + timedelta(hours=2), category="AI", event="ASK_ANSWERED", actor=None),
    ]
    assert rules.parse_types("ai, decision ,nonsense") == {"AI", "DECISION"}
    assert rules.parse_types(None) is None
    only_ai = rules.filter_items(items, types={"AI"})
    assert [entry["event"] for entry in only_ai] == ["AI_RUN_RECORDED", "ASK_ANSWERED"]
    assert [entry["event"] for entry in rules.filter_items(items, actor="ada")] == ["AI_RUN_RECORDED"]
    window = rules.filter_items(items, since=T0 + timedelta(minutes=30), until=T0 + timedelta(hours=1))
    assert [entry["event"] for entry in window] == ["CASE_DECISION_SIGNED"]
    assert rules.category_counts(items) == {"AI": 2, "DECISION": 1}
    assert rules.page_of(list(range(10)), 2, 4) == [4, 5, 6, 7]
    assert rules.page_of(list(range(10)), 1, 10_000) == list(range(10))


def test_public_items_carry_no_merge_keys_and_iso_times():
    entry = rules.public(_item(T0, key="audit:1"))
    assert not any(key.startswith("_") for key in entry)
    assert entry["at"] == T0.isoformat()
    assert set(entry) == {"at", "category", "event", "title", "actor", "object", "reason", "details", "origin"}


# --------------------------------------------------------------------------------------------- titles and text


def test_titles_are_plain_words():
    assert rules.title("Risk review completed", "Risk control review required") == (
        "Risk review completed: Risk control review required"
    )
    assert rules.title("Case opened") == "Case opened"
    assert rules.readable("CASE_REVIEW_COMPLETED") == "Case review completed"
    assert rules.audit_title("TASK_COMPLETED") == "Task completed"
    assert rules.audit_title("INTELLIGENCE_STATUS_CHANGED") == "Investigation intelligence: status changed"
    assert (
        rules.audit_title("INVESTIGATION_STATE_CHANGED", "now in progress")
        == "Investigation state changed: now in progress"
    )
    assert rules.audit_title("SOMETHING_NEW_HAPPENED") == "Something new happened"


@pytest.mark.parametrize(
    "action, category",
    [
        ("TASK_ASSIGNED", "TASK"),
        ("SIGNAL_MERGED", "SIGNAL"),
        ("EVIDENCE_REQUEST_RESPONDED", "REQUEST"),
        ("EVIDENCE_REVIEWED", "EVIDENCE"),
        ("LATE_EVIDENCE_RECEIVED", "EVIDENCE"),
        ("CASE_REVIEW_STARTED", "REVIEW"),
        ("BRIEF_SUBMITTED", "BRIEF"),
        ("BRIEF_GENERATED", "AI"),
        ("CASE_DECISION_SIGNED", "DECISION"),
        ("DECISION_ADVISORY_CREATED", "AI"),
        ("DECISION_UNDER_RECONSIDERATION", "IMPACT"),
        ("FOLLOW_UP_STARTED", "FOLLOW_UP"),
        ("IMPACT_ASSESSMENT_COMPLETED", "IMPACT"),
        ("INVESTIGATION_SCOPE_CHANGED", "SCOPE"),
        ("INVESTIGATION_STATE_CHANGED", "CASE"),
        ("GENAI_EXECUTION_RECORDED", "AI"),
        ("CASE_AUDIT_EXPORTED", "AUDIT"),
        ("PRODUCT360_TEMPORAL_RETRIEVAL", "AUDIT"),
    ],
)
def test_audit_actions_land_in_their_category(action, category):
    assert rules.audit_category(action) == category


def test_details_never_carry_secrets_or_bare_ids_and_stay_small():
    details = rules.safe_details(
        {
            "password": "Hunter2!",
            "mfa_code": "123456",
            "session_token": "abc",
            "api_key": "sk-1",
            "fingerprint": "f" * 64,
            "user_prompt": "who is the patient",
            "decision_id": OTHER,
            "decision_business_id": "DEC000001",
            "outcome": "ACCEPT_CONCLUSION",
            "note": "x" * 1000,
            "nested": {"a": 1},
            "flags": ["A", "B"],
        }
    )
    assert set(details) == {"decision_business_id", "outcome", "note", "flags"}
    assert len(details["note"]) <= rules.DETAIL_TEXT_MAX
    assert rules.safe_details({"outcome": "X", "other": "Y"}, ("outcome",)) == {"outcome": "X"}
    assert rules.safe_details(None) == {}
    many = rules.safe_details({f"k{index}": index for index in range(50)})
    assert len(many) == rules.DETAIL_KEYS_MAX


def test_actors_are_shown_by_name_never_by_id():
    names = {PERSON: "Ada Lovelace"}
    assert rules.actor_view(PERSON, "INVESTIGATOR", names, lambda code: "Investigator") == {
        "name": "Ada Lovelace",
        "role_label": "Investigator",
    }
    assert rules.actor_view(OTHER, None, names) == {"name": rules.UNKNOWN_PERSON, "role_label": None}
    assert rules.actor_view("MDARIX-Decision-Center", None, names)["name"] == "MDARIX"
    assert rules.actor_view(None, None, names) is None
    assert rules.origin_of(PERSON) == "HUMAN"
    assert rules.origin_of("system:scheduler") == "SYSTEM"
    assert rules.origin_of(PERSON, ai=True) == "AI"
    assert rules.audit_origin(PERSON, "DECISION_ADVISORY_CREATED") == "AI"


# ------------------------------------------------------------------------------------------------- known then


def test_a_record_is_known_from_its_first_known_time_but_not_before_it_was_linked():
    ingested, linked = T0, T0 + timedelta(days=2)
    assert rules.known_at((ingested, None, T0 - timedelta(days=1)), linked) == linked
    assert rules.known_at((None, T0, None), None) == T0
    assert rules.known_at((None, None), linked) == linked
    assert rules.known_at((), None) is None


def test_partition_into_known_then_and_arrived_later():
    items = [
        {"business_id": "E1", "known_at": T0 - timedelta(hours=1)},
        {"business_id": "E2", "known_at": T0},
        {"business_id": "E3", "known_at": T0 + timedelta(seconds=1)},
        {"business_id": "E4", "known_at": None},
    ]
    known, later = rules.partition_known(items, T0)
    assert [entry["business_id"] for entry in known] == ["E1", "E2"]
    assert [entry["business_id"] for entry in later] == ["E3", "E4"]


def test_a_status_as_of_a_moment_is_rebuilt_from_its_history():
    history = [
        (T0 + timedelta(days=1), "PROPOSED", "PARTIALLY_SUPPORTED"),
        (T0 + timedelta(days=3), "PARTIALLY_SUPPORTED", "STRONGLY_SUPPORTED"),
    ]
    now = "STRONGLY_SUPPORTED"
    assert rules.value_as_of(history, T0 + timedelta(days=2), current=now) == "PARTIALLY_SUPPORTED"
    assert rules.value_as_of(history, T0 + timedelta(days=4), current=now) == "STRONGLY_SUPPORTED"
    # Before the first recorded change: the value that change started from.
    assert rules.value_as_of(history, T0, current=now) == "PROPOSED"
    # The order of the history does not matter.
    assert rules.value_as_of(list(reversed(history)), T0 + timedelta(days=2), current=now) == "PARTIALLY_SUPPORTED"
    # Without history: the current value when it was set by then (or never dated), else the default.
    assert rules.value_as_of([], T0, current="resolved", current_changed_at=T0 - timedelta(days=1)) == "resolved"
    assert rules.value_as_of([], T0, current="resolved", current_changed_at=None) == "resolved"
    assert (
        rules.value_as_of([], T0, current="resolved", current_changed_at=T0 + timedelta(days=1), default="open")
        == "open"
    )


def test_the_evidence_set_hash_is_the_decision_briefs():
    from backend.app.decision_brief.rules import evidence_set_hash

    items = [(TASK, "ACCEPTED", "SUPPORTING"), (OTHER, None, None)]
    assert rules.evidence_set_hash(items) == evidence_set_hash(items)
    assert rules.evidence_set_hash(reversed(items)) == evidence_set_hash(items)


# ---------------------------------------------------------------------------------------------------- AI runs


@pytest.mark.parametrize(
    "provider, model, template, kind",
    [
        ("mdarix-controlled-investigator", "llama", "R1-MVP-P3-Investigator-v2", "analysis"),
        ("mdarix-controlled-hypothesis-engine", "x", None, "hypotheses"),
        ("mdarix-controlled-ai-challenger", "x", None, "challenger"),
        ("mdarix-controlled-unknowns-radar", "x", None, "unknowns"),
        ("mdarix-controlled-failure-chain", "x", None, "failure_chain"),
        ("mdarix-controlled-decision-advisory", "x", None, "decision_advisory"),
        ("deterministic-r1", "constrained-counterfactual", "D16-1", "counterfactual"),
        ("deterministic-r1", "controlled-scenario", "D32-1", "scenario"),
        ("groq", "llama-3", "v1.0", "evidence_extraction"),
        ("unknown-provider", "m", "t", "other"),
    ],
)
def test_ai_run_kinds(provider, model, template, kind):
    assert rules.ai_kind(provider, model, template) == kind
    assert kind in rules.AI_KINDS


def test_guardrails_status_usage_and_times_of_a_run():
    output = {
        "guardrails": {"no_root_cause_conclusion": True, "human_authority_required": True, "x": False, "note": "n"},
        "rejected_items": [{}, {}],
        "model_provenance": {"checks_dropped": [{}], "model_analysis": {"input_tokens": 120, "output_tokens": 40}},
    }
    summary = rules.guardrail_summary(output, "VALIDATED", None)
    assert summary == {
        "validation_status": "VALIDATED",
        "checks": 3,
        "passed": 2,
        "failed": ["x"],
        "rejected_items": 2,
        "dropped_statements": 1,
        "error": None,
    }
    assert rules.guardrail_summary(None, None, None)["checks"] == 0
    assert rules.usage(output) == {"input_tokens": 120, "output_tokens": 40, "estimated_cost": None}
    assert rules.run_status("VALIDATED", None) == "VALIDATED"
    assert rules.run_status("FAILED", None) == "FAILED"
    assert rules.run_status(None, "boom") == "FAILED"
    assert rules.run_status(None, None) == "COMPLETED"
    times = rules.run_times(T0, 1500)
    assert times == {
        "started_at": (T0 - timedelta(milliseconds=1500)).isoformat(),
        "finished_at": T0.isoformat(),
        "duration_ms": 1500,
    }
    assert rules.run_times(T0, None)["started_at"] is None


def test_the_context_hash_does_not_depend_on_key_order():
    first = rules.context_hash({"a": 1, "b": [1, 2]}, {"evidence": ["E1"]})
    second = rules.context_hash({"b": [1, 2], "a": 1}, {"evidence": ["E1"]})
    assert first == second and len(first) == 64
    assert rules.context_hash({"a": 2}, None) != rules.context_hash({"a": 1}, None)
    assert rules.context_hash(None, None) is None


def test_ai_counts():
    runs = [
        {"kind": "analysis", "used_in_signed_decision": True, "human_review": {"status": "ACCEPTED"}},
        {"kind": "analysis", "used_in_signed_decision": False, "human_review": None, "status": "FAILED"},
        {"kind": "ask"},
    ]
    assert rules.ai_counts(runs) == {
        "total": 3,
        "by_kind": {"analysis": 2, "ask": 1},
        "used_in_signed_decision": 1,
        "human_reviewed": 1,
        "failed": 1,
    }


# ------------------------------------------------------------------------------------------------- integrity


def _legacy_record(decision_id: str) -> dict:
    material = {
        "decision_id": decision_id,
        "version": "1",
        "type": "INVESTIGATION_DECISION",
        "decision": "APPROVE",
        "remarks": "Approved after review",
    }
    fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return {
        "object_version": "1",
        "decision_type": "INVESTIGATION_DECISION",
        "decision": "APPROVE",
        "remarks": "Approved after review",
        "signer_user_id": PERSON,
        "content_fingerprint": fingerprint,
        "signature_hash": hashlib.sha256((fingerprint + PERSON + "1").encode()).hexdigest(),
        "status": "SIGNED",
    }


def test_a_legacy_signature_verifies_until_it_is_changed():
    record = _legacy_record(OTHER)
    checks = rules.legacy_signature_checks(record, OTHER)
    assert rules.checks_status(checks) == "VALID"
    tampered = rules.legacy_signature_checks({**record, "remarks": "Approved (edited)"}, OTHER)
    assert rules.checks_status(tampered) == "INVALID"
    assert {check["key"]: check["ok"] for check in tampered} == {"fingerprint": False, "signature": True}
    assert rules.checks_status(rules.legacy_signature_checks(record, TASK)) == "INVALID"
    assert rules.checks_status(rules.legacy_signature_checks({**record, "status": "INVALIDATED"}, OTHER)) == "INVALID"
    assert rules.checks_status([]) == "INVALID"


def test_the_audit_chain_summary_of_the_planes():
    valid = {"plane": "data", "status": "VALID", "checked_events": 10, "first_broken_seq": None}
    broken = {"plane": "control", "status": "BROKEN", "checked_events": 5, "first_broken_seq": 3}
    unchecked = {"plane": "control", "status": "NOT_CHECKED", "checked_events": 0, "reason": "Too many"}
    assert rules.combine_chains([valid])["status"] == "VALID"
    both = rules.combine_chains([valid, broken])
    assert both["status"] == "BROKEN" and both["checked_events"] == 15
    assert both["first_break"] == {"plane": "control", "seq": 3}
    partly = rules.combine_chains([valid, unchecked])
    assert partly["status"] == "NOT_CHECKED" and partly["reason"] == "Too many" and partly["first_break"] is None
    assert rules.combine_chains([])["status"] == "NOT_CHECKED"


def test_the_csv_rows_of_an_export():
    timeline = [rules.public(_item(T0, actor={"name": "Ada", "role_label": "Investigator"}))]
    runs = [{"kind": "analysis", "provider": "p", "model": "m", "business_id": "AIX000001", "finished_at": "t"}]
    integrity = {
        "signatures": [{"business_id": "SIG000001", "decision_business_id": "DEC000001", "status": "VALID"}],
        "brief_hashes": [{"business_id": "DBV000001", "version": 1, "hash_verified": True}],
        "audit_chain": {"status": "VALID", "checked_events": 4},
    }
    rows = rules.csv_rows(timeline, runs, integrity)
    assert [row["section"] for row in rows] == ["TIMELINE", "AI_RUN", "SIGNATURE", "BRIEF_HASH", "AUDIT_CHAIN"]
    assert all(set(row) == set(rules.TIMELINE_CSV_FIELDS) for row in rows)
    assert rows[0]["actor"] == "Ada" and rows[1]["object_business_id"] == "AIX000001"
