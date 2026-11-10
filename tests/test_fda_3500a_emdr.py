"""An approved US report on FDA's own Form 3500A (09/2025) and as FDA's eMDR file (HL7 ICSR XML).

The form: FDA's fillable PDF (static XFA with an AcroForm copy) filled block by block from the approved snapshot, the
XFA layer dropped so every viewer shows the values, MDARIX's record page last. The file: validated against the eMDR
Implementation Package's schemas, refused while a block FDA requires is missing, and compared with FDA's own examples
("Manufacturer Initial - Typical" and "User Facility Initial", their data fed in)."""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from lxml import etree
from pypdf import PdfReader

from backend.app.authority_reports import emdr, fda_3500a
from reports.pdf import text_of

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 4, 9, 30, 5, tzinfo=timezone.utc)
CONTACT = (
    "Medisynth Devices (Sample), Plot 4, MIDC, Pune, India; contact: Jane Doe, +1(240)276-0001, mdr@example.invalid"
)


def _party(**extra):
    base = dict(
        id=None,
        market="US",
        role="MANUFACTURER",
        organisation="Medisynth Devices (Sample)",
        address="Plot 4, MIDC, Pune, India",
        contact_name="Jane Doe",
        contact_phone="+1(240)276-0001",
        contact_email="mdr@example.invalid",
    )
    return SimpleNamespace(**{**base, **extra})


def _sections(values: dict) -> list[dict]:
    return [{"fields": [{"id": key, "number": "", "label": key, "value": value} for key, value in values.items()]}]


REPORT = {
    "MFR_REPORT": "1234567-2026-00001",
    "A1": "PT-0006",
    "A2": "64 years",
    "A3": "Female",
    "A4": "71 kg",
    "B1": "Adverse event; Product problem (e.g., defects/malfunctions)",
    "B2": "Required intervention to prevent permanent impairment/damage",
    "B3": "2026-10-02",
    "B4": "2026-11-04",
    "B5": "The monitor read SpO2 4 to 6 points high against a reference oximeter.",
    "D1": "PulseWatch 410",
    "D2A": "DQA",
    "D2B": "Oximeter",
    "D3": CONTACT,
    "D4_MODEL": "PW-410 2.1",
    "D4_LOT": "L2026-07",
    "D4_EXPIRY": "2028-01-31",
    "D5": "Health professional",
    "D8": "Unknown",
    "D9": "Returned to manufacturer",
    "E2": "Yes",
    "E3": "Nurse",
    "E4": "Unknown",
    "G1": CONTACT,
    "G2": "Health professional",
    "G3": "2026-10-03",
    "G4": "K123456",
    "G6": "30-day; Initial",
    "G8": "1234567-2026-00001",
    "H1": "Serious injury; Malfunction",
    "H3": "Case INV-0004: closed",
    "H5": "Yes",
    "H6_CLINICAL": "E0101 Term (FDA 1884)",
    "H6_IMPACT": "F0101 Term (FDA 1802)",
    "H6_PROBLEM": "A090807 High Readings (FDA 2896)",
    "H6_COMPONENT": "G01 Term (FDA 765)",
    "H6_TYPE": "B01 Term (FDA 10)",
    "H6_FINDINGS": "C01 Term (FDA 202)",
    "H6_CONCLUSIONS": "D01 Term (FDA 4318); D9999 Not mapped",
    "H11": "Case INV-0004: closed",
}
SIGNATURE = {
    "signer_name": "Rahul Colleague",
    "signer_role": "Leader",
    "signed_at": "2026-11-04T09:02:00+00:00",
    "meaning": "Approved for submission",
    "record_business_id": "SIG-0001",
    "record_id": "r1",
    "content_fingerprint": "ab" * 32,
}


def _view(values: dict, practice: bool = True) -> dict:
    return {
        "sections": _sections(values),
        "complaint": {"ref": "SAMPLE-RV-06", "product_name": "PulseWatch 410", "version": "2.1"},
        "form": {"version": "Form FDA 3500A (09/2025)"},
        "snapshot": {"version": 1, "same_person": False},
        "preparers": ["Asha Rao"],
        "practice_label": "Practice record" if practice else None,
        "signature": SIGNATURE,
        "signatures": [],
    }


