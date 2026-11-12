"""B8 step 8 (B8-13, 14, 15, 18): the EU MIR file frozen at Send for approval, on the sample's EU report
(SAMPLE-RV-07). Send is refused while the authority would refuse the file; the approved snapshot keeps the XML, its
SHA-256 and the parties' parts, under the fingerprint the approver signs; the download serves those bytes, only from
the approved snapshot. A report approved before B8 keeps its PDF and has no XML (B8-D10)."""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader

from backend.app.authority_reports import forms, mir_pdf, mir_xml
from backend.app.authority_reports import router as reports
from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot
from backend.app.db.models.regulatory_reference import MarketResponsibleParty
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.human_decision.rules import fingerprint
from tests.test_authority_reports_api import REPORTS, _fields, _ok, trial  # noqa: F401
from tests.test_b8_mir_chain import _approve, _code, _initial

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.db, pytest.mark.requirement("B8-05", "B8-15", "B8-24", "B8-26")]

PARTIES = "/api/v1/regulatory-reference/responsible-parties"
PARTS = {
    "street": "1 Rue Exemple",
    "city": "Paris",
    "postcode": "75001",
    "country_code": "FR",
    "contact_first_name": "Ana",
    "contact_last_name": "Sample",
    "contact_phone": "+33 1 00 00 00 00",
    "contact_email": "vigilance@example.com",
}
CODES = {"A": "A0401", "B": "B01", "C": "C04", "D": "D01", "E": "E0101", "F": "F27", "G": "G04010"}


def _fill(trial, report_id: str, **typed) -> None:  # noqa: F811
    """Every mandatory field still empty gets a value that fits it (the entry screens have their own tests)."""
    detail = _ok(trial["user"].get(f"{REPORTS}/{report_id}"))
    entries = {}
    for item in _fields(detail).values():
        if item["missing_class"] != forms.MUST or not item["editable"] or (item["value"] and not item["problem"]):
            continue
        if item["code_annex"]:
            entries[item["id"]] = {"value": f"{CODES[item['code_annex']]} Sample term", "codes": ["x"]}
        elif item["options"]:
            entries[item["id"]] = {"value": item["options"][0]}
        elif item["kind"] in ("DATE", "DATE_RANGE"):
            entries[item["id"]] = {"value": "2026-10-29"}
        else:
            entries[item["id"]] = {"value": "Sample text"}
    entries |= {key: {"value": value} for key, value in typed.items()}
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(report_id))
        row.entries = {**(row.entries or {}), **entries}
        db.commit()


@pytest.fixture
def eu_parties(trial):  # noqa: F811
    """The EU manufacturer (in the US) and its authorised representative, with every part (the sample's own are held
    in memory only)."""
    user, made = trial["user"], []
    for role, name, country in (
        ("MANUFACTURER", "Orbit Medical Devices (Sample)", "US"),
        ("AUTHORISED_REPRESENTATIVE", "EU Rep (sample)", "FR"),
    ):
        body = {"market": "EU", "role": role, "organisation": name, **PARTS, "country_code": country}
        made.append(_ok(user.put(PARTIES, json=body)))
    yield made
    for party in made:
        user.delete(f"{PARTIES}/{party['id']}")


@pytest.fixture
def report(trial):  # noqa: F811
    """The sample's EU report, reset, as the organization's own (not the sample's: those read the sample's parties,
    step 12), so these tests read the stored parties; its source and typed values put back afterwards."""
    report_id = _initial(trial)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(report_id))
        kept, source = dict(row.entries or {}), row.source_system
        row.source_system = None
        db.commit()
    yield report_id
    _initial(trial)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.get(ReportObligation, uuid.UUID(report_id))
        row.entries, row.source_system = kept, source
        db.commit()


def _party(trial, party_id: str, **values) -> None:  # noqa: F811
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        party = db.get(MarketResponsibleParty, uuid.UUID(party_id))
        for key, value in values.items():
            setattr(party, key, value)
        db.commit()


def _send(trial, report_id: str):  # noqa: F811
    return trial["user"].post(f"{REPORTS}/{report_id}/snapshots")


