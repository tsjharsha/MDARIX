"""Just enough TrueType for the PDF writer: a font's character map, glyph widths and metrics, and a subset that keeps
only the glyphs a document uses (glyph numbers unchanged, so the PDF can address glyphs by number).

No dependency: the fonts are the vendored files in reports/fonts (SIL Open Font License, licence files beside them).
"""

from __future__ import annotations

import struct
from functools import lru_cache
from pathlib import Path

FONT_DIR = Path(__file__).with_name("fonts")

# Tables a TrueType font program embedded in a PDF needs (PDF 32000-1, 9.9); the rest (layout, names) is dropped.
KEPT_TABLES = (b"head", b"hhea", b"maxp", b"hmtx", b"loca", b"glyf", b"cvt ", b"fpgm", b"prep")


class Font:
    def __init__(self, path: Path):
        self.name = path.stem
        self.data = path.read_bytes()
        count = struct.unpack(">H", self.data[4:6])[0]
        self.tables: dict[bytes, tuple[int, int]] = {}
        for index in range(count):
            tag, _check, offset, length = struct.unpack(">4sIII", self.data[12 + 16 * index : 28 + 16 * index])
            self.tables[tag] = (offset, length)
        head = self._table(b"head")
        self.units = struct.unpack(">H", head[18:20])[0]
        self.bbox = struct.unpack(">hhhh", head[36:44])
        self.long_loca = struct.unpack(">h", head[50:52])[0] == 1
        hhea = self._table(b"hhea")
        self.ascent, self.descent = struct.unpack(">hh", hhea[4:8])
        metrics = struct.unpack(">H", hhea[34:36])[0]
        self.glyphs = struct.unpack(">H", self._table(b"maxp")[4:6])[0]
        hmtx = self._table(b"hmtx")
        widths = [struct.unpack(">H", hmtx[4 * i : 4 * i + 2])[0] for i in range(metrics)]
        self.widths = widths + [widths[-1]] * (self.glyphs - metrics)
        os2 = self._table(b"OS/2")
        self.cap_height = struct.unpack(">h", os2[88:90])[0] if len(os2) >= 90 else self.ascent
        self.cmap = _cmap(self._table(b"cmap"))

    def _table(self, tag: bytes) -> bytes:
        offset, length = self.tables[tag]
        return self.data[offset : offset + length]

    def glyph(self, char: str) -> int | None:
        return self.cmap.get(ord(char))

    def advance(self, gid: int, size: float) -> float:
        """The glyph's width in points at this size."""
        return self.widths[gid] * size / self.units

    def pdf_width(self, gid: int) -> int:
        """The glyph's width in the PDF's thousandths of an em."""
        return round(self.widths[gid] * 1000 / self.units)

    def subset(self, used: set[int]) -> bytes:
        """The font program with only these glyphs' outlines (and the parts of composite glyphs they use)."""
        glyf, loca = self._table(b"glyf"), self._table(b"loca")
        offsets = (
            struct.unpack(f">{self.glyphs + 1}I", loca[: 4 * (self.glyphs + 1)])
            if self.long_loca
            else [2 * value for value in struct.unpack(f">{self.glyphs + 1}H", loca[: 2 * (self.glyphs + 1)])]
        )
        keep, todo = set(), {0, *used}
        while todo:
            gid = todo.pop()
            if gid in keep or gid >= self.glyphs:
                continue
            keep.add(gid)
            todo |= _components(glyf[offsets[gid] : offsets[gid + 1]])
        out, new_loca = bytearray(), []
        for gid in range(self.glyphs):
            new_loca.append(len(out))
            if gid in keep:
                out += glyf[offsets[gid] : offsets[gid + 1]]
                out += b"\0" * (-len(out) % 4)
        new_loca.append(len(out))
        head = bytearray(self._table(b"head"))
        head[8:12] = b"\0\0\0\0"  # checkSumAdjustment, set below
        head[50:52] = struct.pack(">h", 1)  # long loca offsets
        tables = {tag: self._table(tag) for tag in KEPT_TABLES if tag in self.tables}
        tables.update({b"glyf": bytes(out), b"loca": struct.pack(f">{len(new_loca)}I", *new_loca), b"head": head})
        program = _sfnt(tables)
        adjustment = (0xB1B0AFBA - _checksum(program)) & 0xFFFFFFFF
        head_at = program.index(bytes(head[:8]) + b"\0\0\0\0")
        return program[: head_at + 8] + struct.pack(">I", adjustment) + program[head_at + 12 :]


