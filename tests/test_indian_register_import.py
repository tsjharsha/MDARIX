"""Stage 4, "Your Excel just works" (0.10.65): a realistic Indian complaint register imports on the first try, with no
edits to the file, and every column it holds is either used or named as not used.

The register is a synthetic fixture (tests/fixtures/indian_register, fictional "(Sample)" names): a hidden first sheet,
the complaints on sheet 2 below a title row and a blank row, DD/MM/YYYY dates, a software version "1.4.2+build",
Y/N/Yes/No/1/0/NA harm columns, a kit with two lots, "India, Germany" in one country cell, a batch sheet with
"1,25,000" and "1250,00", and the same as CSV files without a byte-order mark (Windows-1252 and UTF-8).

The first tests read the file without a database (J4, J5, J6, J41, J42); the rest import it end to end through the one
upload path as an Indian trial (A), check every field, and fix or dismiss set-aside rows on screen (C, J11).
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from pathlib import Path

import pytest

from backend.app.reportability import markets
from backend.app.trial import columns, imports, xlsx

FIXTURES = Path(__file__).parent / "fixtures" / "indian_register"
WORKBOOK = (FIXTURES / "indian_register.xlsx").read_bytes()
COMPLAINTS_CSV = (FIXTURES / "indian_register_complaints.csv").read_bytes()
BATCHES_CSV = (FIXTURES / "indian_register_batches.csv").read_bytes()
NOT_USED = ["Sr. No.", "Complaint Received Date"]
EXPECTED = {
    4: {
        "complaint_id": "MSD/CC/26/001",
        "received_date": "2026-08-14",
        "event_date": "2026-08-12",
        "product_name": "Pulse Oximeter PX-20 (Sample)",
        "product_id": "PX-20",
        "version": "1.4.2+build",
        "lot_id": "B2607-11",
        "serial_number": "PX20-0012345",
        "death": "N",
        "serious_injury": "N",
        "malfunction": "Y",
        "country": "India",
        "status": "Open",
    },
    5: {
        "complaint_id": "MSD/CC/26/002",
        "received_date": "2026-09-03",
        "event_date": "2026-09-01",
        "lot_id": "K2606-03",
        "death": "No",
        "serious_injury": "Yes",
        "malfunction": "1",
        "country": "India, Germany",
        "status": "Under Investigation",
    },
    6: {"complaint_id": "MSD/CC/26/002", "lot_id": "K2606-07", "description": ""},
    7: {
        "complaint_id": "MSD/CC/26/003",
        "received_date": "2026-10-21",
        "product_name": "Cathéter Guide CG-2 (Sample)",
        "death": "0",
        "serious_injury": "",  # "NA": not known, never a No
        "malfunction": "Yes",
        "country": "Germany",
        "status": "Closed",
    },
}


def _read(raw: bytes, entity: str = "complaints", date_format: str = "AUTO", **reading):
    report = imports._Report()
    rows = imports._parse(entity, raw, report, imports.TRIAL_POLICY, date_format, imports.FileReading(**reading))
    imports._check_values(entity, rows, report, report.date_order)
    return rows, report


# ------------------------------------------------------------------------------------------ the file is understood


@pytest.mark.parametrize("raw", [WORKBOOK, COMPLAINTS_CSV], ids=["xlsx", "csv-windows-1252"])
def test_the_register_is_read_as_it_comes(raw):
    rows, report = _read(raw)
    assert report.error_count == 0, report.issues
    # J6: the column names below the title and blank rows; the row numbers are the file's own.
    assert report.header_line == 3 and [line for line, _ in rows] == [4, 5, 6, 7]
    # J5: every header is used or named as not used; the second received-date column says which one was used.
    assert report.ignored == NOT_USED
    assert report.duplicates == [
        {"header": "Complaint Received Date", "column": "received_date", "kept": "Date of Complaint"}
    ]
    assert {item["header"]: item["column"] for item in report.mapping} == {
        "Complaint No.": "complaint_id",
        "Date of Complaint": "received_date",
        "Model": "product_id",
        "SW Version": "version",
        "Batch/Lot No.": "lot_id",
        "Serial No.": "serial_number",
    }
    assert report.headers["death"] == "Death (Y/N)" and report.headers["event_date"] == "Event Date (DD/MM/YYYY)"
    assert report.headers["malfunction"] == "Malfunction Y/N"
    # J4: the order of day and month is found from the file ("(DD/MM/YYYY)" in a header), dates read as one format.
    assert report.date_order == "DMY"
    by_line = dict(rows)
    for line, expected in EXPECTED.items():
        for column, value in expected.items():
            assert by_line[line][column] == value, (line, column)
    # J42: "Cathéter" stays "Cathéter" from the CSV without a byte-order mark.
    assert "Cathéter tip kinked" in by_line[7]["description"]


def test_the_workbook_says_which_sheet_it_read_and_reads_another_on_request():
    _rows, report = _read(WORKBOOK)
    assert report.sheet == "Complaint Register" and report.sheets == ["Complaint Register", "Batch Register"]
    assert "Hidden sheets are not read: 'Lists'" in report.notes[0] and "'Batch Register'" in report.notes[0]
    # A lots file from the same workbook reads the batch sheet: its names fit the lots template best.
    lots, lot_report = _read(WORKBOOK, "lots")
    assert lot_report.error_count == 0, lot_report.issues
    assert lot_report.sheet == "Batch Register"
    assert [(row["lot_id"], row["quantity"], row["expiry_date"]) for _, row in lots] == [
        ("B2607-11", "125000", "2031-06-30"),
        ("B2608-02", "1250", "2031-08-04"),
    ]
    # The person chooses the sheet; a sheet that is not there is refused with the sheets it has.
    _rows, named = _read(WORKBOOK, "lots", sheet="complaint register")
    assert named.sheet == "Complaint Register" and named.error_count
    _rows, missing = _read(WORKBOOK, sheet="Sheet9")
    assert (
        "no sheet called 'Sheet9'" in missing.issues[0]["message"]
        and "'Batch Register'" in missing.issues[0]["message"]
    )


def test_the_batch_csv_without_a_byte_order_mark_reads_indian_numbers():
    rows, report = _read(BATCHES_CSV, "lots")
    assert report.error_count == 0, report.issues
    assert [row["quantity"] for _, row in rows] == ["125000", "1250"]
    assert report.typed[(4, "quantity")] == "1,25,000"


def test_numbers_are_never_read_as_125000_by_accident():  # J41
    read = imports.whole_number
    assert read("1,25,000") == 125000 and read("12,50,000") == 1250000 and read("1,250,000") == 1250000
    assert read("1250,00") == 1250 and read("1.250,00") == 1250 and read("1,250.00") == 1250
    assert read("1 250") == 1250 and read("1,5") is None and read("12,5,00") is None
    # "1,250" and "1.250" differ by the chosen format; the other one is named when it reads the value whole.
    assert read("1,250") == 1250 and read("1,250", "DECIMAL_COMMA") is None
    assert read("1.250") is None and read("1.250", "DECIMAL_COMMA") == 1250
    message = imports.count_problem("1.250")
    assert "If it means 1,250, choose 'Numbers in the file: 1.250,00'" in message
    assert "write it as 1250, 1,250 or 1,25,000" in imports.count_problem("about 200")
    _rows, report = _read(b"lot_id,product_id,version,quantity\nL-1,P-1,Rev A,1.250\n", "lots")
    assert report.issues[0]["row"] == 2 and report.issues[0]["column"] == "quantity"
    _rows, decimal = _read(
        b"lot_id,product_id,version,quantity\nL-1,P-1,Rev A,1.250\n", "lots", numbers="DECIMAL_COMMA"
    )
    assert decimal.error_count == 0


def test_impossible_dates_are_refused_in_words():  # J41
    raw = (
        b"Complaint No.,Model,Description,Event Date\n"
        b"C-1,P-1,Alarm,03/04/2062\nC-2,P-1,Alarm,03/04/1926\nC-3,P-1,Alarm,31/02/2026\nC-4,P-1,Alarm,14-Mar-26\n"
    )
    rows, report = _read(raw, date_format="DMY")
    found = {issue["row"]: issue for issue in report.issues}
    assert found[2]["message"].startswith("'03/04/2062' reads as 3 Apr 2062, a day still to come")
    assert found[2]["header"] == "Event Date" and found[2]["column"] == "event_date"
    assert found[3]["message"].startswith("'03/04/1926' reads as 3 Apr 1926, before 1970")
    assert "is not a date" in found[3 + 1]["message"]
    assert 5 not in found and dict(rows)[5]["event_date"] == "2026-03-14"
    # A planned date may lie ahead: a lot's expiry.
    assert imports.date_problem("expiry_date", "2031-06-30") is None
    assert imports.date_problem("event_date", "2026-11-02", today=date(2026, 11, 1)) is None  # tomorrow is allowed


def test_the_date_order_is_found_from_the_file_or_the_organizations_usual_one():  # J4
    order = imports.resolve_date_order
    assert order(["Event Date"], ["03/04/2026", "14/04/2026"], "MDY")[0] == "DMY"
    assert order(["Event Date"], ["04/13/2026"], "DMY")[0] == "MDY"
    usual, note = order(["Event Date"], ["03/04/2026"], "DMY")
    assert usual == "DMY" and "your organization's usual order" in note
    assert order(["Date (MM/DD/YYYY)"], ["03/04/2026"], "DMY")[0] == "MDY"
    assert imports.usual_formats("Asia/Kolkata") == {"date_order": "DMY", "number_format": "GROUP"}
    assert imports.usual_formats("America/Chicago")["date_order"] == "MDY"
    assert imports.usual_formats("Europe/Berlin")["number_format"] == "DECIMAL_COMMA"
    assert imports.usual_formats("Europe/London")["number_format"] == "GROUP"


def _book_1904(serial: int) -> bytes:
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><workbookPr date1904="1"/>'
            '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
        )
        archive.writestr(
            "xl/styles.xml",
            f'<styleSheet xmlns="{main}"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{main}"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Received</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>Event date</t></is></c></row>'
            f'<row r="2"><c r="A2" s="1"><v>{serial}</v></c><c r="B2"><v>{serial}</v></c></row>'
            "</sheetData></worksheet>",
        )
    return out.getvalue()


def test_a_1904_workbook_and_excel_day_numbers_read_as_the_right_day():  # J41
    serial = (date(2026, 3, 14) - date(1904, 1, 1)).days
    with xlsx.Workbook(_book_1904(serial)) as book:
        assert book.date1904 and book.rows(book.sheets[0])[1][0] == "2026-03-14"
    # A day number left as a number in a date column (a CSV saved from Excel) is read in the workbook's system.
    assert imports.iso_date("46095", "ISO", imports.EXCEL_EPOCH) == "2026-03-14"
    assert imports.iso_date("46095", "ISO") is None  # outside a file, never guessed
    rows, report = _read(b"Complaint No.,Model,Description,Event Date\nC-1,P-1,Alarm,46095\n")
    assert dict(rows)[2]["event_date"] == "2026-03-14" and any("Excel day numbers" in note for note in report.notes)


def test_a_complaints_file_without_a_date_column_asks_which_column_holds_it():  # J5
    raw = b"Complaint No.,Model,Description,Logged On\nC-1,P-1,Alarm,14/03/2026\n"
    rows, report = _read(raw)
    assert rows == [] and report.needs_date_column and report.date_candidates == ["Logged On"]
    assert report.file_problems == 1 and "every complaint is dated today" in report.issues[0]["message"]
    rows, chosen = _read(raw, date_column="logged on")
    assert chosen.error_count == 0 and dict(rows)[2]["received_date"] == "2026-03-14"
    assert {"header": "Logged On", "column": "received_date"} in chosen.mapping and chosen.ignored == []
    rows, none = _read(raw, date_column="none")
    assert none.error_count == 0 and any("dated the day it is imported" in note for note in none.notes)
    _rows, wrong = _read(raw, date_column="Nope")
    assert wrong.needs_date_column and "no column 'Nope'" in wrong.issues[0]["message"]


def test_header_variants_and_yes_no_columns():  # J5
    assert columns.normalize("Death (Y/N)") == "death" and columns.normalize("Malfunction Y/N") == "malfunction"
    assert columns.normalize("Event Date (DD/MM/YYYY)") == "eventdate" and columns.normalize("Lot #") == "lotnumber"
    assert columns.date_order_hint("Event Date (DD/MM/YYYY)") == "DMY"
    raw = b"Complaint No.,Model,Description,Received On,Death (Y/N)\nC-1,P-1,Alarm,2026-03-14,Maybe\n"
    _rows, report = _read(raw)
    assert report.issues[0]["header"] == "Death (Y/N)"
    assert report.issues[0]["message"].startswith("'Maybe' is not a yes or no: use Y, N, Yes, No, 1 or 0")


def test_a_software_version_with_build_metadata_and_two_countries_in_one_cell():  # J41
    _rows, report = _read(
        b"Complaint No.,Model,Description,Received On,SW Version\nC-1,P-1,Alarm,2026-03-14,1.4.2+build\n"
    )
    assert report.error_count == 0, report.issues
    assert markets.markets_of("India, Germany") == [markets.IN, markets.EU_NI]
    assert markets.market_of("India, Germany") == markets.IN
    assert markets.markets_of("USA") == [markets.US] and markets.markets_of("") == []


# --------------------------------------------------------------------------------- end to end, the one upload path

UPLOAD = "/api/v1/data/import"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def indian_trial():
    """An Indian organization's free trial (time zone Asia/Kolkata from its sign-up country)."""
    from fastapi.testclient import TestClient

    from backend.app.db.models.foundation import Tenant
    from backend.app.db.session import SessionLocal
    from backend.app.main import app
    from tests.conftest import authenticated_client
    from tests.signup_profile import PROFILE
    from tests.test_free_trial import PASSWORD, _activation_token, _purge_trial_business_data, _request_id

    _purge_trial_business_data()
    email = f"trial-{uuid.uuid4().hex[:10]}@example.invalid"
    signup = TestClient(app).post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "display_name": "Asha Quality",
            "organization": "Medisynth Devices (Sample)",
            **PROFILE,
            "country": "India",
        },
    )
    assert signup.status_code == 200, signup.text
    admin = authenticated_client()
    approval = _ok(admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"))
    user = TestClient(app)
    _ok(
        user.post(
            "/api/v1/auth/activate-account", json={"token": _activation_token(approval, email), "password": PASSWORD}
        )
    )
    _ok(user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}))
    db = SessionLocal()
    try:
        tenant_id = db.query(Tenant.id).filter(Tenant.tenant_key == approval["tenant_key"]).scalar()
    finally:
        db.close()
    yield {"user": user, "tenant_id": tenant_id}
    _purge_trial_business_data()