def _fields(pdf: bytes) -> dict[str, str]:
    """Every filled field's value by its own name (its /T): text, or a box's state."""
    out = {}
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for annotation in page.get("/Annots") or []:
            widget = annotation.get_object()
            if widget.get("/T") and widget.get("/V") not in (None, "", "/Off"):
                out[str(widget["/T"])[:-3]] = str(widget["/V"])
    return out


# --------------------------------------------------------------------------------------------- the form


def test_the_blank_form_is_fdas_own_file_a_static_xfa_form_with_acroform_fields():
    manifest = json.loads((ROOT / "data/fda_forms/manifest.json").read_text(encoding="utf-8"))
    entry = manifest["files"][0]
    assert hashlib.sha256(fda_3500a.FORM_FILE.read_bytes()).hexdigest() == entry["sha256"]
    for name, digest in manifest["files"][1]["sha256"].items():
        assert hashlib.sha256((emdr.SCHEMA.parent / name).read_bytes()).hexdigest() == digest, name
    form = PdfReader(fda_3500a.FORM_FILE).trailer["/Root"]["/AcroForm"]
    assert "/XFA" in form and len(PdfReader(fda_3500a.FORM_FILE).get_fields()) > 300


def test_the_approved_values_fill_fdas_form_block_by_block_and_every_viewer_shows_them():
    pdf = fda_3500a.render(
        _view(REPORT), "Medisynth Devices (Sample)", emdr.office([_party()], emdr.OFFICE_ROLES, CONTACT)
    )
    reader = PdfReader(io.BytesIO(pdf))
    root = reader.trailer["/Root"]
    # The XFA layer and its viewer check are gone, so Chrome, Edge and Acrobat all read the AcroForm values.
    assert "/XFA" not in root["/AcroForm"] and bool(root["/AcroForm"]["/NeedAppearances"])
    assert "/JavaScript" not in root.get("/Names", {})
    assert len(reader.pages) == 10  # FDA's nine pages, then MDARIX's record page
    fields = _fields(pdf)
    assert fields["mfr"] == fields["manuRepNum"] == "1234567-2026-00001"
    assert (fields["patAge"], fields["ageYrs"], fields["patWeight"], fields["weightKG"]) == ("64", "/1", "71", "/1")
    assert fields["sexF"] == "/1" and "sexM" not in fields
    assert fields["adverse"] == fields["prodProblem"] == fields["reqInterv"] == "/1"
    assert (fields["dateAdvEvent"], fields["dateReport"], fields["expDate"]) == (
        "02-Oct-2026",
        "04-Nov-2026",
        "31-Jan-2028",
    )
    assert (fields["brandName"], fields["proCode"], fields["commonName"]) == ("PulseWatch 410", "DQA", "Oximeter")
    assert fields["devOpHP"] == "/1" and fields["evalRet"] == "/1" and fields["repHPY"] == "/1"
    assert fields["repOccupation"] == "Nurse"
    # G1 in its four boxes, from the contact office the report was approved with.
    assert fields["manuName"] == "Medisynth Devices (Sample) (contact: Jane Doe)"
    assert (fields["manuEmail"], fields["manuPhone"]) == ("mdr@example.invalid", "+1(240)276-0001")
    assert fields["repsrcHP"] == "/Yes" and fields["rep30"] == fields["repInit"] == "/Yes"
    assert fields["eventSInj"] == fields["eventMal"] == "/Yes" and "eventDeath" not in fields
    assert (fields["devProbCode2"], fields["invConc"]) == ("2896", "4318")
    # The record page: MDARIX's own, the practice label, who prepared and approved it, the checksum.
    record = reader.pages[-1].extract_text()
    assert "MDARIX record - not part of Form FDA 3500A" in record and "Practice record: free trial" in record
    assert "Asha Rao" in record and "Rahul Colleague" in record and "ab" * 32 in record.replace("\n", "")


def test_unknown_is_never_no_and_a_value_that_is_no_choice_ticks_nothing():
    pdf = fda_3500a.render(_view(REPORT), "Org")
    fields = _fields(pdf)
    assert fields["thirdParU"] == "/1" and "thirdParN" not in fields and "thirdParY" not in fields
    assert fields["reportFDAU"] == "/1" and "reportFDAN" not in fields
    # H3 holds the case's state, not FDA's Yes or No: neither box, and the record page says so.
    assert "evalManuY" not in fields and "evalManuN" not in fields
    _, left = fda_3500a.placements(_sections(REPORT))
    assert ("H3", "Case INV-0004: closed", "not one of the form's choices") in left
    assert ("H6_CONCLUSIONS", "D9999 Not mapped", "no FDA code is mapped to it") in left


