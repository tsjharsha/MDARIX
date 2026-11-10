"""A document version as a PDF (the signed record, by the dependency-free writer in reports/pdf.py) and as a DOCX (by
python-docx, owner decision D-T5), from the same view: the title block with the version, template version, period
and cut-off, the clauses each marked "pending approval" until confirmed, the practice-record label in a trial and the
template's starter-text mark; each data section with the IDs of the records behind each row; each judgement section
marked "written by the manufacturer"; the signature manifestation; and the list of every source record.

The PDF cannot carry its own SHA-256: it carries the checksum of the signed content, and the PDF's SHA-256 is kept with
the signature (signed_approval_records) and printed on the screen and in the DOCX.
"""

from __future__ import annotations

import io
from collections import defaultdict

from backend.app.qms_documents.templates import WRITTEN_BY_MANUFACTURER

REFS_PER_LINE = 12
SOURCE_LABELS = {
    "Capa": "CAPAs",
    "Case": "Investigations",
    "CaseReview": "Risk reviews",
    "Change": "Change records",
    "Complaint": "Complaints",
    "Decision": "Decisions",
    "Disposition": "Dispositions",
    "Evidence": "Evidence",
    "FollowUp": "Impact decisions",
    "Hypothesis": "Hypotheses",
    "Lot": "Lots",
    "MarketAssessment": "Market assessments",
    "Product": "Products",
    "Risk": "Risks",
    "SecondLook": "Second-look decisions",
    "Signal": "Signals",
    "Signature": "Signature records",
}


def _refs(row: dict) -> str:
    refs = [source["ref"] for source in row.get("sources") or [] if source.get("ref")]
    if not refs:
        return ""
    shown = ", ".join(refs[:REFS_PER_LINE])
    more = len(refs) - REFS_PER_LINE + int(row.get("more") or 0)
    return f"Records: {shown}" + (f" and {more} more" if more > 0 else "")


def header_lines(view: dict) -> list[str]:
    period = view.get("period")
    scope = view.get("scope_ref")
    lines = [
        f"Organization: {view.get('organization') or '-'}",
        f"{view['title']}, version {view['version']} ({'signed' if view.get('signature') else 'draft, not signed'})"
        + (f"; {scope}" if scope else ""),
        f"Template version: {view['template_version']}. Document ID: {view.get('business_id') or view.get('id')}",
        (
            f"Period: {period['from']} to {period['to']} ({period['days']} days). "
            if period
            else "Records up to the cut-off. "
        )
        + f"Data cut-off: {view['cut_off']}",
    ]
    if view.get("practice_label"):
        lines.append(view["practice_label"])
    return lines


def clause_line(view: dict) -> str:
    return "Clauses it serves: " + "; ".join(
        f"{clause['short']} {clause['title']} ({clause['state']})" for clause in view.get("clauses") or []
    )