def _complaints(tenant_id) -> dict:
    from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        found = {}
        for complaint in db.query(Complaint).filter(
            Complaint.tenant_id == tenant_id, Complaint.complaint_identifier.like("MSD/CC/%")
        ):
            product = db.get(Product, complaint.product_id)
            version = db.get(ProductVersion, complaint.product_version_id) if complaint.product_version_id else None
            lot = db.get(LotBatch, complaint.lot_batch_id) if complaint.lot_batch_id else None
            found[complaint.complaint_identifier] = {
                "product": product.product_identifier,
                "product_name": product.name,
                "version": version.version_identifier if version else None,
                "lot": lot.lot_identifier if lot else None,
                "other_lots": complaint.other_lots,
                "received": complaint.complaint_timestamp.date().isoformat(),
                "event": complaint.event_timestamp.date().isoformat() if complaint.event_timestamp else None,
                "serial": complaint.serial_number,
                "death": complaint.death,
                "serious_injury": complaint.serious_injury,
                "malfunction": complaint.malfunction,
                "country": complaint.country,
                "description": complaint.description,
                "status": complaint.status,
            }
        lots = {
            lot.lot_identifier: (lot.quantity, lot.expiry_date and lot.expiry_date.isoformat())
            for lot in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier.like("B26%"))
        }
        return found, lots
    finally:
        db.close()


