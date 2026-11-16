"""0.10.96 (B3): the US eMDR complete for manufacturers, against the database.

Send for approval checks the eMDR file (A2), gives the report its number (A3) and freezes the file with the snapshot
(A4); the files come only from the approved snapshot."""

# ruff: noqa: F811 (``trial`` is the shared fixture, imported)
from __future__ import annotations

import threading
import time
import uuid
from datetime import date, datetime, timezone

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_authority_reports_api import REPORTS, _ok, _ready_us, _start_rv06, trial  # noqa: F401 (a fixture)

pytestmark = pytest.mark.db


def _xml(client, report: dict, snapshot: str):
    return client.get(f"{REPORTS}/{report['id']}/emdr.xml", params={"snapshot": snapshot})


def _us_report(tenant_id, number: str | None = None) -> uuid.UUID:
    """A US draft on another of the organization's complaints, as Start report makes it (only what the number needs)."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        taken = [row[0] for row in db.query(ReportObligation.complaint_id).filter(ReportObligation.market == "US")]
        complaint = (
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.id.notin_(taken or [uuid.uuid4()]))
            .order_by(Complaint.id)
            .first()[0]
        )
        row = ReportObligation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_id=complaint,
            market="US",
            kind="INITIAL",
            form_code="FDA_3500A",
            form_version="Form FDA 3500A (09/2025)",
            entries={"MFR_REPORT": {"value": number}} if number else {},
            created_by="test",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return row.id


def _assign(tenant_id, report_id, pause: float = 0.0, ready=None) -> str:
    """Send for approval's numbering step, in its own transaction (as the route runs it)."""
    from backend.app.authority_reports import router

    with SessionLocal() as db, SessionLocal() as control:
        bind_tenant(db, tenant_id)
        bind_system(control, "test: the organization's trial flag")
        row = db.query(ReportObligation).filter(ReportObligation.id == report_id).with_for_update().one()
        if ready is not None:
            ready.wait()
        router.assign_number(db, control, row, "test", datetime.now(timezone.utc))
        time.sleep(pause)  # holds the lock: a report sent meanwhile waits for this commit
        number = (row.entries.get("MFR_REPORT") or {}).get("value")
        db.commit()
        return number


def _numbered(trial) -> None:
    """The organization has typed its first number (the A2 test types it on SAMPLE-RV-06)."""
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        found = db.query(ReportObligation.entries["MFR_REPORT"]["value"].astext).filter(
            ReportObligation.entries["MFR_REPORT"]["value"].astext.isnot(None)
        )
        if found.first() is None:
            _us_report(trial["tenant_id"], f"1234567-{date.today().year}-00001")


# --------------------------------------------------------------------------------------------- A3 (first number)


def test_b3_the_first_number_is_asked_once(trial):

    user = trial["user"]
    detail = _start_rv06(trial)
    assert detail["state"] == "DRAFT" and not detail["pending_snapshot"], detail["state"]
    # No number yet in the organization: Send for approval asks for the first one, and freezes nothing.
    refused = user.post(f"{REPORTS}/{detail['id']}/snapshots")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "REPORT_NUMBER_FIRST", refused.text
    assert "1234567-2026-00001" in refused.json()["detail"]["message"]
    # The numbering step leaves the number blank for the person to type: nothing is invented.
    assert _assign(trial["tenant_id"], _us_report(trial["tenant_id"])) is None
    # Once typed (the next test types it on SAMPLE-RV-06), every later report is numbered without typing:
    # test_b3_two_reports_sent_at_once_get_different_numbers.


# --------------------------------------------------------------------------------------------- A2


