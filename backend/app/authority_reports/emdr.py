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
# The rule book (decision D17): the mapping workbook's US sheet, exported by scripts/export_us_emdr_rules.py. Version 2
# (register emdr-rule-book-2, B9 step 5) adds the importer and user facility rows; its manufacturer rows are version
# 1's (us_emdr.csv) byte for byte. Its block numbers are FDA's package's (D2B is the procode); the report's fields
# follow the 09/2025 form (D2A is the procode). A required row with no field here fails at the first check.
RULES = Path(__file__).with_name("rules") / "us_emdr_v2.csv"
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
    # Section F (B9 step 5): an importer's or a user facility's own blocks.
    ("F1", "Check one: User Facility, Importer"): "F1",
    ("F2", "UF/Distributor (Importer) Report Number"): "F2",
    ("F4", "User Facility or Distributor (Importer) Contact Email"): "F4",
    ("F7", "Type of report"): "F7",
    ("F10", "Health Effect - Clinical Code"): "F10_CLINICAL",
    ("F10", "Health Effect - Impact Code"): "F10_IMPACT",
    ("F10", "Medical Device Problem Code"): "F10_PROBLEM",
    ("F10", "Component Code"): "F10_COMPONENT",
}
# Report types: manufacturer, importer and user facility (B9), each initial (-I) or follow-up (-F).
KINDS = {"M-I": "m_i", "M-F": "m_f", "I-I": "i_i", "I-F": "i_f", "U-I": "u_i", "U-F": "u_f"}
# B9: the reporting role behind a US report type (21 CFR 803.40 importer, 803.30 user facility); absent: manufacturer.
ROLE_OF_TYPE = {"US_IMP_30_DAY": "IMPORTER", "US_UF_10_WORK_DAY": "USER_FACILITY"}
_LETTER = {"IMPORTER": "I", "USER_FACILITY": "U"}
# F2 (B9 step 6, never with G8): an importer's CFN or FEI, the year and 5 digits; a user facility's 10-digit HCFA
# number, the year and 4 digits.
ROLE_NUMBER = {"I": re.compile(r"^(\d{7}|\d{10})-\d{4}-\d{5}$"), "U": re.compile(r"^\d{10}-\d{4}-\d{4}$")}
ROLE_FORMAT = {
    "I": "your 7-digit CFN or 10-digit FEI, the year and a 5-digit number (1234567-2026-00001)",
    "U": "your 10-digit HCFA number, the year and a 4-digit number (1234567890-2026-0001)",
}
# F10's four codes sit at the XPaths of H6's patient and device codes (FDA's importer and user facility examples).
F10 = {
    "F10_CLINICAL": "H6_CLINICAL",
    "F10_IMPACT": "H6_IMPACT",
    "F10_PROBLEM": "H6_PROBLEM",
    "F10_COMPONENT": "H6_COMPONENT",
}
REPORTER = {"I": "C53617", "U": "C53567"}  # F1: FDA's Type_of_Reporter (importer, user facility)
REPORTER_ROLE = {"I": ("IMPORTER",), "U": ("USER_FACILITY",)}  # whose party F3 to F5 read
INITIAL_CODE = "C53620"  # F7 "Initial" (FDA's Type_of_Report)
FOLLOW_UP = re.compile(r"\bfollow-up #?(\d+)\b", re.IGNORECASE)  # G6 or F7 on a follow-up: "30-day; Follow-up #2"
# FDA's XPaths (HL7Medwatch.xlsx, 3500A_HL7_Pointers) of the blocks MDARIX carries, namespace left out (``plain``):
# the eSubmitter-layout PDF reads the file back through them, and the tests compare the file with FDA's examples.
FOLLOW_UP_CODE = "C53579"  # G6 "Follow-up" (FDA's Type_of_Report)
# What a follow-up always sends, and its narratives, sent only as typed on it (never the initial's text again).
FOLLOW_UP_SENDS, NARRATIVES = frozenset({"MFR_REPORT", "G8", "G6", "H2"}), frozenset({"B5", "H11"})
NOT_ON_FOLLOW_UP = frozenset({"B4"})  # FDA's "Manufacturer Follow-up" leaves B4 out: never sent, never "cleared"
IE = "//message/controlActProcess/subject/investigationEvent"
DEV = IE + "/pertainsTo/procedureEvent/device/identifiedDevice"
_PERSON = IE + "/trigger/reaction/subject/investigativeSubject"
_MAKER = DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor"
_REASON = "//message/controlActProcess/reasonOf/detectedIssueEvent/code[@code='{}']/../value/@code"
POINTERS = {
    "version": "//versionCode/@code",
    "G8": IE + "/id/@extension",
    "B1": IE + "/code/@code",
    "B2": IE + "/pertinentInformation2/caseSeriousness/code[@code='C49489']/../value/@code",
    "B3": IE + "/trigger/reaction/effectiveTime/@value",
    "B4": "//message/controlActProcess/effectiveTime/@value",
    "B5": IE + "/trigger/reaction/text/text()",
    "B6": _PERSON + "/subjectOf/observation/code[@code='C36292']/../value/text()",
    "B7": _PERSON + "/subjectOf/observation/code[@code='C53263']/../value/text()",
    "A1": _PERSON + "/subjectAffectedPerson/name/text()",
    "A3": _PERSON + "/subjectAffectedPerson/administrativeGenderCode/@code",
    "A2": _PERSON + "/subjectOf/observation/code[@code='C25150']/../value/@value",
    "A4": _PERSON + "/subjectOf/observation/code[@code='C25208']/../value/@value",
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
    "G1 email": _MAKER + "/contactParty[1]/telecom[starts-with(@value, 'mailto:')]/@value",
    "G1 phone": _MAKER + "/contactParty[1]/telecom[starts-with(@value, 'tel:')]/@value",
    "G2": _REASON.format("C53566"),
    "G3": IE + "/pertinentInformation1/secondaryCaseNotification/receiver/time/high/@value",
    "G6": _REASON.format("C53571"),
    "H1": _REASON.format("C53570"),
    "H3": DEV + "/subjectOf/deviceObservation/code[@code='C53629']/../value/@value",
    "H4": DEV + "/identifiedDevice/existenceTime/@value",
    "H5": DEV + "/subjectOf/deviceObservation/code[@code='C53602']/../value/@value",
    "H6 clinical": _PERSON + "/subjectOf/observation/code[@code='C53983']/../value/@code",
    "H6 impact": _PERSON + "/subjectOf/observation/code[@code='C122929']/../value/@code",
    "H6 problem": DEV + "/subjectOf/deviceObservation/code[@code='C53982']/../value/@code",
    "H6 component": DEV + "/subjectOf/deviceObservation/code[@code='C54577']/../value/@code",
    "H6 type": _MAKER
    + "/asRole/performance/investigationEvent/component3/evaluationMethod/code[@code='C53984']/../value/@code",
    "H6 findings": _MAKER
    + "/asRole/performance/investigationEvent/component1/evaluationResult/code[@code='C53985']/../value/@code",
    "H6 conclusions": _MAKER
    + "/asRole/performance/investigationEvent/component2/evaluationConclusion/code[@code='C53986']/../value/@code",
    "H7": DEV + "/subjectOf/deviceObservation/code[@code='C53603']/../value/@code",
    "H8": DEV + "/subjectOf/deviceObservation/code[@code='C53645']/../value/@code",
    "H9": DEV + "/subjectOf/deviceObservation/code[@code='C53619']/../value/text()",
    "H10": DEV + "/subjectOf/deviceObservation/code[@code='C103162']/../value/text()",
    "H11": IE + "/text/text()",
    # Section F (B9 step 6): the first notification is the importer's or user facility's own, the second the
    # manufacturer it was sent to (FDA's importer and user facility examples).
    "F1": IE + "/pertinentInformation1/secondaryCaseNotification/author/assignedEntity/code/@code",
    "F2": IE + "/pertinentInformation1/secondaryCaseNotification/id/@extension",
    "F4 email": IE + "/pertinentInformation1/secondaryCaseNotification/author/assignedEntity/assignedOrganization"
    "/contactParty/contactPerson/telecom[starts-with(@value, 'mailto:')]/@value",
    "F6": IE + "/pertinentInformation1/secondaryCaseNotification/effectiveTime/@value",
    "F7": IE + "/pertinentInformation1/secondaryCaseNotification/code/@code",
    "F7 number": IE + "/pertinentInformation1/sequenceNumber/@value",
    "F9": DEV + "/subjectOf/deviceObservation/code[@code='C53451']/../value/@value",
    "F11": IE + "/pertinentInformation1/secondaryCaseNotification/receiver/time/@value",
    "F12": IE + "/trigger/reaction/location/locatedEntity/location/code/@code",
    "F13": IE + "/pertinentInformation1/secondaryCaseNotification/receiver/time/low/@value",
    "F14": IE + "/pertinentInformation1/secondaryCaseNotification/receiver/assignedEntity/assignedOrganization"
    "/name/text()",
}