def test_a_missing_value_stays_blank_and_g1_without_its_settings_goes_whole_in_the_name_box():
    values = {key: value for key, value in REPORT.items() if key not in ("B3", "D4_LOT")}
    fields = _fields(fda_3500a.render(_view(values, practice=False), "Org"))
    assert "dateAdvEvent" not in fields and "lotNum" not in fields
    assert fields["manuName"] == CONTACT and "manuEmail" not in fields
    record = text_of(fda_3500a.record_page(_view(values, practice=False), "Org", []))
    assert "Practice record" not in record and "MDARIX record - not part of Form FDA 3500A" in record


def test_a_long_description_continues_on_page_two_at_a_word_and_the_limits_are_the_forms():
    words = "The pump alarmed during set-up and stopped the infusion. " * 80
    pages, left = fda_3500a.placements(_sections({"B5": words.strip()}))
    first, second = pages[1]["advEvDesc[0]"], pages[2]["advEvDescribe[0]"]
    assert len(first) <= 2500 and first.endswith(" ") and first + second == words.strip() and not left
    widths = {}
    for page in PdfReader(fda_3500a.FORM_FILE).pages:
        for annotation in page["/Annots"]:
            widget = annotation.get_object()
            widths[str(widget.get("/T"))] = widget.get("/MaxLen")
    for field_id, limit in fda_3500a.LIMITS.items():
        assert widths[fda_3500a.TEXT[field_id][1] + "[0]"] == limit, field_id


# --------------------------------------------------------------------------------------------- the eMDR file


def test_the_emdr_file_validates_against_fdas_schema_and_carries_the_ids():
    missing, left = emdr.check(_sections(REPORT), [_party()])
    assert missing == []
    assert "H3: not one of FDA's choices" in left and "H6_CONCLUSIONS: D9999 Not mapped (no FDA code)" in left
    xml = emdr.build(_sections(REPORT), [_party()], sender="Medisynth Devices (Sample)", now=NOW, practice=True)
    assert emdr.validate(xml) == []
    doc = _plain(xml)
    # The batch ID is the registration number that starts G8, with the time the file is made; one message of one.
    assert doc.xpath("/PORR_IN040001UV01/id/@extension") == ["1234567-20261104093005"]
    assert doc.xpath("//batchTotalNumber/@value") == ["1"] and doc.xpath("//message/id/@extension") == ["1"]
    assert doc.xpath("//controlActProcess/subject/investigationEvent/id/@extension") == ["1234567-2026-00001"]
    assert b"Practice record: free trial" in xml and b"MDARIX never submits" in xml
    # Unknown is sent as unknown (no value), never as No.
    assert doc.xpath("//observation/code[@code='C85488']/../value/@nullFlavor") == ["ASKU"]
    assert doc.xpath("//primarySourceReport/receiver/@negationInd") == []
    assert b"practice" not in emdr.build(_sections(REPORT), [_party()], sender="Org", now=NOW, practice=False).lower()


def test_a_report_with_only_what_fda_requires_validates():
    required = ("MFR_REPORT", "B1", "B5", "D2A", "G1", "H1", *emdr.REQUIRED_CODES)
    values = {key: REPORT[key] for key in required}
    assert emdr.check(_sections(values), [_party()])[0] == []
    assert emdr.validate(emdr.build(_sections(values), [_party()], sender="Org", now=NOW, practice=False)) == []


def test_a_block_fda_requires_stops_the_file_and_is_named():
    values = {key: value for key, value in REPORT.items() if key not in ("H6_COMPONENT", "D2A")}
    values["G8"] = "MDX-2026-0001"
    values["H6_TYPE"] = "B01 Term"  # an IMDRF code FDA's mapping has no code for
    values["G1"] = CONTACT.removesuffix(", mdr@example.invalid")  # as the worksheet reads a party with no email
    missing, _ = emdr.check(_sections(values), [_party(contact_email=None)])
    assert missing == [
        "D2A: missing",
        "G8: FDA's format is your 7-digit CFN or 10-digit FEI, the year and a 5-digit number (1234567-2026-00001)",
        "G1: the contact office needs an email of up to 50 characters (in Settings)",
        "H6_COMPONENT: at least one code with its FDA code",
        "H6_TYPE: at least one code with its FDA code (none of these has one)",
    ]
    # Settings changed after approval (or G1 typed on the report): the file waits for a report that reads the same.
    assert emdr.check(_sections(REPORT), [_party(organisation="Other name")])[0][0].startswith("G1: set your")
    assert emdr.check(_sections({**REPORT, "B5": "Ελλάδα"}), [_party()])[0] == [
        "B5: has characters FDA's eMDR does not take (Windows-1252 only)"
    ]


