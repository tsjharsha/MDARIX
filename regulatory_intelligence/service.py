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


def validate_confidence_semantics() -> dict[str, str]:
    required = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
    if set(CONFIDENCE_SEMANTICS) != required or any(not value.strip() for value in CONFIDENCE_SEMANTICS.values()):
        raise ValueError("Invalid regulatory confidence semantics")
    return dict(CONFIDENCE_SEMANTICS)


def detect_unsupported_claims(claims: list[dict], verified_citations: list[dict]) -> list[dict]:
    """Return a deterministic traceability result for every generated claim."""
    by_claim: dict[str, list[dict]] = {}
    for citation in verified_citations:
        by_claim.setdefault(str(citation.get("claim_id", "")), []).append(citation)
    result = []
    for claim in claims:
        claim_id = str(claim.get("claim_id", ""))
        linked = by_claim.get(claim_id, [])
        result.append({
            "claim_id": claim_id,
            "traceability_status": "TRACEABLE" if linked else "UNTRACEABLE",
            "citation_ids": [item.get("citation_id") for item in linked],
            "authoritative_clauses": [item.get("traceability_key") for item in linked],
            "unsupported": not bool(linked),
        })
    return result


TEMPLATES = {
    "ESTAR_510K": "FDA 510(k) submission draft",
    "GSPR": "EU MDR Annex I GSPR evidence draft",
    "CER": "Clinical Evaluation Report evidence outline",
    "IFU": "Instructions for Use controlled draft",
}

AUTHORING_SECTIONS = {
    "GSPR": ("device_scope", "general_requirements", "risk_controls", "verification_evidence", "residual_risks"),
    "CER": ("device_description", "state_of_the_art", "clinical_evaluation_plan", "clinical_evidence", "benefit_risk_conclusion", "post_market_follow_up"),
    "IFU": ("intended_purpose", "indications_and_contraindications", "warnings_and_precautions", "instructions", "residual_risks", "storage_and_disposal"),
    "ESTAR_510K": ("device_description", "indications_for_use", "substantial_equivalence", "performance_testing", "labeling"),
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
        validate_confidence_semantics()
        citations = verify_citations(context.get("citations", []))
        traceability = detect_unsupported_claims(context.get("claims", []), citations["verified"])
        traceability_by_claim = {item["claim_id"]: item for item in traceability}
        required_sections = AUTHORING_SECTIONS[kind]
        authored = context.get("authoring_sections", {})
        missing_sections = [name for name in required_sections if not authored.get(name)]
        sections = []
        for item in context.get("claims", []):
            claim_citations = [c for c in citations["verified"] if c.get("claim_id") == item.get("claim_id")]
            confidence = "HIGH" if claim_citations else "UNKNOWN"
            if item.get("contradicted"):
                confidence = "LOW"
            elif item.get("evidence_only") and claim_citations:
                confidence = "MEDIUM"
            trace = traceability_by_claim.get(str(item.get("claim_id", "")), {})
            sections.append({
                "claim_id": item.get("claim_id"),
                "text": item.get("text", ""),
                "confidence": confidence,
                "confidence_definition": CONFIDENCE_SEMANTICS[confidence],
                "citation_ids": [c.get("citation_id") for c in claim_citations],
                "unsupported": not bool(claim_citations),
                "traceability_status": trace.get("traceability_status", "UNTRACEABLE"),
                "authoritative_clauses": trace.get("authoritative_clauses", []),
            })
        sections.extend({
            "section_id": name,
            "title": name.replace("_", " ").title(),
            "content": authored.get(name, ""),
            "status": "COMPLETE" if authored.get(name) else "MISSING",
            "human_review_required": True,
        } for name in required_sections)
        limitations = [
                "Draft is evidence-organizing assistance, not regulatory advice or a submission decision.",
                "Human review and approval are mandatory.",
                "Licensed ISO text is not bundled; only registered official metadata and links are used.",
            ]
        if missing_sections:
            limitations.append("Required authoring sections are incomplete: " + ", ".join(missing_sections))
        if traceability and not all(item["traceability_status"] == "TRACEABLE" for item in traceability):
            limitations.append("One or more generated statements lack an authoritative clause citation and require human verification.")
        citations["traceability"] = {
            "claims_total": len(traceability),
            "claims_traceable": sum(item["traceability_status"] == "TRACEABLE" for item in traceability),
            "claims_untraceable": sum(item["traceability_status"] != "TRACEABLE" for item in traceability),
            "all_statements_traceable": all(item["traceability_status"] == "TRACEABLE" for item in traceability),
        }
        return RegulatoryDraft(
            document_type=kind,
            title=TEMPLATES[kind],
            sections=sections,
            citations=citations,
            limitations=limitations,
        )