def _pending(trial, report_id: str) -> ReportSnapshot:  # noqa: F811
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.query(ReportSnapshot).filter_by(obligation_id=uuid.UUID(report_id), state="PENDING").one()
        db.expunge(row)
        return row


def _approve_pending(trial, report_id: str) -> ReportSnapshot:  # noqa: F811
    """The waiting snapshot approved as the approval flow leaves it (that flow has its own tests)."""
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        row = db.query(ReportSnapshot).filter_by(obligation_id=uuid.UUID(report_id), state="PENDING").one()
        row.state, row.signed_record_id, row.approved_by = "APPROVED", uuid.uuid4(), "test-approver"
        row.approved_at = datetime.now(timezone.utc)
        db.get(ReportObligation, row.obligation_id).state = "APPROVED"
        db.commit()
        db.refresh(row)
        db.expunge(row)
        return row


def _xml(trial, report_id: str, snapshot):  # noqa: F811
    return trial["user"].get(f"{REPORTS}/{report_id}/mir.xml", params={"snapshot": str(snapshot)})


def test_b8_send_is_refused_while_the_authority_would_refuse_the_file(trial, eu_parties, report):  # noqa: F811
    _fill(trial, report, **{"1_2E": forms.MIR_INITIAL})
    user = trial["user"]
    _party(trial, eu_parties[0]["id"], street=None, city=None)  # the manufacturer's street and city not entered yet
    refused = _send(trial, report)
    assert refused.status_code == 422 and _code(refused) == "MIR_MISSING", refused.text
    assert refused.json()["detail"]["missing"] == [
        "1.3.2 Orbit Medical Devices (Sample): street, city (Settings, Products)"
    ]
    _party(trial, eu_parties[0]["id"], street="1 Main St", city="Springfield")
    _fill(trial, report, **{"2_4": "Class V"})  # no such class: the schema refuses it
    refused = _send(trial, report)
    assert refused.status_code == 422 and _code(refused) == "MIR_INVALID", refused.text
    assert refused.json()["detail"]["errors"][0].startswith("2.4a-d ")
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    assert detail["mir"]["snapshot"] is None and detail["mir"]["errors"][0].startswith("2.4a-d ")
    # B8 run 4: 2.4 is a fixed list; a class typed before it is shown as "choose again", never changed silently.
    risk = _fields(detail)["2_4"]
    assert (
        risk["value"] == "Class V" and risk["problem"].startswith("Choose again") and "MDR class IIb" in risk["options"]
    )
    assert (
        user.put(f"{REPORTS}/{report}/fields/2_4", json={"value": "Class V"}).json()["detail"]["code"] == "NOT_A_CHOICE"
    )
    _fill(trial, report, **{"2_4": "IIb"})  # typed before the list: read as the MDR class
    assert _fields(_ok(user.get(f"{REPORTS}/{report}")))["2_4"]["value"] == "MDR class IIb"
    _ok(_send(trial, report))
    frozen = _pending(trial, report)
    assert frozen.fields["mir_type"] == forms.MIR_INITIAL
    assert hashlib.sha256(frozen.fields["mir_xml"].encode()).hexdigest() == frozen.fields["mir_sha256"]
    assert frozen.fields["mir_parties"]["MANUFACTURER"]["country_code"] == "US"
    assert "<reportType>Initial</reportType>" in frozen.fields["mir_xml"]


def test_b8_the_xml_downloaded_is_the_one_approved_byte_for_byte(trial, eu_parties, report):  # noqa: F811
    _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "2_4": "IIb"})
    _ok(_send(trial, report))
    frozen = _approve_pending(trial, report)
    user = trial["user"]
    _party(trial, eu_parties[1]["id"], city="Lyon")
    got = _xml(trial, report, frozen.id)
    assert got.status_code == 200 and got.headers["content-type"].startswith("application/xml")
    assert got.content == frozen.fields["mir_xml"].encode("utf-8")  # Settings changed after approval: same bytes
    assert b"<ARCity>Paris</ARCity>" in got.content
    assert _ok(user.get(f"{REPORTS}/{report}"))["mir"]["sha256"] == frozen.fields["mir_sha256"]
    # B8 step 9: the approved report's PDF is its MIR file, read back, with the file's SHA-256 on the record page.
    pdf = user.get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": str(frozen.id)})
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages).replace(chr(10), "")
    assert mir_pdf.TITLE in text and frozen.fields["mir_sha256"] in text