# --------------------------------------------------------------------------------------------- FDA's examples

EXAMPLES = ROOT / "tests" / "fixtures" / "emdr_examples"
# FDA's XPaths (HL7Medwatch.xlsx, 3500A_HL7_Pointers) of the blocks MDARIX carries, namespace left out.
IE = "//message/controlActProcess/subject/investigationEvent"
DEV = IE + "/pertainsTo/procedureEvent/device/identifiedDevice"
POINTERS = {
    "version": "//versionCode/@code",
    "G8": IE + "/id/@extension",
    "B1": IE + "/code/@code",
    "B2": IE + "/pertinentInformation2/caseSeriousness/code[@code='C49489']/../value/@code",
    "B3": IE + "/trigger/reaction/effectiveTime/@value",
    "B4": "//message/controlActProcess/effectiveTime/@value",
    "B5": IE + "/trigger/reaction/text/text()",
    "B6": IE
    + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='C36292']/../value/text()",
    "B7": IE
    + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='C53263']/../value/text()",
    "A3": IE + "/trigger/reaction/subject/investigativeSubject/subjectAffectedPerson/administrativeGenderCode/@code",
    "A2": IE
    + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='C25150']/../value/@value",
    "A4": IE
    + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='C25208']/../value/@value",
    "D1": DEV + "/identifiedDevice/inventoryItem/manufacturedDeviceModel/manufacturerModelName/text()",
    "D2 procode": DEV + "/identifiedDevice/inventoryItem/manufacturedDeviceModel/code/@code",
    "D2 common name": DEV + "/identifiedDevice/inventoryItem/manufacturedDeviceModel/code/originalText/text()",
    "D4 model": DEV + "/identifiedDevice/inventoryItem/manufacturedDeviceModel/id/@extension",
    "D4 lot": DEV + "/identifiedDevice/lotNumberText/text()",
    "D4 catalog": DEV + "/identifiedDevice/asManufacturedProduct/id/@extension",
    "D4 expiry": DEV + "/identifiedDevice/expirationTime/@value",
    "D4 serial": DEV + "/identifiedDevice/id/@extension",
    "D4 UDI": DEV + "/identifiedDevice/asManufacturedProduct/code/@code",
    "D5": IE + "/pertainsTo/procedureEvent/authorOrPerformer/assignedEntity/code/@code",
    "D6A": IE + "/pertainsTo/procedureEvent/component1/implantation/effectiveTime/@value",
    "D6B": IE + "/pertainsTo/procedureEvent/component2/explantation/effectiveTime/@value",
    "D7A": IE + "/pertainsTo/procedureEvent/pertinentInformation1/observation/code[@code='C53563']/../value/@value",
    "D8": IE + "/pertainsTo/procedureEvent/pertinentInformation1/observation/code[@code='C85488']/../value/@value",
    "D9": DEV + "/subjectOf/deviceObservation/code[@code='C53449']/../value/@value",
    "D10": IE + "/pertainsTo/procedureEvent/pertinentInformation1/observation/code[@code='C53630']/../value/text()",
    "E3": IE + "/trigger/reaction/pertinentInformation/primarySourceReport/author/assignedEntity/code/@code",
    "E4": IE + "/trigger/reaction/pertinentInformation/primarySourceReport/receiver/@negationInd",
    "G1 email": DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor/contactParty[1]/telecom"
    "[starts-with(@value, 'mailto:')]/@value",
    "G1 phone": DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor/contactParty[1]/telecom"
    "[starts-with(@value, 'tel:')]/@value",
    "G2": "//message/controlActProcess/reasonOf/detectedIssueEvent/code[@code='C53566']/../value/@code",
    "G3": IE + "/pertinentInformation1/secondaryCaseNotification/receiver/time/high/@value",
    "G6": "//message/controlActProcess/reasonOf/detectedIssueEvent/code[@code='C53571']/../value/@code",
    "H1": "//message/controlActProcess/reasonOf/detectedIssueEvent/code[@code='C53570']/../value/@code",
    "H3": DEV + "/subjectOf/deviceObservation/code[@code='C53629']/../value/@value",
    "H4": DEV + "/identifiedDevice/existenceTime/@value",
    "H5": DEV + "/subjectOf/deviceObservation/code[@code='C53602']/../value/@value",
    "H6 clinical": IE
    + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='C53983']/../value/@code",
    "H6 impact": IE
    + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='C122929']/../value/@code",
    "H6 problem": DEV + "/subjectOf/deviceObservation/code[@code='C53982']/../value/@code",
    "H6 component": DEV + "/subjectOf/deviceObservation/code[@code='C54577']/../value/@code",
    "H6 type": DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor/asRole/performance"
    "/investigationEvent/component3/evaluationMethod/code[@code='C53984']/../value/@code",
    "H6 findings": DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor/asRole/performance"
    "/investigationEvent/component1/evaluationResult/code[@code='C53985']/../value/@code",
    "H6 conclusions": DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor/asRole/performance"
    "/investigationEvent/component2/evaluationConclusion/code[@code='C53986']/../value/@code",
    "H7": DEV + "/subjectOf/deviceObservation/code[@code='C53603']/../value/@code",
    "H8": DEV + "/subjectOf/deviceObservation/code[@code='C53645']/../value/@code",
    "H9": DEV + "/subjectOf/deviceObservation/code[@code='C53619']/../value/text()",
    "H10": DEV + "/subjectOf/deviceObservation/code[@code='C103162']/../value/text()",
    "H11": IE + "/text/text()",
}
# FDA's "Manufacturer Initial - Typical", as MDARIX holds it once approved (the example's PDF, block by block).
TYPICAL = {
    "MFR_REPORT": "1234567-2023-00001",
    "G8": "1234567-2023-00001",
    "A1": "JD",
    "A2": "50 years",
    "A3": "Male",
    "A4": "180 lb",
    "B1": "Adverse event; Product problem",
    "B2": "Death; Other serious or important medical events",
    "B3": "2023-07-01",
    "B4": "2023-08-01",
    "B5": "Sample event narrative.",
    "B6": "Sample lab test narrative.",
    "B7": "Sample medical history narrative.",
    "D1": "BYPASS BRAND",
    "D2A": "DSQ",
    "D2B": "VENTRICULAR (ASSIST) BYPASS",
    "D4_MODEL": "M2000",
    "D4_LOT": "L000001234",
    "D4_CATALOG": "C4512",
    "D4_EXPIRY": "2025-01-01",
    "D4_SERIAL": "S100012345",
    "D4_UDI": "(01)51022222233336(11)141231(17)150707(10)A213B1(21)1234",
    "D5": "Other: Technician",
    "D6A": "2023-06-30",
    "D6B": "2023-07-01",
    "D7A": "Yes",
    "D8": "Yes",
    "D9": "Returned to manufacturer",
    "D10": "Concomitant Product 1",
    "E3": "Physician",
    "E4": "Yes",
    "G1": "Bypass Mfr G1 Contact; contact: Pam Reese, +1(703)925-8821x12345, pam.a.reese@bypassmfr.com",
    "G2": "Health professional; User facility; Other source description",
    "G3": "2023-07-02",
    "G4": "P012345",
    "G6": "30-day; Initial",
    "H1": "Death",
    "H3": "No",
    "H4": "2022-12-01",
    "H5": "No",
    "H6_CLINICAL": "E1 (FDA 1884); E2 (FDA 1708)",
    "H6_IMPACT": "F1 (FDA 1802); F2 (FDA 4634)",
    "H6_PROBLEM": "A1 (FDA 2896); A2 (FDA 1384)",
    "H6_COMPONENT": "G1 (FDA 765); G2 (FDA 527)",
    "H6_TYPE": "B1 (FDA 10); B2 (FDA 4110)",
    "H6_FINDINGS": "C1 (FDA 202); C2 (FDA 110)",
    "H6_CONCLUSIONS": "D1 (FDA 4318); D2 (FDA 4302)",
    "H7": "Recall; Repair; Other remedial action description",
    "H8": "Initial use of device",
    "H9": "RN12345",
    "H10": "1234567890-2023-00001; MW12345678",
    "H11": "Sample additional manufacturer narrative.",
}
TYPICAL_PARTY = _party(
    organisation="Bypass Mfr G1 Contact",
    address=None,
    contact_name="Pam Reese",
    contact_phone="+1(703)925-8821x12345",
    contact_email="pam.a.reese@bypassmfr.com",
)
# What MDARIX does not send that FDA's example does, block by block, and why: a 3500A value MDARIX does not hold in
# FDA's parts (dates of death and of return, race, ethnicity and gender, a person's name and an address in parts, a
# fax, D3's manufacturer and a reprocessor), "Other" with its words (D5, G2, H7), a second device BLA number, an
# exemption number, adverse event terms (G7, drugs only), an attachment, and section F's user facility blocks.
NOT_SENT = {
    "D5": ["C17649"],  # "Other: Technician"
    "D10": ["Concomitant Product 2"],  # MDARIX holds D10 as one text
    "G2": ["C17649"],  # "Other source description"
    "H7": ["C17649"],  # "Other remedial action description"
}


