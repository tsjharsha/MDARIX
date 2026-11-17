"""E3 + W6: the decision record and the decision-and-impact summary of a signed investigation decision
(backend/app/human_decision/summary.py), on the flagship sample SAMPLE-INV-001.

The record shows exactly what was recorded (the question, the signer and role, the evidence and hypotheses of the
signed brief, the AI proposals with their reviews, the rationale, the signature with MFA, the dates and the linked
actions), "not recorded" (None or empty) where nothing was, and "too early" until a signed effectiveness check. It is
read only inside the signed-in organization and stays in its query budget.

The module's tests share one trial and run in file order.
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_w1_flagship import _flag, _intel, _ok, _purge

pytestmark = pytest.mark.db

RATIONALE = "The NovaSense sensors accepted under reduced inspection explain the pressure alarms."


def _summary(user, case_id: str, status: int = 200):
    return _ok(user.get(f"/api/v1/investigations/{case_id}/decision/summary"), status)


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "case_id": _flag(user)["investigation"]["id"]}
    finally:
        _purge(tenant_id)


def test_before_signing_there_is_no_decision_and_nothing_is_invented(trial):
    body = _summary(trial["user"], trial["case_id"])
    assert body["decision"] is None
    assert body["investigation"]["ref"] == "SAMPLE-INV-001" and "Rev B" in body["investigation"]["question"]
    # W1c: the product's risk file is read before the decision, for the Investigation Brief's risk part.
    assert "SAMPLE-RSK-01" in [risk["ref"] for risk in body["risks"]]


def test_g06_the_orbitcare_rise_reads_the_trend_checks_one_number_everywhere(trial):
    from backend.app.trial import flagship, sample_ai, sample_decision

    user = trial["user"]
    product_id = _flag(user)["product"]["id"]
    rows = _ok(user.get(f"/api/v1/triage/trends?group=version&product_id={product_id}"))["items"]
    ratio = max(row["ratio"] for row in rows if row["product"]["id"] == product_id and row["ratio"] is not None)
    assert f"{ratio:.1f}" == f"{flagship.SIGNAL_RATIO:.1f}"
    # The AI note, the evidence document and the brief state that number, and no other figure for the rise.
    texts = [
        *(text for _, text in sample_ai.OBSERVATIONS),
        sample_decision.NARRATIVE["problem_statement"],
        *sample_decision.SAMPLE_CHALLENGE_ANSWERS.values(),
    ]
    assert sum(flagship.SIGNAL_TEXT in text for text in texts) == 2
    assert not any("sevenfold" in text or "5.6" in text or "0.8 a month" in text for text in texts)
    # As the trial shows them: the recorded AI observation and the trend summary evidence.
    case_id = trial["case_id"]
    observations = [row for row in _intel(user, case_id, "observations") if row.get("ai_execution_id")]
    assert any(flagship.SIGNAL_TEXT in row["statement"] for row in observations)
    from backend.app.db.models.foundation import Evidence

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        content = (
            db.query(Evidence.content)
            .filter(Evidence.tenant_id == trial["tenant_id"], Evidence.evidence_identifier == "SAMPLE-EV-003")
            .scalar()
        )
    assert flagship.SIGNAL_TEXT in content


def test_the_signed_record_shows_exactly_what_was_recorded(trial, monkeypatch):
    from auth import totp

    user, case_id = trial["user"], trial["case_id"]
    observations = [row for row in _intel(user, case_id, "observations") if row.get("ai_execution_id")]
    _ok(user.post(f"/api/v1/ai-outputs/{observations[0]['id']}/review", json={"decision": "ACCEPTED"}))
    supplier = next(
        row
        for row in _intel(user, case_id, "hypotheses")
        if row["origin"] == "HUMAN" and "NovaSense" in row["statement"]
    )
    base = f"/api/v1/investigations/{case_id}/decision-brief/versions/1"
    _ok(user.post(f"{base}/start-review", json={}))
    brief = _ok(user.post(f"{base}/review", json={"action": "ACCEPT_FOR_DECISION", "comment": "Evidence holds."}))
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    started = _ok(user.post("/api/v1/auth/mfa/enroll"))
    _ok(user.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(started["secret"])}))
    due = (datetime.now(timezone.utc) + timedelta(days=20)).replace(microsecond=0)
    _ok(
        user.post(
            f"/api/v1/investigations/{case_id}/decision/sign",
            json={
                "brief_version_id": brief["id"],
                "brief_content_hash": brief["content_hash"],
                "outcome": "ACCEPT_CONCLUSION",
                "rationale": RATIONALE,
                "root_cause_attribution": "DEVICE_RELATED",
                "root_cause_category": "MATERIAL",
                "root_cause_hypothesis_ids": [supplier["id"]],
                "residual_unknowns_acknowledged": True,
                "follow_ups": [
                    {
                        "action_type": "RISK_REASSESSMENT_REQUIRED",
                        "title": "Reassess SAMPLE-RSK-01",
                        "due_at": due.isoformat(),
                    }
                ],
                "password": PASSWORD,
                "mfa_code": totp.code_at(started["secret"], int(time.time() // 30) + 1),
            },
        )
    )
    body = _summary(user, case_id)
    decision = body["decision"]
    assert decision["outcome"] == "ACCEPT_CONCLUSION" and decision["rationale"] == RATIONALE
    assert decision["conditions"] is None and decision["status"] == "SIGNED"
    assert "NovaSense" in decision["conclusion"] and decision["brief_version"] == 1
    assert decision["effective_on"] == date.today().isoformat()
    # No effectiveness check yet: the review date is not recorded, and nothing says the action worked.
    assert decision["review_on"] is None
    assert body["worked"] == {"state": "NOT_PLANNED", "text": "No effectiveness check is planned yet.", "on": None}
    signature = body["signature"]
    assert signature["mfa_verified"] is True and signature["verification"] == "VALID"
    assert signature["meaning"] and signature["name"] == body["owner"]["name"] and signature["signed_at"]
    assert body["owner"]["role_label"]
    # The evidence and hypotheses of the signed brief, as the signer saw them.
    signed_brief = _ok(user.get(f"/api/v1/investigations/{case_id}/decision"))["brief"]
    assert body["evidence"]["supporting"] == [
        {"ref": item["evidence_business_id"], "title": item["title"]} for item in signed_brief["supporting_evidence"]
    ]
    assert len(body["evidence"]["supporting"]) >= 2 and all(item["title"] for item in body["evidence"]["supporting"])
    assert [item["ref"] for item in body["hypotheses"]["accepted"]] == [supplier["business_id"]]
    assert "NovaSense" in body["hypotheses"]["leading"]["statement"]
    # The sample brief was written before the AI proposal: its one alternative is the ward-settings explanation, judged
    # weakly supported. No hypothesis was rejected, so none is listed as rejected.
    alternatives = body["hypotheses"]["alternatives"]
    assert [(item["origin"], item["status_label"]) for item in alternatives] == [("HUMAN", "Weakly supported")]
    assert body["hypotheses"]["rejected"] == []
    # The recorded AI proposal: one observation accepted by the person, one not reviewed; the brief used no AI.
    (proposal,) = body["ai"]["proposals"]
    assert proposal["recorded"] is True and proposal["reviews"] == {"ACCEPTED": 1, "NOT_REVIEWED": 1}
    assert body["ai"]["in_brief"] == []
    # What it affects: the brief's scope and the product's risk file.
    affects = body["affects"]
    assert affects["product"]["name"].startswith("OrbitCare 300") and affects["versions"] == ["Rev B"]
    assert [lot[-3:] for lot in affects["lots"]] == ["003", "004"]
    assert [risk["ref"] for risk in affects["risks"]] == ["SAMPLE-RSK-01", "SAMPLE-RSK-02"]
    # What happens next: the follow-up with its date, soonest first.
    assert body["next"][0]["what"] == "Reassess SAMPLE-RSK-01" and body["next"][0]["due"] == due.date().isoformat()
    trial["decision_id"] = decision["id"]


def test_a_planned_check_sets_the_review_date_and_it_is_too_early(trial):
    user, case_id = trial["user"], trial["case_id"]
    capa = _flag(user)["capa"]
    planned = (date.today() + timedelta(days=90)).isoformat()
    _ok(
        user.put(
            f"/api/v1/capas/{capa['id']}/effectiveness/plan",
            json={
                "criteria": "No pressure-alarm complaint from lots made after the 32-unit inspection is restored.",
                "planned_on": planned,
                "measured_from": date.today().isoformat(),
            },
        )
    )
    body = _summary(user, case_id)
    assert body["decision"]["review_on"] == planned
    # W1c: the check's criteria, as planned, for the Investigation Brief's effectiveness part.
    check = next(item["check"] for item in body["capas"] if item["id"] == capa["id"])
    assert check["criteria"].startswith("No pressure-alarm complaint from lots made after")
    assert body["worked"] == {
        "state": "TOO_EARLY",
        "text": f"Too early: the effectiveness check is planned for {planned}. Only a signed check says an action worked.",
        "on": planned,
    }
    assert any(item["kind"] == "EFFECTIVENESS_CHECK" and item["due"] == planned for item in body["next"])
    # The same record by the decision's own id.
    by_id = _ok(user.get(f"/api/v1/decisions/{trial['decision_id']}/summary"))
    assert by_id["decision"]["id"] == trial["decision_id"] and by_id["worked"] == body["worked"]


def test_another_organization_never_reads_the_record(trial):
    other, approval, _ = _approved_trial_client()
    try:
        assert other.get(f"/api/v1/investigations/{trial['case_id']}/decision/summary").status_code == 404
        assert other.get(f"/api/v1/decisions/{trial['decision_id']}/summary").status_code == 404
        # Its own flagship case has no signed decision.
        assert _summary(other, _flag(other)["investigation"]["id"])["decision"] is None
    finally:
        _purge(uuid.UUID(approval["tenant_id"]))


def test_the_summary_read_stays_in_its_query_budget(trial):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    from backend.app.evidence_workflow.inventory import load_case
    from backend.app.human_decision import summary

    seen = {"count": 0}

    def count(*_args, **_kwargs):
        seen["count"] += 1

    with SessionLocal() as data, SessionLocal() as control:
        bind_tenant(data, trial["tenant_id"])
        bind_tenant(control, trial["tenant_id"])
        case = load_case(data, trial["tenant_id"], uuid.UUID(trial["case_id"]))
        event.listen(Engine, "before_cursor_execute", count)
        started = time.perf_counter()
        try:
            body = summary.for_case(control, data, case)
        finally:
            event.remove(Engine, "before_cursor_execute", count)
        elapsed = time.perf_counter() - started
    assert body["decision"] is not None and seen["count"] <= 25 and elapsed < 0.5, (seen["count"], elapsed)


# Pure ------------------------------------------------------------------------------------------------------------


def _capa(check=None, status="open"):
    return {"ref": "CAPA-1", "title": "Restore inspection", "status": status, "due_at": None, "check": check}


def test_worked_says_only_what_a_signed_check_says():
    from backend.app.human_decision.summary import NO_ACTION, NO_CHECK, worked

    assert worked([]) == {"state": "NOT_PLANNED", "text": NO_ACTION, "on": None}
    assert worked([_capa()]) == {"state": "NOT_PLANNED", "text": NO_CHECK, "on": None}
    planned = {"round": 1, "status": "PLANNED", "planned_on": "2027-02-01", "signed_at": None, "result_summary": None}
    assert worked([_capa(planned)])["state"] == "TOO_EARLY"
    signed = {**planned, "status": "NOT_EFFECTIVE", "signed_at": "2027-02-02T10:00:00+00:00"}
    assert worked([_capa(signed)]) == {
        "state": "NOT_EFFECTIVE",
        "text": "CAPA-1: signed not effective (round 1).",
        "on": "2027-02-02",
    }


def test_next_steps_are_dated_soonest_first_and_closed_items_drop_out():
    from backend.app.human_decision.summary import next_steps

    follow_ups = [
        {"title": None, "action_label": "CAPA required", "status": "OPEN", "due_at": None},
        {"title": "Reassess", "status": "IN_PROGRESS", "due_at": "2026-12-01T00:00:00+00:00"},
        {"title": "Done", "status": "COMPLETED", "due_at": "2026-11-01T00:00:00+00:00"},
    ]
    items = next_steps(follow_ups, [_capa(status="closed")])
    assert [(item["what"], item["due"]) for item in items] == [("Reassess", "2026-12-01"), ("CAPA required", None)]
