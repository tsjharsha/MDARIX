"""Reading the worksheets of an Excel workbook (.xlsx) as rows of text, with the standard library only.

An .xlsx file is a zip of XML parts. This reads the workbook's sheets (their names, which are hidden, its date system),
a sheet's rows, its shared strings and the number formats of its cell styles: text stays text, numbers are written
without a trailing ".0", TRUE/FALSE become Y/N, and a number shown as a date becomes YYYY-MM-DD, in the 1900 or the
1904 date system (so dates in a workbook never need a date-order choice). Formulas are read as their cached result. Guarded against oversized and malformed files: the zip's total uncompressed size, each part's size, its
compression ratio and its number of parts are checked before anything is unpacked; the worksheet and its shared
strings are read as a stream (each row leaves memory once read), and reading stops once the sheet holds more rows,
cells or elements than the import can take, so a small "zip bomb" never becomes millions of objects in memory. Every
XML part is parsed by ElementTree (which resolves no external entities), and a workbook with macros (.xlsm) is not
read.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from xml.etree import ElementTree

MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
MAX_PARTS = 2_000
MAX_COLUMNS = 200
# Small parts (workbook, relationships, styles) are read whole; no real workbook's come near this.
MAX_SMALL_PART_BYTES = 5 * 1024 * 1024
# A part over 1 MB unpacked that unpacks to more than this many times its packed size is refused: real worksheets
# pack 5 to 30 times, a bomb a thousand times.
MAX_COMPRESSION_RATIO = 100
RATIO_CHECKED_FROM_BYTES = 1024 * 1024
# Rows read past the caller's limit before reading stops, so a file just over it still gets its exact count.
ROW_MARGIN = 100
# XML elements one cell may hold (a value, an inline string, rich-text runs); elements read in all, per cell the
# sheet may have; how deep elements may nest. Far above any real sheet, far below what fills memory.
MAX_ELEMENTS_PER_CELL = 1_000
ELEMENTS_PER_CELL = 4
MAX_DEPTH = 64
TOO_LARGE = "The workbook is too large to read. Save the sheet as CSV UTF-8 and upload that."

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
# Built-in number formats that show a date (ECMA-376 18.8.30).
_BUILTIN_DATES = {14, 15, 16, 17, 22, 27, 30, 36, 45, 46, 47, 50, 57}
_CELL = re.compile(r"^([A-Z]{1,3})(\d+)$")
_EXCEL_EPOCH = date(1899, 12, 30)


class XlsxError(ValueError):
    """The workbook cannot be read; the message says why, for the uploader."""


def is_xlsx(raw: bytes) -> bool:
    return raw[:4] == b"PK\x03\x04"


def _column_index(letters: str) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - 64)
    return index - 1


def _date_format(code: str) -> bool:
    """A custom number format shows a date when it uses days, years or month names outside quotes and brackets
    (a time-only format such as h:mm does not)."""
    text = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", code.lower())
    return bool(re.search(r"[dy]", text)) or "mmm" in text


def _number(text: str) -> str:
    """A whole number without Excel's ".0"; any other number exactly as the workbook stores it."""
    try:
        value = float(text)
    except ValueError:
        return text
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return text


def _serial_date(text: str, epoch: date = _EXCEL_EPOCH) -> str | None:
    try:
        serial = float(text)
    except ValueError:
        return None
    if not 1 <= serial < 2958466:  # Excel's valid range, 1900-01-01 to 9999-12-31
        return None
    return (epoch + timedelta(days=int(serial))).isoformat()


def _unreadable() -> XlsxError:
    return XlsxError("The workbook could not be read. Save it again in Excel, or as CSV UTF-8.")


def _xml(archive: zipfile.ZipFile, name: str):
    """A small part (workbook, relationships, styles) read whole; None when the workbook has no such part."""
    try:
        if archive.getinfo(name).file_size > MAX_SMALL_PART_BYTES:
            raise XlsxError(TOO_LARGE)
        with archive.open(name) as part:
            return ElementTree.parse(part).getroot()
    except KeyError:
        return None
    except ElementTree.ParseError as exc:
        raise _unreadable() from exc


def _stream(archive: zipfile.ZipFile, name: str, max_elements: int, unit: str):
    """Each element of a part once it is read, as ``(element, inside)``: ``inside`` when it is part of a ``unit``
    element (a cell, a shared string) not read yet. Every other element is dropped from the tree once the caller has
    it, so memory holds about one row at a time. Refuses a part nested deeper than ``MAX_DEPTH`` or holding more than
    ``max_elements`` elements, or a unit of more than ``MAX_ELEMENTS_PER_CELL``."""
    try:
        part = archive.open(name)
    except KeyError:
        return
    stack: list = []
    seen = units = in_unit = 0
    with part:
        try:
            for event, element in ElementTree.iterparse(part, events=("start", "end")):
                if event == "start":
                    seen += 1
                    if seen > max_elements or len(stack) >= MAX_DEPTH:
                        raise XlsxError(TOO_LARGE)
                    stack.append(element)
                    if element.tag == unit:
                        units, in_unit = units + 1, 0
                    elif units:
                        in_unit += 1
                        if in_unit > MAX_ELEMENTS_PER_CELL:
                            raise XlsxError(TOO_LARGE)
                    continue
                stack.pop()
                if element.tag == unit:
                    units -= 1
                inside = units > 0
                yield element, inside
                if not inside and stack:
                    stack[-1].remove(element)
        except ElementTree.ParseError as exc:
            raise _unreadable() from exc