XLSX = {"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@pytest.mark.db
def test_the_indian_register_imports_end_to_end_on_the_first_try(indian_trial):
    user, tenant_id = indian_trial["user"], indian_trial["tenant_id"]
    templates = _ok(user.get(f"{UPLOAD}/templates"))
    assert templates["usual"] == {"date_order": "DMY", "number_format": "GROUP"}
    assert templates["row_limit"] == 5000 and templates["file_limit_bytes"] == 2 * 1024 * 1024
    params = {"date_format": "AUTO", "file_name": "Complaint register FY26-27.xlsx"}
    check = _ok(user.post(f"{UPLOAD}/complaints/check", params={"date_format": "AUTO"}, content=WORKBOOK, headers=XLSX))
    assert check["ready"], check["issues"]
    assert check["sheet"] == "Complaint Register" and check["header_row"] == 3 and check["date_format_used"] == "DMY"
    assert check["ignored_columns"] == NOT_USED and check["rows_to_import"] == 4
    imported = _ok(user.post(f"{UPLOAD}/complaints", params=params, content=WORKBOOK, headers=XLSX))
    assert imported["created"] - sum(imported["also_created"].values()) == 3
    assert imported["also_created"] == {"products": 3, "versions": 1, "lots": 4}
    assert imported["quality_report"]["columns_not_used"] == [
        "Sr. No.",
        "Complaint Received Date (the same as Date of Complaint)",
    ]
    assert imported["quality_report"]["rows_read"] == 4 and imported["quality_report"]["balanced"]
    # The batches from the same workbook: the batch sheet, "1,25,000" and "1250,00", expiry dates.
    lots = _ok(user.post(f"{UPLOAD}/lots", params={"date_format": "AUTO"}, content=WORKBOOK, headers=XLSX))
    assert lots["created"] == 1 and lots["updated"] == 1

    complaints, batch = _complaints(tenant_id)
    assert complaints["MSD/CC/26/001"] == {
        "product": "PX-20",
        "product_name": "Pulse Oximeter PX-20 (Sample)",
        "version": "1.4.2+build",
        "lot": "B2607-11",
        "other_lots": None,
        "received": "2026-08-14",
        "event": "2026-08-12",
        "serial": "PX20-0012345",
        "death": False,
        "serious_injury": False,
        "malfunction": True,
        "country": "India",
        "description": "SpO2 reading 5 points higher than the ward monitor during a routine check.",
        "status": "open",
    }
    kit = complaints["MSD/CC/26/002"]
    assert (kit["lot"], kit["other_lots"]) == ("K2606-03", ["K2606-07"])  # a kit's second lot is not a duplicate
    assert (kit["death"], kit["serious_injury"], kit["malfunction"]) == (False, True, True)
    assert kit["country"] == "India, Germany" and kit["status"] == "under investigation"
    assert (kit["received"], kit["event"]) == ("2026-09-03", "2026-09-01")
    catheter = complaints["MSD/CC/26/003"]
    assert catheter["product_name"] == "Cathéter Guide CG-2 (Sample)" and catheter["description"].startswith("Cathéter")
    assert (catheter["death"], catheter["serious_injury"], catheter["malfunction"]) == (False, None, True)
    assert batch == {"B2607-11": (125000, "2031-06-30"), "B2608-02": (1250, "2031-08-04")}

    # "India, Germany": both markets are assessed, India's first.
    complaint = _ok(user.get("/api/v1/complaints", params={"q": "MSD/CC/26/002"}))["items"][0]
    view = _ok(user.get(f"/api/v1/complaints/{complaint['id']}/market-assessments"))
    preselected = {item["market"] for item in view["markets"] if item["preselected"]}
    assert preselected == {markets.IN, markets.EU_NI} and view["preselected"] == markets.IN

    # The same register as Windows CSV, through the trial's old route (a thin alias of the one path): read the same,
    # it changes nothing.
    again = _ok(user.post("/api/v1/trial/imports/complaints", params={"date_format": "AUTO"}, content=COMPLAINTS_CSV))
    assert again["created"] == 0 and again["updated"] == 0
    assert again["quality_report"]["rows_unchanged"] == 4  # the kit's two rows included
    assert _complaints(tenant_id)[0] == complaints
    runs = _ok(user.get(f"{UPLOAD}/runs"))["runs"]
    assert runs[0]["report"]["columns_not_used"] == again["quality_report"]["columns_not_used"]
    assert any(run["file_name"] == "Complaint register FY26-27.xlsx" for run in runs)


@pytest.mark.db
def test_set_aside_rows_are_fixed_on_screen_or_dismissed_and_close_when_imported_again(indian_trial):  # J11
    from backend.app.db.models.foundation import AuditEvent
    from backend.app.db.session import SessionLocal

    user, tenant_id = indian_trial["user"], indian_trial["tenant_id"]
    raw = (
        "Complaint No.,Model,Description,Date of Complaint\n"
        "FIX-1,PX-20,Display froze during a spot check.,03/04/2062\n"
        "FIX-2,PX-20,Probe cable frayed; reported by Mr. Ravi Kumar on 98450 12345.,03/04/2026\n"
        "FIX-3,PX-20,Battery drained within an hour.,\n"
        "FIX-4,PX-20,,05/04/2026\n"
    ).encode()
    params = {"date_format": "DMY", "on_problems": "skip", "file_name": "fix.csv"}
    first = _ok(user.post(f"{UPLOAD}/complaints", params=params, content=raw))
    assert first["quarantined_rows"] == 3 and first["created"] >= 1
    aside = _ok(user.get(f"{UPLOAD}/quarantine", params={"import_ref": first["import_ref"]}))["items"]
    by_ref = {item["row"]["complaint_id"]: item for item in aside}
    assert set(by_ref) == {"FIX-1", "FIX-2", "FIX-4"}  # FIX-3 has no date, which is no problem of the file
    assert any("a day still to come" in problem for problem in by_ref["FIX-1"]["problems"])
    # The stored row keeps personal details only as placeholders (stage 1), and so does the screen.
    assert "Ravi" not in str(by_ref["FIX-2"]) and "[PERSON]" in by_ref["FIX-2"]["row"]["description"]

    # Fix FIX-1 on screen: only the field its reason names; the other values stay as stored.
    fixed = _ok(
        user.post(
            f"{UPLOAD}/quarantine/{by_ref['FIX-1']['id']}/reprocess", json={"row": {"received_date": "2026-04-03"}}
        )
    )
    assert fixed["quarantine_row"]["status"] == "REPROCESSED" and fixed["created"] == 1
    assert (
        user.post(
            f"{UPLOAD}/quarantine/{by_ref['FIX-1']['id']}/reprocess", json={"row": {"received_date": "2026-04-03"}}
        ).status_code
        == 409
    )
    unknown = user.post(f"{UPLOAD}/quarantine/{by_ref['FIX-4']['id']}/reprocess", json={"row": {"patient": "x"}})
    assert unknown.status_code == 422 and "no column 'patient'" in unknown.json()["detail"]["message"]
    still = user.post(f"{UPLOAD}/quarantine/{by_ref['FIX-4']['id']}/reprocess", json={"row": {"description": ""}})
    assert still.status_code == 422  # the same checks: still no description, the row stays open

    # Dismiss FIX-2 with a reason; a name in the reason is masked.
    short = user.post(f"{UPLOAD}/quarantine/{by_ref['FIX-2']['id']}/dismiss", json={"reason": "x"})
    assert short.status_code == 422
    dismissed = _ok(
        user.post(
            f"{UPLOAD}/quarantine/{by_ref['FIX-2']['id']}/dismiss",
            json={"reason": "Duplicate of a call Mr. Ravi Kumar logged in the QMS."},
        )
    )["quarantine_row"]
    assert dismissed["status"] == "DISMISSED" and "Ravi" not in dismissed["resolution_note"]
    assert "[PERSON]" in dismissed["resolution_note"]

    # FIX-4 fixed in the file and imported again: its open set-aside row closes, and leaves Triage.
    escalated = user.post(
        "/api/v1/triage/escalate",
        json={"kind": "QUARANTINE", "id": by_ref["FIX-4"]["id"], "reason": "Checking the missing description."},
    )
    assert escalated.status_code == 200, escalated.text
    triage = {item["ref"] for item in _ok(user.get("/api/v1/triage", params={"show": "all"}))["items"]}
    assert "FIX-4" in triage
    reimport = "Complaint No.,Model,Description,Date of Complaint\nFIX-4,PX-20,Strap buckle broke.,05/04/2026\n"
    again = _ok(user.post(f"{UPLOAD}/complaints", params={"date_format": "DMY"}, content=reimport.encode()))
    assert again["set_aside_closed"] == [by_ref["FIX-4"]["id"]]
    listing = _ok(user.get(f"{UPLOAD}/quarantine", params={"import_ref": first["import_ref"]}))
    assert listing["counts"] == {"open": 0, "reprocessed": 2, "dismissed": 1}
    triage = {item["ref"]: item for item in _ok(user.get("/api/v1/triage", params={"show": "all"}))["items"]}
    assert triage.get("FIX-4", {}).get("kind") != "QUARANTINE"
    run = _ok(user.get(f"{UPLOAD}/runs/{first['import_ref']}"))
    assert run["quarantine_now"] == {"open": 0, "reprocessed": 2, "dismissed": 1}

    db = SessionLocal()
    try:
        actions = [
            row.action
            for row in db.query(AuditEvent).filter(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action.in_(["QUARANTINE_ROW_REPROCESSED", "QUARANTINE_ROW_DISMISSED"]),
            )
        ]
        dismissal = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "QUARANTINE_ROW_DISMISSED")
            .one()
        )
        latest = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "TRIAL_DATA_IMPORTED")
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
    finally:
        db.close()
    assert sorted(actions) == ["QUARANTINE_ROW_DISMISSED", "QUARANTINE_ROW_REPROCESSED"]
    assert "Ravi" not in str(dismissal.details) and dismissal.details["quarantine_row"] == by_ref["FIX-2"]["id"]
    assert latest.details["set_aside_closed"] == [by_ref["FIX-4"]["id"]]
