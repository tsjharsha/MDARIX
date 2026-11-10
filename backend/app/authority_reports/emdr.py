"""The approved US report as FDA's eMDR file: an HL7 ICSR (R2) XML message, built as FDA's eMDR Implementation Package
defines it (HL7Medwatch.xlsx: each 3500A block's XPath, its vocabulary and its field length; the example "Manufacturer
Initial - Typical" for the element order) and validated against the package's own schemas (data/fda_forms).

MDARIX never submits: the customer sends the file through their own ESG account or eSubmitter and records the
submission in MDARIX. The file is an initial manufacturer report (21 CFR 803.50), one report per file.

Values come from the approved snapshot only, read as FDA's choices (fda_3500a.CHOICES); the contact office (G1) and
the manufacturer (D3) come from the organization's US responsible party in Settings, and only while that party still
reads exactly as the approved report does. IDs: the report number is G8; the batch ID is the establishment
registration number that starts G8 with the time the file is made; the message is number 1 of 1. Nothing is invented:

- ``check`` names every block FDA requires for the report type, as the rule book (rules/us_emdr.csv) lists them
  (initial: B5, D2 procode, G1 email, G8, H1 and the seven H6 code kinds; follow-up: G6 with its number and G8;
  FDA's "Required 3500A fields"), and B1, which FDA's schema needs on an initial report, that is missing or
  does not fit FDA's format, and every required value longer than FDA's field or outside FDA's character set
  (Windows-1252). Any of these blocks the file.
- ``left_out`` names approved values the file does not carry (not one of FDA's choices, too long for an optional
  field, or an address FDA wants in parts). They do not block the file; the screen says them.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from lxml import etree

from backend.app.authority_reports import fda_3500a as fda

SCHEMA = Path(__file__).resolve().parents[3] / "data" / "fda_forms" / "emdr_schemas" / "Con170227.xsd"
HL7 = "urn:hl7-org:v3"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
NCI = "2.16.840.1.113883.3.26.1.1"
FDA_OID = "2.16.840.1.113883.3.24"
REPORT_NUMBER = re.compile(r"^(\d{7}|\d{10})-\d{4}-\d{5,7}$")
PHONE = re.compile(r"^\+\d{1,3}\(\d{1,5}\)\d{3,4}-\d{4}(x\d{1,5})?$")
OFFICE_ROLES, MAKER_ROLES = ("MANUFACTURER", "IMPORTER"), ("MANUFACTURER",)
REQUIRED_CODES = ("H6_CLINICAL", "H6_IMPACT", "H6_PROBLEM", "H6_COMPONENT", "H6_TYPE", "H6_FINDINGS", "H6_CONCLUSIONS")
# FDA's field lengths (HL7Medwatch.xlsx, "Field Lengths") for the text MDARIX places.
LENGTHS = {
    "A1": 10,
    "D1": 80,
    "D2A": 3,
    "D2B": 80,
    "D4_MODEL": 80,
    "D4_LOT": 30,
    "D4_CATALOG": 30,
    "D4_SERIAL": 30,
    "D4_UDI": 150,
    "D10": 50,
    "G4": 12,
    "G8": 23,
    "H9": 50,
}
_REQUIRED_TEXT = {"B5", "D2A"}  # and G8, which follows the front page's number
_DATES = {"B3", "B4", "D4_EXPIRY", "D6A", "D6B", "G3", "H4"}
# The rule book (decision D17): the manufacturer rows of the mapping workbook's US sheet, exported by
# scripts/export_us_emdr_rules.py. Its block numbers are FDA's package's (D2B is the procode); the report's fields
# follow the 09/2025 form (D2A is the procode). A required row with no field here fails at the first check.
RULES = Path(__file__).with_name("rules") / "us_emdr.csv"
RULE_FIELDS = {
    ("B5", "Describe event or problem"): "B5",
    ("D2B", "Procode"): "D2A",
    ("G1", "Manufacturer Contact Email"): "G1",
    ("G6", "Type of report"): "G6",
    ("G8", "MFR Report #"): "G8",
    ("H1", "Type of reportable event"): "H1",
    ("H6", "Health Effect - Clinical Code"): "H6_CLINICAL",
    ("H6", "Health Effect - Impact Code"): "H6_IMPACT",
    ("H6", "Medical Device Problem Code"): "H6_PROBLEM",
    ("H6", "Component Code"): "H6_COMPONENT",
    ("H6", "Type of Investigation"): "H6_TYPE",
    ("H6", "Investigation Findings"): "H6_FINDINGS",
    ("H6", "Investigation Conclusions"): "H6_CONCLUSIONS",
}
KINDS = {"M-I": "m_i", "M-F": "m_f"}  # manufacturer initial, manufacturer follow-up
FOLLOW_UP = re.compile(r"\bfollow-up #?(\d+)\b", re.IGNORECASE)  # G6 on a follow-up: "30-day; Follow-up #2"


@lru_cache(maxsize=len(KINDS))
def required(kind: str = "M-I") -> frozenset[str]:
    """The report's fields FDA requires on this report type (its "Required 3500A fields"), read from the rule book."""
    with RULES.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row[KINDS[kind]] == "required"]
    return frozenset(RULE_FIELDS[row["block"], row["label"]] for row in rows)