def role_kind(role: str | None, follow_up: bool) -> str:
    """The eMDR report type of a role (None: manufacturer) and place in its chain: M-I, M-F, I-I, I-F, U-I or U-F."""
    return f"{_LETTER.get(role or '', 'M')}-{'F' if follow_up else 'I'}"


def report_values(sections: list[dict], kind: str = "M-I") -> dict[str, str]:
    """The report's values as the file reads them: on an importer's or user facility's report, F10's codes in H6's
    places (the same XPaths) and nothing of sections G and H (manufacturers only)."""
    vals = fda.values(sections)
    if kind[0] == "M":
        return vals
    out = {key: text for key, text in vals.items() if key[0] not in "GH" and key != "MFR_REPORT"}
    return out | {F10[key]: text for key, text in vals.items() if key in F10}


def _sent(text: str | None) -> tuple[str | None, str | None]:
    """F11 or F13 ("Yes, 2026-11-04" / "No"): FDA's negation ("false": it was sent) and the day, or (None, None)."""
    words = (text or "").strip().lower()
    if words.startswith("yes"):
        found = re.search(r"\d{4}-\d{2}-\d{2}", words)
        return "false", _day(found.group(0)) if found else None
    return ("true", None) if words.startswith("no") else (None, None)


@lru_cache(maxsize=len(KINDS))
def required(kind: str = "M-I") -> frozenset[str]:
    """The report's fields FDA requires on this report type (its "Required 3500A fields"), read from the rule book."""
    with RULES.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row[KINDS[kind]] == "required"]
    return frozenset(RULE_FIELDS[row["block"], row["label"]] for row in rows)


