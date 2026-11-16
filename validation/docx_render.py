"""B6b B5: render the validation pack's Markdown to DOCX (python-docx, E19) and to PDF lines (``reports.pdf``).

shortcut: only the Markdown the pack writes is supported (headings #..###, paragraphs, "- " bullets, pipe tables,
**bold** runs); anything else is written as plain text. Upgrade if a hand-written document needs more.
The DOCX is re-zipped with fixed entry dates and fixed core properties, so the same input gives byte-identical files
(B6-51)."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _blocks(markdown: str):
    """("heading", level, text) | ("bullet", text) | ("table", rows) | ("para", text), in order."""
    table: list[list[str]] = []
    for line in markdown.splitlines() + [""]:
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                table.append(cells)
            continue
        if table:
            yield ("table", table)
            table = []
        if not line.strip():
            continue
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        if heading:
            yield ("heading", len(heading.group(1)), heading.group(2))
        elif line.startswith("- "):
            yield ("bullet", line[2:])
        else:
            yield ("para", line)


def _runs(paragraph, text: str) -> None:
    for i, piece in enumerate(_BOLD.split(text)):
        if piece:
            paragraph.add_run(piece).bold = i % 2 == 1


def _deterministic(raw: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(raw))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            info = zipfile.ZipInfo(item.filename, _FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, source.read(item.filename))
    return out.getvalue()


def render_docx(markdown: str, *, title: str, document_date: str) -> bytes:
    """The DOCX of ``markdown``; ``document_date`` (YYYY-MM-DD) is written as the created and modified date."""
    from docx import Document

    document = Document()
    fixed = datetime.fromisoformat(document_date).replace(tzinfo=timezone.utc)
    props = document.core_properties
    props.title, props.author, props.last_modified_by = title, "MDARIX validation pack generator", ""
    props.created = props.modified = fixed
    props.revision = 1
    for block in _blocks(markdown):
        if block[0] == "heading":
            document.add_heading(block[2], level=block[1] - 1 if block[1] > 1 else 0)
        elif block[0] == "bullet":
            _runs(document.add_paragraph(style="List Bullet"), block[1])
        elif block[0] == "para":
            _runs(document.add_paragraph(), block[1])
        else:
            rows = block[1]
            width = max(len(row) for row in rows)
            table = document.add_table(rows=len(rows), cols=width)
            table.style = "Table Grid"
            for r, row in enumerate(rows):
                for c in range(width):
                    cell = table.cell(r, c)
                    cell.text = ""
                    _runs(cell.paragraphs[0], row[c] if c < len(row) else "")
                    if r == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True
    buffer = io.BytesIO()
    document.save(buffer)
    return _deterministic(buffer.getvalue())


def pdf_lines(markdown: str) -> list[tuple[str, str]]:
    """``reports.pdf`` body lines: headings as "heading", tables one row per line, the rest as "body"."""
    lines: list[tuple[str, str]] = []
    for block in _blocks(markdown):
        if block[0] == "heading":
            lines += [("", "body"), (block[2], "heading")]
        elif block[0] == "bullet":
            lines.append(("- " + _BOLD.sub(r"\1", block[1]), "body"))
        elif block[0] == "para":
            lines.append((_BOLD.sub(r"\1", block[1]), "body"))
        else:
            for r, row in enumerate(block[1]):
                lines.append((" | ".join(_BOLD.sub(r"\1", cell) for cell in row), "muted" if r == 0 else "body"))
            lines.append(("", "body"))
    return lines