def next_number(numbers: list[str], year: int, practice: bool) -> str | None:
    """The next manufacturer report number (G8; decision D5, owner Q2 and Q5): the CFN or FEI of the organization's
    last number, the year, and the last sequence of that year plus one (5 digits, from 00001 each year). A practice
    report's sequence starts with 7, as FDA's test reports do (70001). None before the organization's first number,
    which a person types once. ``numbers``: every number the organization has used, oldest first."""
    found = [number.split("-") for number in numbers if REPORT_NUMBER.match(number)]
    if not found:
        return None
    prefix = found[-1][0]
    used = [
        int(seq) for cfn, yyyy, seq in found if cfn == prefix and yyyy == str(year) and seq.startswith("7") == practice
    ]
    # shortcut: no guard past 69999 (a real organization's) or 79999 (practice) a year; add one if anyone nears it.
    return f"{prefix}-{year}-{(max(used) + 1 if used else 70001 if practice else 1):05d}"


def office(parties, roles: tuple[str, ...], text: str | None) -> dict | None:
    """The responsible party behind a block's approved text (G1, D3), in parts: only while it reads exactly as the
    approved report does (the worksheet writes the same text from it)."""
    from backend.app.authority_reports.worksheet import _party

    found = _party({"parties": parties}, roles, "")
    if not text or not found or found[0] != text:
        return None
    party = next(item for role in roles for item in parties if item.role == role)
    return {
        "name": party.organisation,
        "address": party.address,
        "person": party.contact_name,
        "email": party.contact_email,
        "phone": party.contact_phone,
    }


