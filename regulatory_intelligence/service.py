"""Bounded, human-reviewed regulatory drafting service."""
from dataclasses import dataclass
from typing import Any

from .catalog import verify_citations


CONFIDENCE_SEMANTICS = {
    "HIGH": "Directly supported by at least one verified authoritative citation and no contradiction.",
    "MEDIUM": "Supported by relevant retrieved evidence, but citation coverage or completeness is limited.",
    "LOW": "Potentially relevant but incomplete, indirect, or contradicted; human review is required.",
    "UNKNOWN": "Insufficient verified evidence to assess the claim.",
}


TEMPLATES = {
    "ESTAR_510K": "FDA 510(k) submission draft",
    "GSPR": "EU MDR Annex I GSPR evidence draft",
    "CER": "Clinical Evaluation Report evidence outline",
    "IFU": "Instructions for Use controlled draft",
}


@dataclass(frozen=True)
class RegulatoryDraft:
    document_type: str
    title: str
    sections: list[dict[str, Any]]
    citations: dict[str, Any]
    limitations: list[str]
    human_review_required: bool = True


class RegulatoryDraftService:
    def generate(self, document_type: str, context: dict[str, Any]) -> RegulatoryDraft:
        kind = document_type.upper()
        if kind not in TEMPLATES:
            raise ValueError(f"Unsupported regulatory document type: {document_type}")
        citations = verify_citations(context.get("citations", []))
        sections = []
        for item in context.get("claims", []):
            claim_citations = [c for c in citations["verified"] if c.get("claim_id") == item.get("claim_id")]
            confidence = "HIGH" if claim_citations else "UNKNOWN"
            sections.append({
                "claim_id": item.get("claim_id"),
                "text": item.get("text", ""),
                "confidence": confidence,
                "confidence_definition": CONFIDENCE_SEMANTICS[confidence],
                "citation_ids": [c.get("citation_id") for c in claim_citations],
                "unsupported": not bool(claim_citations),
            })
        return RegulatoryDraft(
            document_type=kind,
            title=TEMPLATES[kind],
            sections=sections,
            citations=citations,
            limitations=[
                "Draft is evidence-organizing assistance, not regulatory advice or a submission decision.",
                "Human review and approval are mandatory.",
                "Licensed ISO text is not bundled; only registered official metadata and links are used.",
            ],
        )
