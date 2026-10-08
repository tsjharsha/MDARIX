from reports.service import REPORT_VERSION, generate_report


def test_compliance_report_payload_is_renderable_in_all_formats():
    context = {
        "audit_events": [{"action": "SIGNED_APPROVAL_CREATED", "reason": "Reviewed evidence"}],
        "signature_verification": [{"valid": True}],
        "counts": {"audit_events": 1, "signatures": 1, "valid_signatures": 1},
    }
    json_result = generate_report("AUDIT_APPROVAL", "tenant-a", context=context, output_format="JSON")
    csv_result = generate_report("AUDIT_APPROVAL", "tenant-a", context=context, output_format="CSV")
    pdf_result = generate_report("AUDIT_APPROVAL", "tenant-a", context=context, output_format="PDF")
    assert json_result["report_version"] == REPORT_VERSION
    assert json_result["context"]["counts"]["valid_signatures"] == 1
    assert csv_result["content_type"] == "text/csv" and "SIGNED_APPROVAL_CREATED" in csv_result["content"]
    assert pdf_result["content_type"] == "application/pdf" and pdf_result["content"].startswith(b"%PDF")


def test_governed_word_and_estar_exports_are_watermarked_and_versioned():
    context = {"public_fact": "visible", "secret_field": "must not export"}
    word = generate_report(
        "AUDIT_APPROVAL",
        "tenant-a",
        context=context,
        hidden_fields={"secret_field"},
        output_format="WORD",
        watermark="DEMO CONTROLLED COPY",
    )
    xml = generate_report(
        "AUDIT_APPROVAL",
        "tenant-a",
        context=context,
        hidden_fields={"secret_field"},
        output_format="ESTAR_XML",
        watermark="DEMO CONTROLLED COPY",
    )
    assert word["content_type"] == "application/msword"
    assert b"DEMO CONTROLLED COPY" in word["content"]
    assert b"secret_field" not in word["content"]
    assert xml["content_type"] == "application/xml"
    assert b'schema-version="internal-1.0"' in xml["content"]
    assert b"NOT_PERFORMED" in xml["content"]
    assert b"secret_field" not in xml["content"]
