from regulatory_intelligence.catalog import official_source_manifest, verify_citations
from regulatory_intelligence.context import build_regulatory_context
from regulatory_intelligence.service import CONFIDENCE_SEMANTICS, RegulatoryDraftService, validate_confidence_semantics


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


def test_verified_claim_contains_authoritative_traceability_and_document_metrics():
    draft = RegulatoryDraftService().generate("CER", {
        "claims": [
            {"claim_id": "c1", "text": "Supported claim."},
            {"claim_id": "c2", "text": "Unproven claim."},
        ],
        "citations": [{"citation_id": "ref-1", "claim_id": "c1", "source_id": "FDA-510K", "clause": "510(k)", "url": "https://www.fda.gov/medical-devices/premarket-submissions/premarket-notification-510k"}],
    })
    assert draft.sections[0]["traceability_status"] == "TRACEABLE"
    assert draft.sections[0]["authoritative_clauses"] == ["FDA-510K:510(k)"]
    assert draft.citations["traceability"]["claims_untraceable"] == 1


def test_confidence_semantics_and_customer_context_are_validated():
    assert set(validate_confidence_semantics()) == set(CONFIDENCE_SEMANTICS)
    context = build_regulatory_context("tenant-a", [{"tenant_id": "tenant-a", "id": 1}, {"tenant_id": "tenant-b", "id": 2}], [])
    assert [item["id"] for item in context["records"]] == [1]
    assert {item["source_id"] for item in official_source_manifest()} == {"FDA-510K", "EU-MDR-2017-745", "ISO-13485", "ISO-14971"}