def test_b8_the_fingerprint_covers_the_xml(trial, eu_parties, report):  # noqa: F811
    _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "2_4": "IIb"})
    _ok(_send(trial, report))
    frozen = _pending(trial, report)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        obligation = db.get(ReportObligation, uuid.UUID(report))
        conclusion = obligation.assessment_id

        def mark(fields: dict) -> str:
            sections = fields["sections"]
            return fingerprint(reports.snapshot_material(obligation, fields["complaint"], conclusion, sections, fields))

        assert mark(frozen.fields) == frozen.content_fingerprint
        assert mark({**frozen.fields, "mir_sha256": "0" * 64}) != frozen.content_fingerprint
        assert mark({**frozen.fields, "mir_parties": {}}) != frozen.content_fingerprint


def test_b8_no_xml_before_approval_or_from_a_superseded_snapshot(trial, eu_parties, report, monkeypatch):  # noqa: F811
    _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "2_4": "IIb"})
    _ok(_send(trial, report))
    waiting = _pending(trial, report)
    early = _xml(trial, report, waiting.id)
    assert early.status_code == 409 and _code(early) == "APPROVE_FIRST"
    approved = _approve_pending(trial, report)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        db.get(ReportSnapshot, approved.id).state = "SUPERSEDED"
        db.commit()
    old = _xml(trial, report, approved.id)
    assert old.status_code == 409 and _code(old) == "SNAPSHOT_NOT_APPROVED"
    monkeypatch.setenv("MDARIX_B8_EU_MIR", "0")
    assert _code(_xml(trial, report, approved.id)) == "NOT_AN_EU_MIR"


def test_b8_a_report_approved_before_b8_still_downloads_its_pdf(trial, report):  # noqa: F811
    _approve(trial, report, "APPROVED")  # a snapshot as before B8: its sections, no MIR file
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        snapshot = db.query(ReportSnapshot).filter_by(obligation_id=uuid.UUID(report), state="APPROVED").one().id
    missing = _xml(trial, report, snapshot)
    assert missing.status_code == 404 and _code(missing) == "NO_MIR_FILE"
    pdf = trial["user"].get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": str(snapshot)})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert _ok(trial["user"].get(f"{REPORTS}/{report}"))["mir"] == {
        "snapshot": None,
        "sha256": None,
        "missing": [],
        "errors": [],
    }


def test_b8_the_sample_eu_report_gives_the_pdf_and_the_xml(trial):  # noqa: F811
    """Step 12: RV-07 builds its MIR file from the sample's EU parties held in memory: none is stored."""
    report = _initial(trial)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        kept = dict(db.get(ReportObligation, uuid.UUID(report)).entries or {})
        stored = db.query(MarketResponsibleParty).filter_by(market="EU").count()
    try:
        values = _fields(_ok(trial["user"].get(f"{REPORTS}/{report}")))
        assert values["1_3_2C"]["value"].startswith("Orbit Medical Devices (Sample)")
        assert values["1_3_3"]["value"].startswith("Sample EU Authorised Representative (Sample)")
        _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "2_4": "IIb"})  # the class, as the trial user enters it
        _ok(_send(trial, report))
        frozen = _approve_pending(trial, report)
        xml = _xml(trial, report, frozen.id)
        assert xml.status_code == 200 and mir_xml.validate(xml.content, forms.MIR_INITIAL) == []
        assert b"<ARName>Sample EU Authorised Representative (Sample)</ARName>" in xml.content
        assert b"<ncaName>" in xml.content and b"(ANSM)" in xml.content
        pdf = trial["user"].get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": str(frozen.id)})
        assert mir_pdf.TITLE in "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        with SessionLocal() as db:
            bind_tenant(db, trial["tenant_id"])
            assert db.query(MarketResponsibleParty).filter_by(market="EU").count() == stored
    finally:
        _initial(trial)
        with SessionLocal() as db:
            bind_tenant(db, trial["tenant_id"])
            db.get(ReportObligation, uuid.UUID(report)).entries = kept
            db.commit()