def check(sections: list[dict], parties, kind: str = "M-I") -> tuple[list[str], list[str]]:
    """What stops the eMDR file (missing or not in FDA's format), and the approved values it leaves out.

    ``kind`` is the report type (M-I manufacturer initial, M-F manufacturer follow-up): the blocks FDA requires on it
    come from the rule book (``required``); the format of any value given is checked on both."""
    vals, names = fda.values(sections), fda.labels(sections)
    name = lambda key: names.get(key, key)  # noqa: E731
    need = required(kind)
    missing: list[str] = []
    left: list[str] = []
    for key in sorted(_REQUIRED_TEXT & need - set(vals)):
        missing.append(f"{name(key)}: missing")
    number = vals.get("G8") or vals.get("MFR_REPORT")
    if not number:
        if "G8" in need:
            missing.append(f"{name('G8')}: missing")
    elif not REPORT_NUMBER.match(number):
        missing.append(
            f"{name('G8')}: FDA's format is your 7-digit CFN or 10-digit FEI, the year and a 5-digit number "
            "(1234567-2026-00001)"
        )
    if "G6" in need and not FOLLOW_UP.search(vals.get("G6", "")):
        missing.append(f"{name('G6')}: Follow-up with its number (Follow-up #1)")
    if vals.get("D2A") and not re.fullmatch(r"[A-Z]{3}", vals["D2A"]):
        missing.append(f"{name('D2A')}: three capital letters (FDA's product code)")
    contact = office(parties, OFFICE_ROLES, vals.get("G1"))
    if "G1" not in need:
        pass
    elif contact is None:
        missing.append(
            f"{name('G1')}: set your organization's US contact office in Settings, with an email, and approve the "
            "report again so it reads the same"
        )
    elif not contact["email"] or len(contact["email"]) > 50:
        missing.append(f"{name('G1')}: the contact office needs an email of up to 50 characters (in Settings)")
    else:
        if contact["phone"] and not PHONE.match(contact["phone"]):
            left.append(f"{name('G1')} phone: FDA's format is +1(240)276-0001")
        if contact["address"] or contact["person"]:
            left.append(f"{name('G1')} address and contact person: FDA wants them in parts; give them in eSubmitter")
    if vals.get("D3") and office(parties, MAKER_ROLES, vals["D3"]) is None:
        left.append(f"{name('D3')}: not your organization's US manufacturer as set in Settings")
    # FDA's schema needs an initial report's type (B1); a follow-up sends only what is new.
    if kind == "M-I" and not fda.choices("B1", vals.get("B1", ""))[0]:
        missing.append(f"{name('B1')}: adverse event, product problem or both")
    found, other = fda.choices("H1", vals.get("H1", ""))
    if not found and "H1" in need:
        missing.append(f"{name('H1')}: death, serious injury or malfunction")
    for key in REQUIRED_CODES:
        codes, uncoded = fda.fda_codes(vals.get(key, ""))
        if not codes and key in need:
            missing.append(
                f"{name(key)}: at least one code with its FDA code" + (" (none of these has one)" * bool(uncoded))
            )
        elif uncoded:
            left.append(f"{name(key)}: {'; '.join(uncoded)} (no FDA code)")
    for key, text in vals.items():
        if key in LENGTHS and len(text) > LENGTHS[key]:
            (missing if key in _REQUIRED_TEXT & need else left).append(
                f"{name(key)}: longer than FDA's {LENGTHS[key]} characters"
            )
        if key in _DATES and fda.day(text) is None:
            left.append(f"{name(key)}: not a date")
        if key in fda.CHOICES and key != "H1":
            if fda.choices(key, text)[1]:
                left.append(f"{name(key)}: not one of FDA's choices")
        try:
            text.encode("cp1252")
        except UnicodeEncodeError:
            missing.append(f"{name(key)}: has characters FDA's eMDR does not take (Windows-1252 only)")
    if other:
        left.append(f"{name('H1')}: {'; '.join(other)} is not one of FDA's choices")
    for key, why in (
        ("A5", "FDA codes race and ethnicity separately"),
        ("D7B", "FDA wants the reprocessor's address in parts"),
        ("E1", "FDA wants the reporter's name and address in parts"),
        ("E2", "FDA reads it from the occupation (E3)" if "E3" not in vals else None),
    ):
        if key in vals and why:
            left.append(f"{name(key)}: {why}")
    if "A2" in vals and not (fda._AGE.match(vals["A2"]) or fda.day(vals["A2"])):
        left.append(f"{name('A2')}: neither an age nor a date")
    if "A4" in vals and not fda._WEIGHT.match(vals["A4"]):
        left.append(f"{name('A4')}: not a weight in kg or lb")
    if "E3" in vals and vals["E3"].lower() not in fda.OCCUPATIONS:
        left.append(f"{name('E3')}: not one of FDA's occupations")
    return missing, sorted(set(left), key=left.index)


def _e(parent, tag: str, text: str | None = None, **attrs):
    element = etree.SubElement(parent, f"{{{HL7}}}{tag}", attrs)
    if text is not None:
        element.text = text
    return element


def _type(element, kind: str):
    element.set(f"{{{XSI}}}type", kind)
    return element


def _day(text: str | None) -> str | None:
    found = fda.day(text) if text else None
    return found.strftime("%Y%m%d") if found else None


def _coded(parent, wrapper: str, item: str, concept: str, name: str, value_code: str, *, original: str | None = None):
    holder = _e(_e(parent, wrapper), item, moodCode="EVN") if item == "observation" else _e(_e(parent, wrapper), item)
    _e(holder, "code", code=concept, codeSystem=NCI, codeSystemName=name)
    value = _type(_e(holder, "value", code=value_code, codeSystem=NCI), "CE")
    if original:
        _e(value, "originalText", original)
    return holder


