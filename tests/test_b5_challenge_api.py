"""B5 step 5: the challenge API on the sample case (SAMPLE-INV-001). Read (drafts and questions, viewed once per scope
version), adopt (a hypothesis tagged with its rule, ticked facts as unreviewed record summaries), dismiss with a
reason, answer a question in the brief draft (the content hash changes), refusals on a closed case, another
organization's case is not found, the switch, and the audit rows."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import (
    AuditEvent,
    Evidence,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
)
from backend.app.db.models.intelligence import IntelligenceEvent
from backend.app.db.models.reviews import DecisionBriefVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.conftest import authenticated_client
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .one()
        )
        case_id = case.id
    try:
        yield {
            "user": user,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "base": f"/api/v1/investigations/{case_id}/challenge",
        }
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b5-challenge-cleanup")


def _db(trial):
    db = SessionLocal()
    bind_tenant(db, trial["tenant_id"])
    return db


def _audits(trial, action) -> int:
    with _db(trial) as db:
        return (
            db.query(AuditEvent).filter(AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == action).count()
        )


def _by_rule(view, rule):
    return [item for item in view["drafts"] if item["rule"] == rule]


def test_the_sample_reads_drafts_and_questions_viewed_once(trial):
    first = trial["user"].get(trial["base"])
    assert first.status_code == 200, first.text
    view = first.json()
    assert "facts" not in view and view["rule_version"] == 1
    (h1,) = _by_rule(view, "H-1")
    assert "SAMPLE-CHG-014" in h1["title"] and h1["duplicate_of"]  # the sample author's supplier hypothesis
    assert any("Rev A" in fact["text"] for fact in h1["against"])
    (h2,) = _by_rule(view, "H-2")
    assert h2["title"].endswith("lots 003 and 004")
    assert all(item["label"].endswith("Not a finding.") for item in view["drafts"])
    rules_asked = {item["rule"] for item in view["questions"]}
    assert {"C-1", "C-5", "C-7"} <= rules_asked
    c1 = next(item for item in view["questions"] if item["rule"] == "C-1")
    assert c1["material"] and c1["key"] in view["blocking"]
    assert trial["user"].get(trial["base"]).status_code == 200
    assert _audits(trial, "CHALLENGE_VIEWED") == 1


def test_dismiss_needs_a_reason_and_is_kept(trial):
    user, base = trial["user"], trial["base"]
    (h2,) = _by_rule(user.get(base).json(), "H-2")
    assert user.post(f"{base}/drafts/dismiss", json={"key": h2["key"], "reason": "no"}).status_code == 422
    stale = user.post(f"{base}/drafts/dismiss", json={"key": "H-2:not-a-draft", "reason": "A reason long enough."})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "DRAFT_NOT_CURRENT"
    done = user.post(f"{base}/drafts/dismiss", json={"key": h2["key"], "reason": "Lots 003-004 are the supplier's."})
    assert done.status_code == 200, done.text
    (h2,) = _by_rule(user.get(base).json(), "H-2")
    assert h2["action"]["state"] == "DISMISSED" and h2["action"]["reason"].startswith("Lots 003")
    assert _audits(trial, "DRAFT_DISMISSED") == 1


def test_adopt_makes_a_tagged_hypothesis_with_unreviewed_record_summaries(trial):
    user, base = trial["user"], trial["base"]
    (h1,) = _by_rule(user.get(base).json(), "H-1")
    bad = user.post(f"{base}/drafts/adopt", json={"key": h1["key"], "facts": [{"side": "for", "index": 99}]})
    assert bad.status_code == 422
    picked = [{"side": "for", "index": 0}, {"side": "against", "index": 0}]
    adopted = user.post(f"{base}/drafts/adopt", json={"key": h1["key"], "facts": picked})
    assert adopted.status_code == 201, adopted.text
    body = adopted.json()
    with _db(trial) as db:
        row = db.query(Hypothesis).filter(Hypothesis.id == uuid.UUID(body["hypothesis"]["id"])).one()
        assert (row.draft_rule, row.draft_rule_version, row.origin, row.human_status) == ("H-1", 1, "human", "PROPOSED")
        links = db.query(HypothesisEvidence, Evidence).join(Evidence, Evidence.id == HypothesisEvidence.evidence_id)
        links = links.filter(HypothesisEvidence.hypothesis_id == row.id).all()
        assert sorted(link.relation_type for link, _ in links) == ["contradict", "support"]
        assert all(
            (ev.evidence_type, ev.fact_type, ev.reliability_status) == ("record_summary", "derived_fact", "unreviewed")
            for _, ev in links
        )
    again = user.post(f"{base}/drafts/adopt", json={"key": h1["key"], "facts": []})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "DRAFT_ALREADY_ADOPTED"
    (h1,) = _by_rule(user.get(base).json(), "H-1")
    assert h1["action"]["state"] == "ADOPTED" and h1["action"]["hypothesis"] == body["hypothesis"]["business_id"]
    assert _audits(trial, "DRAFT_ADOPTED") == 1


def test_answers_live_in_the_brief_draft_and_change_its_hash(trial):
    user, base = trial["user"], trial["base"]
    view = user.get(base).json()
    key = view["blocking"][0]
    text = "The Rev A complaints predate the change; they are the base rate."
    # The sample brief is in review: answers wait for a draft.
    refused = user.post(f"{base}/questions/answer", json={"key": key, "text": text})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "BRIEF_NOT_EDITABLE"
    with _db(trial) as db:
        brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == trial["case_id"]).one()
        brief.status = "DRAFT"  # as a returned brief's new draft
        before = brief.content_hash
        db.commit()
    assert user.post(f"{base}/questions/answer", json={"key": key, "text": "short"}).status_code == 422
    answered = user.post(f"{base}/questions/answer", json={"key": key, "text": text})
    assert answered.status_code == 200, answered.text
    with _db(trial) as db:
        brief = db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == trial["case_id"]).one()
        assert brief.narrative["challenge_answers"][key]["text"] == text and brief.content_hash != before
    view = user.get(base).json()
    assert key not in view["blocking"]
    assert next(item for item in view["questions"] if item["key"] == key)["answer"]["text"] == text
    assert _audits(trial, "CHALLENGE_ANSWERED") == 1


def test_other_organizations_and_the_switch(trial, monkeypatch):
    assert authenticated_client().get(trial["base"]).status_code == 404
    monkeypatch.setenv("MDARIX_CHALLENGE", "off")
    assert trial["user"].get(trial["base"]).status_code == 404
    assert trial["user"].get("/api/v1/session/context").json()["challenge"] is False


def test_a_closed_case_refuses_every_write(trial):
    user, base = trial["user"], trial["base"]
    with _db(trial) as db:
        case = db.query(Investigation).filter(Investigation.id == trial["case_id"]).one()
        case.workflow_state, case.status = "CLOSED", "closed"
        db.commit()
    assert user.get(base).status_code == 200  # still readable
    for path, body in (
        ("drafts/adopt", {"key": "H-4", "facts": []}),
        ("drafts/dismiss", {"key": "H-4", "reason": "A reason long enough."}),
        ("questions/answer", {"key": "C-8", "text": "An answer long enough."}),
    ):
        response = user.post(f"{base}/{path}", json=body)
        assert response.status_code == 409 and response.json()["detail"]["code"] == "CASE_CLOSED", path
    with _db(trial) as db:
        events = db.query(IntelligenceEvent).filter(IntelligenceEvent.investigation_id == trial["case_id"])
        assert events.filter(IntelligenceEvent.object_type == "CHALLENGE_DRAFT").count() == 2
