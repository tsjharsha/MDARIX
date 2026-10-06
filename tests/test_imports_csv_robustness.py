"""CSV imports read real-world files exactly: strict UTF-8 (with or without BOM), comma, semicolon or tab, a raw
body or a multipart upload, and day/month order only when the uploader declares it."""

import pytest
from fastapi import HTTPException

from backend.app.trial import imports
from tests.test_business_permissions import _client_with_role


def _rows(raw: bytes, entity: str = "products", date_format: str = "ISO"):
    report = imports._Report()
    rows = imports._parse(entity, raw, report, imports.WORKSPACE_POLICY, date_format)
    return rows, report


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_the_delimiter_is_detected_from_the_header(delimiter):
    text = delimiter.join(["product_id", "product_name", "version"]) + "\n"
    text += delimiter.join(["P-1", "Pump, large", "Rev A"]) + "\n" if delimiter != "," else 'P-1,"Pump, large",Rev A\n'
    rows, report = _rows(text.encode())
    assert report.error_count == 0, report.issues
    assert rows == [(2, {"product_id": "P-1", "product_name": "Pump, large", "version": "Rev A"})]


def test_utf8_with_a_byte_order_mark_keeps_every_character():
    raw = "﻿product_id;product_name\r\nP-1;Gerät für Ärzte – Größe M\r\n".encode("utf-8")
    rows, report = _rows(raw)
    assert report.error_count == 0
    assert rows[0][1] == {"product_id": "P-1", "product_name": "Gerät für Ärzte – Größe M"}


def test_a_file_that_is_not_utf8_is_refused_with_instructions_not_garbled():
    raw = "product_id,product_name\nP-1,Gerät\n".encode("cp1252")
    rows, report = _rows(raw)
    assert rows == [] and report.error_count == 1
    assert report.issues[0]["row"] == 2 and "CSV UTF-8" in report.issues[0]["message"]
    utf16 = "product_id,product_name\nP-1,X\n".encode("utf-16")
    rows, report = _rows(utf16)
    assert rows == [] and "UTF-16" in report.issues[0]["message"]


def test_dates_are_iso_unless_the_order_is_declared():
    assert imports.iso_date("2026-03-04") == "2026-03-04"
    assert imports.iso_date("04/03/2026") is None  # never guessed
    assert imports.iso_date("04/03/2026", "DMY") == "2026-03-04"
    assert imports.iso_date("04/03/2026", "MDY") == "2026-04-03"
    assert imports.iso_date("31/12/2026", "MDY") is None  # month 31 does not exist
    assert imports.iso_date("2026-02-30", "DMY") is None
    assert imports.iso_date("20260304") is None  # only the dashed form


def test_parsed_dates_become_iso_and_wrong_ones_name_the_expected_format():
    header = b"lot_id,product_id,version,manufacture_date\n"
    rows, _ = _rows(header + b"L-1,P-1,Rev A,15/07/2026\n", "lots", "DMY")
    assert rows[0][1]["manufacture_date"] == "2026-07-15"
    rows, report = _rows(header + b"L-1,P-1,Rev A,15/07/2026\n", "lots", "ISO")
    imports._check_values("lots", rows, report, "ISO")
    assert "'15/07/2026' is not a date in YYYY-MM-DD format." in [issue["message"] for issue in report.issues]
    rows, report = _rows(header + b"L-1,P-1,Rev A,07/15/2026\n", "lots", "DMY")
    imports._check_values("lots", rows, report, "DMY")
    assert any("YYYY-MM-DD or DD/MM/YYYY" in issue["message"] for issue in report.issues)


def test_an_unknown_date_format_is_refused():
    assert imports.date_format_or_422(None) == "ISO" and imports.date_format_or_422("dmy") == "DMY"
    with pytest.raises(HTTPException) as refused:
        imports.date_format_or_422("YMD")
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "DATE_FORMAT_INVALID"


# ------------------------------------------------------------------------------------------- through the API


def test_any_organization_checks_a_multipart_upload_with_semicolons_and_day_first_dates():
    investigator = _client_with_role("Investigator")  # a paying organization, not a trial
    csv_bytes = "product_id;product_name;version;version_release_date\nIMPX-1;Pompe à perfusion;Rev A;15/07/2026\n"
    checked = investigator.post(
        "/api/v1/data/import/products/check?date_format=DMY",
        files={"file": ("products.csv", csv_bytes.encode("utf-8-sig"), "text/csv")},
    )
    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert body["ready"], body["issues"]
    assert body["preview"][0] == {
        "product_id": "IMPX-1",
        "product_name": "Pompe à perfusion",
        "version": "Rev A",
        "version_release_date": "2026-07-15",
    }


def test_a_raw_body_still_works_and_a_bad_form_or_format_is_refused():
    investigator = _client_with_role("Investigator")
    raw = investigator.post(
        "/api/v1/data/import/products/check",
        content=b"product_id\tproduct_name\nIMPX-2\tTab pump\n",
        headers={"Content-Type": "text/csv"},
    )
    assert raw.status_code == 200 and raw.json()["ready"], raw.text
    wrong_field = investigator.post(
        "/api/v1/data/import/products/check", files={"upload": ("p.csv", b"product_id,product_name\n", "text/csv")}
    )
    assert wrong_field.status_code == 422 and wrong_field.json()["detail"]["code"] == "UPLOAD_INVALID"
    bad_format = investigator.post("/api/v1/data/import/products/check?date_format=YMD", content=b"x")
    assert bad_format.status_code == 422 and bad_format.json()["detail"]["code"] == "DATE_FORMAT_INVALID"
    garbled = investigator.post(
        "/api/v1/data/import/products/check", content="product_id,product_name\nP,Gerät\n".encode("cp1252")
    )
    assert garbled.status_code == 200 and not garbled.json()["ready"]
    assert "CSV UTF-8" in garbled.json()["issues"][0]["message"]
