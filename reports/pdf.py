"""A small, dependency-free PDF writer for governed reports.

Reports can run to thousands of lines (an evidence package lists every audit event and signature), so the writer
paginates: long values wrap at the page width, every page carries the watermark, the MDARIX brand line and "Page i of
n", and the file has a correct cross-reference table so strict readers open it.

Text is set in Inter (the app's sans font) with Noto Sans Devanagari for Indian names and places, both embedded as
subsets (reports/fonts, SIL Open Font License), so every character prints as written: "≤ 25 °C", "5 μL", "₹ 1,25,000",
"OrbitCare™", "रमेश". Each font carries a ToUnicode map, so text copied or searched in a reader is the text written.
Only hashes (32 or more hexadecimal characters) are set in the standard Courier, where fixed width helps a reader
compare them. Columns written with runs of spaces keep their alignment: a run of two or more spaces moves the text
to its character column.
"""

from __future__ import annotations

import re
import zlib
from bisect import bisect_right
from functools import lru_cache
from typing import Iterable

from reports import ttf

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN = 48
BODY_FONT_SIZE = 9
BODY_LEADING = 11.5
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN
# The column unit: callers that align columns with spaces count characters of this width (Courier's 0.6 em at 9 pt).
COLUMN = BODY_FONT_SIZE * 0.6
CHARS_PER_LINE = int(TEXT_WIDTH / COLUMN)
HEADER_TOP = PAGE_HEIGHT - MARGIN - 16
FOOTER_TOP = MARGIN + 14
FOOTER_SIZE = 7.5
PAGE_LABEL_WIDTH = 70
BRAND = "MDARIX"
BRAND_LINE = "complaint handling and post-market vigilance"
TEAL = (0.031, 0.482, 0.471)  # #087b78, the site's and the app's teal

Line = tuple[str, str]  # (text, style) where style is "body", "heading", "muted" or PAGE_BREAK

# Font resource names: the sans regular and semibold, the Devanagari fallback, and Courier for hashes.
SANS, SANS_BOLD, DEVANAGARI, MONO = "F1", "F2", "F3", "F4"
FONT_FILES = {SANS: "Inter-Regular.ttf", SANS_BOLD: "Inter-SemiBold.ttf", DEVANAGARI: "NotoSansDevanagari-Regular.ttf"}
HASH = re.compile(r"\b[0-9a-fA-F]{32,}\b")
DEVANAGARI_I = "ि"  # the short i sign, written before the consonant it follows in the text


def _clean(value: str) -> str:
    return "".join(" " if ch in "\r\n\t" else ch for ch in value if ch in "\r\n\t" or ord(ch) >= 32)


def _visual(value: str) -> str:
    """Devanagari's short i sign is drawn before its consonant; the writer has no shaping engine, so it moves it.
    shortcut: no conjunct forms (a virama shows as a visible sign) and copied text has the sign before the consonant;
    embed a shaping engine if customers write Devanagari beyond names and places."""
    if DEVANAGARI_I not in value:
        return value
    chars = list(value)
    for index in range(1, len(chars)):
        if chars[index] == DEVANAGARI_I and "क" <= chars[index - 1] <= "ह":
            chars[index - 1], chars[index] = chars[index], chars[index - 1]
    return "".join(chars)


@lru_cache(maxsize=8192)
def _font_for(ch: str, base: str) -> tuple[str, str]:
    if ch == " " or ttf.load(FONT_FILES[base]).glyph(ch) is not None:
        return base, ch
    if ttf.load(FONT_FILES[DEVANAGARI]).glyph(ch) is not None:
        return DEVANAGARI, ch
    return base, "?"  # a script no embedded font has (reported, never silently dropped)


def _runs(text: str, base: str) -> list[tuple[str, str]]:
    """The text in (font, characters) runs: hashes in Courier, Devanagari in Noto, the rest in the base sans font."""
    hashed = {index for match in HASH.finditer(text) for index in range(match.start(), match.end())}
    runs: list[tuple[str, str]] = []
    for index, ch in enumerate(text):
        font, ch = (MONO, ch) if index in hashed else _font_for(ch, base)
        if runs and runs[-1][0] == font:
            runs[-1] = (font, runs[-1][1] + ch)
        else:
            runs.append((font, ch))
    return runs


@lru_cache(maxsize=4096)
def _char_width(font: str, ch: str, size: float) -> float:
    if font == MONO:
        return 0.6 * size
    face = ttf.load(FONT_FILES[font])
    gid = face.glyph(ch)
    return face.advance(gid if gid is not None else 0, size)