def _components(glyph: bytes) -> set[int]:
    """The glyphs a composite glyph is built from (none for a simple glyph)."""
    if len(glyph) < 10 or struct.unpack(">h", glyph[:2])[0] >= 0:
        return set()
    found, at = set(), 10
    while True:
        flags, gid = struct.unpack(">HH", glyph[at : at + 4])
        found.add(gid)
        at += 4 + (4 if flags & 0x0001 else 2)
        at += 8 if flags & 0x0080 else 4 if flags & 0x0040 else 2 if flags & 0x0008 else 0
        if not flags & 0x0020:
            return found


def _cmap(table: bytes) -> dict[int, int]:
    """Unicode code point -> glyph number, from the format 12 (full Unicode) or format 4 (BMP) subtable."""
    count = struct.unpack(">H", table[2:4])[0]
    records = [struct.unpack(">HHI", table[4 + 8 * i : 12 + 8 * i]) for i in range(count)]
    by_kind = {(platform, encoding): offset for platform, encoding, offset in records}
    full = by_kind.get((3, 10)) or by_kind.get((0, 4))
    if full is not None and struct.unpack(">H", table[full : full + 2])[0] == 12:
        groups = struct.unpack(">I", table[full + 12 : full + 16])[0]
        mapping = {}
        for index in range(groups):
            start, end, gid = struct.unpack(">III", table[full + 16 + 12 * index : full + 28 + 12 * index])
            mapping.update({code: gid + code - start for code in range(start, end + 1)})
        return mapping
    offset = by_kind.get((3, 1)) or by_kind.get((0, 3))
    segments = struct.unpack(">H", table[offset + 6 : offset + 8])[0] // 2
    ends_at = offset + 14
    ends = struct.unpack(f">{segments}H", table[ends_at : ends_at + 2 * segments])
    starts_at = ends_at + 2 * segments + 2
    starts = struct.unpack(f">{segments}H", table[starts_at : starts_at + 2 * segments])
    deltas_at = starts_at + 2 * segments
    deltas = struct.unpack(f">{segments}h", table[deltas_at : deltas_at + 2 * segments])
    ranges_at = deltas_at + 2 * segments
    ranges = struct.unpack(f">{segments}H", table[ranges_at : ranges_at + 2 * segments])
    mapping = {}
    for index in range(segments):
        for code in range(starts[index], ends[index] + 1):
            if code == 0xFFFF:
                continue
            if ranges[index] == 0:
                gid = (code + deltas[index]) & 0xFFFF
            else:
                at = ranges_at + 2 * index + ranges[index] + 2 * (code - starts[index])
                gid = struct.unpack(">H", table[at : at + 2])[0]
                gid = (gid + deltas[index]) & 0xFFFF if gid else 0
            if gid:
                mapping[code] = gid
    return mapping


def _checksum(data: bytes) -> int:
    data = data + b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


def _sfnt(tables: dict[bytes, bytes]) -> tuple[bytes, dict[bytes, int]]:
    tags = sorted(tables)
    count = len(tags)
    power = 1 << (count.bit_length() - 1)
    header = struct.pack(">IHHHH", 0x00010000, count, power * 16, power.bit_length() - 1, count * 16 - power * 16)
    offset = 12 + 16 * count
    directory, body = bytearray(), bytearray()
    for tag in tags:
        data = bytes(tables[tag])
        directory += struct.pack(">4sIII", tag, _checksum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return header + bytes(directory) + bytes(body)


@lru_cache(maxsize=None)
def load(file_name: str) -> Font:
    return Font(FONT_DIR / file_name)