@dataclass(frozen=True)
class Sheet:
    """A worksheet of the workbook, in tab order: its name, its part in the zip and whether Excel hides it."""

    name: str
    part: str
    hidden: bool


def _sheets(archive: zipfile.ZipFile) -> tuple[list[Sheet], bool]:
    """The workbook's worksheets in tab order, and whether it counts dates from 1904 (Excel for Mac's old default)."""
    workbook = _xml(archive, "xl/workbook.xml")
    rels = _xml(archive, "xl/_rels/workbook.xml.rels")
    if workbook is None or rels is None:
        raise XlsxError("This is not an Excel workbook (.xlsx). Upload the export as .xlsx or CSV UTF-8.")
    targets = {}
    for rel in rels.findall("rel:Relationship", _NS):
        target = rel.get("Target", "").lstrip("/")
        targets[rel.get("Id")] = target if target.startswith("xl/") else f"xl/{target}"
    sheets = [
        Sheet(
            name=sheet.get("name", ""),
            part=targets.get(sheet.get(f"{{{_NS['r']}}}id"), ""),
            hidden=sheet.get("state", "visible") in ("hidden", "veryHidden"),
        )
        for sheet in workbook.findall("m:sheets/m:sheet", _NS)
    ]
    if not sheets:
        raise XlsxError("The workbook has no worksheet.")
    settings = workbook.find("m:workbookPr", _NS)
    date1904 = settings is not None and settings.get("date1904", "").lower() in ("1", "true")
    return sheets, date1904


def _date_styles(archive: zipfile.ZipFile) -> set[int]:
    """The indexes of the cell styles whose number format shows a date."""
    styles = _xml(archive, "xl/styles.xml")
    if styles is None:
        return set()
    custom = {
        int(item.get("numFmtId", "0")): item.get("formatCode", "") for item in styles.findall("m:numFmts/m:numFmt", _NS)
    }
    dated = set()
    for index, xf in enumerate(styles.findall("m:cellXfs/m:xf", _NS)):
        fmt = int(xf.get("numFmtId", "0"))
        if fmt in _BUILTIN_DATES or (fmt in custom and _date_format(custom[fmt])):
            dated.add(index)
    return dated


_TAG_SI = f"{{{_NS['m']}}}si"
_TAG_T = f"{{{_NS['m']}}}t"
_TAG_ROW = f"{{{_NS['m']}}}row"
_TAG_C = f"{{{_NS['m']}}}c"


def _shared_strings(archive: zipfile.ZipFile, max_strings: int) -> list[str]:
    """The shared strings, read as a stream: at most ``max_strings`` (no sheet the import takes needs more)."""
    strings: list[str] = []
    for element, _inside in _stream(archive, "xl/sharedStrings.xml", max_strings * ELEMENTS_PER_CELL, _TAG_SI):
        if element.tag != _TAG_SI:
            continue
        if len(strings) >= max_strings:
            raise XlsxError(TOO_LARGE)
        strings.append("".join(node.text or "" for node in element.iter(_TAG_T)))
    return strings


def _check_sizes(parts: list[zipfile.ZipInfo], max_bytes: int) -> None:
    """Refuse a workbook before anything is unpacked: too many parts, too large unpacked, or packed like a bomb."""
    if len(parts) > MAX_PARTS or sum(part.file_size for part in parts) > max_bytes:
        raise XlsxError(TOO_LARGE)
    for part in parts:
        ratio = part.file_size / max(1, part.compress_size)
        if part.file_size > RATIO_CHECKED_FROM_BYTES and ratio > MAX_COMPRESSION_RATIO:
            raise XlsxError(TOO_LARGE)


def _cell_text(cell, strings: list[str], dated: set[int], epoch: date = _EXCEL_EPOCH) -> str:
    kind = cell.get("t", "n")
    value_node = cell.find("m:v", _NS)
    raw_value = value_node.text if value_node is not None and value_node.text is not None else ""
    if kind == "s":
        return strings[int(raw_value)] if raw_value.isdigit() and int(raw_value) < len(strings) else ""
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(_TAG_T))
    if kind == "b":
        return "Y" if raw_value == "1" else "N" if raw_value == "0" else ""
    if kind in ("str", "e"):
        return raw_value if kind == "str" else ""
    if raw_value:
        style = int(cell.get("s", "0") or 0) if str(cell.get("s", "0") or 0).isdigit() else 0
        return (_serial_date(raw_value, epoch) if style in dated else None) or _number(raw_value)
    return ""


