from regulatory_intelligence.catalog import verify_citations
from regulatory_intelligence.service import CONFIDENCE_SEMANTICS, RegulatoryDraftService


def test_official_citation_is_verified_and_untrusted_domain_rejected():
    result = verify_citations([
        {"citation_id": "c1", "claim_id": "claim-1", "source_id": "FDA-510K", "clause": "510(k)", "url": "https://www.fda.gov/medical-devices/premarket-submissions/premarket-notification-510k"},
        {"citation_id": "bad", "claim_id": "claim-1", "source_id": "FDA-510K", "clause": "510(k)", "url": "https://example.invalid/fda"},
    ])
    assert len(result["verified"]) == 1
    assert len(result["rejected"]) == 1
    assert result["all_verified"] is False


def test_draft_marks_uncited_claims_unknown_and_requires_human_review():
    draft = RegulatoryDraftService().generate("GSPR", {
        "claims": [{"claim_id": "claim-1", "text": "The device has a documented risk control."}, {"claim_id": "claim-2", "text": "Unsupported conclusion."}],
        "citations": [{"citation_id": "c1", "claim_id": "claim-1", "source_id": "EU-MDR-2017-745", "clause": "Annex I", "url": "https://eur-lex.europa.eu/eli/reg/2017/745/oj"}],
    })
    assert draft.sections[0]["confidence"] == "HIGH"
    assert draft.sections[1]["confidence"] == "UNKNOWN"
    assert draft.sections[1]["unsupported"] is True
    assert draft.human_review_required is True
    assert set(CONFIDENCE_SEMANTICS) == {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}


def test_document_specific_authoring_sections_are_validated():
    draft = RegulatoryDraftService().generate("IFU", {
        "authoring_sections": {"intended_purpose": "Use for evaluation."},
        "claims": [], "citations": [],
    })
    statuses = {item["section_id"]: item["status"] for item in draft.sections}
    assert statuses["intended_purpose"] == "COMPLETE"
    assert statuses["instructions"] == "MISSING"
    assert any("Required authoring sections" in item for item in draft.limitations)