def test_b3_send_for_approval_is_refused_while_fda_would_refuse_the_file(trial, monkeypatch):
    from backend.app.authority_reports import emdr

    user = trial["user"]
    detail = _start_rv06(trial)
    assert detail["state"] == "DRAFT" and not detail["pending_snapshot"], detail["state"]
    _ok(user.put(f"{REPORTS}/{detail['id']}/fields/MFR_REPORT", json={"value": "1234567-2026-00001"}))
    refused = user.post(f"{REPORTS}/{detail['id']}/snapshots")
    assert refused.status_code == 422, refused.text
    body = refused.json()["detail"]
    assert body["code"] == "EMDR_MISSING" and body["missing"]
    # Each block FDA would refuse the file for is named, and nothing was frozen.
    assert any(line.startswith("H6 Type of investigation code:") for line in body["missing"]), body["missing"]
    assert "H6 Type of investigation code" in body["message"]
    assert _ok(user.get(f"{REPORTS}/{detail['id']}"))["snapshots"] == []
    _ready_us(user, detail["id"], number=None)
    # A file FDA's schema would refuse is refused too.
    monkeypatch.setattr(emdr, "validate", lambda xml: ["line 9: Element 'x': This element is not expected."])
    invalid = user.post(f"{REPORTS}/{detail['id']}/snapshots")
    assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "EMDR_INVALID", invalid.text
    monkeypatch.undo()
    sent = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    assert sent["pending_snapshot"] and sent["emdr"]["missing"] == []


def test_b3_the_draft_shows_the_schema_result_and_no_xml_downloads(trial):
    user = trial["user"]
    detail = _start_rv06(trial)
    if detail["state"] == "DRAFT" and not detail["pending_snapshot"]:
        _ready_us(user, detail["id"])
        detail = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    # The draft says what the file needs, what it leaves out and whether FDA's schema takes it.
    assert detail["emdr"]["missing"] == [] and detail["emdr"]["schema_errors"] == []
    assert isinstance(detail["emdr"]["left_out"], list)
    # The snapshot awaiting approval previews as a DRAFT PDF; its XML never downloads before approval (D7).
    pending = detail["pending_snapshot"]["id"]
    refused = _xml(user, detail, pending)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "APPROVE_FIRST", refused.text
    preview = user.get(f"{REPORTS}/{detail['id']}/worksheet.pdf", params={"snapshot": pending})
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF-")


# --------------------------------------------------------------------------------------------- A3


def test_b3_two_reports_sent_at_once_get_different_numbers(trial):
    _numbered(trial)
    first, second = _us_report(trial["tenant_id"]), _us_report(trial["tenant_id"])
    ready, found = threading.Barrier(2), {}

    def send(report_id):
        found[report_id] = _assign(trial["tenant_id"], report_id, pause=0.5, ready=ready)

    threads = [threading.Thread(target=send, args=(report,)) for report in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert len(found) == 2 and found[first] != found[second], found
    # A practice organization's numbers are FDA's test numbers, one after the other.
    sequences = sorted(int(number.rsplit("-", 1)[1]) for number in found.values())
    assert sequences[0] >= 70001 and sequences[1] == sequences[0] + 1, found


def test_b3_a_number_is_never_reused_even_after_a_cancellation(trial):
    from fastapi import HTTPException

    _numbered(trial)
    cancelled = _us_report(trial["tenant_id"])
    number = _assign(trial["tenant_id"], cancelled)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.get(ReportObligation, cancelled).state = "CANCELLED"
        db.commit()
    later = _assign(trial["tenant_id"], _us_report(trial["tenant_id"]))
    assert later != number and int(later.rsplit("-", 1)[1]) == int(number.rsplit("-", 1)[1]) + 1
    # A typed number another report holds (a cancelled one too) is refused.
    with pytest.raises(HTTPException) as refused:
        _assign(trial["tenant_id"], _us_report(trial["tenant_id"], number))
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "REPORT_NUMBER_IN_USE"


# --------------------------------------------------------------------------------------------- A4


def _approved(trial) -> dict:
    """SAMPLE-RV-06's US report, sent for approval and approved by a colleague."""
    from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

    user, colleague = trial["user"], trial["colleague"]
    detail = _start_rv06(trial)
    if detail["state"] == "DRAFT":
        if not detail["pending_snapshot"]:
            _numbered(trial)
            _ready_us(user, detail["id"], number=None)
            detail = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
        pending = detail["pending_snapshot"]["id"]
        detail = _ok(
            colleague.post(
                f"{REPORTS}/{detail['id']}/snapshots/{pending}/approve", json={"password": COLLEAGUE_PASSWORD}
            )
        )
    assert detail["state"] == "APPROVED", detail["state"]
    return detail


def test_b3_the_xml_downloaded_is_the_one_approved_byte_for_byte(trial):
    import hashlib

    from backend.app.db.models.authority_reports import ReportSnapshot
    from tests.report_fill import US_PARTY

    user = trial["user"]
    detail = _approved(trial)
    snapshot = detail["approved_snapshot"]["id"]
    first = _xml(user, detail, snapshot)
    assert first.status_code == 200, first.text
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        fields = db.get(ReportSnapshot, uuid.UUID(snapshot)).fields
    assert first.content == fields["emdr_xml"].encode("utf-8")
    assert hashlib.sha256(first.content).hexdigest() == fields["emdr_sha256"]
    # B4 is the organization's day the report was sent for approval, in the file and in the frozen sections.
    b4 = next(item for part in fields["sections"] for item in part["fields"] if item["id"] == "B4")
    assert b4["value"] and f'value="{b4["value"].replace("-", "")}"'.encode() in first.content
    # Settings change after approval: the file downloaded is still the one approved, byte for byte.
    moved = {**US_PARTY, "contact_email": "other@example.invalid", "organisation": "Renamed Devices (sample)"}
    _ok(user.put("/api/v1/regulatory-reference/responsible-parties", json=moved))
    again = _xml(user, detail, snapshot)
    assert again.status_code == 200 and again.content == first.content
    _ok(user.put("/api/v1/regulatory-reference/responsible-parties", json=US_PARTY))


def test_b3_a_snapshot_approved_before_b3_still_downloads(trial):
    from sqlalchemy.orm.attributes import flag_modified

    from backend.app.authority_reports import emdr
    from backend.app.db.models.authority_reports import ReportSnapshot

    user = trial["user"]
    detail = _approved(trial)
    snapshot = detail["approved_snapshot"]["id"]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportSnapshot, uuid.UUID(snapshot))
        kept = dict(row.fields)
        row.fields = {key: value for key, value in kept.items() if not key.startswith("emdr_")}
        flag_modified(row, "fields")
        db.commit()
    try:
        built = _xml(user, detail, snapshot)  # no file kept: built now, as before 0.10.96
        assert built.status_code == 200, built.text
        assert emdr.validate(built.content) == []
    finally:
        with SessionLocal() as db:
            bind_tenant(db, trial["tenant_id"])
            row = db.get(ReportSnapshot, uuid.UUID(snapshot))
            row.fields = kept
            flag_modified(row, "fields")
            db.commit()


