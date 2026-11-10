"""Hardening 0.10.95 (code-audit fixes 6-12): the fixes a pure test proves, with no database."""

from __future__ import annotations

import base64
import uuid
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
