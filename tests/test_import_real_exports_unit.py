"""Uploading a quality system's export as it comes (backend/app/trial/columns.py, xlsx.py, imports.py), without a
database: its headers matched to the template, columns the template does not know left out, Excel workbooks read,
the quality system's own complaint status kept."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from backend.app.trial import columns, imports, xlsx

TRACKWISE = [
    "Complaint Number",
    "Product Code",
    "Product Name",
    "Complaint Description",
    "Lot #",
    "Date Received",
    "Awareness Date",
    "State",
    "Country of Occurrence",
    "Patient Name",
    "Serious Injury",
]


def _template(entity: str) -> list[str]:
    spec = imports.TEMPLATES[entity]
    return spec["required"] + spec["optional"]


def test_a_trackwise_export_reads_its_headers_and_leaves_out_what_it_does_not_know():
    matched = columns.match("complaints", TRACKWISE, _template("complaints"))
    assert matched["fields"] == [
        "complaint_id",
        "product_id",
        "product_name",
        "description",
        "lot_id",
        "received_date",
        "awareness_date",
        "status",
        "country",
        None,
        "serious_injury",
    ]
    # A column the template does not know (here a person's name) is left out and said back; never stored.
    assert matched["ignored"] == ["Patient Name"]
    assert {"header": "Lot #", "column": "lot_id"} in matched["mapping"]


def test_the_template_name_wins_and_a_second_column_for_the_same_field_is_left_out():
    matched = columns.match("complaints", ["Short Description", "description", "complaint_id"], _template("complaints"))
    assert matched["fields"] == [None, "description", "complaint_id"]
    assert matched["duplicates"] == [{"header": "Short Description", "column": "description", "kept": "description"}]
    # Matching is per template: "description" is a risk's description in a risks file.
    assert columns.match("risks", ["Hazard Description"], _template("risks"))["fields"] == ["description"]


def test_a_missing_required_column_names_what_it_is_usually_called():
    report = imports._Report()
    rows = imports._parse(
        "complaints", b"Product Code,Complaint Description\nP-1,Alarm\n", report, imports.TRIAL_POLICY
    )
    assert rows == []
    message = report.issues[0]["message"]
    assert "'complaint_id'" in message and "Complaint Id" in message


def test_the_quality_systems_own_status_is_kept_for_the_second_look():
    report = imports._Report()
    header = b"Complaint Number,Product Code,Complaint Description,Status\n"
    rows = imports._parse(
        "complaints", header + b"C-1,P-1,Alarm,Closed - No Action\nC-2,P-1,Alarm,Void\n", report, imports.TRIAL_POLICY
    )
    imports._check_values("complaints", rows, report)
    assert report.error_count == 0, report.issues
    assert [row["status"] for _, row in rows] == ["Closed - No Action", "Void"]
    too_long = imports._Report()
    rows = imports._parse("complaints", header + b"C-3,P-1,Alarm," + b"x" * 41 + b"\n", too_long, imports.TRIAL_POLICY)
    imports._check_values("complaints", rows, too_long)
    assert "under 40 characters" in too_long.issues[0]["message"]


# ------------------------------------------------------------------------------------------- Excel workbooks


def _workbook(rows: list[list], *, macros: bool = False) -> bytes:
    """A minimal .xlsx: shared strings for text, style 1 shows a date (built-in format 14)."""
    strings: list[str] = []
    cells_xml = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if isinstance(value, bool):
                cells.append(f'<c r="{ref}" t="b"><v>{int(value)}</v></c>')
            elif isinstance(value, date):
                serial = (value - date(1899, 12, 30)).days
                cells.append(f'<c r="{ref}" s="1"><v>{serial}</v></c>')
            elif isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif value is None:
                continue
            else:
                strings.append(str(value))
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        cells_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets><sheet name="Export" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{main}">' + "".join(f"<si><t>{text}</t></si>" for text in strings) + "</sst>",
        )
        archive.writestr(
            "xl/styles.xml",
            f'<styleSheet xmlns="{main}"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{main}"><sheetData>{"".join(cells_xml)}</sheetData></worksheet>',
        )
        if macros:
            archive.writestr("xl/vbaProject.bin", b"\x00")
    return out.getvalue()


def test_an_excel_export_is_read_with_its_dates_numbers_and_yes_no():
    raw = _workbook(
        [
            ["Complaint Number", "Product Code", "Complaint Description", "Date Received", "Serious Injury", "Units"],
            ["C-100", "P-9", "Alarm during infusion", date(2026, 3, 4), True, 250.0],
            ["C-101", "P-9", "Display froze", date(2026, 3, 5), False, 3],
        ]
    )
    assert xlsx.is_xlsx(raw)
    assert xlsx.read_rows(raw)[1] == ["C-100", "P-9", "Alarm during infusion", "2026-03-04", "Y", "250"]
    report = imports._Report()
    rows = imports._parse("complaints", raw, report, imports.TRIAL_POLICY)
    assert report.error_count == 0, report.issues
    assert rows[0][1]["received_date"] == "2026-03-04" and rows[1][1]["serious_injury"] == "N"
    assert "Excel workbook" in report.notes[0] and report.ignored == ["Units"]


def test_a_workbook_with_macros_or_too_large_is_not_read(monkeypatch):
    with pytest.raises(xlsx.XlsxError, match="macros"):
        xlsx.read_rows(_workbook([["a"]], macros=True))
    monkeypatch.setattr(xlsx, "MAX_UNCOMPRESSED_BYTES", 10)
    report = imports._Report()
    assert imports._parse("complaints", _workbook([["a"]]), report, imports.TRIAL_POLICY) == []
    assert "too large" in report.issues[0]["message"]
    with pytest.raises(xlsx.XlsxError):
        xlsx.read_rows(b"PK\x03\x04 not really a zip")


def test_custom_date_formats_are_recognized_and_times_alone_are_not():
    assert xlsx._date_format("dd/mm/yyyy") and xlsx._date_format('d "of" mmm yy') and xlsx._date_format("mmm-yy")
    assert not xlsx._date_format("h:mm:ss") and not xlsx._date_format("#,##0.00") and not xlsx._date_format("General")


# ------------------------------------------------------------------------------------- oversized workbooks (SEC-02)


def _bomb(megabytes: int, unit: bytes = b"<c/>", *, rows_wrapped: bool = False) -> bytes:
    """A workbook of a few kilobytes whose sheet unpacks to ``megabytes`` of tiny elements (a "zip bomb")."""
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    head = f'<?xml version="1.0"?><worksheet xmlns="{main}"><sheetData>'.encode()
    tail = b"</sheetData></worksheet>"
    if rows_wrapped:
        unit = b"<row>" + unit + b"</row>"
    count = (megabytes * 1024 * 1024 - len(head) - len(tail)) // len(unit)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
        )
        with archive.open("xl/worksheets/sheet1.xml", "w") as part:
            part.write(head)
            chunk = unit * 100_000
            for _ in range(count // 100_000):
                part.write(chunk)
            part.write(unit * (count % 100_000))
            part.write(tail)
    return out.getvalue()


def _peak_megabytes(action) -> float:
    import tracemalloc

    tracemalloc.start()
    try:
        action()
    finally:
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return peak / (1024 * 1024)


def test_a_small_workbook_that_unpacks_to_60_mb_is_refused_before_it_is_unpacked():
    raw = _bomb(59)
    assert len(raw) < 200_000  # the review's bomb was 60 KB
    report = imports._Report()
    peak = _peak_megabytes(lambda: imports._parse("complaints", raw, report, imports.TRIAL_POLICY))
    assert "too large" in report.issues[0]["message"] and "CSV UTF-8" in report.issues[0]["message"]
    assert peak < 20, peak


def test_a_bomb_past_the_size_checks_is_read_as_a_stream_and_stopped(monkeypatch):
    # With the size and ratio checks relaxed, the sheet is still read as a stream and refused at the element cap, so
    # memory stays small (the whole tree of this sheet would take several hundred megabytes).
    monkeypatch.setattr(xlsx, "MAX_COMPRESSION_RATIO", 10**9)
    monkeypatch.setattr(xlsx, "MAX_UNCOMPRESSED_BYTES", 10**9)
    raw = _bomb(2)

    def read():
        with pytest.raises(xlsx.XlsxError, match="too large"):
            xlsx.read_rows(raw, max_rows=50)

    assert _peak_megabytes(read) < 20
    # One cell holding thousands of elements is refused too.
    one_cell = _bomb(1, b'<c t="inlineStr"><is>' + b"<r/>" * 2000 + b"</is></c>", rows_wrapped=True)
    with pytest.raises(xlsx.XlsxError, match="too large"):
        xlsx.read_rows(one_cell, max_rows=5000)


def test_reading_stops_soon_after_the_row_limit_with_a_clear_message():
    header = [["Complaint Number", "Product Code", "Complaint Description"]]
    just_over = _workbook(header + [[f"C-{n}", "P-9", "Alarm"] for n in range(5050)])
    assert len(xlsx.read_rows(just_over, max_rows=5000)) == 5051  # within the margin: read, and counted later
    far_over = _workbook(header + [[f"C-{n}", "P-9", "Alarm"] for n in range(5200)])
    with pytest.raises(xlsx.XlsxError, match="more than 5,000 rows"):
        xlsx.read_rows(far_over, max_rows=5000)
    report = imports._Report()
    assert imports._parse("complaints", far_over, report, imports.TRIAL_POLICY) == []
    assert "Split it into smaller files" in report.issues[0]["message"]
