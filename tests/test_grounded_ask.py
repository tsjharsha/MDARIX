"""Ask MDARIX answers from the tenant's evidence search, fits the model's input limit, and checks its citations."""

import json

import pytest

from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from genai import provider as provider_module
from genai.ask import check_answer, compact_context, normalize_answer
from genai.provider import GenAIProvider, GenAIResult
from retrieval.embedding_provider import DeterministicEmbeddingProvider
from retrieval.indexing import index_tenant_evidence
from tests.chunk_cleanup import restore_chunks
from tests.conftest import authenticated_client
from tests.test_day11_ai_investigator import context


@pytest.fixture(scope="module", autouse=True)
def searchable_golden_evidence():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").one()
        with restore_chunks(db, tenant.id):
            index_tenant_evidence(db, tenant.id, provider=DeterministicEmbeddingProvider())
            yield
    finally:
        db.close()


class RecordingModel(GenAIProvider):
    calls: list = []

    def health(self):
        return {"configured": True}

    def complete(self, prompt, context=None, **kwargs):
        size = len(prompt) + len(json.dumps(context, default=str))
        RecordingModel.calls.append({"prompt": prompt, "context": context, "size": size, "limit": self.max_input * 4})
        found = [item["id"] for item in context.get("retrieved_evidence", [])]
        answer = (
            f"## Answer\nThe supplier changed its process [{found[0]}]. An unknown record says more [EV-NOT-REAL-9].\n"
            "Also see EV‑VS001‑002."
        )
        return GenAIResult("groq", "test-model", "test", {"answer": answer, "limitations": []}, 10, 10, 0.0, 5)


@pytest.fixture
def model(monkeypatch):
    RecordingModel.calls = []
    monkeypatch.setattr(provider_module, "GenAIProvider", RecordingModel)
    return RecordingModel


def _ask(question, investigation=True):
    _, investigation_id = context()
    payload = {"prompt": question, "investigation_id": str(investigation_id) if investigation else None}
    response = authenticated_client().post("/api/v1/stage3/interactions", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["response"]


def test_ask_searches_the_evidence_and_checks_the_citations(model):
    response = _ask("Did the supplier change its process before Component Rev B?")
    call = model.calls[-1]
    retrieved = call["context"]["retrieved_evidence"]
    assert retrieved and all(item["text"] for item in retrieved)
    assert call["size"] <= call["limit"]  # a large investigation still fits the model's input limit
    assert response["search"]["records_found"] >= 1
    assert any(source.get("found_by") == "search" for source in response["sources_provenance"])
    check = response["answer_check"]
    assert check["unverified_citations"] == ["EV-NOT-REAL-9"]
    assert retrieved[0]["id"] in check["cited"]
    assert any("EV-NOT-REAL-9" in note for note in response["limitations"])
    # Typographic hyphens become plain ones, so identifiers are recognised and highlighted.
    assert "EV-VS001-002" in response["provider_output"]["answer"]


def test_ask_without_an_investigation_searches_the_whole_tenant(model):
    response = _ask("Which records describe a supplier process change?", investigation=False)
    assert response["search"]["records_found"] >= 1
    assert response["grounding"]["tenant_scope_enforced"] is True
    assert response["grounding"]["investigation_scoped"] is False
    assert response["grounding"]["searched_tenant_evidence"] is True
    tenant_evidence = {item["id"] for item in model.calls[-1]["context"]["retrieved_evidence"]}
    assert all(not identifier.lower().count("ground_truth") for identifier in tenant_evidence)


def test_without_a_model_ask_still_returns_the_sources_it_found():
    response = _ask("Did the supplier change its process before Component Rev B?")
    assert response["provider_output"]["answer"] is None
    assert response["search"]["records_found"] >= 1 and response["sources_provenance"]


def test_compact_context_keeps_the_facts_and_fits_the_budget():
    grounded = {
        "policy_version": "P",
        "investigation": {"id": "7b1c3f1e-0000-4000-8000-000000000000", "investigation_question": "Why?"},
        "evidence_context": [
            {
                "id": "x",
                "evidence_identifier": f"EV-{index:03d}",
                "title": "Record " * 20,
                "evidence_type": "note",
                "chunks": [{"excerpt": "text " * 40}],
                "entity_links": [{"entity_type": "Product"}] * 5,
            }
            for index in range(40)
        ],
        "relationship_context": {"nodes": [{}] * 50, "relationships": [{}] * 80},
        "product_context": {"complaints": [{"complaint_identifier": f"C-{i}", "detail": "d" * 200} for i in range(60)]},
    }
    compact = compact_context(grounded, 6000)
    assert len(json.dumps(compact)) <= 6000
    assert compact["all_evidence_identifiers"] == [f"EV-{index:03d}" for index in range(40)]
    assert "id" not in compact["investigation"] and compact["investigation"]["investigation_question"] == "Why?"
    assert compact["relationship_summary"] == {"nodes": 50, "relationships": 80}


def test_answer_checks():
    assert normalize_answer("EV‑001 and EV–002") == "EV-001 and EV-002"
    check = check_answer("Fine [EV-1]. The change caused the shutdowns.", {"EV-1"})
    assert check["unverified_citations"] == [] and check["causal_or_decision_wording"] is True
    assert check_answer(None, set())["cited"] == []