def build(sections: list[dict], parties, *, sender: str, now: datetime, practice: bool) -> bytes:
    """The eMDR XML of an approved report (``check`` first: this writes only what it finds)."""
    vals = fda.values(sections)
    pick = lambda key: fda.choices(key, vals[key])[0] if key in vals else []  # noqa: E731
    number = vals.get("G8") or vals["MFR_REPORT"]
    contact = office(parties, OFFICE_ROLES, vals.get("G1")) or {}
    maker = office(parties, MAKER_ROLES, vals.get("D3")) or {}

    root = etree.Element(f"{{{HL7}}}PORR_IN040001UV01", ITSVersion="XML_1.0", nsmap={None: HL7, "xsi": XSI})
    if practice:
        root.append(etree.Comment(" " + fda.PRACTICE + " Not for submission to FDA. "))
    root.append(
        etree.Comment(" Prepared by MDARIX. MDARIX never submits: you send this file through your ESG account. ")
    )
    _e(
        root,
        "id",
        assigningAuthorityName="MessageSender",
        extension=f"{number.split('-')[0]}-{now:%Y%m%d%H%M%S}",
        root="1.1",
    )
    _e(root, "creationTime", value=f"{now:%Y%m%d}")
    _e(root, "responseModeCode")
    _e(root, "versionCode", code="V3NORMED_2016")
    _e(root, "interactionId")
    _e(root, "batchTotalNumber", value="1")
    for role, name in (("receiver", "CDRH"), ("sender", sender)):
        party = _e(root, role)
        _e(party, "telecom")
        device = _e(party, "device")
        _e(device, "id", nullFlavor="NA")
        if role == "sender":
            _e(device, "softwareName", "MDARIX")
        organization = _e(_e(device, "asAgent"), "representedOrganization")
        _e(organization, "id", nullFlavor="NA")
        _e(organization, "name", name[:100])
    message = _e(root, "message")
    _e(message, "id", extension="1")
    _e(message, "creationTime", nullFlavor="NA")
    _e(message, "interactionId", root="2.16.840.1.113883.1.6", extension="PORR_IN04001", assigningAuthorityName="HL7")
    for tag in ("processingCode", "processingModeCode", "acceptAckCode"):
        _e(message, tag, nullFlavor="NA")
    for role in ("receiver", "sender"):
        party = _e(message, role)
        _e(party, "telecom")
        _e(_e(party, "device"), "id", nullFlavor="NA")
    act = _e(message, "controlActProcess", moodCode="EVN")
    _e(act, "code", code="PORR_TE040001UV01", codeSystem="HL7", codeSystemName="HL7 Trigger Event Id")
    reported = _day(vals.get("B4"))
    _e(act, "effectiveTime", **({"value": reported} if reported else {"nullFlavor": "NI"}))
    event = _e(_e(act, "subject"), "investigationEvent")
    _e(event, "id", assigningAuthorityName="FDA", extension=number, root=FDA_OID)
    for _, code in pick("B1"):
        _e(event, "code", code=code, codeSystem=NCI, codeSystemName="Adverse_Event_Or_Product_Problem_Report")
    if vals.get("H11"):
        _e(event, "text", vals["H11"], mediaType="text/plain")
    for tag in ("statusCode", "activityTime", "availabilityTime"):
        _e(event, tag)
    _e(_e(event, "authorOrPerformer", typeCode="AUT"), "assignedEntity")

    reaction = _e(_e(event, "trigger"), "reaction")
    _e(reaction, "text", vals["B5"], mediaType="text/plain")
    happened = _day(vals.get("B3"))
    _e(reaction, "effectiveTime", **({"value": happened} if happened else {"nullFlavor": "NI"}))
    subject = _e(_e(reaction, "subject"), "investigativeSubject")
    person = _e(subject, "subjectAffectedPerson")
    if vals.get("A1") and len(vals["A1"]) <= LENGTHS["A1"]:
        _e(person, "name", vals["A1"])
    for _, code in pick("A3"):
        _e(person, "administrativeGenderCode", code=code, codeSystem=NCI, codeSystemName="Sex")
    born = _day(vals.get("A2"))
    if born:
        _e(person, "birthTime", value=born)
    age, weight = fda._AGE.match(vals.get("A2", "")), fda._WEIGHT.match(vals.get("A4", ""))
    for found, concept, name, unit in (
        (age, "C25150", "Age", age and {"year": "YR", "month": "MO", "week": "WK", "day": "DA"}[age.group(2).lower()]),
        (weight, "C25208", "Weight", weight and ("KG" if weight.group(2).lower() == "kg" else "LBS")),
    ):
        if found:
            observation = _e(_e(subject, "subjectOf"), "observation", moodCode="EVN")
            _e(observation, "code", code=concept, codeSystem=NCI, codeSystemName=name)
            _type(_e(observation, "value", value=found.group(1), unit=unit), "PQ")
    for key, concept, name in (("B6", "C36292", "Test_Result"), ("B7", "C53263", "Other_Personal_Medical_History")):
        if vals.get(key):
            observation = _e(_e(subject, "subjectOf"), "observation", moodCode="EVN")
            _e(observation, "code", code=concept, codeSystem=NCI, codeSystemName=name)
            _type(_e(observation, "value", vals[key], mediaType="text/plain"), "ED")
    for key, concept, name in (
        ("H6_CLINICAL", "C53983", "Patient_Problem_Code"),
        ("H6_IMPACT", "C122929", "Patient_Impact_Code"),
    ):
        for code in fda.fda_codes(vals.get(key, ""))[0]:
            _coded(subject, "subjectOf", "observation", concept, name, code)
    source = _e(_e(reaction, "pertinentInformation"), "primarySourceReport")
    _e(source, "id", nullFlavor="ASKU")
    _e(source, "code", nullFlavor="ASKU")
    sent = fda.choices("E4", vals["E4"])[0] if "E4" in vals else []
    receiver = _e(source, "receiver", **({"negationInd": sent[0][1]} if sent and sent[0][1] else {}))
    _e(_e(_e(receiver, "assignedEntity"), "assignedOrganization"), "name", "FDA")
    author = _e(_e(source, "author"), "assignedEntity")
    occupation = fda.OCCUPATIONS.get(vals.get("E3", "").lower())
    if occupation:
        _e(author, "code", code=occupation[1], codeSystem=NCI, codeSystemName="Occupation")

    # Section F's notification, empty in a manufacturer's report: as every manufacturer example of FDA's has it.
    first = _e(event, "pertinentInformation1")
    _e(first, "sequenceNumber", nullFlavor="NI")
    empty = _e(first, "secondaryCaseNotification")
    _e(empty, "id", assigningAuthorityName="FDA", extension="NI", root=FDA_OID)
    _e(empty, "code", codeSystem=NCI, codeSystemName="Type_of_Report")
    _e(empty, "effectiveTime", nullFlavor="NI")
    to = _e(empty, "receiver")
    _e(to, "time", nullFlavor="NI")
    _e(
        _e(_e(to, "assignedEntity"), "assignedOrganization"),
        "code",
        code="C17237",
        codeSystem=NCI,
        codeSystemName="Report_Receiver",
    )
    _e(_e(_e(empty, "author"), "assignedEntity"), "code", codeSystem=NCI, codeSystemName="Type_of_Reporter")
    # G3: the date the manufacturer received it (the second notification, as FDA's example).
    received = _day(vals.get("G3"))
    notification = _e(_e(event, "pertinentInformation1"), "secondaryCaseNotification")
    _e(notification, "id", nullFlavor="NA")
    _e(notification, "code", nullFlavor="NI")
    receiver = _e(notification, "receiver")
    when = _e(receiver, "time")
    _e(when, "low", nullFlavor="NI")
    _e(when, "high", **({"value": received} if received else {"nullFlavor": "NI"}))
    _e(receiver, "assignedEntity")
    for _, code in pick("B2"):
        seriousness = _e(_e(event, "pertinentInformation2"), "caseSeriousness")
        _e(seriousness, "code", code="C49489", codeSystem=NCI, codeSystemName="Adverse_Event_Outcome")
        _type(_e(seriousness, "value", code=code, codeSystem=NCI), "CE")

    procedure = _e(_e(event, "pertainsTo"), "procedureEvent")
    _e(procedure, "code", nullFlavor="ASKU")
    outer = _e(_e(procedure, "device"), "identifiedDevice")
    _e(outer, "id", nullFlavor="NI")
    device = _e(outer, "identifiedDevice")
    fits = lambda key: vals.get(key) and len(vals[key]) <= LENGTHS.get(key, 10**6)  # noqa: E731
    if fits("D4_SERIAL"):
        _e(device, "id", extension=vals["D4_SERIAL"])
    made = _day(vals.get("H4"))
    if made:
        _e(device, "existenceTime", value=made)
    if fits("D4_LOT"):
        _e(device, "lotNumberText", vals["D4_LOT"], mediaType="text/plain")
    expiry = _day(vals.get("D4_EXPIRY"))
    _e(device, "expirationTime", **({"value": expiry} if expiry else {"nullFlavor": "NI"}))  # the schema wants it
    product = _e(device, "asManufacturedProduct")
    if fits("D4_CATALOG"):
        _e(product, "id", extension=vals["D4_CATALOG"])
    if fits("D4_UDI"):
        _e(product, "code", code=vals["D4_UDI"])
    maker_element = _e(product, "manufacturerOrReprocessor")
    _e(maker_element, "code", code="C53616", codeSystem=NCI, codeSystemName="Type_of_Manufacturer")
    _e(maker_element, "name", maker["name"][:50]) if maker.get("name") else _e(maker_element, "name", nullFlavor="NI")
    _e(
        maker_element,
        "telecom",
        **({"value": f"mailto:{maker['email']}"} if 0 < len(maker.get("email") or "") <= 50 else {}),
    )
    investigation = _e(_e(_e(maker_element, "asRole"), "performance"), "investigationEvent")
    for key, component, item, concept, name in (
        ("H6_FINDINGS", "component1", "evaluationResult", "C53985", "Evaluation_Result_Code"),
        ("H6_CONCLUSIONS", "component2", "evaluationConclusion", "C53986", "Evaluation_Conclusion_Code"),
        ("H6_TYPE", "component3", "evaluationMethod", "C53984", "Evaluation_Method_Code"),
    ):
        for code in fda.fda_codes(vals.get(key, ""))[0]:
            _coded(investigation, component, item, concept, name, code)
    office_element = _e(maker_element, "contactParty")
    _e(_e(office_element, "addr"), "additionalLocator", contact.get("name", "")[:60])
    if contact.get("email"):
        _e(office_element, "telecom", value=f"mailto:{contact['email']}")
    if contact.get("phone") and PHONE.match(contact["phone"]):
        _e(office_element, "telecom", value=f"tel:{contact['phone']}")
    _e(office_element, "contactManufacturerContact")
    model = _e(_e(device, "inventoryItem"), "manufacturedDeviceModel")
    if fits("D4_MODEL"):
        _e(model, "id", extension=vals["D4_MODEL"])
    kind = _e(model, "code", code=vals["D2A"], codeSystemName="Type_of_Device", codeSystem=NCI)
    if fits("D2B"):
        _e(kind, "originalText", vals["D2B"], mediaType="text/plain")
    if fits("D1"):
        _e(model, "manufacturerModelName", vals["D1"], mediaType="text/plain")
    if fits("G4"):
        _e(_e(model, "asRegulatedProduct"), "id", extension=vals["G4"])

    def observe(concept: str, name: str):
        observation = _e(_e(outer, "subjectOf"), "deviceObservation")
        _e(observation, "code", code=concept, codeSystem=NCI, codeSystemName=name)
        return observation

    for _, flag in pick("D9"):
        observation = observe("C53449", "Device_available_for_evaluation")
        _e(observation, "effectiveTime", nullFlavor="NI")
        _type(_e(observation, "value", value=flag), "BL")
    for key, concept, name in (
        ("H6_PROBLEM", "C53982", "Device_Problem_Code"),
        ("H6_COMPONENT", "C54577", "Component_Code"),
    ):
        for code in fda.fda_codes(vals.get(key, ""))[0]:
            _type(_e(observe(concept, name), "value", code=code, codeSystem=NCI), "CE")
    for key, concept, name in (
        ("H3", "C53629", "Device_Evaluated_By_Manufacturer"),
        ("H5", "C53602", "Device_Labeled_for_single_use"),
    ):
        for _, flag in pick(key):
            _type(_e(observe(concept, name), "value", value=flag), "BL")
    for key, concept, name in (("H7", "C53603", "Type_of_Remedial_Action"), ("H8", "C53645", "Usage_of_Device")):
        for _, code in pick(key):
            _type(_e(observe(concept, name), "value", code=code, codeSystem=NCI), "CE")
    if fits("H9"):
        _type(_e(observe("C53619", "Corrective_Action_Number"), "value", vals["H9"], mediaType="text/plain"), "ED")
    for related in (part.strip() for part in vals.get("H10", "").split(";")):
        if 7 <= len(related) <= 23:
            _type(_e(observe("C103162", "Related Record"), "value", related, mediaType="text/plain"), "ED")

    for _, code in pick("D5")[:1]:
        operator = _e(_e(procedure, "authorOrPerformer", typeCode="AUT"), "assignedEntity")
        _e(operator, "code", code=code, codeSystemName="Operator_of_Medical_Device", codeSystem=NCI)
    for key, concept, name in (
        ("D7A", "C53563", "Single-Use_Device_Reprocessed_and_Reused_on_Patient"),
        ("D8", "C85488", "Device_Serviced_By_Third_Party"),
    ):
        # The schema wants one of these: a blank D7A goes as "no information" (FDA's way to send a blank value).
        found = pick(key) or ([(None, "NI")] if key == "D7A" and not ("D8" in vals or fits("D10")) else [])
        for _, flag in found:
            observation = _e(_e(procedure, "pertinentInformation1"), "observation", moodCode="EVN")
            _e(observation, "code", code=concept, codeSystem=NCI, codeSystemName=name)
            _type(
                _e(observation, "value", **({"nullFlavor": flag} if flag in ("ASKU", "NI") else {"value": flag})), "BL"
            )
    if fits("D10"):
        observation = _e(_e(procedure, "pertinentInformation1"), "observation", moodCode="EVN")
        _e(observation, "code", code="C53630", codeSystem=NCI, codeSystemName="Concomitant_Therapy")
        _type(_e(observation, "value", vals["D10"], mediaType="text/plain"), "ED")
    for key, component, item in (("D6A", "component1", "implantation"), ("D6B", "component2", "explantation")):
        when = _day(vals.get(key))
        if when:
            _e(_e(_e(procedure, component), item), "effectiveTime", value=when)
    _e(_e(_e(event, "component"), "adverseEventAssessment"), "subject1").append(etree.Element(f"{{{HL7}}}primaryRole"))

    def reason(concept: str, name: str, code: str):
        issue = _e(_e(act, "reasonOf"), "detectedIssueEvent")
        _e(issue, "code", code=concept, codeSystem=NCI, codeSystemName=name)
        _type(_e(issue, "value", code=code, codeSystem=NCI), "CE")

    for _, code in pick("G2"):
        reason("C53566", "Report_Source", code)
    for _, code in pick("G6"):
        reason("C53571", "Type_of_Report", code)
    for _, code in pick("H1"):
        reason("C53570", "Type_of_Reportable_Event", code)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def prepare(sections: list[dict], parties, *, kind: str, sender: str, now: datetime, practice: bool) -> dict:
    """The file as Send for approval checks it (0.10.96): the blocks FDA requires that are missing or not in its
    format; when none, the file itself and its schema errors (none: FDA's schema takes it)."""
    missing, left = check(sections, parties, kind)
    xml = None if missing else build(sections, parties, sender=sender, now=now, practice=practice)
    return {"missing": missing, "left_out": left, "errors": validate(xml) if xml else [], "xml": xml}


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMA)))


def validate(xml: bytes) -> list[str]:
    """The schema errors of a file, against FDA's published eMDR schema (none: it validates)."""
    schema = _schema()
    if schema.validate(etree.fromstring(xml)):
        return []
    return [f"line {error.line}: {error.message}" for error in schema.error_log]
