"""Reading the first worksheet of an Excel workbook (.xlsx) as rows of text, with the standard library only.

An .xlsx file is a zip of XML parts. This reads the workbook's first sheet, its shared strings and the number formats
of its cell styles: text stays text, numbers are written without a trailing ".0", TRUE/FALSE become Y/N, and a number
shown as a date becomes YYYY-MM-DD (so dates in a workbook never need a date-order choice). Formulas are read as their
cached result. Guarded against oversized and malformed files: the zip's total uncompressed size and its number of
parts are capped, every XML part is parsed by ElementTree (which resolves no external entities), and a workbook with
macros (.xlsm) is not read.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree

MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
MAX_PARTS = 2_000
MAX_COLUMNS = 200

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


def _serial_date(text: str) -> str | None:
    try:
        serial = float(text)
    except ValueError:
        return None
    if not 1 <= serial < 2958466:  # Excel's valid range, 1900-01-01 to 9999-12-31
        return None
    return (_EXCEL_EPOCH + timedelta(days=int(serial))).isoformat()


def _xml(archive: zipfile.ZipFile, name: str):
    try:
        with archive.open(name) as part:
            return ElementTree.parse(part).getroot()
    except KeyError:
        return None
    except ElementTree.ParseError as exc:
        raise XlsxError("The workbook could not be read. Save it again in Excel, or as CSV UTF-8.") from exc


def _first_sheet(archive: zipfile.ZipFile) -> str:
    workbook = _xml(archive, "xl/workbook.xml")
    rels = _xml(archive, "xl/_rels/workbook.xml.rels")
    if workbook is None or rels is None:
        raise XlsxError("This is not an Excel workbook (.xlsx). Upload the export as .xlsx or CSV UTF-8.")
    sheet = workbook.find("m:sheets/m:sheet", _NS)
    if sheet is None:
        raise XlsxError("The workbook has no worksheet.")
    rel_id = sheet.get(f"{{{_NS['r']}}}id")
    for rel in rels.findall("rel:Relationship", _NS):
        if rel.get("Id") == rel_id:
            target = rel.get("Target", "").lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise XlsxError("The workbook's first worksheet could not be found.")


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


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = _xml(archive, "xl/sharedStrings.xml")
    if root is None:
        return []
    return ["".join(node.text or "" for node in item.iter(f"{{{_NS['m']}}}t")) for item in root.findall("m:si", _NS)]


def read_rows(raw: bytes) -> list[list[str]]:
    """The first worksheet's rows as lists of text (empty cells as ""), in sheet order. Raises XlsxError."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise XlsxError("The file could not be opened as an Excel workbook (.xlsx).") from exc
    with archive:
        parts = archive.infolist()
        if len(parts) > MAX_PARTS or sum(part.file_size for part in parts) > MAX_UNCOMPRESSED_BYTES:
            raise XlsxError("The workbook is too large to read. Save the sheet as CSV UTF-8 and upload that.")
        if any(part.filename == "xl/vbaProject.bin" for part in parts):
            raise XlsxError("Workbooks with macros are not read. Save it as .xlsx without macros, or as CSV UTF-8.")
        sheet_name = _first_sheet(archive)
        strings = _shared_strings(archive)
        dated = _date_styles(archive)
        sheet = _xml(archive, sheet_name)
        if sheet is None:
            raise XlsxError("The workbook's first worksheet could not be read.")
    rows: list[list[str]] = []
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        cells: dict[int, str] = {}
        for cell in row.findall("m:c", _NS):
            match = _CELL.match(cell.get("r", ""))
            column = _column_index(match.group(1)) if match else len(cells)
            if column >= MAX_COLUMNS:
                continue
            kind = cell.get("t", "n")
            value_node = cell.find("m:v", _NS)
            raw_value = value_node.text if value_node is not None and value_node.text is not None else ""
            if kind == "s":
                text = strings[int(raw_value)] if raw_value.isdigit() and int(raw_value) < len(strings) else ""
            elif kind == "inlineStr":
                text = "".join(node.text or "" for node in cell.iter(f"{{{_NS['m']}}}t"))
            elif kind == "b":
                text = "Y" if raw_value == "1" else "N" if raw_value == "0" else ""
            elif kind in ("str", "e"):
                text = raw_value if kind == "str" else ""
            elif raw_value:
                style = int(cell.get("s", "0") or 0)
                text = (_serial_date(raw_value) if style in dated else None) or _number(raw_value)
            else:
                text = ""
            cells[column] = text.strip()
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(index, "") for index in range(width)])
    return rows
