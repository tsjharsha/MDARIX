"""Ask MDARIX answers from the tenant's real evidence search, and every citation in the answer is checked.

The question is run through trusted retrieval (meaning + structure, tenant-scoped; investigation-scoped when one is
chosen). The best matches go to the model with their full text, within a size budget. After the answer comes back,
each [EV-...] citation is compared with the evidence the model was actually given: unknown citations and causal or
decision wording are reported to the reader, never silently passed through.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceChunk
from investigator.model_provider import asserts_causality_or_decision
from retrieval.schemas import RetrievalRequest
from retrieval.service import RetrievalError, TrustedRetrievalService

SEARCH_TOP_K = 8
TEXT_BUDGET = 6000  # characters of retrieved evidence text sent with the question
TEXT_PER_ITEM = 1000
CITATION = re.compile(r"\[([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\]")
UNICODE_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")


def normalize_answer(answer: str | None) -> str | None:
    """Models sometimes write identifiers with typographic hyphens (EV\u2011001); use plain ones so they match."""
    return UNICODE_DASHES.sub("-", answer) if answer else answer


def search_evidence(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    question: str,
    investigation_id: uuid.UUID | None = None,
    product_version_id: uuid.UUID | None = None,
    temporal_mode: str = "current",
    as_of: datetime | None = None,
    service: TrustedRetrievalService | None = None,
) -> dict[str, Any]:
    """The evidence that best answers the question, with text for the model and metadata for the reader."""
    mode = temporal_mode.lower() if temporal_mode.lower() in {"current", "event", "known"} else "current"
    request = RetrievalRequest(
        tenant_id=tenant_id,
        query_text=question[:2000],
        retrieval_mode="hybrid",
        investigation_id=investigation_id,
        product_version_id=product_version_id,
        temporal_mode=mode,
        event_as_of=as_of if mode == "event" else None,
        knowledge_as_of=as_of if mode == "known" else None,
        top_k=SEARCH_TOP_K,
    )
    try:
        response = (service or TrustedRetrievalService()).retrieve(db, request)
    except RetrievalError as exc:
        return {"status": "SEARCH_FAILED", "evidence": [], "sources": [], "limitations": [str(exc)]}

    texts: dict[str, str] = {}
    chunk_ids = [result.chunk_id for result in response.results]
    if chunk_ids:
        rows = (
            db.query(EvidenceChunk.id, EvidenceChunk.text_content)
            .filter(EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.id.in_(chunk_ids))
            .all()
        )
        texts = {str(row.id): row.text_content or "" for row in rows}

    evidence, sources, seen, used = [], [], set(), 0
    for result in response.results:
        if not result.evidence_available or "ground_truth" in (result.evidence_identifier or "").lower():
            continue  # evaluation ground truth never reaches the model
        text = (texts.get(str(result.chunk_id)) or result.excerpt or "")[:TEXT_PER_ITEM]
        if result.evidence_identifier in seen:
            continue
        if used + len(text) > TEXT_BUDGET:
            break
        seen.add(result.evidence_identifier)
        used += len(text)
        evidence.append(
            {
                "id": result.evidence_identifier,
                "type": result.evidence_type,
                "title": result.evidence_title,
                "date": result.temporal_context.get("effective_timestamp"),
                "text": text,
            }
        )
        sources.append(
            {
                "evidence_identifier": result.evidence_identifier,
                "title": result.evidence_title,
                "source_reference": None,
                "temporal": {"effective_timestamp": result.temporal_context.get("effective_timestamp")},
                "found_by": "search",
                "retrieval_method": result.retrieval_method,
                "relevance": round(result.retrieval_score, 3),
            }
        )
    return {
        "status": response.status,
        "retrieval_query_id": str(response.retrieval_query_id),
        "embedding_model": response.results[0].provenance.get("embedding_model") if response.results else None,
        "evidence": evidence,
        "sources": sources,
        "limitations": list(response.limitations),
    }


UUID_TEXT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DROP_KEYS = {"provenance", "entity_links", "chunks", "observations", "metadata"}


def _lean(value: Any, max_items: int) -> Any:
    """Drop internal IDs and bookkeeping; keep the readable facts. Lists keep their first max_items entries."""
    if isinstance(value, dict):
        lean = {}
        for key, item in value.items():
            if key in DROP_KEYS or key == "id" or (key.endswith("_id") and key != "evidence_identifier"):
                continue
            if isinstance(item, str) and UUID_TEXT.match(item):
                continue
            item = _lean(item, max_items)
            if item not in (None, "", [], {}):
                lean[key] = item
        return lean
    if isinstance(value, list):
        return [_lean(item, max_items) for item in value[:max_items]]
    return value


def compact_context(grounded: dict[str, Any], budget_chars: int) -> dict[str, Any]:
    """The investigation context in a size the model accepts: facts kept, internal detail dropped first.

    Evidence keeps identifier, title, type, reliability, date and its first excerpt. If it is still too large, the
    lists are shortened step by step; the identifiers of all evidence stay listed so the model knows they exist.
    """
    import json

    evidence = [
        {
            "evidence_identifier": item.get("evidence_identifier"),
            "title": item.get("title"),
            "type": item.get("evidence_type"),
            "reliability": item.get("reliability_status"),
            "date": (item.get("temporal") or {}).get("effective_timestamp")
            or (item.get("temporal") or {}).get("recorded_timestamp"),
            "excerpt": next((chunk.get("excerpt") for chunk in item.get("chunks") or [] if chunk.get("excerpt")), None),
        }
        for item in grounded.get("evidence_context") or []
    ]
    relationships = grounded.get("relationship_context") or {}
    for max_items in (12, 8, 5, 3):
        compact = {
            key: grounded[key]
            for key in ("policy_version", "tenant_scope_enforced", "field_policy", "temporal_context", "limitations")
            if key in grounded
        }
        compact["investigation"] = _lean(grounded.get("investigation") or {}, max_items)
        compact["product_context"] = _lean(grounded.get("product_context") or {}, max_items)
        compact["evidence_context"] = [_lean(item, max_items) for item in evidence[: max_items * 2]]
        compact["all_evidence_identifiers"] = [item["evidence_identifier"] for item in evidence]
        compact["relationship_summary"] = {
            "nodes": len(relationships.get("nodes") or []),
            "relationships": len(relationships.get("relationships") or []),
        }
        if "retrieved_evidence" in grounded:
            compact["retrieved_evidence"] = grounded["retrieved_evidence"]
        if len(json.dumps(compact, default=str)) <= budget_chars:
            return compact
    compact.pop("product_context", None)
    return compact


def check_answer(answer: str | None, known_identifiers: set[str]) -> dict[str, Any]:
    """Citations in the answer that are not in the evidence the model was given, and causal/decision wording."""
    if not answer:
        return {"cited": [], "unverified_citations": [], "causal_or_decision_wording": False, "notes": []}
    bracketed = list(dict.fromkeys(CITATION.findall(answer)))
    unverified = [identifier for identifier in bracketed if identifier not in known_identifiers]
    mentioned = [identifier for identifier in sorted(known_identifiers) if identifier and identifier in answer]
    cited = list(dict.fromkeys(bracketed + mentioned))
    sentences = re.split(r"(?<=[.!?])\s+|\n+", answer)
    causal = any(asserts_causality_or_decision(sentence) for sentence in sentences)
    notes = []
    if unverified:
        notes.append(
            "The answer cites "
            + ", ".join(unverified)
            + ", which is not among the records MDARIX gave it. Treat that part with caution."
        )
    if causal:
        notes.append(
            "The answer contains wording that sounds like a causal or regulatory conclusion; a person decides."
        )
    return {"cited": cited, "unverified_citations": unverified, "causal_or_decision_wording": causal, "notes": notes}