def _segments(text: str) -> list[tuple[int, str]]:
    """The line cut at its column gaps: (character column, text) for the start and after each run of 2+ spaces."""
    return [(match.start(2), match.group(2)) for match in re.finditer(r"(^ +| {2,})?([^ ]+(?: [^ ]+)*)", text)]


def _layout(text: str, base: str, size: float) -> list[tuple[float, list[tuple[str, str]], float]]:
    """Where each segment of a line goes: (x offset, runs, width). A segment starts at its character column, or a
    space after the one before when that one is wider."""
    placed, end = [], 0.0
    space = _char_width(base, " ", size)
    for column, segment in _segments(text):
        x = column * COLUMN if not placed else max(column * COLUMN, end + space)
        runs = _runs(segment, base)
        width = sum(_char_width(font, ch, size) for font, chars in runs for ch in chars)
        placed.append((x, runs, width))
        end = x + width
    return placed


def _ends(text: str, base: str, size: float) -> list[float]:
    """Where each character of the line ends, in points from the left margin (the layout of _layout)."""
    ends, end = [0.0] * len(text), 0.0
    space = _char_width(base, " ", size)
    for number, (column, segment) in enumerate(_segments(text)):
        x = column * COLUMN if number == 0 else max(column * COLUMN, end + space)
        index = column
        for font, chars in _runs(segment, base):
            for ch in chars:
                x += _char_width(font, ch, size)
                ends[index] = x
                index += 1
        end = x
    for index in range(1, len(ends)):  # a space between segments ends where the text before it ends
        ends[index] = max(ends[index], ends[index - 1])
    return ends


def text_width(text: str, base: str = SANS, size: float = BODY_FONT_SIZE) -> float:
    ends = _ends(_visual(_clean(text)), base, size)
    return ends[-1] if ends else 0.0


def wrap(text: str, width: float = TEXT_WIDTH, base: str = SANS, size: float = BODY_FONT_SIZE) -> list[str]:
    """Wrap one logical line to the width in points, keeping its indentation on continuation lines (long tokens are
    broken, never lost)."""
    text = _clean(text)
    if not text.strip():
        return [""]
    indent = len(text) - len(text.lstrip(" "))
    continuation = " " * min(indent + 2, CHARS_PER_LINE // 2)
    lines, rest = [], text
    while True:
        ends = _ends(rest, base, size)
        if not ends or ends[-1] <= width:
            break
        fits = bisect_right(ends, width)  # the longest prefix that fits
        lead = len(rest) - len(rest.lstrip(" "))
        space = rest.rfind(" ", lead, fits + 1)
        cut = space if space > lead else max(fits, lead + 1)
        lines.append(rest[:cut].rstrip(" "))
        rest = continuation + rest[cut:].lstrip(" ")
    lines.append(rest)
    return lines


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


PAGE_BREAK = "pagebreak"  # a body line's style that starts a new page
STYLES = {"heading": (SANS_BOLD, 10.5, 0), "muted": (SANS, BODY_FONT_SIZE, 0.45), "body": (SANS, BODY_FONT_SIZE, 0)}


class _Fonts:
    """The characters each embedded font prints, numbered in order of first use (the PDF's character ids)."""

    def __init__(self):
        self.ids: dict[str, dict[str, int]] = {name: {} for name in FONT_FILES}

    def encode(self, font: str, chars: str) -> str:
        if font == MONO:
            return f"({chars})"
        ids = self.ids[font]
        return "<" + "".join(f"{ids.setdefault(ch, len(ids) + 1):04X}" for ch in chars) + ">"


def render(title: str, header_lines: Iterable[str], body: Iterable[Line], *, watermark: str, footer: str) -> bytes:
    """The PDF: a title block, then the body paginated; every page carries the watermark and its number."""
    wrapped: list[Line] = []
    for text, style in body:
        if style == PAGE_BREAK:
            wrapped.append(("", PAGE_BREAK))
            continue
        font, size, _ = STYLES.get(style, STYLES["body"])
        text = text.strip() if style == "heading" else text
        wrapped.extend((piece, style) for piece in wrap(text, TEXT_WIDTH, font, size))
    titles = wrap(title, TEXT_WIDTH, SANS_BOLD, 13)
    header = [piece for line in header_lines for piece in wrap(line, TEXT_WIDTH)]
    footers = wrap(footer, TEXT_WIDTH - PAGE_LABEL_WIDTH - 8, SANS, FOOTER_SIZE)
    body_top = HEADER_TOP - 16 * len(titles)
    per_page = int((body_top - FOOTER_TOP - (len(footers) - 1) * 9) / BODY_LEADING)
    first_page_capacity = max(1, per_page - len(header) - 1)
    # A PAGE_BREAK line starts a new page (an approved report's approval stands on its own last page).
    pages: list[list[Line]] = [[]]
    for line in wrapped:
        capacity = first_page_capacity if len(pages) == 1 else per_page
        if line[1] == PAGE_BREAK or len(pages[-1]) >= capacity:
            pages.append([])
        if line[1] != PAGE_BREAK:
            pages[-1].append(line)
    total = len(pages)
    fonts = _Fonts()
    objects: list[bytes] = []

    def add(body_bytes: bytes) -> int:
        objects.append(body_bytes)
        return len(objects)

    catalog = add(b"")  # placeholders, filled once the ids they point to are known
    pages_id = add(b"")
    font_ids = {name: add(b"") for name in FONT_FILES}
    courier = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    resources = " ".join(f"/{name} {number} 0 R" for name, number in font_ids.items()) + f" /{MONO} {courier} 0 R"
    page_ids = []
    for number, lines in enumerate(pages, 1):
        stream = _page_stream(
            fonts, titles, header if number == 1 else [], lines, watermark, footers, f"Page {number} of {total}"
        )
        content = add(_stream(stream))
        page_ids.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                    f"/Resources << /Font << {resources} >> >> /Contents {content} 0 R >>"
                ).encode()
            )
        )
    for name, number in font_ids.items():
        objects[number - 1] = _type0(add, FONT_FILES[name], fonts.ids[name])
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


