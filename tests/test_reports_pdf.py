"""The evidence package PDF lists every audit event and signature, over as many pages as it takes."""

import uuid

from reports.pdf import escape, page_count
from reports.service import generate_report
from regulatory_intelligence.estar import generate_estar_package


def _events(count):
    return [
        {
            "id": str(uuid.uuid4()),
            "action": "DECISION_SIGNED" if index % 2 else "EVIDENCE_LINKED",
            "entity_id": str(uuid.uuid4()),
            "actor_ref": f"user-{index}",
            "reason": "Reviewed (all) evidence \\ backslash",
            "details": {"note": "x" * 300},
        }
        for index in range(count)
    ]


def test_every_audit_event_and_signature_is_in_a_multi_page_pdf():
    events = _events(200)
    signatures = [{"signature_id": str(uuid.uuid4()), "valid": True, "decision": "APPROVE"} for _ in range(30)]
    result = generate_report(
        "AUDIT_APPROVAL",
        str(uuid.uuid4()),
        context={"audit_events": events, "signature_verification": signatures, "data_cut_off": "2026-10-05T00:00:00"},
        output_format="PDF",
        tenant_name="Acme Care",
    )
    pdf = result["content"]
    assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert page_count(pdf) > 1
    for event in events:
        assert event["id"].encode() in pdf
    for signature in signatures:
        assert signature["signature_id"].encode() in pdf
    # Parentheses and backslashes are escaped, so the text cannot break out of its PDF string.
    assert escape("Reviewed (all) evidence \\ backslash").encode() in pdf
    assert b"Data cut-off: 2026-10-05T00:00:00" in pdf and b"Acme Care" in pdf
    assert b"Page 1 of" in pdf


def test_a_small_report_is_one_page():
    result = generate_report("DECISION_BRIEF", "tenant-a", context={"summary": {"decisions": 1}}, output_format="PDF")
    assert page_count(result["content"]) == 1


def test_the_estar_preparation_pdf_still_renders_its_sections():
    import io
    import zipfile

    package = generate_estar_package(
        tenant_id="tenant-a",
        title="510(k) preparation",
        sections=[
            {"claim_id": "A1", "text": "Claim text", "citation_ids": ["c1"]},
            {"section_id": "device_description", "content": "A syringe pump.", "status": "COMPLETE"},
        ],
        citations={"verified": [{"citation_id": "c1"}], "rejected": [], "all_verified": True},
    )
    with zipfile.ZipFile(io.BytesIO(package["content"])) as archive:
        pdf = archive.read("estar-preparation.pdf")
        xml = archive.read("estar-preparation.xml")
    assert pdf.startswith(b"%PDF") and b"A syringe pump." in pdf
    assert b'id="device_description"' in xml
