"""A worksheet as a PDF (reports/pdf.py, as the ready-to-use documents) and a DOCX (python-docx), from the screen's
view: the title block with the form version, the "draft: MDARIX never submits" line, the practice-record label in a
trial and the starter-text mark; every section in the form's order, each field with its value, status and source;
the list of source records; and last the approval manifestation of an approved snapshot (21 CFR 11.50: the printed
name, the date and time, the meaning), on its own last page."""

from __future__ import annotations

import io

from backend.app.qms_documents.render import SOURCE_LABELS
from reports.pdf import PAGE_BREAK

DRAFT_LINE = "DRAFT - MDARIX NEVER SUBMITS. Enter this report in the authority's route yourself."
LABELS = {**SOURCE_LABELS, "Classification": "Classifications", "ImdrfMapping": "IMDRF mappings", "Triage": "Triage"}


def _title(view: dict) -> str:
    return f"{view['form']['title']}"


def header_lines(view: dict, organization: str | None) -> list[str]:
    snapshot = view.get("snapshot")
    complaint = view["complaint"]
    state = (
        f"approved snapshot {snapshot['version']}"
        if snapshot and snapshot["state"] == "APPROVED"
        else f"snapshot {snapshot['version']}, {snapshot['state'].lower()}"
        if snapshot
        else f"working draft ({view['state_label'].lower()})"
    )
    lines = [
        f"Organization: {organization or '-'}",
        f"Form version: {view['form']['version']}",
        f"Authority: {view['form']['authority']}",
        f"Complaint {complaint['ref']}: {complaint['product_name'] or '-'} {complaint['version'] or ''}",
        f"Market: {view['market_label']}; {state}",
        f"Deadline: {view['deadline'].get('due_label') or view['deadline']['due_on'] or 'not set'}"
        + (" (provisional)" if view["deadline"]["provisional"] else ""),
        DRAFT_LINE,
    ]
    if view.get("practice_label"):
        lines.append(view["practice_label"])
    return lines


def _value(item: dict) -> str:
    value = item["value"] if item["value"] else "-"
    return f"{item['number'] + ' ' if item['number'] else ''}{item['label']}: {value}"


def _status(item: dict) -> str:
    source = item.get("source") or {}
    where = source.get("label") or ""
    ref = f" ({source['ref']})" if source.get("ref") else ""
    by = f": {item['by']}" if item.get("by") else ""
    return f"[{item['status_label']}{by}]" + (f" {where}{ref}" if where else "")


def _sources(view: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for section in view["sections"]:
        for item in section["fields"]:
            source = item.get("source") or {}
            if source.get("ref"):
                refs = found.setdefault(source["type"], [])
                if source["ref"] not in refs:
                    refs.append(source["ref"])
    return dict(sorted(found.items()))


def manifestation(view: dict) -> list[str]:
    signature = view.get("signature")
    if not signature:
        return ["Not approved: a working draft or a snapshot waiting for approval is not the content to submit."]
    return [
        f"Approved by {signature['signer_name']} ({signature['signer_role']}) on {signature['signed_at']}.",
        f"Meaning: {signature['meaning']}",
        f"Signature record: {signature['record_business_id'] or signature['record_id']}.",
        f"Content checksum (SHA-256 of the snapshot): {signature['content_fingerprint']}",
    ]


def lines(view: dict) -> list[tuple[str, str]]:
    clauses = "; ".join(f"{chip['short']}: {chip['title']}" for chip in view["form"]["clauses"])
    out: list[tuple[str, str]] = [
        (f"Field order: {view['form']['source_document']}.", "muted"),
        (f"Clauses: {clauses} (pending approval)" if clauses else "", "muted"),
        (view["starter_mark"], "muted"),
        # 0.10.76: the EU, GB and Canada forms are starters, and say which report type this one is.
        (
            f"Starter form, for your consultant to confirm. Type of report: {view['form'].get('report_kind')}."
            if view["form"].get("starter")
            else "",
            "muted",
        ),
        (view["never_submits"], "muted"),
    ]
    for section in view["sections"]:
        out += [("", "body"), (section["title"], "heading")]
        if section.get("note"):
            out.append((section["note"], "muted"))
        if not section["fields"]:
            continue
        for item in section["fields"]:
            out.append((_value(item), "body"))
            out.append((f"    {_status(item)}", "muted"))
    out += [("", "body"), ("Source records", "heading")]
    for kind, refs in _sources(view).items():
        out.append((f"{LABELS.get(kind, kind)}: {', '.join(refs)}", "body"))
    # The approval last; an approved report's on its own last page (0.10.75, C3).
    out += [("", PAGE_BREAK if view.get("signature") else "body"), ("Approval", "heading")]
    out += [(line, "body") for line in manifestation(view)]
    return out


def render_pdf(view: dict, organization: str | None) -> bytes:
    from reports import pdf

    watermark = (
        "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "DRAFT - MDARIX NEVER SUBMITS"
    )
    footer = f"{view['complaint']['ref']} - {view['form']['version']} - MDARIX never submits"
    return pdf.render(
        f"MDARIX {_title(view)}", header_lines(view, organization), lines(view), watermark=watermark, footer=footer
    )


def render_docx(view: dict, organization: str | None) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = f"MDARIX {_title(view)}"
    document.add_heading(_title(view), level=0)
    for line in header_lines(view, organization):
        paragraph = document.add_paragraph()
        paragraph.add_run(line).bold = line == DRAFT_LINE
    for text, style in lines(view):
        if style == PAGE_BREAK:
            document.add_page_break()
            continue
        if not text:
            continue
        if style == "heading":
            document.add_heading(text, level=1)
        elif text.startswith("    "):
            run = document.add_paragraph().add_run(text.strip())
            run.italic, run.font.size = True, Pt(8)
        elif style == "muted":
            document.add_paragraph().add_run(text).italic = True
        else:
            document.add_paragraph(text)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def render(view: dict, kind: str, *, organization: str | None) -> bytes:
    return render_pdf(view, organization) if kind == "pdf" else render_docx(view, organization)