def _plain(xml: bytes):
    """The document with its namespace left out, so FDA's XPaths read it as written."""
    doc = etree.fromstring(xml)
    for element in doc.iter():
        if isinstance(element.tag, str):
            element.tag = etree.QName(element).localname
    etree.cleanup_namespaces(doc)
    return doc.getroottree()


def _paths(doc) -> set[str]:
    out = set()
    for element in doc.iter():
        if not isinstance(element.tag, str):
            continue
        parts, node = [], element
        while node is not None:
            code = node.find("code")
            tag = node.tag
            if (
                tag in ("observation", "deviceObservation", "detectedIssueEvent", "caseSeriousness")
                and code is not None
            ):
                tag += f"[{code.get('code')}]"
            parts.append(tag)
            node = node.getparent()
        out.add("/".join(reversed(parts)))
    return out


def _example(name: str):
    return _plain((EXAMPLES / name).read_bytes())


def test_fdas_manufacturer_initial_typical_example_is_reproduced_block_by_block():
    missing, left = emdr.check(_sections(TYPICAL), [TYPICAL_PARTY])
    assert missing == []
    xml = emdr.build(_sections(TYPICAL), [TYPICAL_PARTY], sender="USA Device Manufacturer", now=NOW, practice=False)
    assert (
        emdr.validate(xml) == [] and emdr.validate((EXAMPLES / "Manufacturer Initial - Typical.xml").read_bytes()) == []
    )
    ours, theirs = _plain(xml), _example("Manufacturer Initial - Typical.xml")
    for block, path in POINTERS.items():
        expected = sorted(value for value in theirs.xpath(path) if value not in NOT_SENT.get(block, []))
        assert sorted(ours.xpath(path)) == expected, block
    # No element FDA's example lacks: MDARIX's file is FDA's structure, with fewer blocks filled.
    assert _paths(ours) <= _paths(theirs), sorted(_paths(ours) - _paths(theirs))
    # The left-out values are said, never dropped in silence.
    assert "D5: not one of FDA's choices" in left and "H7: not one of FDA's choices" in left


