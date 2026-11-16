"""B6b B5: a small standard-library XLSX writer (owner decision B6b-D12) for the validation pack.

One sheet per table; the first row is the header (bold); text and numbers only. Every text cell is an inline string,
so a value that starts with "=" stays text and is never a formula. The zip entries carry a fixed date, so the same
tables give byte-identical files (B6-51)."""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

_FIXED_DATE = (1980, 1, 1, 0, 0, 0)
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _column(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _cell(ref: str, value, header: bool) -> str:
    style = ' s="1"' if header else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(_BAD_XML.sub("", "" if value is None else str(value)))
    return f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet(rows: list[list]) -> str:
    body = "".join(
        f'<row r="{r + 1}">' + "".join(_cell(f"{_column(c)}{r + 1}", v, r == 0) for c, v in enumerate(row)) + "</row>"
        for r, row in enumerate(rows)
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{_MAIN}"><sheetData>{body}</sheetData></worksheet>'


def write(sheets: dict[str, list[list]]) -> bytes:
    """The workbook as bytes: ``sheets`` maps a sheet name (at most 31 characters) to its rows, header first."""
    names = list(sheets)
    if not names:
        raise ValueError("A workbook needs at least one sheet.")
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(len(names))
            )
            + "</Types>"
        ),
        "_rels/.rels": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{_PKG}">'
            f'<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{_MAIN}" xmlns:r="{_REL}"><sheets>'
            + "".join(
                f'<sheet name="{escape(name[:31])}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                for i, name in enumerate(names)
            )
            + "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{_PKG}">'
            + "".join(
                f'<Relationship Id="rId{i + 1}" Type="{_REL}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                for i in range(len(names))
            )
            + f'<Relationship Id="rId{len(names) + 1}" Type="{_REL}/styles" Target="styles.xml"/></Relationships>'
        ),
        "xl/styles.xml": (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{_MAIN}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="2"><xf fontId="0"/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>'
        ),
    }
    for i, name in enumerate(names):
        parts[f"xl/worksheets/sheet{i + 1}.xml"] = _sheet(sheets[name])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, xml in parts.items():
            info = zipfile.ZipInfo(name, _FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, xml.encode("utf-8"))
    return buffer.getvalue()