def _stream(data: bytes, extra: str = "") -> bytes:
    packed = zlib.compress(data, 9)
    head = f"<< /Length {len(packed)} /Filter /FlateDecode{extra} >>\nstream\n".encode()
    return head + packed + b"\nendstream"


def _type0(add, file_name: str, ids: dict[str, int]) -> bytes:
    """A composite font: the subset program, widths and ToUnicode map for the characters used, each id its glyph."""
    face = ttf.load(file_name)
    glyphs = {cid: face.glyph(ch) or 0 for ch, cid in ids.items()}
    tag = "".join(chr(65 + (sum(map(ord, "".join(ids))) // 26**i) % 26) for i in range(6))  # subset prefix
    name = f"{tag}+{face.name}"
    program = face.subset(set(glyphs.values()))
    font_file = add(_stream(program, f" /Length1 {len(program)}"))
    scale = 1000 / face.units
    descriptor = add(
        (
            f"<< /Type /FontDescriptor /FontName /{name} /Flags 32 /FontBBox [{' '.join(str(round(v * scale)) for v in face.bbox)}] "
            f"/ItalicAngle 0 /Ascent {round(face.ascent * scale)} /Descent {round(face.descent * scale)} "
            f"/CapHeight {round(face.cap_height * scale)} /StemV 80 /FontFile2 {font_file} 0 R >>"
        ).encode()
    )
    cid_map = bytearray(2 * (len(ids) + 1))
    for cid, gid in glyphs.items():
        cid_map[2 * cid : 2 * cid + 2] = gid.to_bytes(2, "big")
    cid_to_gid = add(_stream(bytes(cid_map)))
    widths = " ".join(str(face.pdf_width(glyphs[cid])) for cid in sorted(glyphs))
    descendant = add(
        (
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {descriptor} 0 R /DW {face.pdf_width(0)} /W [{f'1 [{widths}]' if widths else ''}] /CIDToGIDMap {cid_to_gid} 0 R >>"
        ).encode()
    )
    to_unicode = add(_stream(_cmap(ids).encode()))
    return (
        f"<< /Type /Font /Subtype /Type0 /BaseFont /{name} /Encoding /Identity-H "
        f"/DescendantFonts [{descendant} 0 R] /ToUnicode {to_unicode} 0 R >>"
    ).encode()


def _cmap(ids: dict[str, int]) -> str:
    entries = [f"<{cid:04X}> <{ch.encode('utf-16-be').hex().upper()}>" for ch, cid in ids.items()]
    chunks = [entries[i : i + 100] for i in range(0, len(entries), 100)]
    body = "".join(f"{len(chunk)} beginbfchar\n" + "\n".join(chunk) + "\nendbfchar\n" for chunk in chunks)
    return (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /MDARIX-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{body}endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    )


def _text(fonts, x: float, y: float, text: str, *, font: str = SANS, size: float = BODY_FONT_SIZE, gray=0) -> str:
    """One line: each segment in its own text object at its column; font changes inside a segment share it."""
    color = f"{' '.join(f'{c:.3f}' for c in gray)} rg" if isinstance(gray, tuple) else f"{gray:.2f} g"
    parts = []
    for offset, runs, _ in _layout(_visual(_clean(text)), font, size):
        shown = " ".join(f"/{name} {size} Tf {fonts.encode(name, chars)} Tj" for name, chars in runs)
        parts.append(f"BT {color} {x + offset:.1f} {y:.1f} Td {shown} ET\n")
    return "".join(parts)


def _page_stream(fonts, titles, header, lines, watermark, footers, page_label) -> bytes:
    top = PAGE_HEIGHT - MARGIN + 6
    brand_width = text_width(BRAND, SANS_BOLD, 8) + text_width(f"  {BRAND_LINE}", SANS, 7.5)
    parts = [
        _text(fonts, MARGIN, top, watermark, font=SANS_BOLD, size=8, gray=0.35),
        _text(fonts, PAGE_WIDTH - MARGIN - brand_width, top, BRAND, font=SANS_BOLD, size=8, gray=TEAL),
        _text(fonts, PAGE_WIDTH - MARGIN - text_width(BRAND_LINE, SANS, 7.5), top, BRAND_LINE, size=7.5, gray=0.45),
        f"{' '.join(f'{c:.3f}' for c in TEAL)} RG 0.6 w {MARGIN} {top - 4:.1f} m {PAGE_WIDTH - MARGIN} {top - 4:.1f} l S\n",
    ]
    y = HEADER_TOP
    for line in titles:
        parts.append(_text(fonts, MARGIN, y, line, font=SANS_BOLD, size=13))
        y -= 16
    for line in header:
        parts.append(_text(fonts, MARGIN, y, line, gray=0.25))
        y -= BODY_LEADING
    if header:
        y -= BODY_LEADING
    for text, style in lines:
        font, size, gray = STYLES.get(style, STYLES["body"])
        parts.append(_text(fonts, MARGIN, y, text, font=font, size=size, gray=gray))
        y -= BODY_LEADING
    for index, line in enumerate(footers):
        parts.append(_text(fonts, MARGIN, MARGIN - 4 - 9 * index, line, size=FOOTER_SIZE, gray=0.4))
    label_x = PAGE_WIDTH - MARGIN - text_width(page_label, SANS, FOOTER_SIZE)
    parts.append(_text(fonts, label_x, MARGIN - 4, page_label, size=FOOTER_SIZE, gray=0.4))
    return "".join(parts).encode("latin-1")


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


def text_of(pdf: bytes) -> str:
    """The text a PDF written here shows, read back through its fonts' ToUnicode maps: one line per text line, the
    segments of a line separated by a space. For tests, and for checking an exported file by hand."""
    objects = {int(n): body for n, body in re.findall(rb"(\d+) 0 obj\n(.*?)\nendobj\n", pdf, re.S)}

    def data(body: bytes) -> bytes:
        raw = body[body.index(b"stream\n") + 7 : body.rindex(b"\nendstream")]
        return zlib.decompress(raw) if b"/FlateDecode" in body[: body.index(b"stream\n")] else raw

    maps: dict[str, dict[int, str]] = {}
    page = next(body for body in objects.values() if body.startswith(b"<< /Type /Page "))
    for name, number in re.findall(rb"/(F\d) (\d+) 0 R", page):
        font = objects[int(number)]
        found = re.search(rb"/ToUnicode (\d+) 0 R", font)
        if found:
            cmap = data(objects[int(found.group(1))]).decode().split("endcodespacerange")[1]
            maps[name.decode()] = {
                int(cid, 16): bytes.fromhex(text).decode("utf-16-be")
                for cid, text in re.findall(r"<([0-9A-F]{4})> <([0-9A-F]+)>", cmap)
            }
    lines: list[str] = []
    for body in objects.values():
        if not body.startswith(b"<< /Length") or b"stream\n" not in body:
            continue
        content = data(body)
        if b" Tf " not in content[:200]:
            continue
        last_y = None
        for y, shown in re.findall(rb"BT [^T]*? ([\d.]+) Td (.*?) ET", content):
            text = ""
            for name, item in re.findall(rb"/(F\d) [\d.]+ Tf (<[0-9A-F]*>|\([^)]*\)) Tj", shown):
                if item.startswith(b"<"):
                    mapping = maps.get(name.decode(), {})
                    hexed = item[1:-1].decode()
                    text += "".join(mapping.get(int(hexed[i : i + 4], 16), "?") for i in range(0, len(hexed), 4))
                else:
                    text += item[1:-1].decode("latin-1")
            if y == last_y:
                lines[-1] += " " + text
            else:
                lines.append(text)
            last_y = y
    return "\n".join(lines)
