"""The EU report as a readable PDF of its MIR file (B8 step 9): sections 1 to 5, each block with the help text's
number and label, in the form's order, the values read back from the XML itself. What the PDF shows is what the file
says.

The title says who made it (B8-D18): "EU MIR 7.3.1 content, prepared by MDARIX". It never claims the Commission or an
authority made it. A record page follows: who prepared it, the source records, the approval and the file's SHA-256. A
report not yet approved is marked DRAFT - NOT APPROVED (D7). No date or time is written into the PDF, so the same
file renders the same bytes.
"""

from __future__ import annotations

import hashlib
import re

from lxml import etree

from backend.app.authority_reports import emdr_pdf, forms, mir_rules, mir_xml

TITLE = "EU MIR 7.3.1 content, prepared by MDARIX"
SECTIONS = {
    "1": "1 Administrative information",
    "2": "2 Medical device information",
    "3": "3 Incident information",
    "4": "4 Manufacturer's analysis",
    "5": "5 General comments",
}
# Parts shown with the group they belong to ("Manufacturer · city").
_GROUPS = {
    "mfrDetails": "Manufacturer",
    "arDetails": "Authorised representative",
    "reporterDetails": "Submitter",
    "deviceMarketDate": "Date",
    "implantDuration": "Duration",
    "patientAgeAtEvent": "Age",
}
_PERIOD = re.compile(r"^timePeriod(N(?:-\d)?)$")


def _words(name: str) -> str:
    """An element's name as words: "mfrOrgStreet" -> "Mfr org street", "ARCity" -> "AR city"."""
    parts = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name.replace("_", " ")).split()
    words = " ".join(part if part.isupper() and len(part) > 1 else part.lower() for part in parts)
    return words[:1].upper() + words[1:]


def _labels() -> dict[str, str]:
    return {row["block"]: row["label"] for row in mir_rules.rows(forms.EU_MIR.code)}


def _block(element) -> str | None:
    """The rule book's block of an element, or of the nearest parent that has one."""
    while element is not None and element.tag != "incident":
        found = mir_xml._block(element.tag)
        if found != element.tag:
            return found.split(" ", 1)[0]
        element = element.getparent()
    return None


def _label(element) -> str:
    parent = element.getparent().tag
    period = _PERIOD.match(parent)
    if period:
        return f"Period {period.group(1)} · {_words(element.tag)}"
    group = _GROUPS.get(parent)
    return f"{group} · {_words(element.tag)}" if group else _words(element.tag)


def body(xml: bytes) -> list[tuple[str, str]]:
    """Sections 1 to 5: each block the file holds, with its number and label, and its values. A block with several
    places names each one."""
    root = etree.fromstring(xml)
    labels = _labels()
    blocks: dict[str, list] = {}
    for element in root.iter():
        if len(element) == 0 and element is not root and (element.text or "").strip():
            blocks.setdefault(_block(element) or "", []).append(element)
    lines: list[tuple[str, str]] = []
    section = None
    for block, elements in blocks.items():
        if block[:1] != section and block[:1] in SECTIONS:
            section = block[:1]
            lines += [("", "body"), (SECTIONS[section], "heading")]
        lines.append((f"{block} {labels.get(block, '')}".strip(), "body"))
        if len(elements) == 1 and block:
            lines.append((f"    {elements[0].text.strip()}", "body"))
        else:
            lines += [(f"    {_label(element)}: {element.text.strip()}", "body") for element in elements]
    return lines


def render(xml: bytes, view: dict, organization: str | None, *, note: str = "") -> bytes:
    """The PDF of a report's MIR file. ``view``: the report as the screen reads it, with the snapshot's sections and,
    once approved, its signature (without one, the PDF is a DRAFT preview). ``note``: how the file was made."""
    from backend.app.authority_reports.render import PREVIEW_LINE, PREVIEW_MARK
    from reports import pdf

    root = etree.fromstring(xml)
    complaint = view["complaint"]
    header = [
        f"Report type: {root.findtext('admin_info/reportType') or '-'} · Manufacturer's reference: "
        f"{root.findtext('admin_info/mfrRef') or '-'} · Authority: {root.findtext('admin_info/ncaName') or '-'}",
        f"Organization: {organization or '-'} · Complaint {complaint['ref']}: "
        f"{complaint['product_name'] or '-'} {complaint['version'] or ''}".rstrip(),
        "Prepared by MDARIX from the report's MIR file (XML), in the blocks and order of the MIR form 7.3.1.",
        "MDARIX never submits: you send the MIR file to the national competent authority. Import the XML into the "
        "official MIR PDF if your authority asks for it.",
    ]
    draft = not view.get("signature")
    if view.get("practice_label"):
        header.insert(0, view["practice_label"])
    if draft:
        header.insert(0, PREVIEW_LINE)
    watermark = (
        PREVIEW_MARK
        if draft
        else "PRACTICE RECORD - NOT YOUR REGULATORY RECORD"
        if view.get("practice_label")
        else "EU MIR CONTENT - PREPARED BY MDARIX"
    )
    lines = body(xml) + emdr_pdf.record(view, [], hashlib.sha256(xml).hexdigest(), note, name="MIR")
    footer = f"{complaint['ref']} - EU MIR 7.3.1 content - prepared by MDARIX, which never submits"
    return pdf.render(TITLE, header, lines, watermark=watermark, footer=footer)
