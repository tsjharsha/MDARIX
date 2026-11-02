"""Writes the synthetic Indian complaint register used by tests/test_indian_register_import.py (stage 4, "Your Excel
just works"): every name in it is fictional and marked "(Sample)".

    python tests/fixtures/indian_register/make_register.py

- ``indian_register.xlsx``: a hidden first sheet "Lists" (the drop-down values), the complaints on sheet 2
  "Complaint Register" below a title row and a blank row, and the batches on sheet 3 "Batch Register". Dates as
  Excel dates shown DD/MM/YYYY and as typed text, a software version "1.4.2+build", a kit with two lots on two rows,
  "India, Germany" in one country cell, and the batch quantities "1,25,000" and "1250,00".
- ``indian_register_complaints.csv``: the same complaints as Excel's plain "CSV" saves them on Windows (Windows-1252,
  no byte-order mark, so "Cathéter" is the byte E9), title and blank row included.
- ``indian_register_batches.csv``: the batches as UTF-8 without a byte-order mark.

Only the standard library is used, so the files can be written again anywhere.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
HIDDEN = ' state="hidden"'
TITLE = "Customer Complaint Register FY 2026-27 - Medisynth Devices (Sample) Pvt. Ltd."
COMPLAINT_HEADERS = [
    "Sr. No.",
    "Complaint No.",
    "Date of Complaint",
    "Complaint Received Date",
    "Event Date (DD/MM/YYYY)",
    "Product Name",
    "Model",
    "SW Version",
    "Batch/Lot No.",
    "Serial No.",
    "Death (Y/N)",
    "Serious Injury (Y/N)",
    "Malfunction Y/N",
    "Country",
    "Description",
    "Status",
]
# Date of Complaint is an Excel date (a date object) in the workbook and typed DD/MM/YYYY in the CSV.
COMPLAINTS = [
    [
        "1",
        "MSD/CC/26/001",
        date(2026, 8, 14),
        "16/08/2026",
        "12/08/2026",
        "Pulse Oximeter PX-20 (Sample)",
        "PX-20",
        "1.4.2+build",
        "B2607-11",
        "PX20-0012345",
        "N",
        "N",
        "Y",
        "India",
        "SpO2 reading 5 points higher than the ward monitor during a routine check.",
        "Open",
    ],
    [
        "2",
        "MSD/CC/26/002",
        date(2026, 9, 3),
        "04/09/2026",
        "01/09/2026",
        "Infusion Set Kit IK-5 (Sample)",
        "IK-5",
        "",
        "K2606-03",
        "",
        "No",
        "Yes",
        "1",
        "India, Germany",
        "Leak at the luer connector of the kit; the extension line came from a second lot.",
        "Under Investigation",
    ],
    # The kit's second lot, on a row of its own (the same complaint number).
    [
        "3",
        "MSD/CC/26/002",
        "",
        "",
        "",
        "Infusion Set Kit IK-5 (Sample)",
        "IK-5",
        "",
        "K2606-07",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ],
    [
        "4",
        "MSD/CC/26/003",
        date(2026, 10, 21),
        "22/10/2026",
        "20/10/2026",
        "Cathéter Guide CG-2 (Sample)",
        "CG-2",
        "",
        "C2605-19",
        "",
        "0",
        "NA",
        "Yes",
        "Germany",
        "Cathéter tip kinked during insertion; replaced, no harm to the patient.",
        "Closed",
    ],
]
BATCH_HEADERS = ["Batch No.", "Model", "SW Version", "Mfg. Date", "Expiry Date", "Batch Qty"]
BATCHES = [
    ["B2607-11", "PX-20", "1.4.2+build", date(2026, 7, 1), "30/06/2031", "1,25,000"],
    ["B2608-02", "PX-20", "1.4.2+build", date(2026, 8, 5), "04/08/2031", "1250,00"],
]
LISTS = [["Yes/No"], ["Y"], ["N"], ["Status"], ["Open"], ["Under Investigation"], ["Closed"]]


def _text(value) -> str:
    return value.strftime("%d/%m/%Y") if isinstance(value, date) else str(value)


def _csv(headers: list[str], rows: list[list], encoding: str) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([TITLE] + [""] * (len(headers) - 1))
    writer.writerow([""] * len(headers))
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_text(value) for value in row])
    return out.getvalue().encode(encoding)


def _sheet(rows: list[list], strings: list[str]) -> str:
    """A worksheet: row numbers as Excel writes them (a blank row has no element), text as shared strings, a date
    as its day number with style 1 (dd/mm/yyyy)."""
    xml = []
    for number, row in enumerate(rows, 1):
        cells = []
        for index, value in enumerate(row):
            ref = f"{chr(65 + index)}{number}"
            if isinstance(value, date):
                cells.append(f'<c r="{ref}" s="1"><v>{(value - date(1899, 12, 30)).days}</v></c>')
            elif value in ("", None):
                continue
            else:
                if value not in strings:
                    strings.append(value)
                cells.append(f'<c r="{ref}" t="s"><v>{strings.index(value)}</v></c>')
        if cells:
            xml.append(f'<row r="{number}">{"".join(cells)}</row>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    return f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{main}"><sheetData>{"".join(xml)}</sheetData></worksheet>'


def workbook() -> bytes:
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    strings: list[str] = []
    sheets = [
        ("Lists", _sheet(LISTS, strings), True),
        ("Complaint Register", _sheet([[TITLE], [], COMPLAINT_HEADERS, *COMPLAINTS], strings), False),
        ("Batch Register", _sheet([["Batch Register (Sample)"], [], BATCH_HEADERS, *BATCHES], strings), False),
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{n}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for n in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            + "".join(
                f'<sheet name="{escape(name)}" sheetId="{n}"{HIDDEN if hidden else ""} r:id="rId{n}"/>'
                for n, (name, _xml, hidden) in enumerate(sheets, 1)
            )
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{n}" Target="worksheets/sheet{n}.xml" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
                for n in range(1, len(sheets) + 1)
            )
            + f'<Relationship Id="rId{len(sheets) + 1}" Target="styles.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"/>'
            f'<Relationship Id="rId{len(sheets) + 2}" Target="sharedStrings.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings"/>'
            "</Relationships>",
        )
        for n, (_name, xml, _hidden) in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{n}.xml", xml)
        archive.writestr(
            "xl/styles.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="{main}">'
            '<numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts>'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
            "</styleSheet>",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{main}" count="{len(strings)}" uniqueCount="{len(strings)}">'
            + "".join(f"<si><t>{escape(text)}</t></si>" for text in strings)
            + "</sst>",
        )
    return out.getvalue()


def main() -> None:
    (HERE / "indian_register.xlsx").write_bytes(workbook())
    (HERE / "indian_register_complaints.csv").write_bytes(_csv(COMPLAINT_HEADERS, COMPLAINTS, "cp1252"))
    (HERE / "indian_register_batches.csv").write_bytes(_csv(BATCH_HEADERS, BATCHES, "utf-8"))


if __name__ == "__main__":
    main()
