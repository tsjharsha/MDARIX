"""A small, dependency-free PDF writer for governed reports.

Reports can run to thousands of lines (an evidence package lists every audit event and signature), so the writer
paginates: long values wrap at the page width, every page carries the watermark and "Page i of n", and the file has a
correct cross-reference table so strict readers open it. Text is written with the standard Courier font because its
fixed character width makes wrapping deterministic; headings use Helvetica-Bold.
"""

from __future__ import annotations

import textwrap
from typing import Iterable

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN = 48
BODY_FONT_SIZE = 9
BODY_LEADING = 11.5
# Courier is 0.6 em wide: at 9 pt a character takes 5.4 pt, so the printable width holds this many characters.
CHARS_PER_LINE = int((PAGE_WIDTH - 2 * MARGIN) / (BODY_FONT_SIZE * 0.6))
HEADER_BOTTOM = PAGE_HEIGHT - MARGIN - 26
FOOTER_TOP = MARGIN + 14
BODY_LINES_PER_PAGE = int((HEADER_BOTTOM - FOOTER_TOP) / BODY_LEADING)

Line = tuple[str, str]  # (text, style) where style is "body", "heading" or "muted"
# Characters outside Latin-1 that WinAnsiEncoding (the fonts' encoding) still has, as octal escapes: dashes and quotes.
WIN_ANSI = {"–": "\\226", "—": "\\227", "‘": "\\221", "’": "\\222", "“": "\\223", "”": "\\224"}


def escape(value: str) -> str:
    """A PDF string literal body: backslash and parentheses escaped, typographic dashes and quotes in the fonts'
    encoding, anything else outside Latin-1 made printable."""
    out = []
    for ch in value:
        if ch in "\\()":
            out.append("\\" + ch)
        elif ch in WIN_ANSI:
            out.append(WIN_ANSI[ch])
        elif ch in "\r\n\t":
            out.append(" ")
        elif ord(ch) < 32 or ord(ch) > 255:
            out.append("?")
        else:
            out.append(ch)
    return "".join(out)


def wrap(text: str, width: int = CHARS_PER_LINE) -> list[str]:
    """Wrap one logical line, keeping its indentation on continuation lines (long tokens are broken, never lost)."""
    if not text.strip():
        return [""]
    indent = len(text) - len(text.lstrip(" "))
    continuation = " " * min(indent + 2, width // 2)
    return textwrap.wrap(
        text,
        width=width,
        subsequent_indent=continuation,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    ) or [""]


def flatten(value, indent: int = 0, *, max_items: int | None = None) -> list[Line]:
    """Readable lines for nested report data: ``key: value`` pairs, nested blocks indented, list items dashed."""
    pad = " " * indent
    lines: list[Line] = []
    if isinstance(value, dict):
        if not value:
            return [(f"{pad}(none)", "body")]
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                if not item:
                    lines.append((f"{pad}{key}: (none)", "body"))
                    continue
                lines.append((f"{pad}{key}:", "body"))
                lines.extend(flatten(item, indent + 2, max_items=max_items))
            else:
                lines.append((f"{pad}{key}: {_scalar(item)}", "body"))
        return lines
    if isinstance(value, list):
        if not value:
            return [(f"{pad}(none)", "body")]
        shown = value if max_items is None else value[:max_items]
        for item in shown:
            if isinstance(item, (dict, list)):
                nested = flatten(item, indent + 2, max_items=max_items)
                first, *rest = nested
                lines.append((f"{pad}- {first[0].lstrip(' ')}", "body"))
                lines.extend(rest)
            else:
                lines.append((f"{pad}- {_scalar(item)}", "body"))
        if max_items is not None and len(value) > max_items:
            lines.append((f"{pad}... {len(value) - max_items} more", "muted"))
        return lines
    return [(f"{pad}{_scalar(value)}", "body")]


def _scalar(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def render(title: str, header_lines: Iterable[str], body: Iterable[Line], *, watermark: str, footer: str) -> bytes:
    """The PDF: a title block, then the body paginated; every page carries the watermark and its number."""
    wrapped: list[Line] = []
    for text, style in body:
        for piece in wrap(text):
            wrapped.append((piece, style))
    header = [line for line in header_lines]
    # The title block takes the top of the first page; later pages start their body straight under the header.
    first_page_capacity = max(1, BODY_LINES_PER_PAGE - len(header) - 2)
    pages: list[list[Line]] = []
    cursor = 0
    while True:
        capacity = first_page_capacity if not pages else BODY_LINES_PER_PAGE
        pages.append(wrapped[cursor : cursor + capacity])
        cursor += capacity
        if cursor >= len(wrapped):
            break
    total = len(pages)
    objects: list[bytes] = []

    def add(body_bytes: bytes) -> int:
        objects.append(body_bytes)
        return len(objects)

    catalog = add(b"")  # placeholder, filled once the page tree id is known
    pages_id = add(b"")
    courier = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    page_ids = []
    for number, lines in enumerate(pages, 1):
        stream = _page_stream(
            title, header if number == 1 else [], lines, watermark=watermark, footer=footer, page=number, total=total
        )
        content = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_ids.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                    f"/Resources << /Font << /F1 {courier} 0 R /F2 {bold} 0 R >> >> /Contents {content} 0 R >>"
                ).encode()
            )
        )
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for index, body_bytes in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body_bytes + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _text(x: float, y: float, text: str, *, font: str = "F1", size: float = BODY_FONT_SIZE, gray: float = 0) -> str:
    return f"BT {gray:.2f} g /{font} {size} Tf {x:.1f} {y:.1f} Td ({escape(text)}) Tj ET\n"


def _page_stream(title, header, lines, *, watermark, footer, page, total) -> bytes:
    parts = [
        _text(MARGIN, PAGE_HEIGHT - MARGIN + 6, watermark, font="F2", size=8, gray=0.35),
        _text(MARGIN, PAGE_HEIGHT - MARGIN - 10, title, font="F2", size=13),
    ]
    y = HEADER_BOTTOM
    for line in header:
        parts.append(_text(MARGIN, y, line[: CHARS_PER_LINE + 10], size=BODY_FONT_SIZE, gray=0.25))
        y -= BODY_LEADING
    if header:
        y -= BODY_LEADING
    for text, style in lines:
        if style == "heading":
            parts.append(_text(MARGIN, y, text.strip(), font="F2", size=10.5))
        elif style == "muted":
            parts.append(_text(MARGIN, y, text, gray=0.45))
        else:
            parts.append(_text(MARGIN, y, text))
        y -= BODY_LEADING
    parts.append(_text(MARGIN, MARGIN - 4, footer[: CHARS_PER_LINE - 16], size=7.5, gray=0.4))
    parts.append(_text(PAGE_WIDTH - MARGIN - 70, MARGIN - 4, f"Page {page} of {total}", size=7.5, gray=0.4))
    return "".join(parts).encode("latin-1", errors="replace")


def page_count(pdf: bytes) -> int:
    """How many pages a PDF written here has (for tests and job metadata)."""
    marker = b"/Type /Pages /Kids ["
    start = pdf.find(marker)
    if start < 0:
        return 0
    tail = pdf[start:]
    count_at = tail.find(b"/Count ")
    end = tail.find(b" ", count_at + 7)
    return int(tail[count_at + 7 : end])
