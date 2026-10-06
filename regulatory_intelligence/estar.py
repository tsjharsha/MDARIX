"""Controlled eSTAR preparation package generation.

FDA eSTAR is an official, versioned submission package. MDARIX must not claim
that a home-grown XML file is an FDA eSTAR submission. This module therefore
produces a deterministic preparation package that can be reviewed and mapped
into the current official eSTAR template.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from reports.service import _render_pdf

NS = "urn:mdarix:regulatory:estar-preparation:v1"
ET.register_namespace("mdarix", NS)


def validate_estar_xml(xml_bytes: bytes) -> dict:
    errors: list[str] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return {"valid": False, "errors": [f"XML_PARSE_ERROR: {exc}"]}
    if root.tag != f"{{{NS}}}estarPreparation":
        errors.append("ROOT_ELEMENT_INVALID")
    required = {"documentType", "templateVersion", "tenantId", "title", "humanReviewRequired", "sections"}
    present = {child.tag.rsplit("}", 1)[-1] for child in root}
    errors.extend(f"MISSING_{name.upper()}" for name in sorted(required - present))
    if (
        root.find(f"{{{NS}}}documentType") is not None
        and root.find(f"{{{NS}}}documentType").text != "ESTAR_510K_PREPARATION"
    ):
        errors.append("DOCUMENT_TYPE_INVALID")
    if (
        root.find(f"{{{NS}}}humanReviewRequired") is not None
        and root.find(f"{{{NS}}}humanReviewRequired").text != "true"
    ):
        errors.append("HUMAN_REVIEW_REQUIRED")
    for section in root.findall(f"{{{NS}}}sections/{{{NS}}}section"):
        if not section.get("id") or not section.find(f"{{{NS}}}text").text:
            errors.append("SECTION_MISSING_ID_OR_TEXT")
        if section.find(f"{{{NS}}}citations") is None:
            errors.append("SECTION_CITATIONS_MISSING")
    return {"valid": not errors, "errors": errors, "schema": "MDARIX eSTAR preparation v1"}


def generate_estar_package(
    *, tenant_id: str, title: str, sections: list[dict], citations: dict, document_version: int = 1
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    root = ET.Element(f"{{{NS}}}estarPreparation", {"version": "1.0"})
    fields = {
        "documentType": "ESTAR_510K_PREPARATION",
        "templateVersion": "MDARIX-eSTAR-prep-1.0",
        "tenantId": str(tenant_id),
        "title": title,
        "humanReviewRequired": "true",
    }
    for name, value in fields.items():
        ET.SubElement(root, f"{{{NS}}}{name}").text = value
    ET.SubElement(root, f"{{{NS}}}generatedAt").text = now
    ET.SubElement(root, f"{{{NS}}}documentVersion").text = str(document_version)
    sections_node = ET.SubElement(root, f"{{{NS}}}sections")
    for item in sections:
        # Claims carry claim_id/text; authoring sections carry section_id/content (and the model's ai_draft).
        identifier = item.get("claim_id") or item.get("section_id") or "UNSPECIFIED"
        text = item.get("text") or item.get("content") or item.get("ai_draft") or ""
        node = ET.SubElement(sections_node, f"{{{NS}}}section", {"id": str(identifier)})
        ET.SubElement(node, f"{{{NS}}}text").text = str(text)
        ET.SubElement(node, f"{{{NS}}}confidence").text = str(item.get("confidence", "UNKNOWN"))
        citation_node = ET.SubElement(node, f"{{{NS}}}citations")
        for citation_id in item.get("citation_ids", []):
            ET.SubElement(citation_node, f"{{{NS}}}citationRef").text = str(citation_id)
    citations_node = ET.SubElement(root, f"{{{NS}}}citationVerification")
    citations_node.text = json.dumps(citations, sort_keys=True)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    validation = validate_estar_xml(xml_bytes)
    if not validation["valid"]:
        raise ValueError("ESTAR_PREPARATION_INVALID: " + ",".join(validation["errors"]))
    pdf_data = {
        "title": title,
        "tenant_id": str(tenant_id),
        "report_version": f"eSTAR-prep-{document_version}",
        "generated_at": now,
        "sections": sections,
        "citation_verification": citations,
        "limitations": [
            "Preparation package only; map into the current official FDA eSTAR template before submission."
        ],
    }
    pdf_bytes = _render_pdf(pdf_data, f"MDARIX CONTROLLED PREPARATION COPY - {tenant_id} - v{document_version}")
    manifest = {
        "package_type": "MDARIX_ESTAR_PREPARATION",
        "version": "1.0",
        "document_version": document_version,
        "tenant_id": str(tenant_id),
        "xml_validation": validation,
        "human_review_required": True,
        "official_template_required": True,
    }
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("estar-preparation.xml", xml_bytes)
        archive.writestr("estar-preparation.pdf", pdf_bytes)
    return {
        "content": package.getvalue(),
        "content_type": "application/zip",
        "filename": f"{tenant_id}-estar-preparation-v{document_version}.zip",
        "validation": validation,
        "manifest": manifest,
    }
