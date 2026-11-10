"""Hardening 0.10.95 (code-audit fixes 6-12): the fixes a pure test proves, with no database."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.authority_reports import router as reports
from backend.app.authority_reports import worksheet
from tests.test_object_storage_scan import clamd  # noqa: F401 (the scan stub, a fixture)

pytestmark = pytest.mark.unit


def _attached(text: bytes) -> reports.FileIn:
    return reports.FileIn(name="ack.txt", content_type="text/plain", data=base64.b64encode(text).decode())


def test_a_report_file_the_scanner_refuses_is_not_kept(clamd, monkeypatch, tmp_path):  # noqa: F811 (audit 7)
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    with pytest.raises(HTTPException) as refused:
        reports._file(_attached(b"X5O!P%@AP EICAR test"))
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "MALWARE_SCAN_REJECTED"


def test_a_clean_report_file_is_kept(clamd, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    kept = reports._file(_attached(b"Acknowledgement 1"))
    assert kept["content"] == b"Acknowledgement 1" and kept["content_type"] == "text/plain"
    assert clamd.received == b"Acknowledgement 1"


def _us_context(**answers) -> dict:
    current = SimpleNamespace(
        id=uuid.uuid4(),
        market="US",
        version=1,
        conclusion="REPORTABLE",
        answers={key: {"answer": value} for key, value in answers.items()},
    )
    return {"current": current, "draft": None, "record": {"complaint_identifier": "C-1", "business_id": None}}


def test_fda_h1_says_death_only_when_the_device_caused_or_contributed():  # audit 10
    event_type = worksheet.SOURCES["us_event_type"]
    assert event_type(_us_context(US1="YES", US3="NO")) is None
    assert event_type(_us_context(US1="YES", US3="YES"))[0] == "Death"
    assert event_type(_us_context(US1="YES", US2A="YES", US3="YES"))[0] == "Death; Serious injury"
    assert event_type(_us_context(US1="YES", US3="NO", US4="YES", US5="YES"))[0] == "Malfunction"


def _aware(market: str, at: str, org_zone: str) -> str:
    context = {
        "market": market,
        "seen": {"aware_at": at, "org_zone": org_zone},
        "complaint": SimpleNamespace(id=uuid.uuid4()),
        "record": {"complaint_identifier": "C-1", "business_id": None},
    }
    return worksheet.SOURCES["aware_date"](context)[0]


def test_the_awareness_box_prints_the_local_day_the_deadline_counts_from():  # audit 11
    from backend.app.reportability import deadlines

    # 23:30 in New York is the next day in UTC: FDA box G3 prints the New York day.
    assert _aware("US", "2026-11-10T04:30:00+00:00", "America/New_York") == "2026-11-09"
    # 00:30 IST is the previous day in UTC: India's form prints the India day.
    assert _aware("IN", "2026-11-09T19:00:00+00:00", "Asia/Kolkata") == "2026-11-10"
    # The day printed is the day the deadline counts from.
    moment = datetime.fromisoformat("2026-11-09T19:00:00+00:00")
    assert deadlines.count(moment, 1, "CALENDAR", "IN", "Asia/Kolkata").day.isoformat() == "2026-11-10"
    # A day given without a time stays that day.
    assert _aware("US", "2026-11-10T12:00:00+00:00", "Asia/Kolkata") == "2026-11-10"


def test_each_window_counts_by_the_market_it_covers():  # audit 12
    from backend.app.reportability import deadlines, rules

    windows = [
        {"name": name, "markets": [country], "triggers": ["DEATH"], "days": 15, "day_basis": "CALENDAR"}
        for name, country in (("India window", "India"), ("US window", "United States"))
    ]
    record = {"country": "United States, India", "death": True}
    aware = datetime.fromisoformat("2026-11-10T06:00:00+00:00")
    found = {clock.name: clock for clock in rules.clocks(record, windows, aware, aware, "Asia/Kolkata")}
    india = deadlines.count(aware, 15, "CALENDAR", "IN", "Asia/Kolkata")
    us = deadlines.count(aware, 15, "CALENDAR", "US", "Asia/Kolkata")
    assert india.day < us.day  # India counts the awareness day as day 1
    assert (found["India window"].due, found["India window"].market) == (india.day, "IN")
    assert (found["US window"].due, found["US window"].market) == (us.day, "US")


def test_files_mdarix_makes_do_not_count_against_the_upload_quota(monkeypatch, tmp_path):  # audit 15
    from object_storage.service import ObjectStorageService, StorageError, refused_upload

    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_TENANT_QUOTA_BYTES", "100")
    storage = ObjectStorageService(root=str(tmp_path))
    monkeypatch.setattr(storage, "scan", lambda *_: True)
    for folder in ("exports", "reports", "documents"):
        storage.put("t1", f"{folder}/big.bin", b"x" * 500, internal=True)
    storage.put("t1", "upload-1", b"x" * 60)
    with pytest.raises(StorageError) as full:
        storage.put("t1", "upload-2", b"x" * 60)
    assert (refused_upload(full.value).status_code, refused_upload(StorageError("Invalid key")).status_code) == (
        413,
        422,
    )


def test_the_export_writes_a_binary_column_as_base64(monkeypatch):  # audit 18
    import io
    import json
    import zipfile

    from backend.app import tenant_export

    pdf = b"%PDF-1.4 \x00\xff submitted copy"

    class Result:
        rows = [SimpleNamespace(_mapping={"id": "r1", "content": pdf})]

        def keys(self):
            return ["id", "content"]

        def fetchmany(self, _):
            rows, self.rows = self.rows, []
            return rows

    monkeypatch.setattr(tenant_export, "_tables", lambda db: [("public", "report_submission_copies")])
    buffer, manifest = io.BytesIO(), {"tables": {}}
    with zipfile.ZipFile(buffer, "w") as archive:
        tenant_export._write_tables(SimpleNamespace(execute=lambda *a: Result()), archive, "t1", "data/", manifest)
    line = zipfile.ZipFile(buffer).read("data/public.report_submission_copies.jsonl")
    assert base64.b64decode(json.loads(line)["content"]) == pdf