def too_many_rows(max_rows: int) -> str:
    return (
        f"The sheet has more than {max_rows:,} rows, more than one import can take. Split it into smaller files, or "
        "remove the rows you do not need, and upload again."
    )


class Workbook:
    """An opened workbook: its sheets in tab order (hidden ones marked), its date system, and each sheet's rows on
    request. The size, compression and macro checks run when it is opened, before anything is unpacked.

    ``max_rows`` is the most data rows the caller takes: reading a sheet stops, and the workbook is refused, once it
    has ``ROW_MARGIN`` more rows than that (a file just over the limit is still read and counted). ``max_bytes`` caps
    the workbook's total unpacked size further than ``MAX_UNCOMPRESSED_BYTES``."""

    def __init__(self, raw: bytes, *, max_rows: int | None = None, max_bytes: int | None = None) -> None:
        try:
            self._archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise XlsxError("The file could not be opened as an Excel workbook (.xlsx).") from exc
        parts = self._archive.infolist()
        _check_sizes(parts, MAX_UNCOMPRESSED_BYTES if max_bytes is None else min(max_bytes, MAX_UNCOMPRESSED_BYTES))
        if any(part.filename == "xl/vbaProject.bin" for part in parts):
            raise XlsxError("Workbooks with macros are not read. Save it as .xlsx without macros, or as CSV UTF-8.")
        self.sheets, self.date1904 = _sheets(self._archive)
        # The day Excel's day numbers count from: 1899-12-30, or 1904-01-01 in the 1904 date system (J41).
        self.epoch = date(1904, 1, 1) if self.date1904 else _EXCEL_EPOCH
        self.max_rows = max_rows
        # The header row, the data rows the caller takes and the margin.
        self.row_cap = 1 + (max_rows if max_rows is not None else 1_000_000) + ROW_MARGIN
        self._cell_cap = self.row_cap * MAX_COLUMNS
        self._strings: list[str] | None = None
        self._dated = _date_styles(self._archive)

    def close(self) -> None:
        self._archive.close()

    def __enter__(self) -> "Workbook":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def rows(self, sheet: Sheet, stop_after: int | None = None) -> list[list[str]]:
        """The sheet's rows as lists of text (empty cells as ""): ``rows[n - 1]`` is the sheet's row n, so a row
        number said back is the one Excel shows (empty rows are kept as []; empty rows at the end are not).
        ``stop_after`` stops after that many rows (to look at the first rows only)."""
        if sheet.part not in self._archive.namelist():
            raise XlsxError(f"The worksheet '{sheet.name}' could not be read.")
        if self._strings is None:
            self._strings = _shared_strings(self._archive, self._cell_cap)
        rows: list[list[str]] = []
        cells: dict[int, str] = {}
        number = 0
        for element, _inside in _stream(self._archive, sheet.part, self._cell_cap * ELEMENTS_PER_CELL, _TAG_C):
            if element.tag == _TAG_C:
                match = _CELL.match(element.get("r", ""))
                column = _column_index(match.group(1)) if match else len(cells)
                if column < MAX_COLUMNS:
                    cells[column] = _cell_text(element, self._strings, self._dated, self.epoch).strip()
            elif element.tag == _TAG_ROW:
                stated = element.get("r", "")
                number = int(stated) if stated.isdigit() else number + 1
                if any(cells.values()):
                    if number - 1 > self.row_cap:
                        raise XlsxError(too_many_rows(self.max_rows) if self.max_rows is not None else TOO_LARGE)
                    rows.extend([] for _ in range(number - 1 - len(rows)))
                    width = max(cells) + 1
                    rows.append([cells.get(index, "") for index in range(width)])
                    if len(rows) > self.row_cap:
                        raise XlsxError(too_many_rows(self.max_rows) if self.max_rows is not None else TOO_LARGE)
                    if stop_after is not None and len(rows) >= stop_after:
                        break
                cells = {}
        return rows

    def sheet(self, name: str | None = None) -> Sheet:
        """The sheet called ``name`` (any case), or the first sheet when None."""
        if name is None:
            return self.sheets[0]
        for sheet in self.sheets:
            if sheet.name.strip().lower() == name.strip().lower():
                return sheet
        names = ", ".join(f"'{sheet.name}'" for sheet in self.sheets if not sheet.hidden)
        raise XlsxError(f"The workbook has no sheet called '{name}'. Its sheets: {names}.")


def read_rows(
    raw: bytes, *, max_rows: int | None = None, max_bytes: int | None = None, sheet: str | None = None
) -> list[list[str]]:
    """One worksheet's rows (``Workbook.rows``): the sheet called ``sheet``, else the first. Raises XlsxError."""
    with Workbook(raw, max_rows=max_rows, max_bytes=max_bytes) as book:
        return book.rows(book.sheet(sheet))
