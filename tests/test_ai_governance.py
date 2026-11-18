"""E1: AI governance on one screen (backend/app/ai_governance.py) and U7, the AI lock-in of a signed decision.

On the flagship sample of a fresh trial: the approved providers come from the vetted register, the sample's recorded
answer is counted apart from live ones (its reviews too), every disagreement is listed with its reason, the trial's
owner reads only its own organization (a colleague gets 403, as on the AI settings), the platform administrator sees
counts per organization, and the AI record locked into a signed decision does not move when the model or the review
changes later.

The module's tests share one trial and run in file order.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_release_c1_0_10_73 import _invite
from tests.test_support_access_sod import _platform_admin
from tests.test_w1_flagship import _flag, _intel, _ok, _purge

pytestmark = pytest.mark.db

GOVERNANCE = "/api/v1/admin/ai-governance"
REJECT_REASON = "The lot 004 figure is not in the inspection record."


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "case_id": _flag(user)["investigation"]["id"]}
    finally:
        _purge(tenant_id)


def _observations(trial) -> list[dict]:
    return [row for row in _intel(trial["user"], trial["case_id"], "observations") if row.get("ai_execution_id")]


def _live_result(trial, provider: str = "groq") -> uuid.UUID:
    """A saved result a model wrote (as a live AI run leaves it); no model is called."""
    from backend.app.db.models.foundation import AIExecution

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = AIExecution(
            id=uuid.uuid4(),
            tenant_id=trial["tenant_id"],
            investigation_id=uuid.UUID(trial["case_id"]),
            provider=provider,
            model_name="llama-test",
            model_version="1",
            prompt_template_version="hypotheses-v3",
            evidence_refs={"evidence_identifiers": ["SAMPLE-EV-001", "SAMPLE-EV-002"]},
            structured_output={"hypotheses": []},
            execution_timestamp=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return row.id


def test_the_register_and_the_statement_are_shown_in_plain_words(trial):
    body = _ok(trial["user"].get(GOVERNANCE))
    assert body["statement"].startswith("MDARIX never trains models on your data")
    assert "never decisions" in body["statement"]
    approved = {item["name"]: item for item in body["providers"]["approved"]}
    assert approved["groq"]["trains_on_data"] == "No" and approved["groq"]["checked_on"] and approved["groq"]["terms"]
    assert approved["groq"]["region"] and "no training" in approved["groq"]["why"]
    assert approved["openrouter"]["trains_on_data"] == "No (opt-out confirmed)"
    assert any(item["name"] == "Paid-plan AI providers" for item in body["providers"]["not_used"])
    controls = body["controls"]
    assert controls["free_trial"] is True and controls["organization_on"] is False
    # The trial's own person, with the per-person switch that applies to free trials.
    assert [person["ai"] for person in controls["people"]] == ["Active"]


def test_recorded_answers_are_counted_apart_with_their_reviews(trial):
    user = trial["user"]
    first, second = _observations(trial)
    _ok(user.post(f"/api/v1/ai-outputs/{first['id']}/review", json={"decision": "ACCEPTED"}))
    _ok(user.post(f"/api/v1/ai-outputs/{second['id']}/review", json={"decision": "REJECTED", "reason": REJECT_REASON}))
    body = _ok(user.get(GOVERNANCE))
    assert body["recorded_label"] == "Recorded with the sample · no model was called"
    assert body["outputs"]["recorded"] == 1 and body["outputs"]["live"] == 0
    (item,) = body["outputs"]["items"]
    assert item["recorded"] is True and item["sources"] == 3 and item["prompt_version"]
    assert item["reviews"] == {"ACCEPTED": 1, "REJECTED": 1}
    assert body["agreement"]["recorded"] == {"ACCEPTED": 1, "EDITED": 0, "REJECTED": 1}
    assert body["agreement"]["live"] == {"ACCEPTED": 0, "EDITED": 0, "REJECTED": 0}
    (disagreement,) = body["agreement"]["disagreements"]
    assert disagreement["reason"] == REJECT_REASON and disagreement["recorded"] is True
    assert disagreement["decision"] == "REJECTED" and disagreement["reviewer"]


def test_a_live_output_and_its_review_count_as_live(trial):
    user = trial["user"]
    live = _live_result(trial)
    trial["live_id"] = live
    _ok(
        user.post(
            f"/api/v1/ai-outputs/{live}/review",
            json={"decision": "EDITED", "edited_text": "{}", "reason": "Too broad a claim."},
        )
    )
    body = _ok(user.get(GOVERNANCE))
    assert body["outputs"]["recorded"] == 1 and body["outputs"]["live"] == 1
    newest = body["outputs"]["items"][0]
    assert (newest["provider"], newest["model"], newest["recorded"], newest["sources"]) == (
        "groq",
        "llama-test",
        False,
        2,
    )
    assert body["agreement"]["live"] == {"ACCEPTED": 0, "EDITED": 1, "REJECTED": 0}
    assert body["agreement"]["recorded"]["REJECTED"] == 1
    assert [item["recorded"] for item in body["agreement"]["disagreements"]].count(False) == 1


def test_only_the_owner_reads_it_and_only_for_their_organization(trial):
    _, colleague, _ = _invite(trial["user"], None)
    assert colleague.get(GOVERNANCE).status_code == 403
    other, approval, _ = _approved_trial_client()
    try:
        body = _ok(other.get(GOVERNANCE))
        assert body["outputs"]["live"] == 0 and body["agreement"]["disagreements"] == []
        assert all(item["model"] != "llama-test" for item in body["outputs"]["items"])
    finally:
        _purge(uuid.UUID(approval["tenant_id"]))
    # The platform view is for platform administrators only.
    assert trial["user"].get("/api/v1/platform-admin/ai-governance").status_code in (401, 403)


def test_the_platform_administrator_sees_counts_per_organization(trial):
    admin, _ = _platform_admin()
    body = _ok(admin.get("/api/v1/platform-admin/ai-governance"))
    row = next(item for item in body["organizations"] if item["tenant_id"] == str(trial["tenant_id"]))
    assert (row["live"], row["recorded"], row["EDITED"], row["REJECTED"], row["ACCEPTED"]) == (1, 1, 1, 1, 1)
    assert "reason" not in row and body["providers"]["approved"]


def test_the_signed_record_locks_the_ai_used_and_later_changes_do_not_move_it(trial, monkeypatch):
    from auth import totp

    from backend.app.db.models.foundation import AIExecution

    user, case_id = trial["user"], trial["case_id"]
    supplier = next(
        row
        for row in _intel(user, case_id, "hypotheses")
        if row["origin"] == "HUMAN" and "NovaSense" in row["statement"]
    )
    # UX1: the sample reviewer accepted the brief for decision (staged with the trial); the person signs it.
    brief = _ok(user.get(f"/api/v1/investigations/{case_id}/decision"))["brief"]
    assert brief["status"] == "APPROVED_FOR_DECISION"
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    started = _ok(user.post("/api/v1/auth/mfa/enroll"))
    _ok(user.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(started["secret"])}))
    _ok(
        user.post(
            f"/api/v1/investigations/{case_id}/decision/sign",
            json={
                "brief_version_id": brief["id"],
                "brief_content_hash": brief["content_hash"],
                "outcome": "ACCEPT_CONCLUSION",
                "rationale": "The NovaSense sensors accepted under reduced inspection explain the alarms.",
                "root_cause_attribution": "DEVICE_RELATED",
                "root_cause_category": "MATERIAL",
                "root_cause_hypothesis_ids": [supplier["id"]],
                "residual_unknowns_acknowledged": True,
                "follow_ups": [],
                "password": PASSWORD,
                "mfa_code": totp.code_at(started["secret"], int(time.time() // 30) + 1),
            },
        )
    )
    summary_path = f"/api/v1/investigations/{case_id}/decision/summary"
    signed = _ok(user.get(summary_path))
    locked = signed["ai"]["locked"]
    by_provider = {item["provider"]: item for item in locked}
    recorded, live = by_provider["sample-recorded"], by_provider["groq"]
    assert recorded["recorded"] is True and recorded["prompt_version"] and len(recorded["sources"]) == 3
    assert sorted(item["state"] for item in recorded["verdicts"]) == ["ACCEPTED", "REJECTED"]
    assert REJECT_REASON in [item["reason"] for item in recorded["verdicts"]]
    assert all(item["reviewer"] for item in recorded["verdicts"])
    assert (live["model"], live["prompt_version"], live["sources"]) == (
        "llama-test",
        "hypotheses-v3",
        ["SAMPLE-EV-001", "SAMPLE-EV-002"],
    )
    assert [item["state"] for item in live["verdicts"]] == ["EDITED"] and live["in_signed_brief"] is False

    # Later: the reviewer changes their mind and the saved result names another model.
    _ok(user.post(f"/api/v1/ai-outputs/{trial['live_id']}/review", json={"decision": "ACCEPTED"}))
    with SessionLocal() as db:
        bind_system(db, "test: a later model change")
        db.query(AIExecution).filter(AIExecution.id == trial["live_id"]).update({"model_name": "another-model"})
        db.commit()
    later = _ok(user.get(summary_path))
    assert later["ai"]["locked"] == locked
    assert later["signature"]["verification"] == "VALID"
    # The live read moved: the governance screen shows the new state.
    assert _ok(user.get(GOVERNANCE))["agreement"]["live"]["ACCEPTED"] == 1


def test_lock_sources_are_read_from_the_saved_references():
    from backend.app.ai_governance import sources

    assert sources({"evidence_identifiers": ["A", "B", "A"], "note": "x", "ids": [3]}) == ["A", "B", "3"]
    assert sources(None) == [] and sources(["A"]) == []