# --------------------------------------------------------------------------------------------- A5 and A6


def test_b3_the_default_pdf_is_the_esubmitter_layout_and_the_official_form_is_second(trial):
    import hashlib

    from backend.app.authority_reports import emdr_pdf
    from backend.app.db.models.authority_reports import ReportSnapshot
    from reports.pdf import text_of
    from tests.report_fill import US_PARTY
    from tests.test_fda_3500a_emdr import _fields

    user = trial["user"]
    detail = _approved(trial)
    snapshot = detail["approved_snapshot"]["id"]
    url = f"{REPORTS}/{detail['id']}/worksheet.pdf"
    xml = _xml(user, detail, snapshot).content
    # The default PDF lays out the approved file itself: its number, its blocks, and its SHA-256 on the record page.
    default = user.get(url, params={"snapshot": snapshot})
    assert default.status_code == 200, default.text
    text = text_of(default.content)
    assert emdr_pdf.TITLE in text and "NOT APPROVED" not in text and "eSubmitter Generated" not in text
    assert f"Mfr Report #: {emdr_pdf.read(xml)['G8'][0]}" in text
    assert f"SHA-256 of the eMDR file: {hashlib.sha256(xml).hexdigest()}" in text
    # Settings change after approval: the official form, second, still reads the parties frozen with the file.
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        frozen = db.get(ReportSnapshot, uuid.UUID(snapshot)).fields["emdr_parties"]["G1"]
    moved = {**US_PARTY, "contact_email": "other@example.invalid", "organisation": "Renamed Devices (sample)"}
    _ok(user.put("/api/v1/regulatory-reference/responsible-parties", json=moved))
    try:
        official = user.get(url, params={"snapshot": snapshot, "form": "official"})
        assert official.status_code == 200, official.text
        assert "official-form" in official.headers["content-disposition"]
        assert _fields(official.content)["manuEmail"] == frozen["email"] != "other@example.invalid"
        assert user.get(url, params={"snapshot": snapshot}).content == default.content  # the same bytes again
    finally:
        _ok(user.put("/api/v1/regulatory-reference/responsible-parties", json=US_PARTY))
    # Only a US report's PDF has an official form.
    for path, form in (("worksheet.pdf", "other"), ("worksheet.docx", "official")):
        refused = user.get(f"{REPORTS}/{detail['id']}/{path}", params={"snapshot": snapshot, "form": form})
        assert refused.status_code == 404 and refused.json()["detail"]["code"] == "FORMAT_NOT_SUPPORTED"


