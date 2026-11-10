"""B5 step 6: the Decision Brief's Challenge and Sources sections. Every statement of the challenge section has a
source; the sample brief carries the sample author's answers and its hash still verifies; an unanswered material
question blocks submit; a brief without answers reads as before; with the switch off the sections are not composed."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import Investigation
from backend.app.db.models.reviews import DecisionBriefVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.decision_brief import compose as composer
from backend.app.decision_brief import rules as brief_rules
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case_id = (
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .scalar()
        )
    try:
        yield {"user": user, "tenant_id": tenant_id, "case_id": case_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b5-brief-cleanup")


def _brief(db, trial) -> DecisionBriefVersion:
    bind_tenant(db, trial["tenant_id"])
    return db.query(DecisionBriefVersion).filter(DecisionBriefVersion.investigation_id == trial["case_id"]).one()


def test_every_challenge_statement_has_a_source_and_the_sample_hash_verifies(trial):
    with SessionLocal() as db:
        row = _brief(db, trial)
        content, narrative, stored_hash = row.content, row.narrative, row.content_hash
    challenge, sources = content["challenge"], content["sources"]
    listed = {item["id"] for group in sources["groups"].values() for item in group["items"]}
    rules_listed = {item["rule"] for item in sources["rules"]}
    for draft in challenge["drafts"]:
        assert draft["rule"] in rules_listed and draft["action"]["state"] == "NOT_ACTED_ON"
        for fact in [*draft["for"], *draft["against"], *draft["missing"]]:
            # A statement cites records listed in Sources, or is its rule's statement of what is missing.
            assert {record["id"] for record in fact["records"]} <= listed, fact["text"]
            assert fact["records"] or fact in draft["missing"], fact["text"]
    for item in challenge["questions"]:
        assert item["rule"] in rules_listed and {record["id"] for record in item.get("records", [])} <= listed
    assert sources["summary"] == f"{sources['count']} records, {len(sources['rules'])} rules"
    assert sources["groups"]["complaints"]["count"] >= 14 and "evidence" in sources["groups"]
    assert all(item["origin"] == "SAMPLE" for item in sources["groups"]["complaints"]["items"])
    # The sample author answered the material questions; the signature covers them (content hash).
    assert challenge["blocking"] == [] and set(narrative["challenge_answers"]) == {
        item["key"] for item in challenge["questions"] if item["material"]
    }
    assert brief_rules.content_hash(content, narrative) == stored_hash


def test_an_unanswered_material_question_blocks_submit_until_answered(trial):
    user = trial["user"]
    with SessionLocal() as db:
        row = _brief(db, trial)
        row.status = "DRAFT"  # as a returned brief's new draft
        answers = row.narrative["challenge_answers"]
        row.narrative = {key: value for key, value in row.narrative.items() if key != "challenge_answers"}
        db.commit()
    base = f"/api/v1/investigations/{trial['case_id']}"
    refused = user.post(f"{base}/decision-brief/submit")
    assert refused.status_code == 409, refused.text
    blocking = [item["key"] for item in refused.json()["detail"]["blocking"]]
    assert sorted(blocking) == sorted(f"challenge:{key}" for key in answers)
    for key in answers:
        answered = user.post(f"{base}/challenge/questions/answer", json={"key": key, "text": "An answer long enough."})
        assert answered.status_code == 200, answered.text
    after = user.post(f"{base}/decision-brief/submit")
    if after.status_code == 409:
        assert not [item for item in after.json()["detail"]["blocking"] if item["key"].startswith("challenge:")]


@pytest.mark.unit
def test_a_brief_without_answers_reads_and_hashes_as_before():
    old = {"problem_statement": "P", "proposed_conclusion": "C", "recommended_actions": [], "contributors": ["u"]}
    normalized = brief_rules.normalize_narrative(old)
    assert "challenge_answers" not in normalized
    assert brief_rules.content_hash({"a": 1}, normalized) == brief_rules.content_hash(
        {"a": 1}, brief_rules.normalize_narrative({**old, "challenge_answers": {}})
    )


def test_with_the_switch_off_no_sections_are_composed(trial, monkeypatch):
    monkeypatch.setenv("MDARIX_CHALLENGE", "off")
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        case = db.query(Investigation).filter(Investigation.id == trial["case_id"]).one()
        content, _ = composer.compose(db, db, case, now=datetime.now(timezone.utc))
        db.rollback()
    assert "challenge" not in content and "sources" not in content
