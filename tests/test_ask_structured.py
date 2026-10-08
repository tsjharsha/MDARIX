"""Ask MDARIX's structured answer end to end (Phase 4): with AI refused, the record-based sections of a seeded case
(facts, hypothesis links and the case's evidence review, open unknowns and what they need) with the refusal fields
unchanged; with a model that answers in JSON, its checked statements labelled AI; the conversation list returns the
structured answer; and the AI status of the signed-in organization."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.evidence_intelligence import EvidenceObservation
from backend.app.db.models.foundation import Evidence, Hypothesis, HypothesisEvidence, InvestigationEvidence, Unknown
from backend.app.db.models.stage3 import AIInteraction
from backend.app.db.session import SessionLocal
from backend.app.main import app
from genai.provider import GenAIProvider, GenAIResult, GenAIUnavailable
from tests.reports_seed import cleanup, role_client, seed_case

ASK = "/api/v1/stage3/interactions"
FACT = "Occlusion sensor read 4 psi high in 3 of 10 bench runs."
INTERPRETATION = "Sensor drift may explain the alarms."
NEEDED = "Device history record of the returned lot"


@pytest.fixture(scope="module")
def case():
    """seed_case (product, case, direct and linked evidence, a hypothesis supported by the direct evidence, an open
    unknown) plus: a fact and an AI interpretation on the direct evidence, an unknown in progress with the evidence it
    needs, a resolved unknown, the linked evidence reviewed as contradicting (with a limitation), and a withdrawn
    hypothesis link."""
    seed = seed_case()
    tag, now = seed["tag"], datetime.now(timezone.utc)
    tenant_id, case_id = uuid.UUID(seed["tenant_id"]), uuid.UUID(seed["investigation_id"])
    with SessionLocal() as db:
        direct = db.query(Evidence).filter(Evidence.evidence_identifier == f"EV-{tag}-1").one()
        direct_id = direct.id  # kept: the row is expired once its session commits
        linked = db.query(Evidence).filter(Evidence.evidence_identifier == f"EV-{tag}-2").one()
        hypothesis = db.query(Hypothesis).filter(Hypothesis.investigation_id == case_id).one()
        db.add_all(
            [
                EvidenceObservation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    evidence_id=direct.id,
                    statement=FACT,
                    observation_type="STRUCTURED_EXTRACTION",
                    extraction_method="DETERMINISTIC",
                    epistemic_type="FACT",
                    origin="SYSTEM",
                ),
                EvidenceObservation(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    evidence_id=direct.id,
                    statement=INTERPRETATION,
                    observation_type="AI_EXTRACTED_OBSERVATION",
                    extraction_method="GENAI",
                    epistemic_type="AI_INTERPRETATION",
                    origin="AI",
                ),
                Unknown(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=case_id,
                    description=f"Which lot the returned device came from ({tag})",
                    evidence_needed=NEEDED,
                    status="in_progress",
                    created_at=now,
                    updated_at=now,
                ),
                Unknown(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=case_id,
                    description=f"A question already answered ({tag})",
                    status="resolved",
                    created_at=now,
                    updated_at=now,
                ),
                HypothesisEvidence(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    hypothesis_id=hypothesis.id,
                    evidence_id=linked.id,
                    relation_type="contradict",
                    rationale="Withdrawn link",
                    created_by_type="human",
                    created_at=now,
                    retracted_at=now,
                ),
            ]
        )
        link = (
            db.query(InvestigationEvidence)
            .filter(InvestigationEvidence.investigation_id == case_id, InvestigationEvidence.evidence_id == linked.id)
            .one()
        )
        link.relationship = "CONTRADICTING"
        link.review_status = "ACCEPTED_WITH_LIMITATION"
        link.limitation = "Only the first page is legible"
        link.review_reason = "The note reports normal readings on the day of the alarm"
        link.reviewed_by = "reviewer@example.invalid"
        link.reviewed_at = now
        db.commit()
    yield seed
    with SessionLocal() as db:
        db.query(EvidenceObservation).filter(EvidenceObservation.evidence_id == direct_id).delete(
            synchronize_session=False
        )
        db.query(AIInteraction).filter(AIInteraction.investigation_id == case_id).delete(synchronize_session=False)
        db.commit()
    cleanup(seed)


@pytest.fixture(scope="module")
def investigator():
    return role_client("INVESTIGATOR")[0]


def _refuse(monkeypatch, reason="GENAI_DISABLED_FOR_ORGANIZATION"):
    def refuse(self, *args, **kwargs):
        raise GenAIUnavailable(reason)

    monkeypatch.setattr(GenAIProvider, "complete", refuse)


def _no_raw_json(structured: dict) -> None:
    for key in ("known_facts", "supporting_evidence", "contradicting_evidence", "unknowns", "missing_evidence"):
        for item in structured[key]:
            assert item["statement"] and item["statement"].strip()[:1] not in "{[", item
    assert all(text.strip()[:1] not in "{[" for text in structured["limitations"] + structured["next_steps"])


def test_with_ai_refused_ask_answers_from_the_case_records(monkeypatch, case, investigator):
    _refuse(monkeypatch)
    response = investigator.post(
        ASK, json={"prompt": "Why do occlusion alarms occur?", "investigation_id": case["investigation_id"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The refusal reaches the client exactly as before.
    assert body["status"] == "REFUSED" and body["code"] == "GENAI_DISABLED_FOR_ORGANIZATION"
    assert body["response"]["limitations"] == [body["user_message"]]
    assert body["response"]["refusal"]["code"] == "GENAI_DISABLED_FOR_ORGANIZATION"

    structured = body["structured"]
    assert structured == body["response"]["structured"]
    assert structured["ai_used"] is False and structured["reason_code"] == "AI_DISABLED"
    assert body["user_message"] in structured["ai_note"] and "records only" in structured["ai_note"]
    assert structured["summary"] and structured["summary_origin"] == "SYSTEM"

    facts = {item["statement"]: item for item in structured["known_facts"]}
    assert FACT in facts and INTERPRETATION not in facts
    assert facts[FACT]["epistemic_type"] == "FACT" and facts[FACT]["origin"] == "SYSTEM"
    assert facts[FACT]["sources"][0]["evidence_identifier"] == f"EV-{case['tag']}-1"
    assert facts[FACT]["sources"][0]["kind"] == "evidence" and facts[FACT]["sources"][0]["business_id"]

    supporting = structured["supporting_evidence"]
    assert any(
        "supports the hypothesis" in item["statement"] and item["origin"] == "HUMAN" and item["hypothesis_business_id"]
        for item in supporting
    )
    contradicting = [item["statement"] for item in structured["contradicting_evidence"]]
    assert any("reviewed as contradicting" in text for text in contradicting)
    assert not any("Withdrawn link" in text for text in contradicting)

    unknowns = {item["statement"]: item for item in structured["unknowns"]}
    assert "Lot of the returned device" in unknowns
    assert any(text.startswith("Which lot the returned device came from") for text in unknowns)
    assert not any(text.startswith("A question already answered") for text in unknowns)
    assert all(item["business_id"] and item["status"] in {"open", "in_progress"} for item in unknowns.values())
    missing = [item for item in structured["missing_evidence"] if item["statement"] == NEEDED]
    assert missing and missing[0]["unknown_business_id"]
    assert any("Only the first page is legible" in text for text in structured["limitations"])
    assert isinstance(structured["sources"], list)
    _no_raw_json(structured)


def test_the_conversation_list_returns_the_structured_answer(monkeypatch, case, investigator):
    _refuse(monkeypatch, "GENAI_MONTHLY_BUDGET_REACHED")
    asked = investigator.post(
        ASK, json={"prompt": "What is still unknown?", "investigation_id": case["investigation_id"]}
    ).json()
    assert asked["structured"]["reason_code"] == "BUDGET_EXHAUSTED"
    listed = investigator.get(ASK)
    assert listed.status_code == 200, listed.text
    item = next(entry for entry in listed.json() if entry["id"] == asked["interaction_id"])
    assert item["structured"] == asked["structured"]
    assert item["response"]["structured"] == asked["structured"]


def test_without_a_case_the_structured_answer_comes_from_the_search(monkeypatch, investigator):
    _refuse(monkeypatch)
    body = investigator.post(ASK, json={"prompt": "Which records describe a supplier process change?"}).json()
    structured = body["structured"]
    assert body["status"] == "REFUSED" and structured["ai_used"] is False
    assert structured["unknowns"] == [] and structured["supporting_evidence"] == []
    assert structured["contradicting_evidence"] == []
    assert all(source["kind"] == "evidence" for source in structured["sources"])
    _no_raw_json(structured)


def test_a_model_answer_in_json_is_checked_and_labelled_ai(monkeypatch, case, investigator):
    tag = case["tag"]

    def answer(self, prompt, context=None, **kwargs):
        reply = {
            "summary": "A bench test shows the sensor reading high; the field note disagrees.",
            "known_facts": [
                {"statement": "The bench test found the sensor reading high.", "sources": [f"EV-{tag}-1"]},
                {"statement": "Every pump is affected.", "sources": ["EV-NOT-GIVEN-9"]},
            ],
            "supporting_evidence": [],
            "contradicting_evidence": [{"statement": "The field note reports normal readings.", "sources": []}],
            "unknowns": [{"statement": "Whether the returned lot was affected"}],
            "missing_evidence": [],
            "limitations": [],
            "next_steps": ["Retrieve the device history record."],
        }
        return GenAIResult("test", "test-model", "1", {"answer": json.dumps(reply), "limitations": []}, 10, 10, 0, 5)

    monkeypatch.setattr(GenAIProvider, "complete", answer)
    response = investigator.post(
        ASK, json={"prompt": "Why do occlusion alarms occur?", "investigation_id": case["investigation_id"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "READY_FOR_REVIEW"
    markdown = body["response"]["provider_output"]["answer"]
    assert markdown.startswith("## Answer") and f"[EV-{tag}-1]" in markdown and "{" not in markdown
    assert body["response"]["answer_check"]["unverified_citations"] == ["EV-NOT-GIVEN-9"]

    structured = body["structured"]
    assert structured["ai_used"] is True and structured["summary_origin"] == "AI" and structured["reason_code"] is None
    ai_facts = [item for item in structured["known_facts"] if item["origin"] == "AI"]
    assert [item["statement"] for item in ai_facts] == ["The bench test found the sensor reading high."]
    assert ai_facts[0]["epistemic_type"] == "AI_INTERPRETATION"
    assert [source["evidence_identifier"] for source in ai_facts[0]["sources"]] == [f"EV-{tag}-1"]
    # Record-based facts stay, with their own labels; an uncited model statement is left out and said so.
    assert any(item["statement"] == FACT and item["origin"] == "SYSTEM" for item in structured["known_facts"])
    assert not any(
        item["statement"] == "The field note reports normal readings." for item in structured["contradicting_evidence"]
    )
    assert any("left out" in text for text in structured["limitations"])
    assert any(item["origin"] == "AI" for item in structured["unknowns"])
    _no_raw_json(structured)


def test_ai_status_for_the_signed_in_organization(investigator):
    status = investigator.get("/api/v1/ai/status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert set(body) >= {"enabled", "available", "budget", "reason_code", "message", "manual_paths"}
    assert body["reason_code"] in {None, "AI_DISABLED", "PROVIDER_UNAVAILABLE", "BUDGET_EXHAUSTED"}
    assert (body["reason_code"] == "AI_DISABLED") == (body["enabled"] is False)
    assert body["manual_paths"]["ask"] == "record-based answers" and body["manual_paths"]["hypotheses"] is True
    budget = body["budget"]
    assert budget["remaining"] == max(0, budget["limit"] - budget["used"])
    assert body["message"]
    assert TestClient(app).get("/api/v1/ai/status").status_code == 401