def test_fdas_user_facility_initial_example_matches_in_the_blocks_a_manufacturer_shares():
    # A user facility's report (section F) is not one MDARIX makes: its shared blocks (A, B, D, E and the codes FDA
    # places at the same XPaths as H6) are fed in and compared; F and the facility's report number are not.
    keys = ("A1", "A3", "B1", "B3", "B4", "B5", "B6", "B7", "D1", "D2A", "D2B", "D4_MODEL", "D4_LOT", "D4_CATALOG")
    shared = {
        key: TYPICAL[key] for key in (*keys, "D4_EXPIRY", "D4_SERIAL", "D4_UDI", "D6A", "D6B", "D7A", "D8", "E3", "E4")
    }
    shared |= {
        "MFR_REPORT": "1234567-2023-00001",  # only so the file can be built: the example's own is F2, not G8
        "H6_CLINICAL": "E1 (FDA 1708); E2 (FDA 1884)",
        "H6_IMPACT": "F1 (FDA 1802); F2 (FDA 4634)",
        "H6_PROBLEM": "A1 (FDA 2896); A2 (FDA 1384)",
        "H6_COMPONENT": "G1 (FDA 765); G2 (FDA 527)",
    }
    ours = _plain(emdr.build(_sections(shared), [], sender="USA Device Manufacturer", now=NOW, practice=False))
    theirs = _example("User Facility Initial.xml")
    blocks = ("B1", "B3", "B4", "B5", "B6", "B7", "A3", "D1", "D2 procode", "D2 common name", "D4 model", "D4 lot")
    blocks += ("D4 catalog", "D4 expiry", "D4 serial", "D4 UDI", "D6A", "D6B", "D7A", "D8", "E3", "E4")
    for block in (*blocks, "H6 clinical", "H6 impact", "H6 problem", "H6 component"):
        assert sorted(ours.xpath(POINTERS[block])) == sorted(theirs.xpath(POINTERS[block])), block
    # What only a manufacturer's report has (G and H's reasons and investigation codes) is all that differs in shape.
    extra = {path for path in _paths(ours) - _paths(theirs)}
    assert all(
        "/reasonOf" in path or "/asRole" in path or "/contactParty" in path or path.endswith("investigationEvent/id")
        for path in extra
    ), sorted(extra)