def sources_by_type(view: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for section in view.get("sections") or []:
        for item in section.get("rows") or []:
            for source in item.get("sources") or []:
                refs = found[source["type"]]
                if source.get("ref") and source["ref"] not in refs:
                    refs.append(source["ref"])
    return dict(sorted(found.items()))


def manifestation(view: dict) -> list[str]:
    signature = view.get("signature")
    if not signature:
        return ["Not signed: this is a draft. A draft is not a record to file."]
    lines = [
        f"Signed by {signature['signer_name']} ({signature['signer_role']}) on {signature['signed_at']}.",
        f"Meaning: {signature['meaning']}",
        f"Signature record: {signature['record_business_id'] or signature['record_id']}.",
        f"Content checksum (SHA-256 of the signed content): {signature['content_fingerprint']}",
    ]
    if signature.get("pdf_sha256"):
        lines.append(f"PDF SHA-256 (of the signed PDF file): {signature['pdf_sha256']}")
    writer = view.get("writer_note")
    if writer:
        lines.append(writer)
    return lines


def pdf_lines(view: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = [(clause_line(view), "body"), (view["starter_mark"], "muted")]
    for section in view["sections"]:
        out += [("", "body"), (section["title"], "heading")]
        if section["kind"] == "judgement":
            out.append((f"[{WRITTEN_BY_MANUFACTURER}] {section['prompt']}", "muted"))
            written = (view.get("judgement") or {}).get(section["key"]) or {}
            for paragraph in (written.get("text") or "(not written yet)").splitlines() or [""]:
                out.append((paragraph, "body"))
            if written.get("written_by_name"):
                out.append((f"Written by {written['written_by_name']} on {written['written_at']}.", "muted"))
            continue
        if section.get("note"):
            out.append((section["note"], "muted"))
        for item in section["rows"]:
            out.append((f"- {item['text']}", "body"))
            refs = _refs(item)
            if refs:
                out.append((f"    {refs}", "muted"))
    out += [("", "body"), ("Signature manifestation", "heading"), *((line, "body") for line in manifestation(view))]
    out += [("", "body"), ("Source records", "heading")]
    for kind, refs in sources_by_type(view).items():
        out.append((f"{SOURCE_LABELS.get(kind, kind)}: {', '.join(refs)}", "body"))
    out += [("", "body"), (view["footer_note"], "muted")]
    return out


def render_pdf(view: dict) -> bytes:
    from reports import pdf

    watermark = (
        "PRACTICE RECORD - NOT YOUR REGULATORY RECORD"
        if view.get("practice_label")
        else ("SIGNED VERSION" if view.get("signature") else "DRAFT - NOT SIGNED")
    )
    footer = f"{view.get('organization') or ''} - {view['title']} v{view['version']} - cut-off {view['cut_off']}"
    return pdf.render(
        f"MDARIX {view['title']}", header_lines(view), pdf_lines(view), watermark=watermark, footer=footer
    )


def export_note(view: dict) -> str:
    signature = view.get("signature")
    if signature:
        return (
            f"Exported from signed version {view['version']} ({view.get('business_id') or view['id']}, PDF SHA-256 "
            f"{signature.get('pdf_sha256')}); edits outside MDARIX are not part of this record."
        )
    return (
        f"Exported from draft version {view['version']}, not signed; edits outside MDARIX are not part of this record."
    )


def render_docx(view: dict) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = f"MDARIX {view['title']}"
    document.add_heading(view["title"], level=0)
    note = document.add_paragraph()
    note.add_run(export_note(view)).bold = True
    for line in header_lines(view):
        document.add_paragraph(line)
    document.add_paragraph(clause_line(view))
    document.add_paragraph().add_run(view["starter_mark"]).italic = True
    for section in view["sections"]:
        document.add_heading(section["title"], level=1)
        if section["kind"] == "judgement":
            document.add_paragraph().add_run(f"{WRITTEN_BY_MANUFACTURER}. {section['prompt']}").italic = True
            written = (view.get("judgement") or {}).get(section["key"]) or {}
            document.add_paragraph(written.get("text") or "(not written yet)")
            if written.get("written_by_name"):
                document.add_paragraph().add_run(
                    f"Written by {written['written_by_name']} on {written['written_at']}."
                ).italic = True
            continue
        if section.get("note"):
            document.add_paragraph().add_run(section["note"]).italic = True
        for item in section["rows"]:
            document.add_paragraph(item["text"], style="List Bullet")
            refs = _refs(item)
            if refs:
                document.add_paragraph().add_run(refs).font.size = Pt(8)
    document.add_heading("Signature manifestation", level=1)
    for line in manifestation(view):
        document.add_paragraph(line)
    document.add_heading("Source records", level=1)
    for kind, refs in sources_by_type(view).items():
        document.add_paragraph(f"{SOURCE_LABELS.get(kind, kind)}: {', '.join(refs)}")
    document.add_paragraph().add_run(view["footer_note"]).italic = True
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()
