"""B9 steps 6-8 against the database (B9-21, B9-24): a US importer's report end to end. The organization's US role is
Importer; its signed conclusion (serious injury) makes a Form 3500A report with section F (F1 Importer, F7 Initial,
F11 and F13 from the recipients) and no section G or H; F2 is typed once in FDA's importer format and the eMDR file
carries it, never G8; the file is frozen at approval; "Sent to the manufacturer" and "Sent to FDA" are recorded
separately and the report is submitted once both are."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from backend.app.authority_reports import emdr
from backend.app.db.session import SessionLocal
from tests.report_fill import fill
from tests.test_authority_reports_api import REPORTS, _ok, _sign_rv06, _start_rv06
from tests.test_free_trial import _approved_trial_client
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD
from tests.test_reporting_capa_api import _client

pytestmark = pytest.mark.db

PARTIES = "/api/v1/regulatory-reference/responsible-parties"
IMPORTER = {
    "market": "US",
    "role": "IMPORTER",
    "organisation": "VentraLink Imports (Sample)",
    "contact_email": "imports@example.invalid",
}
MAKER = {
    "market": "US",
    "role": "MANUFACTURER",
    "organisation": "Orbit Medical Devices (Sample)",
    "contact_email": "mdr@example.invalid",
}


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    from tests.code_lists import ensure_loaded
    from tests.test_release_c3_0_10_75 import _classic

    ensure_loaded()
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    _classic(tenant_id)
    colleague = _client(tenant_id, "LEADER", "Rahul Colleague")
    try:
        yield {"user": user, "colleague": colleague, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b9-importer-cleanup")


def _fields(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


def test_an_importers_report_has_section_f_its_own_number_and_two_recipients(trial, monkeypatch):
    monkeypatch.delenv("MDARIX_B9_US_IMPORTER", raising=False)
    user, colleague = trial["user"], trial["colleague"]
    role = user.put(
        "/api/v1/complaints/reportability-roles",
        json={"market": "US", "role": "IMPORTER", "reason": "We import this device into the US from its maker."},
    )
    assert role.status_code == 200, role.text
    _sign_rv06(trial)
    detail = _start_rv06(trial)
    assert detail["report_type"] == "US_IMP_30_DAY", detail["report_type"]
    sections = {section["code"]: section for section in detail["sections"]}
    assert not sections["G"]["fields"] and not sections["H"]["fields"] and not sections["FRONT"]["fields"]
    fields = _fields(detail)
    assert fields["F1"]["value"] == "Importer" and fields["F7"]["value"] == "Initial"
    assert fields["F11"]["value"] == "Yes" and fields["F13"]["value"] == "Yes" and not fields["F1"]["editable"]
    assert [route["code"] for route in detail["routes"]] == ["EMDR", "MFR_COPY"]
    assert [item["label"] for item in detail["recipients"]] == ["Sent to FDA", "Sent to the manufacturer"]
    # A manufacturer's fields are not this report's: G8 and the front page's number answer 404.
    assert user.put(f"{REPORTS}/{detail['id']}/fields/MFR_REPORT", json={"value": "1"}).status_code == 404
    assert detail["emdr"]["missing"], detail["emdr"]  # F2, F4 and F10's codes still to give

    _ok(user.put(PARTIES, json=IMPORTER))
    _ok(user.put(PARTIES, json=MAKER))
    number = f"1234567-{date.today().year}-00001"
    _ok(user.put(f"{REPORTS}/{detail['id']}/fields/F2", json={"value": number}))
    detail = fill(user, REPORTS, detail["id"], ["D2A", "F10_CLINICAL", "F10_IMPACT", "F10_PROBLEM", "F10_COMPONENT"])
    assert detail["emdr"]["missing"] == [], detail["emdr"]
    sent = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    approved = _ok(
        colleague.post(
            f"{REPORTS}/{detail['id']}/snapshots/{sent['pending_snapshot']['id']}/approve",
            json={"password": COLLEAGUE_PASSWORD},
        )
    )
    assert approved["state"] == "APPROVED"
    snapshot = approved["approved_snapshot"]["id"] if approved.get("approved_snapshot") else None
    xml = user.get(f"{REPORTS}/{detail['id']}/emdr.xml", params={"snapshot": snapshot} if snapshot else None)
    assert xml.status_code == 200, xml.text
    assert number.encode() in xml.content and b"C53617" in xml.content  # F2 and F1 Importer
    assert b"contactManufacturerContact" not in xml.content  # no G1
    # F11 and F13: sent, dated the day sent for approval (the frozen file states who must receive it).
    doc = emdr.plain(xml.content)
    assert len(doc.xpath(emdr.POINTERS["F11"])) == 1 and doc.xpath(emdr.POINTERS["F11"]) == doc.xpath(
        emdr.POINTERS["F13"]
    )

    def record(route: str):
        return user.post(
            f"{REPORTS}/{detail['id']}/submissions",
            json={
                "route": route,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "content_note": "Sent with the approved files.",
                "no_differences": True,
            },
        )

    copy = _ok(record("MFR_COPY"))
    assert copy["state"] == "APPROVED"  # FDA's send still to record
    assert [item["recorded"] for item in copy["recipients"]] == [False, True]
    assert record("MFR_COPY").json()["detail"]["code"] == "RECIPIENT_RECORDED"
    done = _ok(record("EMDR"))
    assert done["state"] == "SUBMITTED_PENDING" and all(item["recorded"] for item in done["recipients"])