def test_b3_a_pending_or_superseded_snapshot_never_gives_its_xml(trial):
    user = trial["user"]
    detail = _approved(trial)
    approved = detail["approved_snapshot"]["id"]
    assert _xml(user, detail, approved).status_code == 200
    # Reopened for a correction: the approval is superseded, and its file never downloads again (audit fix 5).
    detail = _ok(user.post(f"{REPORTS}/{detail['id']}/reopen", json={"reason": "Correct the event description"}))
    refused = _xml(user, detail, approved)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SNAPSHOT_NOT_APPROVED", refused.text
    # Sent again, and again: neither the snapshot awaiting approval nor the one it replaced gives its XML.
    first = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))["pending_snapshot"]["id"]
    second = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))["pending_snapshot"]["id"]
    for snapshot in (first, second):
        assert _xml(user, detail, snapshot).status_code == 409


def test_b3_neither_pdf_comes_from_a_superseded_snapshot(trial):
    from reports.pdf import text_of

    user = trial["user"]
    detail = _start_rv06(trial)  # reopened and sent again by the test before: one approval superseded, one pending
    url = f"{REPORTS}/{detail['id']}/worksheet.pdf"
    superseded = [row for row in detail["snapshots"] if row["state"] == "SUPERSEDED" and row["approved_by"]]
    assert superseded and detail["pending_snapshot"], [row["state"] for row in detail["snapshots"]]
    for form in ({}, {"form": "official"}):
        refused = user.get(url, params={"snapshot": superseded[0]["id"], **form})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SNAPSHOT_NOT_APPROVED", form
    # The snapshot awaiting approval: its frozen file previews as a DRAFT; the official form waits for approval (D7).
    pending = detail["pending_snapshot"]["id"]
    preview = user.get(url, params={"snapshot": pending})
    assert preview.status_code == 200 and "DRAFT - NOT APPROVED" in text_of(preview.content)
    refused = user.get(url, params={"snapshot": pending, "form": "official"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "APPROVE_FIRST"


# --------------------------------------------------------------------------------------------- A9 (the sample)


def _sample_us(db, tenant_id):
    from backend.app.db.models.authority_reports import ReportSnapshot
    from backend.app.trial.sample_data import SAMPLE_SOURCE

    report = (
        db.query(ReportObligation)
        .filter_by(tenant_id=tenant_id, form_code="FDA_3500A", source_system=SAMPLE_SOURCE)
        .one()
    )
    snapshot = db.query(ReportSnapshot).filter_by(obligation_id=report.id, state="APPROVED").one()
    return report, snapshot


def test_b3_the_sample_us_report_gives_both_pdfs_and_the_xml(trial):
    """A9: the trial's finished US example (SAMPLE-RV-09) is FDA-valid, so its approval froze the eMDR file; a trial
    made before 0.10.96 gets it once from the refresh step. The trial's own first number is still asked (the A3 test)."""
    from backend.app.authority_reports import emdr, emdr_pdf
    from backend.app.db.models.regulatory_reference import MarketResponsibleParty
    from backend.app.trial import sample_0_10_96
    from backend.app.trial.sample_reports import US_PARTY
    from reports.pdf import text_of
    from tests.test_fda_3500a_emdr import _fields

    user, tenant_id = trial["user"], trial["tenant_id"]

    def files() -> bytes:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            report, snapshot = _sample_us(db, tenant_id)
            report_id, snapshot_id = str(report.id), str(snapshot.id)
        xml = _xml(user, {"id": report_id}, snapshot_id)
        assert xml.status_code == 200, xml.text
        url = f"{REPORTS}/{report_id}/worksheet.pdf"
        default = user.get(url, params={"snapshot": snapshot_id})
        official = user.get(url, params={"snapshot": snapshot_id, "form": "official"})
        assert default.status_code == official.status_code == 200, (default.text, official.text)
        assert emdr_pdf.TITLE in text_of(default.content)
        assert _fields(official.content)["manuEmail"] == US_PARTY["contact_email"]
        return xml.content

    xml = files()
    assert emdr.validate(xml) == []
    found = emdr_pdf.read(xml)
    assert found["G8"] == [f"0000000-{found['B4'][0][:4]}-70001"]  # a practice number (FDA's test sequences: 7)
    for block in ("clinical", "impact", "problem", "component", "type", "findings", "conclusions"):
        assert found[f"H6 {block}"], block  # each IMDRF code with its FDA code
    assert found["G1 email"] == [f"mailto:{US_PARTY['contact_email']}"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        # The sample's US manufacturer was there only while the report was frozen: the organization's stay its own.
        assert db.query(MarketResponsibleParty).filter_by(organisation=US_PARTY["organisation"]).first() is None
        assert sample_0_10_96.refresh(db, tenant_id, apply=False) == 0  # a new trial has it
        # As a trial made before 0.10.96 had it: typed values, and an approved snapshot without a file.
        report, snapshot = _sample_us(db, tenant_id)
        old = {"value": "SAMPLE-0000000-2026-00001 (sample)", "by": report.created_by, "at": "2026-01-01T00:00:00"}
        report.entries = {**report.entries, "MFR_REPORT": old, "G8": old}
        snapshot.fields = {key: value for key, value in snapshot.fields.items() if not key.startswith("emdr_")}
        db.commit()
        assert sample_0_10_96.refresh(db, tenant_id, apply=False) == 1
        assert sample_0_10_96.refresh(db, tenant_id, apply=True) == 1
        db.commit()
        assert sample_0_10_96.refresh(db, tenant_id, apply=True) == 0  # idempotent
        report, snapshot = _sample_us(db, tenant_id)
        assert "G8" not in report.entries and "emdr_xml" in snapshot.fields
    # The approval re-recorded on the new fingerprint, so the files download again.
    assert emdr.validate(files()) == []


def test_b3_the_refresh_lists_the_sample_us_file_only_when_it_can_add_it(monkeypatch):
    """F3: a trial made while the code lists were not loaded has its US example approved without an eMDR file, and
    the refresh cannot add one either (no FDA codes); its listing said "would add" on every run all the same. The
    listing and the apply now agree, with or without the code lists, and the listing changes nothing."""
    from backend.app import regulatory_reference
    from backend.app.trial import sample_0_10_96
    from backend.app.trial.retention import purge_trial
    from tests.code_lists import ensure_loaded
    from tests.test_free_trial import _approved_trial_client

    ensure_loaded()
    with monkeypatch.context() as unloaded:
        unloaded.setattr(regulatory_reference, "newest_release", lambda control: None)
        _, approval, _ = _approved_trial_client()
        tenant_id = uuid.UUID(approval["tenant_id"])
        try:
            with SessionLocal() as db:
                bind_tenant(db, tenant_id)
                report, snapshot = _sample_us(db, tenant_id)
                entries, fields = dict(report.entries), dict(snapshot.fields)
                assert "emdr_xml" not in fields
                assert sample_0_10_96.refresh(db, tenant_id, apply=False) == 0
                assert sample_0_10_96.refresh(db, tenant_id, apply=True) == 0
                db.commit()
                report, snapshot = _sample_us(db, tenant_id)
                assert report.entries == entries and snapshot.fields == fields  # left exactly as it was
                unloaded.undo()  # the code lists loaded: the file is owed, listed once, and added once
                assert sample_0_10_96.refresh(db, tenant_id, apply=False) == 1
                assert "emdr_xml" not in _sample_us(db, tenant_id)[1].fields  # the listing changed nothing
                assert sample_0_10_96.refresh(db, tenant_id, apply=True) == 1
                db.commit()
                assert sample_0_10_96.refresh(db, tenant_id, apply=False) == 0
        finally:
            with SessionLocal() as db:
                purge_trial(db, tenant_id, "test:release-0-10-96-cleanup")