@pytest.mark.parametrize(
    "name",
    [
        "Manufacturer Initial - Typical.xml",
        "Manufacturer Initial - Typical.pdf",
        "Manufacturer Follow-up.xml",
        "Manufacturer Follow-up.pdf",
        "User Facility Initial.xml",
    ],
)
def test_the_examples_kept_here_are_fdas_files(name):
    manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
    data = (EXAMPLES / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == manifest[name]
    assert re.search(rb"V3NORMED_2016", data) if name.endswith(".xml") else data.startswith(b"%PDF-")
    # Every file in the folder is one of FDA's, named in the manifest.
    assert {path.name for path in EXAMPLES.iterdir()} - {"manifest.json"} == set(manifest) - {"note"}


def test_fdas_follow_up_example_validates_against_fdas_schema():
    # The follow-up (supplemental) report FDA publishes passes the schema MDARIX validates with, so a follow-up built
    # the same way (G6 "Follow-up" with its number, H2 types, nullFlavor in the parts the schema needs) will too.
    data = (EXAMPLES / "Manufacturer Follow-up.xml").read_bytes()
    assert emdr.validate(data) == []
    doc = _plain(data)
    assert doc.xpath(IE + "/id/@extension") == ["1234567-2023-00001"]  # the initial report's number (G8)
    g6 = "//message/controlActProcess/reasonOf/detectedIssueEvent[code/@code='C53571']"
    assert doc.xpath(g6 + "/value/@code") == ["C53577", "C53579"]  # G6: 30-day, and Follow-up
    assert doc.xpath(g6 + "[value/@code='C53579']/text/text()") == ["1"]  # the follow-up's number
    h2 = "//message/controlActProcess/reasonOf/detectedIssueEvent[code/@code='C53584']/value/@code"
    assert doc.xpath(h2) == ["C53585", "C53586"]  # H2: two follow-up types ticked


# --------------------------------------------------------------------------------------------- B1 (0.10.89)


def _event(**flags):
    from backend.app.authority_reports.worksheet import SOURCES

    blank = dict(id=None, death=None, serious_injury=None, patient_involved=None, malfunction=None)
    complaint = SimpleNamespace(**blank | flags)
    record = {"complaint_identifier": "SAMPLE-RV-11", "business_id": "C-1"}
    found = SOURCES["event_type"]({"complaint": complaint, "record": record})
    return found[0] if found else None


def test_b1_ticks_adverse_event_only_for_recorded_harm_never_for_a_patient_merely_involved():
    # SAMPLE-RV-11: a patient connected, no harm, a malfunction: only Product problem (both boxes before 0.10.89).
    assert _event(patient_involved=True, death=False, serious_injury=False, malfunction=True) == (
        "Product problem (e.g., defects/malfunctions)"
    )
    assert _event(death=True) == "Adverse event"
    assert _event(serious_injury=True, malfunction=True) == (
        "Adverse event; Product problem (e.g., defects/malfunctions)"
    )
    # A patient involved with the outcome unknown is no basis for either box: B1 stays empty, never guessed.
    assert _event(patient_involved=True) is None
    # The same rule reaches the form and the eMDR file.
    pages, _ = fda_3500a.placements(_sections({"B1": "Product problem (e.g., defects/malfunctions)"}))
    assert pages[1] == {"prodProblem[0]": fda_3500a.ON}
    assert "B1: adverse event, product problem or both" in emdr.check(_sections({}), [])[0]