def next_number(numbers: list[str], year: int, practice: bool, letter: str = "M") -> str | None:
    """The next manufacturer report number (G8; decision D5, owner Q2 and Q5): the CFN or FEI of the organization's
    last number, the year, and the last sequence of that year plus one (5 digits, from 00001 each year). A practice
    report's sequence starts with 7, as FDA's test reports do (70001). None before the organization's first number,
    which a person types once. ``numbers``: every number the organization has used, oldest first. ``letter`` I or U
    (B9 step 6): an importer's F2 (5 digits) or a user facility's (HCFA number, 4 digits, practice from 7001)."""
    found = [number.split("-") for number in numbers if ROLE_NUMBER.get(letter, REPORT_NUMBER).match(number)]
    if not found:
        return None
    prefix = found[-1][0]
    used = [
        int(seq) for cfn, yyyy, seq in found if cfn == prefix and yyyy == str(year) and seq.startswith("7") == practice
    ]
    # shortcut: no guard past 69999 (a real organization's) or 79999 (practice) a year; add one if anyone nears it.
    if letter == "U":
        return f"{prefix}-{year}-{(max(used) + 1 if used else 7001 if practice else 1):04d}"
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

    ``kind`` is the report type (M-I manufacturer initial, M-F manufacturer follow-up; B9: I-I, I-F importer, U-I,
    U-F user facility): the blocks FDA requires on it come from the rule book (``required``); the format of any value
    given is checked on each."""
    vals, names = report_values(sections, kind), fda.labels(sections)
    role = kind[0] if kind[0] != "M" else None
    name = lambda key: names.get(key, key)  # noqa: E731
    need = required(kind) | {F10[key] for key in required(kind) if key in F10}
    missing: list[str] = []
    left: list[str] = []
    for key in sorted(_REQUIRED_TEXT & need - set(vals)):
        missing.append(f"{name(key)}: missing")
    number = vals.get("G8") or vals.get("MFR_REPORT")
    if role:  # F2, never together with G8 (B9 step 6)
        if {"G8", "MFR_REPORT"} & {key for key, text in fda.values(sections).items() if text}:
            missing.append(f"{name('G8')}: an importer's or user facility's report has no manufacturer report number")
        if not vals.get("F2"):
            missing.append(f"{name('F2')}: missing")
        elif not ROLE_NUMBER[role].match(vals["F2"]):
            missing.append(f"{name('F2')}: FDA's format is {ROLE_FORMAT[role]}")
        if "F7" in need and not FOLLOW_UP.search(vals.get("F7", "")):
            missing.append(f"{name('F7')}: Follow-up with its number (Follow-up #1)")
        reporter = office(parties, REPORTER_ROLE[role], vals.get("F4"))
        if "F4" in need and not (reporter and reporter["email"] and len(reporter["email"]) <= 50):
            missing.append(
                f"{name('F4')}: set your organization's US {'importer' if role == 'I' else 'user facility'} in "
                "Settings, with an e-mail of up to 50 characters, and approve the report again so it reads the same"
            )
        if vals.get("F14") and office(parties, MAKER_ROLES, vals["F14"]) is None:
            left.append(f"{name('F14')}: not your organization's US manufacturer as set in Settings")
        if reporter and (reporter["address"] or reporter["person"]):
            left.append(f"{name('F3')} address and contact person: FDA wants them in parts; give them in eSubmitter")
        if vals.get("F12") and not fda.choices("F12", vals["F12"].partition(":")[0])[0]:
            left.append(f"{name('F12')}: not one of FDA's locations")
    elif not number:
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
    if kind.endswith("-I") and not fda.choices("B1", vals.get("B1", ""))[0]:
        missing.append(f"{name('B1')}: adverse event, product problem or both")
    found, other = fda.choices("H1", vals.get("H1", ""))
    if not found and "H1" in need:
        missing.append(f"{name('H1')}: death, serious injury or malfunction")
    shown = {held: own for own, held in F10.items()} if role else {}  # F10's own names on a role's report
    for key in REQUIRED_CODES:
        codes, uncoded = fda.fda_codes(vals.get(key, ""))
        if not codes and key in need:
            missing.append(
                f"{name(shown.get(key, key))}: at least one code with its FDA code"
                + (" (none of these has one)" * bool(uncoded))
            )
        elif uncoded:
            left.append(f"{name(shown.get(key, key))}: {'; '.join(uncoded)} (no FDA code)")
    for key, text in vals.items():
        if key in LENGTHS and len(text) > LENGTHS[key]:
            (missing if key in _REQUIRED_TEXT & need else left).append(
                f"{name(key)}: longer than FDA's {LENGTHS[key]} characters"
            )
        if key in _DATES and fda.day(text) is None:
            left.append(f"{name(key)}: not a date")
        if key in fda.CHOICES and key not in ("H1", "F12"):
            if fda.choices(key, FOLLOW_UP.sub("", text) if key == "G6" else text)[1]:
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


def build(sections: list[dict], parties, *, sender: str, now: datetime, practice: bool, kind: str = "M-I") -> bytes:
    """The eMDR XML of an approved report (``check`` first: this writes only what it finds). ``kind`` I-x or U-x (B9
    step 6): an importer's or user facility's report, its number F2 and section F filled, sections G and H left out."""
    vals = report_values(sections, kind)
    role = kind[0] if kind[0] != "M" else None
    pick = lambda key: fda.choices(key, vals[key])[0] if key in vals else []  # noqa: E731
    number = vals["F2"] if role else vals.get("G8") or vals["MFR_REPORT"]
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
    for side, name in (("receiver", "CDRH"), ("sender", sender)):
        party = _e(root, side)
        _e(party, "telecom")
        device = _e(party, "device")
        _e(device, "id", nullFlavor="NA")
        if side == "sender":
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
    for side in ("receiver", "sender"):
        party = _e(message, side)
        _e(party, "telecom")
        _e(_e(party, "device"), "id", nullFlavor="NA")
    act = _e(message, "controlActProcess", moodCode="EVN")
    _e(act, "code", code="PORR_TE040001UV01", codeSystem="HL7", codeSystemName="HL7 Trigger Event Id")
    reported = _day(vals.get("B4"))
    _e(act, "effectiveTime", **({"value": reported} if reported else {"nullFlavor": "NI"}))
    event = _e(_e(act, "subject"), "investigationEvent")
    # An importer's or user facility's number is F2, in section F; the event's own id is then "NI" (FDA's examples).
    _e(event, "id", assigningAuthorityName="FDA", extension="NI" if role else number, root=FDA_OID)
    for _, code in pick("B1") or [(None, None)]:  # a follow-up that sends no B1: the bare code, as FDA's example
        attrs = {"code": code} if code else {}
        _e(event, "code", **attrs, codeSystem=NCI, codeSystemName="Adverse_Event_Or_Product_Problem_Report")
    if vals.get("H11"):
        _e(event, "text", vals["H11"], mediaType="text/plain")
    for tag in ("statusCode", "activityTime", "availabilityTime"):
        _e(event, tag)
    _e(_e(event, "authorOrPerformer", typeCode="AUT"), "assignedEntity")

    reaction = _e(_e(event, "trigger"), "reaction")
    _e(reaction, "text", vals.get("B5"), mediaType="text/plain")  # empty on a follow-up with no new narrative
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
    for _, code in fda.choices("F12", vals.get("F12", "").partition(":")[0])[0][
        :1
    ]:  # F12, where it happened (FDA's codes); "Other: ..." sends its words
        located = _e(_e(_e(_e(reaction, "location"), "locatedEntity"), "location"), "code", code=code, codeSystem=NCI)
        located.set("codeSystemName", "Location")
        words = vals["F12"].partition(":")[2].strip()
        if code == "C17649" and 0 < len(words) <= 40:
            _e(located, "originalText", words)
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

    if role:
        _section_f(event, vals, parties, role, number)
    else:
        _empty_section_f(event, vals)
    for _, code in pick("B2"):
        seriousness = _e(_e(event, "pertinentInformation2"), "caseSeriousness")
        _e(seriousness, "code", code="C49489", codeSystem=NCI, codeSystemName="Adverse_Event_Outcome")
        _type(_e(seriousness, "value", code=code, codeSystem=NCI), "CE")
    _device(event, vals, pick, maker, contact, role)

    def reason(concept: str, name: str, code: str, text: str | None = None):
        issue = _e(_e(act, "reasonOf"), "detectedIssueEvent")
        _e(issue, "code", code=concept, codeSystem=NCI, codeSystemName=name)
        if text:
            _e(issue, "text", text, mediaType="text/plain")
        _type(_e(issue, "value", code=code, codeSystem=NCI), "CE")

    for _, code in pick("G2"):
        reason("C53566", "Report_Source", code)
    for _, code in fda.choices("G6", FOLLOW_UP.sub("", vals["G6"]))[0] if "G6" in vals else []:
        reason("C53571", "Type_of_Report", code)
    follow_up = FOLLOW_UP.search(vals.get("G6", ""))
    if follow_up:  # G6 "Follow-up" with its number, and H2's types (FDA's "Manufacturer Follow-up" example)
        reason("C53571", "Type_of_Report", FOLLOW_UP_CODE, follow_up.group(1))
        for _, code in pick("H2"):
            reason("C53584", "Type_of_Follow-up", code)
    for _, code in pick("H1"):
        reason("C53570", "Type_of_Reportable_Event", code)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def _section_f(event, vals: dict, parties, role: str, number: str) -> None:
    """Section F of an importer's or user facility's report (B9 step 6), placed as FDA's examples place it: the
    reporter's notification (F1, F2, F3 to F5, F6, F7 with its number, F11 sent to FDA), then the manufacturer's
    (F13 sent to the manufacturer, F14 the manufacturer)."""
    follow_up = FOLLOW_UP.search(vals.get("F7", ""))
    first = _e(event, "pertinentInformation1")
    _e(first, "sequenceNumber", **({"value": follow_up.group(1)} if follow_up else {"nullFlavor": "NI"}))
    note = _e(first, "secondaryCaseNotification")
    _e(note, "id", assigningAuthorityName="FDA", extension=number, root=FDA_OID)
    code = FOLLOW_UP_CODE if follow_up else INITIAL_CODE
    _e(note, "code", code=code, codeSystem=NCI, codeSystemName="Type_of_Report")
    aware = _day(vals.get("F6"))
    _e(note, "effectiveTime", **({"value": aware} if aware else {"nullFlavor": "NI"}))
    negation, sent = _sent(vals.get("F11"))
    to = _e(note, "receiver", **({"negationInd": negation} if negation else {}))
    _e(to, "time", **({"value": sent} if sent else {"nullFlavor": "NI"}))
    receiver = _e(_e(to, "assignedEntity"), "assignedOrganization")
    _e(receiver, "code", code="C17237", codeSystem=NCI, codeSystemName="Report_Receiver")
    author = _e(_e(note, "author"), "assignedEntity")
    _e(author, "code", code=REPORTER[role], codeSystem=NCI, codeSystemName="Type_of_Reporter")
    reporter = office(parties, REPORTER_ROLE[role], vals.get("F4"))
    if reporter:  # F3 to F5: the name (in FDA's place for it), the phone in FDA's format and the e-mail
        organization = _e(author, "assignedOrganization")
        _e(organization, "name", nullFlavor="NA")
        _e(_e(organization, "addr"), "additionalLocator", (reporter["name"] or "")[:60])
        person = _e(_e(organization, "contactParty"), "contactPerson")
        if reporter["phone"] and PHONE.match(reporter["phone"]):
            _e(person, "telecom", value=f"tel:{reporter['phone']}")
        if 0 < len(reporter["email"] or "") <= 50:
            _e(person, "telecom", value=f"mailto:{reporter['email']}")
    negation, sent = _sent(vals.get("F13"))
    second = _e(_e(event, "pertinentInformation1"), "secondaryCaseNotification")
    _e(second, "id", nullFlavor="NA")
    _e(second, "code", nullFlavor="NI")
    to = _e(second, "receiver", **({"negationInd": negation} if negation else {}))
    when = _e(to, "time")
    _e(when, "low", **({"value": sent} if sent else {"nullFlavor": "NI"}))
    _e(when, "high", nullFlavor="NI")
    entity = _e(to, "assignedEntity")
    maker = office(parties, MAKER_ROLES, vals.get("F14"))
    if maker:  # F14: the manufacturer the report went to
        organization = _e(entity, "assignedOrganization")
        _e(organization, "code", code="C53616", codeSystem=NCI, codeSystemName="Report_Receiver")
        _e(organization, "name", (maker["name"] or "")[:50])
        if 0 < len(maker["email"] or "") <= 50:
            _e(organization, "telecom", value=f"mailto:{maker['email']}")


def _empty_section_f(event, vals: dict) -> None:
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


def _device(event, vals: dict, pick, maker: dict, contact: dict, role: str | None) -> None:
    """Section D's device and procedure, F9, and H's evaluation (a manufacturer's only: none on a role's report)."""
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
    if not role:  # G1, the manufacturer's contact office: never on an importer's or user facility's report
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
    procode = {"code": vals["D2A"]} if vals.get("D2A") else {}  # a follow-up sends it only when it changed
    kind = _e(model, "code", **procode, codeSystemName="Type_of_Device", codeSystem=NCI)
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
    age = fda._AGE.match(vals.get("F9", ""))
    if age:  # F9, the device's approximate age
        unit = {"year": "YR", "month": "MO", "week": "WK", "day": "DA"}[age.group(2).lower()]
        _type(_e(observe("C53451", "Approximate_Age_of_Device"), "value", value=age.group(1), unit=unit), "PQ")
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


def delta(sections: list[dict], previous: dict[str, str]) -> tuple[list[dict], list[str]]:
    """A follow-up's sections as its file sends them (0.10.96, B3 B2): a value only when it is new or changed against
    the chain's last submitted report (``previous``, its values), a code only when new, the narratives (B5, H11) only
    as typed on the follow-up, always its number, G6 and H2, and never B4. Also what it says of a value cleared here."""
    names = fda.labels(sections)
    out, left = [], []
    for section in sections:
        fields = []
        for item in section["fields"]:
            key, value = item["id"], str(item.get("value") or "").strip()
            if key in NOT_ON_FOLLOW_UP:
                value = ""
            elif key in NARRATIVES:
                value = value if item.get("status") in ("ENTERED", "CHANGED") else ""
            elif key in REQUIRED_CODES and value:
                held = {part.strip() for part in previous.get(key, "").split(";") if part.strip()}
                now = {part.strip() for part in value.split(";") if part.strip()}
                value = "; ".join(part.strip() for part in value.split(";") if part.strip() not in held)
                left.extend(
                    f"{names.get(key, key)}: {code} removed here; FDA keeps the earlier value"
                    for code in sorted(held - now)
                )
            elif key not in FOLLOW_UP_SENDS and value == previous.get(key, ""):
                value = ""
            if not item.get("value") and previous.get(key) and key not in NARRATIVES | NOT_ON_FOLLOW_UP:
                left.append(f"{names.get(key, key)}: cleared here; FDA keeps the earlier value")
            fields.append({**item, "value": value or None})
        out.append({**section, "fields": fields})
    return out, left


def prepare(
    sections: list[dict], parties, *, kind: str, sender: str, now: datetime, practice: bool, previous=None
) -> dict:
    """The file as Send for approval checks it (0.10.96): the blocks FDA requires that are missing or not in its
    format; when none, the file itself and its schema errors (none: FDA's schema takes it). ``previous``: a follow-up's
    chain values, so its file sends only what changed (``delta``), listed in ``changed`` for the page."""
    cleared: list[str] = []
    changed: list[str] = []
    if previous is not None:
        names = fda.labels(sections)
        sections, cleared = delta(sections, previous)
        changed = [
            f"{names.get(item['id'], item['id'])}: {item['value']}"
            for section in sections
            for item in section["fields"]
            if item.get("value") and item["id"] not in FOLLOW_UP_SENDS
        ]
    missing, left = check(sections, parties, kind)
    left = [*left, *cleared]
    xml = None if missing else build(sections, parties, sender=sender, now=now, practice=practice, kind=kind)
    errors = validate(xml) if xml else []
    return {"missing": missing, "left_out": left, "errors": errors, "xml": xml, "changed": changed}


def plain(xml: bytes):
    """The file with its namespace left out, so FDA's XPaths (``POINTERS``) read it as written."""
    doc = etree.fromstring(xml)
    for element in doc.iter():
        if isinstance(element.tag, str):
            element.tag = etree.QName(element).localname
    etree.cleanup_namespaces(doc)
    return doc.getroottree()


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMA)))


def validate(xml: bytes) -> list[str]:
    """The schema errors of a file, against FDA's published eMDR schema (none: it validates)."""
    schema = _schema()
    if schema.validate(etree.fromstring(xml)):
        return []
    return [f"line {error.line}: {error.message}" for error in schema.error_log]
