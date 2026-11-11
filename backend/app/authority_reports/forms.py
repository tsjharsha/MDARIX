"""The authorities' forms, in their own section and field order (T-G2c, MVP G2c), as code constants.

- **US:** Form FDA 3500A, MedWatch mandatory reporting, edition 09/2025 (OMB 0910-0291), for entry in eSubmitter
  (eMDR). Sections, block numbers and labels are as printed on the form and in FDA's "Form FDA 3500A Supplement
  (09/2025) - Form Instructions", both read from fda.gov (www.fda.gov/media/69876 and www.fda.gov/media/133177) on
  1 Nov 2026. Sections C (drugs and biologics) and F (user facilities and importers) are not filled by a device
  manufacturer; G5 and G7 are for drug, biologic and cosmetic reports (FDA's instructions).
- **India:** the Medical Device Adverse Event Reporting Form, Version 1.2, of the Materiovigilance Programme of India
  (Indian Pharmacopoeia Commission), read from the copy the National Health Systems Resource Centre publishes
  (nhsrcindia.org, "Medical-Devices-Adverse-Event-Reporting-Form-(Version-1.2).pdf") on 1 Nov 2026; ipc.gov.in did not
  answer. The licensing-authority notice (Rule 26) comes later (D-T18).
- **EU / NI, Great Britain and Canada** (0.10.76, Release C part C4), each a starter "for your consultant to confirm",
  on the new navigation only: the European Commission's MIR form 7.3.1 (build SB-11154, 6 May 2026) and its help text;
  MHRA's GB MIR 7.2.1 (4 Jun 2025: its schemas, help text and implementation guide); Health Canada's Mandatory Medical
  Device Problem Reporting Form for Industry, HC Pub. 110180 (April 2018), with SOR/98-282 ss. 59-61.1. All read on
  3 Nov 2026; each form's ``source_document`` names them. Their report types (``report_types``) decide which fields
  are mandatory (``Field.must_in``).

Each field names where its value comes from (``source``, worksheet.py) and, when the records hold none, its missing
class (G2b): must have before submission, may be unknown in an initial report, or follow up later. Patient and reporter
fields keep their place: the sample fills them with fictional values; for any other data they stay blank, marked
"enter in the authority's route" (T-B9), and MDARIX never stores them. Which record feeds which field is MDARIX's
starter mapping, marked starter text until the regulatory consultant reviews it (T-B6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MUST, INITIAL, LATER, NOT_USED = "MUST_HAVE", "MAY_BE_UNKNOWN", "FOLLOW_UP", "NOT_APPLICABLE"
MISSING_LABELS = {
    MUST: "Missing: must have before submission",
    INITIAL: "Missing: may be unknown in an initial report",
    LATER: "Missing: follow up later",
    NOT_USED: "Not used in this report",
}
PATIENT, REPORTER = "PATIENT", "REPORTER"
TEXT, DATE, DATE_RANGE, IMDRF_CODE, LIST_CODE = "TEXT", "DATE", "DATE_RANGE", "IMDRF_CODE", "LIST_CODE"
_DATE_WORD = re.compile(r"\bdate\b", re.I)
_NOT_A_DATE = re.compile(r"^(age|duration)\b", re.I)
# The fields whose value is a code of a published list, with the list it is checked against when loaded
# (backend/app/regulatory_reference.py) and the pattern every code of it has.
LIST_CODES = {
    "us_product_code": ("FDA_PRODUCT_CODE", re.compile(r"^[A-Z]{3}$"), "An FDA product code is three letters"),
    "eu_nomenclature_code": (
        "EMDN",
        re.compile(r"^[A-Z](\d{2})*$"),
        "An EMDN code is a letter and pairs of digits, for example Z12030101",
    ),
    "gmdn_code": (None, re.compile(r"^\d{5}$"), "A GMDN code is five digits"),
}
_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s*(?:to|-|–|—)\s*(\d{4}-\d{2}-\d{2}))?$")


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def value_problem(field: "Field", value: str | None) -> str | None:
    """Why a typed value does not fit its field (0.10.81, F6), or None: a date field takes a date (YYYY-MM-DD), a range
    field a date or "YYYY-MM-DD to YYYY-MM-DD", a list code its list's pattern, and an IMDRF code field only the code
    picker's codes. The server refuses such a value; one stored before is flagged on the report."""
    text = (value or "").strip()
    if not text:
        return None
    kind = field.kind
    if kind == IMDRF_CODE:
        return "Choose the code in the code picker: typed text is not a code"
    if kind == DATE and _day(text) is None:
        return "Enter a date as YYYY-MM-DD"
    if kind == DATE_RANGE:
        found = _RANGE.match(text)
        days = [_day(part) for part in found.groups() if part] if found else []
        if not days or None in days or days != sorted(days):
            return "Enter a date as YYYY-MM-DD, or a range as YYYY-MM-DD to YYYY-MM-DD"
    if kind == LIST_CODE:
        _, pattern, words = LIST_CODES[field.source]
        if not pattern.match(text.upper()):
            return words
    return None


# Codes a form needs beyond its own classes, on the new navigation (0.10.77, C5; starter, for your consultant to
# confirm). An initial 3500A needs a code of each of FDA's seven H6 kinds (0.10.96: FDA's "Required 3500A fields", as
# the rule book authority_reports/rules/us_emdr.csv lists them; Send for approval checks the eMDR file), so the
# meter shows what blocks it. The EU and GB MIR already need Annex A, E and F, and B, C, D (and G) in a final report
# (``must_in``).
CODES_REQUIRED = {
    "FDA_3500A": (
        "H6_CLINICAL",
        "H6_IMPACT",
        "H6_COMPONENT",
        "H6_TYPE",
        "H6_FINDINGS",
        "H6_CONCLUSIONS",
    )
}


@dataclass(frozen=True)
class Field:
    id: str
    number: str
    label: str
    source: str | None = None  # a key of worksheet.SOURCES, or None: a person enters it
    missing: str = INITIAL
    personal: str | None = None  # PATIENT or REPORTER
    note: str = ""
    # The report types in which the field is mandatory (0.10.76); empty: its ``missing`` class for every type.
    must_in: tuple[str, ...] = ()
    # The form's fixed list for this field, as printed (0.10.76); empty: free text.
    options: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        """What the field takes (0.10.81, F6), read from its source and label: an IMDRF code (picked, never typed), a
        published list's code (an FDA product code, an EMDN or GMDN code), a date, a date or a range of dates
        ("from ... to ..."), or text."""
        if self.source and self.source.startswith("imdrf_"):
            return IMDRF_CODE
        if self.source in LIST_CODES:
            return LIST_CODE
        if self.options or self.personal or not _DATE_WORD.search(self.label) or _NOT_A_DATE.match(self.label):
            return TEXT
        return DATE_RANGE if "(from" in self.label else DATE


@dataclass(frozen=True)
class Section:
    code: str
    title: str
    fields: tuple[Field, ...]
    note: str = ""


@dataclass(frozen=True)
class Route:
    code: str
    label: str
    # Each evidence kind of this route and the outcomes it may record (G2b's evidence per route).
    evidence: dict
    acknowledgement_expected: bool = True
    note: str = ""


@dataclass(frozen=True)
class Form:
    code: str
    market: str
    title: str
    version: str
    authority: str
    source_document: str
    sections: tuple[Section, ...]
    routes: tuple[Route, ...]
    basis: tuple[str, ...]
    # The form's report types, in its order, and the field that holds the chosen one (0.10.76).
    report_types: tuple[str, ...] = ()
    type_field: str = ""
    # A starter form "for your consultant to confirm" (0.10.76's three); the 3500A and MDAE forms are not.
    starter: bool = False

    def fields(self) -> list[Field]:
        return [item for section in self.sections for item in section.fields]


_RECEIPT, _ACCEPTED, _REJECTED, _CONTENT = "RECEIPT", "ACCEPTED", "REJECTED", "CONTENT"

FDA_3500A = Form(
    "FDA_3500A",
    "US",
    "Form FDA 3500A worksheet (eMDR)",
    "Form FDA 3500A (09/2025)",
    "U.S. Food and Drug Administration (CDRH)",
    "Form FDA 3500A MedWatch (09/2025) and Form FDA 3500A Supplement (09/2025) - Form Instructions, fda.gov",
    (
        Section(
            "FRONT",
            "Front page",
            # No number of its own (0.10.72: it read "Mfr report # Manufacturer report number").
            (Field("MFR_REPORT", "", "Manufacturer report number", None, MUST),),
            "The same number as G8.",
        ),
        Section(
            "A",
            "A. Patient information",
            (
                Field("A1", "A1", "Patient identifier (in confidence)", personal=PATIENT),
                Field("A2", "A2", "Age or date of birth", personal=PATIENT),
                Field("A3", "A3", "Sex", personal=PATIENT),
                Field("A4", "A4", "Weight", personal=PATIENT),
                Field("A5", "A5", "Race and/or ethnicity", personal=PATIENT),
            ),
            "FDA: do not use the patient's name, medical record number or social security number.",
        ),
        Section(
            "B",
            "B. Adverse event or product problem",
            (
                Field("B1", "B1", "Type of report (adverse event, product problem)", "event_type", MUST),
                Field("B2", "B2", "Outcome attributed to adverse event", "us_outcome", INITIAL),
                Field("B3", "B3", "Date of event", "event_date", INITIAL),
                Field(
                    "B4",
                    "B4",
                    "Date of this report",
                    "sent_day",
                    INITIAL,
                    note="Filled in with the day you send the report for approval.",
                ),
                Field("B5", "B5", "Describe event or problem", "description", MUST),
                Field("B6", "B6", "Relevant test/laboratory data, including dates", personal=PATIENT),
                Field("B7", "B7", "Other relevant history, including preexisting medical conditions", personal=PATIENT),
            ),
        ),
        Section(
            "C",
            "C. Suspect products",
            (),
            "For drugs, biologics and other products: not filled for a device report (section D).",
        ),
        Section(
            "D",
            "D. Suspect medical device",
            (
                Field("D1", "D1", "Brand name", "brand_name", MUST),
                Field("D2A", "D2a", "Procode", "us_product_code", MUST),
                Field("D2B", "D2b", "Common device name", "common_name", MUST),
                Field("D3", "D3", "Manufacturer name, city, state and country", "us_manufacturer", MUST),
                Field("D4_MODEL", "D4", "Model #", "model", INITIAL),
                Field("D4_LOT", "D4", "Lot #", "lot", INITIAL),
                Field("D4_CATALOG", "D4", "Catalog #", None, INITIAL),
                Field("D4_EXPIRY", "D4", "Expiration date", "lot_expiry", INITIAL),
                Field("D4_SERIAL", "D4", "Serial #", "serial", INITIAL),
                Field("D4_UDI", "D4", "Unique Device Identifier (UDI) #", "udi", INITIAL),
                Field("D5", "D5", "Operator of device", "us_operator", INITIAL),
                Field("D6A", "D6a", "If implanted, give date", None, INITIAL),
                Field("D6B", "D6b", "If explanted, give date", None, INITIAL),
                Field("D7A", "D7a", "Is this a single-use device that was reprocessed and reused on a patient?"),
                Field("D7B", "D7b", "If yes, enter the name and address of the reprocessor"),
                Field("D8", "D8", "Was this device ever serviced by a third-party servicer?"),
                Field("D9", "D9", "Is this device available for evaluation?", "available", LATER),
                Field("D10", "D10", "Concomitant medical products and therapy dates", personal=PATIENT),
            ),
        ),
        Section(
            "E",
            "E. Initial reporter",
            (
                Field("E1", "E1", "Name and address (phone, email)", personal=REPORTER),
                Field("E2", "E2", "Health professional?", "health_professional", INITIAL),
                Field("E3", "E3", "Occupation", personal=REPORTER),
                Field("E4", "E4", "Initial reporter also sent report to FDA?"),
            ),
        ),
        Section(
            "F",
            "F. For use by user facility/importer (devices only)",
            # B9 step 7: an importer's or user facility's report only (its role in the US); a manufacturer's report
            # shows the section empty, as before.
            (
                Field("F1", "F1", "Check one: user facility or importer", "us_role_name", MUST),
                Field(
                    "F2",
                    "F2",
                    "UF/importer report number",
                    None,
                    MUST,
                    note="Importer: your CFN or FEI, the year and a 5-digit number. User facility: your 10-digit HCFA "
                    "number, the year and a 4-digit number. Typed once; MDARIX numbers every later report from it.",
                ),
                Field("F3", "F3", "User facility or importer name/address", "us_role_address", INITIAL),
                Field("F4", "F4", "Contact person (with e-mail)", "us_role_contact", MUST),
                Field("F5", "F5", "Contact person's phone number", "us_role_phone", INITIAL),
                Field("F6", "F6", "Date user facility or importer became aware of event", "aware_date", INITIAL),
                Field("F7", "F7", "Type of report", "us_role_report_type", MUST),
                Field("F8", "F8", "Date of this report", "sent_day", INITIAL),
                Field("F9", "F9", "Approximate age of device", None, INITIAL, note="For example: 2 years, 8 months."),
                Field("F10_CLINICAL", "F10", "Health effect - clinical code", "imdrf_E", INITIAL),
                Field("F10_IMPACT", "F10", "Health effect - impact code", "imdrf_F", INITIAL),
                Field("F10_PROBLEM", "F10", "Medical device problem code", "imdrf_A", INITIAL),
                Field("F10_COMPONENT", "F10", "Component code", "imdrf_G", INITIAL),
                Field(
                    "F11",
                    "F11",
                    "Report sent to FDA?",
                    "us_sent_fda",
                    INITIAL,
                    note="From who must receive the report (the signed conclusion's rule), dated the day you send it "
                    "for approval. Record each recipient's send separately.",
                ),
                Field(
                    "F12",
                    "F12",
                    "Location where event occurred",
                    None,
                    INITIAL,
                    options=(
                        "Hospital",
                        "Home",
                        "Nursing home",
                        "Outpatient treatment facility",
                        "Outpatient diagnostic facility",
                        "Ambulatory surgical facility",
                        "Other",
                    ),
                    note='For "Other", type "Other: " and the place (up to 40 characters).',
                ),
                Field("F13", "F13", "Report sent to manufacturer?", "us_sent_manufacturer", INITIAL),
                Field("F14", "F14", "Manufacturer name/address", "us_manufacturer", INITIAL),
            ),
            "Filled by a user facility or an importer, not by the manufacturer.",
        ),
        Section(
            "G",
            "G. All manufacturers",
            (
                Field("G1", "G1", "Contact office (and manufacturing site for devices)", "us_contact_office", MUST),
                Field("G2", "G2", "Report source", "report_source", MUST),
                Field("G3", "G3", "Date received by manufacturer", "aware_date", MUST),
                Field("G4", "G4", "PMA/510(k) #", "us_clearance", MUST),
                Field("G5", "G5", "If IND/Pre-ANDA, give protocol #", missing=NOT_USED),
                Field("G6", "G6", "Type of report", "us_report_type", MUST),
                Field("G7", "G7", "Adverse event term(s)", missing=NOT_USED),
                Field(
                    "G8",
                    "G8",
                    "Manufacturer report number",
                    "front_page",
                    MUST,
                    note="The same number as the front page.",
                ),
            ),
            "G5 and G7 are for drug, biologic and cosmetic reports (FDA's instructions).",
        ),
        Section(
            "H",
            "H. Device manufacturers only",
            (
                Field("H1", "H1", "Type of reportable event", "us_event_type", MUST),
                Field("H2", "H2", "If follow-up, what type?", "follow_up_type", NOT_USED),
                Field("H3", "H3", "Device evaluated by manufacturer?", "case", LATER),
                Field("H4", "H4", "Device manufacture date", None, INITIAL),
                Field("H5", "H5", "Labeled for single use?", "single_use", INITIAL),
                Field("H6_PROBLEM", "H6", "Medical device problem code", "imdrf_A", MUST),
                Field("H6_CLINICAL", "H6", "Health effect - clinical code", "imdrf_E", INITIAL),
                Field("H6_IMPACT", "H6", "Health effect - impact code", "imdrf_F", INITIAL),
                Field("H6_COMPONENT", "H6", "Component code", "imdrf_G", LATER),
                Field("H6_TYPE", "H6", "Type of investigation code", "imdrf_B", LATER),
                Field("H6_FINDINGS", "H6", "Investigation findings code", "imdrf_C", LATER),
                Field(
                    "H6_CONCLUSIONS",
                    "H6",
                    "Investigation conclusions code",
                    "imdrf_D",
                    MUST,
                    note="FDA: conclusion codes must be entered even if the device was not evaluated.",
                ),
                Field("H7", "H7", "If remedial action initiated, check type", "capas", LATER),
                Field("H8", "H8", "Usage of device", None, INITIAL),
                Field("H9", "H9", "If action reported to FDA under 21 USC 360i(g), FDA-assigned recall number"),
                Field("H10", "H10", "Related report number"),
                Field("H11", "H11", "Additional manufacturer narrative", "case", LATER),
            ),
            "H6 codes are suggested from your approved IMDRF mappings of the complaint's problem code; you confirm or change "
            "each one in the code picker (IMDRF and FDA codes).",
        ),
    ),
    (
        Route(
            "EMDR",
            "FDA eMDR through eSubmitter (ESG NextGen)",
            {
                "SUBMITTED_CONTENT": (_CONTENT,),
                "ACK1": (_RECEIPT,),
                "ACK2": (_RECEIPT,),
                "ACK3": (_ACCEPTED, _REJECTED),
                "ACK4": (_RECEIPT,),
                "OTHER": (_RECEIPT,),
            },
            note="Ack1: received by FDA's gateway; Ack2: sent on to CDRH; Ack3 and Ack4 carry the load result. A "
            "receipt is not acceptance: Ack3's pass or fail decides it.",
        ),
        # B9 step 8: an importer's or user facility's copy to the manufacturer (21 CFR 803.30, 803.40), recorded
        # apart from the FDA submission; how it reaches the manufacturer is the customer's procedure.
        Route(
            "MFR_COPY",
            "Sent to the manufacturer (importer or user facility report)",
            {"SUBMITTED_CONTENT": (_CONTENT,), "OTHER": (_RECEIPT,)},
            acknowledgement_expected=False,
            note="Offered only on an importer's or user facility's report that the manufacturer must receive.",
        ),
    ),
    ("CFR803_50", "CFR803_53", "CFR803_3"),
)

MVPI_MDAE = Form(
    "MVPI_MDAE",
    "IN",
    "MvPI Medical Device Adverse Event Reporting Form worksheet",
    "MDAE Reporting Form, Version 1.2",
    "Materiovigilance Programme of India (Indian Pharmacopoeia Commission)",
    "Medical Device Adverse Event Reporting Form, Version 1.2, Materiovigilance Program of India (copy published by "
    "nhsrcindia.org)",
    (
        Section(
            "PRIMARY",
            "Primary information",
            (
                Field(
                    "P1",
                    "1",
                    "Date of report",
                    "sent_day",
                    INITIAL,  # filled at Send for approval: as FDA's B4, it never blocks sending
                    note="Filled in with the day you send the report for approval.",
                ),
                Field("P2", "2", "Type of report (initial, follow up, final, trend)", "in_report_type", MUST),
                Field("P3", "3", "Report reference no. for MDMC only", missing=NOT_USED),
                Field(
                    "P4",
                    "4",
                    "Report reference no. for MAH only",
                    None,
                    MUST,
                    note="Format: see the form's instructions.",
                ),
            ),
        ),
        Section(
            "REPORTER",
            "Reporter details",
            (
                # B9 step 11: from the organization's role in India (Manufacturer or Importer); typed over if needed.
                Field("R1", "1", "Type of reporter", "role_reporter", MUST),
                Field("R2A", "2 a)", "Has the reporter informed the incident to the manufacturer?"),
                Field("R2B", "2 b)", "Is the reporter also submitting the report on behalf of the manufacturer?"),
                Field(
                    "R3", "3", "Reporter contact information (name, address, tel./mobile, email)", "in_reporter", MUST
                ),
            ),
            "Question 2 is asked only when the reporter is not the manufacturer.",
        ),
        Section(
            "CATEGORY",
            "Medical device category",
            (
                Field(
                    "CAT1", "I", "Therapeutic, diagnostic, therapeutic and diagnostic, assistive, preventive, imaging"
                ),
                Field("CAT2", "II", "Implantable or non-implantable device", "implantable"),
                Field("CAT3", "III", "Invasive or non-invasive"),
                Field("CAT4", "IV", "Single use, reusable, or reuse of a manufacturer-marked single-use device", "use"),
                Field("CAT5", "V", "Sterile or non-sterile"),
                Field("CAT6", "VI", "Personal use / homecare use"),
                Field("IVD", "IVD", "In vitro diagnostics (IVD) category", missing=NOT_USED),
            ),
        ),
        Section(
            "A",
            "(A) Medical device description",
            (
                Field("A_COMMON", "", "Common medical device name", "common_name", MUST),
                Field("A_BRAND", "", "Trade name / brand name", "brand_name", MUST),
                Field("A_MANUFACTURER", "", "Manufacturer: name and address", "in_manufacturer", MUST),
                Field("A_IMPORTER", "", "Importer: name and address", "in_importer", INITIAL),
                Field("A_DISTRIBUTOR", "", "Distributor: name and address", None, INITIAL),
                Field("A1", "1", "Device risk classification as per India MDR 2017 (A, B, C, D)", "risk_class", MUST),
                Field("A2", "2", "Is the device refurbished? If yes, by whom"),
                Field("A3", "3", "License no. (manufacturer/importer)", "in_licence", MUST),
                Field("A4", "4", "Model no.", "model", INITIAL),
                Field("A5", "5", "Catalogue no.", None, INITIAL),
                Field("A6", "6", "Lot / batch no.", "lot", INITIAL),
                Field("A7", "7", "Serial no.", "serial", INITIAL),
                Field("A8", "8", "Software version (if applicable)", "software_version"),
                Field("A9", "9", "Associated devices / accessories"),
                Field("A10", "10", "Nomenclature code: GMDN/UMDNS (if applicable)", "gmdn_code", INITIAL),
                Field("A11", "11", "UDI no. (if applicable)", "udi", INITIAL),
                Field("A12", "12", "Installation date (if applicable)"),
                Field("A13", "13", "Expiration date (if applicable)", "lot_expiry"),
                Field("A14", "14", "Last preventive maintenance date (if applicable)"),
                Field("A15", "15", "Last calibration date (if applicable)"),
                Field("A16", "16", "Year of manufacturing", None, INITIAL),
                Field("A17", "17", "How long the device/equipment/machine was in use"),
                Field("A18", "18", "Availability of device for evaluation", "available", LATER),
                Field("A19", "19", "Is the usage of device as per manufacturer claim / instructions for use?"),
            ),
        ),
        Section(
            "B",
            "(B) Event description",
            (
                Field("B1", "1", "Date of event / near miss incident", "event_date", INITIAL),
                Field("B2", "2", "Type of event (adverse event, product problem)", "event_type", MUST),
                Field(
                    "B3",
                    "3",
                    "For implantable medical devices only: implanted and explanted dates",
                    note="Leave blank for a device that is not implanted.",
                ),
                Field("B4", "4", "Location of event", "in_location", INITIAL),
                Field("B5", "5", "Device operator", "in_operator", INITIAL),
                Field("B6", "6", "Device disposition / current location", "in_disposition", LATER),
                Field("B7", "7", "Is device in use after incidence?"),
                Field("B8", "8", "Serious event, with the reason", "in_serious", MUST),
                Field("B9", "9", "Non serious event", "in_non_serious", INITIAL),
                Field("B10", "10", "Other medical devices used at the same time with the above device"),
                Field(
                    "B11",
                    "11",
                    "Event outcome and reoccurrence (abated after use stopped; reappeared after reintroduction)",
                ),
                Field("B12", "12", "Detail description of event", "description", MUST),
                Field(
                    "B13",
                    "13",
                    "Frequency of occurrence of similar adverse event in India in past 3 years",
                    None,
                    LATER,
                ),
                Field(
                    "B14",
                    "14",
                    "Frequency of occurrence of similar adverse event globally in past 3 years",
                    None,
                    LATER,
                ),
            ),
            "Questions 13 and 14 are for the manufacturer or authorized representative only.",
        ),
        Section(
            "C",
            "(C) Patient information, history and outcome",
            (
                Field("C1", "1", "Patient hospital ID", personal=PATIENT),
                Field("C2", "2", "Patient initial", personal=PATIENT),
                Field("C3", "3", "Age", personal=PATIENT),
                Field("C4", "4", "Gender", personal=PATIENT),
                Field("C5", "5", "Weight", personal=PATIENT),
                Field("C6", "6", "Other relevant history, including pre-existing medical conditions", personal=PATIENT),
                Field("C7", "7", "Patient outcomes", personal=PATIENT),
            ),
        ),
        Section(
            "D",
            "(D) Healthcare facility information (if available)",
            (
                Field("D1", "1", "Name", personal=REPORTER),
                Field("D2", "2", "Address", personal=REPORTER),
                Field("D3", "3", "Contact person name at the site of event", personal=REPORTER),
                Field("D4", "4", "Tel. no. / mobile no.", personal=REPORTER),
                Field("D5", "5", "Email", personal=REPORTER),
            ),
        ),
        Section(
            "E",
            "(E) Medical device adverse event assessment",
            (
                Field("E1", "1", "Immediate action taken", "immediate_action", LATER),
                Field("E2", "2", "Suspected root cause of problem", None, LATER),
                Field(
                    "E3",
                    "3",
                    "Association between the suspected medical device and the adverse event (not related, possible, "
                    "probable, related)",
                    None,
                    MUST,
                ),
            ),
            "A judgement: MDARIX never fills it.",
        ),
        Section(
            "F",
            "(F) For manufacturer / authorized representative / license holder only",
            (
                Field("F1", "1", "Investigation needed?", "investigation_needed", INITIAL),
                Field("F2", "2", "Investigation action taken with timeline", "case", LATER),
                Field(
                    "F3",
                    "3",
                    "Root cause of problem (applicable for follow up / final reports)",
                    note="Expected on a follow-up or final report (B9).",
                ),
                Field("F4", "4", "Corrective and preventive action (CAPA) taken", "capas", LATER),
            ),
        ),
    ),
    (
        Route(
            "MVPI_EMAIL",
            "MvPI by e-mail (as the form names it: mvpi-ipc@gov.in)",
            {
                "SUBMITTED_CONTENT": (_CONTENT,),
                "SENT_EMAIL": (_RECEIPT,),
                "REFERENCE": (_RECEIPT,),
                "ACCEPTANCE": (_ACCEPTED,),
                "BOUNCE": (_REJECTED,),
                "REJECTION": (_REJECTED,),
                "OTHER": (_RECEIPT,),
            },
            note="Starter, for your consultant to confirm: keep the sent e-mail with its headers and any reference that comes back. A bounce is "
            "a rejection. Whether MvPI acknowledges, and what counts as acceptance, is for your procedure to confirm.",
        ),
        Route(
            "MVPI_ADRMS",
            "MvPI online reporting (ADRMS)",
            {
                "SUBMITTED_CONTENT": (_CONTENT,),
                "REFERENCE": (_RECEIPT,),
                "ACCEPTANCE": (_ACCEPTED,),
                "REJECTION": (_REJECTED,),
                "OTHER": (_RECEIPT,),
            },
            note="Starter, for your consultant to confirm: the online form may differ from Version 1.2; check it against the portal.",
        ),
    ),
    ("IN_MDR",),
)

# --------------------------------------------------------------------------------------------- 0.10.76 (C4)
# Three starter forms, "for your consultant to confirm" (Release C part C4), on the new navigation only (CLASSIC_MARKETS).
# Each field is the authority's own, in its order and numbering; a long run of address lines (street, number,
# complement, PO box, city, postal code, country, contact names, e-mail, phone) is one field here. ``must_in`` names
# the report types in which a field is mandatory (the form's own rule); a field without it keeps its class for every
# type. Where the source was unclear, the field's note says "to confirm".

MIR_INITIAL, MIR_FOLLOW_UP, MIR_COMBINED = "Initial", "Follow up", "Combined initial and final"
MIR_FINAL, MIR_FINAL_NON = "Final (Reportable incident)", "Final (Non-reportable incident)"
MIR_TYPES = (MIR_INITIAL, MIR_FOLLOW_UP, MIR_COMBINED, MIR_FINAL, MIR_FINAL_NON)
_NOT_NON = (MIR_COMBINED, MIR_INITIAL, MIR_FOLLOW_UP, MIR_FINAL)
_NOT_INITIAL = (MIR_COMBINED, MIR_FOLLOW_UP, MIR_FINAL, MIR_FINAL_NON)
_AFTER_INITIAL = (MIR_FOLLOW_UP, MIR_FINAL, MIR_FINAL_NON)
_NEXT_REPORT = (MIR_INITIAL, MIR_FOLLOW_UP)
_WITH_UDI = (MIR_COMBINED, MIR_FINAL, MIR_FINAL_NON)
_FINAL_SI = (MIR_COMBINED, MIR_FINAL)
_YES_NO = ("Yes", "No")
_MIR_CLASSES = (
    "Serious public health threat",
    "Death",
    "Unanticipated serious deterioration in state of health",
    "All other reportable incidents",
)
_MIR_LOCATIONS = (
    "Healthcare facility/carer",
    "Patient/user",
    "In transit to manufacturer",
    "Manufacturer",
    "Distributor",
    "Discarded",
    "Remains implanted",
    "Unknown",
    "Other",
)
_MIR_USAGE = (
    "Initial use",
    "Reuse of a reusable medical device",
    "Problem noted prior use",
    "Reuse of a single use medical device",
    "Re-serviced/refurbished/fully refurbished",
    "Other",
)
_MIR_MARKET_DATE = (
    "First declaration of conformity",
    "The device first CE marked",
    "First placed on the market",
    "First put into service",
    "If software, date first made available",
)
_MIR_VARIANT = ("Model", "Software", "Lot/Batch", "Product platform", "Other variant")
_MIR_DENOMINATOR = (
    "Devices placed on the market or put into service",
    "Units distributed within each time period",
    "Number of tests performed",
    "Number of episodes of use (for reusable devices)",
    "Active installed base",
    "Units distributed from the date of declaration of conformity/CE mark approval to the end date of each time period",
    "Number of devices implanted",
    "Other",
)


def _mir_device(market: str) -> tuple[Field, ...]:
    """Sections 2.3 to 2.6 shared by the EU and GB forms (GB adds its UK approved body fields)."""
    gb = market == "GB"
    return (
        Field("2_3A", "2.3a", "Medical device name (brand, trade, proprietary or common name)", "brand_name", MUST),
        Field(
            "2_3B",
            "2.3b",
            "Description of the device and its intended purpose",
            None,
            MUST if gb else INITIAL,
            must_in=() if gb else _NOT_INITIAL,
        ),
        *(
            ()
            if gb
            else (
                Field(
                    "2_3B_TEXT",
                    "2.3b",
                    "Nomenclature text",
                    "common_name",
                    INITIAL,
                    must_in=_NOT_INITIAL,
                    note="Only when a nomenclature is chosen in 2.2a. Its place before or after the description is to "
                    "confirm.",
                ),
            )
        ),
        Field("2_3C", "2.3c", "Model", "model"),
        Field("2_3D", "2.3d", "Catalogue/reference number"),
        Field("2_3E", "2.3e", "Serial number", "serial"),
        Field("2_3F", "2.3f", "Lot/batch number", "lot"),
        Field("2_3G", "2.3g", "Software version", "software_version"),
        Field("2_3H", "2.3h", "Firmware version"),
        Field("2_3I", "2.3i", "Device manufacturing date"),
        Field("2_3J", "2.3j", "Device expiry date", "lot_expiry"),
        Field("2_3K", "2.3k", "Date when the device was implanted (from … to …)"),
        Field("2_3L", "2.3l", "Date when the device was explanted (from … to …)"),
        Field("2_3M", "2.3m", "Duration of implantation, if the dates are unknown (years, months, days)"),
        Field("2_3N", "2.3n", "Implant facility"),
        Field("2_3O", "2.3o", "Explant facility"),
        Field(
            "2_3P_NB",
            "2.3p",
            "Notified body (NB) ID number(s), if applicable",
            "nb_number",
            INITIAL,
            must_in=() if gb else _WITH_UDI,
            note="Depends on the risk class (2.4): the per-class rule is to confirm.",
        ),
        Field(
            "2_3P_CERT",
            "2.3p",
            "Notified body (NB) certificate number(s) of the device, if applicable",
            "eu_certificate",
            INITIAL,
            must_in=() if gb else _WITH_UDI,
        ),
        *(
            (
                Field("2_3_UKAB", "", "UK approved body (UKAB) ID number(s), if applicable", note="4 digits."),
                Field(
                    "2_3_UKAB_CERT",
                    "",
                    "UK approved body (UKAB) certificate number(s) of the device, if applicable",
                    "gb_certificate",
                ),
            )
            if gb
            else ()
        ),
        Field("2_3Q", "2.3q", "Date of one of the following (year and month)", options=_MIR_MARKET_DATE),
        Field(
            "2_4",
            "2.4",
            "Risk class of the device when placed on the market (legislation unknown; before the MDD/AIMDD/IVDD; the "
            "MDD/AIMDD/IVDD class; or the MDR/IVDR class and type)",
            "risk_class",
            INITIAL if gb else MUST,
            note="GB: optional in MHRA's schema (to confirm)." if gb else "",
        ),
        *(
            ()
            if gb
            else (
                Field(
                    "2_4E",
                    "2.4e",
                    "Did this device continue to be placed on the EU market after the MDR/IVDR date of application?",
                    options=("No", "Yes"),
                    note="Mandatory when an MDD/AIMDD/IVDD class is chosen in 2.4.",
                ),
                Field(
                    "2_4F",
                    "2.4f",
                    "Does the device fulfil any of these cases: Art. 52(9)/52(10) MDR scientific opinion; companion "
                    "diagnostic with the competent authority or EMA consulted (IVDR)?",
                    options=("No", "Yes"),
                    note="Mandatory for MDR devices and IVDR class C/D or companion diagnostics.",
                ),
            )
        ),
        Field(
            "2_5",
            "2.5",
            "Market distribution of the device (region or country), to the manufacturer's best knowledge",
            None,
            INITIAL,
            must_in=_FINAL_SI,
        ),
        Field("2_6A", "2.6a", "Relevant accessories used with the device (with their manufacturer if different)"),
        Field(
            "2_6B", "2.6b", "Relevant associated devices used with the device (with their manufacturer if different)"
        ),
    )


def _mir_incident(market: str) -> tuple[Section, ...]:
    gb = market == "GB"
    return (
        Section(
            "3_1",
            "3.1 Nature of incident",
            (
                Field(
                    "3_1A",
                    "3.1a",
                    "A comprehensive description of the incident: what went wrong with the device, and the health "
                    "effects (clinical signs, symptoms, conditions and overall health impact)",
                    "description",
                    MUST,
                ),
            ),
        ),
        Section(
            "3_2",
            "3.2 Medical device problem information",
            (
                Field(
                    "3_2A",
                    "3.2a",
                    "IMDRF medical device problem codes (Annex A): choice 1, most relevant",
                    "imdrf_A",
                    MUST,
                    note="GB: A27 when no code fits (MHRA)." if gb else "",
                ),
                Field("3_2B", "3.2b", "Number of patients involved"),
                # 0.10.81 (F12): never guessed from "device returned" (it may be with a distributor or the facility).
                Field(
                    "3_2C",
                    "3.2c",
                    "Current location of the device",
                    None,
                    MUST,
                    options=_MIR_LOCATIONS,
                    note="Where the device is now.",
                ),
                Field(
                    "3_2D",
                    "3.2d",
                    "Operator of the device at the time of the incident",
                    "mir_operator",
                    options=("Healthcare professional", "Patient/lay user", "Other"),
                ),
                Field("3_2E", "3.2e", "Usage of the device (as intended)", options=_MIR_USAGE),
                Field("3_2F", "3.2f", "Remedial actions taken by the healthcare facility, patient or user"),
            ),
        ),
        Section(
            "3_3",
            "3.3 Clinical information" if not gb else "3.3 Patient information",
            (
                Field(
                    "3_3A_E",
                    "3.3a",
                    "IMDRF clinical signs, symptoms and conditions codes (Annex E): choice 1",
                    "imdrf_E",
                    MUST,
                ),
                Field("3_3A_F", "3.3a", "IMDRF health impact codes (Annex F): choice 1", "imdrf_F", MUST),
                Field("3_3B", "3.3b", "Age of the patient at the time of the incident", personal=PATIENT),
                Field("3_3C", "3.3c", "Gender", personal=PATIENT),
                Field("3_3D", "3.3d", "Body weight (kg)", personal=PATIENT),
                *(() if gb else (Field("3_3E", "3.3e", "Height (cm)", personal=PATIENT),)),
                Field(
                    "3_3F",
                    "3.3f",
                    "The patient's prior health conditions or medication relevant to this incident",
                    personal=PATIENT,
                ),
            ),
        ),
        Section(
            "3_4",
            "3.4 Initial reporter",
            (
                Field(
                    "3_4A",
                    "3.4a",
                    "Role of the initial reporter",
                    "mir_reporter_role",
                    MUST,
                    options=("Healthcare professional", "Patient", "Lay user", "Other"),
                ),
                Field("3_4B", "3.4b", "Name of the healthcare facility where the incident occurred", personal=REPORTER),
                Field("3_4C", "3.4c", "Healthcare facility report number, if applicable", personal=REPORTER),
                Field("3_4D", "3.4d-g", "Contact's name, e-mail and phone", personal=REPORTER),
                *(() if gb else (Field("3_4H", "3.4h", "Country of the initial reporter", "incident_country", MUST),)),
                Field(
                    "3_4I",
                    "3.4i-n",
                    "Address (street, number, complement, PO box, city, postal code)",
                    personal=REPORTER,
                ),
            ),
        ),
    )


def _mir_analysis(market: str) -> tuple[Section, ...]:
    gb = market == "GB"
    codes = () if gb else _FINAL_SI
    codes_class = MUST if gb else LATER
    return (
        Section(
            "4_1",
            "4.1 Manufacturer's preliminary comments",
            (
                Field(
                    "4_1A",
                    "4.1a",
                    "Preliminary results and conclusions of the manufacturer's investigation (initial and follow-up "
                    "reports)",
                    "case",
                    LATER,
                    must_in=_NEXT_REPORT,
                ),
                *(
                    ()
                    if gb
                    else (
                        Field(
                            "4_1B",
                            "4.1b",
                            "Suspicion of a relationship between the incident and the medicinal substance(s), "
                            "tissue(s) or cell(s) of human origin associated with the device",
                            options=_YES_NO,
                            note="Only when 2.4f is Yes.",
                        ),
                    )
                ),
                Field(
                    "4_1C",
                    "4.1c",
                    "Initial actions (corrective and/or preventive) implemented by the manufacturer",
                    "capas",
                    LATER,
                    must_in=(MIR_FOLLOW_UP,),
                ),
                Field(
                    "4_1D",
                    "4.1d",
                    "Further investigations intended to reach final conclusions",
                    None,
                    LATER,
                    must_in=(MIR_FOLLOW_UP,),
                ),
            ),
        ),
        Section(
            "4_2",
            "4.2 Cause investigation and conclusion",
            (
                Field(
                    "4_2A",
                    "4.2a",
                    "The manufacturer's evaluation of possible root causes or causative factors, and "
                    "its conclusion (final, serious incident)",
                    None,
                    LATER,
                    must_in=_FINAL_SI,
                ),
                Field(
                    "4_2B",
                    "4.2b",
                    "Rationale for why this is considered not reportable (final, non-reportable)",
                    None,
                    LATER,
                    must_in=(MIR_FINAL_NON,),
                ),
                Field("4_2C", "4.2c", "Is the root cause confirmed?", None, LATER, must_in=_FINAL_SI, options=_YES_NO),
                Field(
                    "4_2D",
                    "4.2d",
                    "Has the risk assessment been reviewed? If yes, is it still adequate, and the results; if no, the "
                    "rationale",
                    None,
                    LATER,
                    must_in=_FINAL_SI,
                ),
                Field(
                    "4_2E_B",
                    "4.2e",
                    "IMDRF type of investigation codes (Annex B): choice 1",
                    "imdrf_B",
                    codes_class,
                    must_in=codes,
                ),
                Field(
                    "4_2E_C",
                    "4.2e",
                    "IMDRF investigation findings codes (Annex C): choice 1",
                    "imdrf_C",
                    codes_class,
                    must_in=codes,
                ),
                Field(
                    "4_2E_D",
                    "4.2e",
                    "IMDRF investigation conclusion codes (Annex D): choice 1",
                    "imdrf_D",
                    codes_class,
                    must_in=codes,
                ),
                Field(
                    "4_2F",
                    "4.2f",
                    "IMDRF component codes (Annex G): choice 1",
                    "imdrf_G",
                    codes_class,
                    must_in=codes,
                    note="GB: MHRA requires a code from every annex (fallback codes for no fit)." if gb else "",
                ),
                Field(
                    "4_2G",
                    "4.2g",
                    "Remedial action, corrective action, preventive action or field safety corrective action (FSCA)",
                    "capas",
                    LATER,
                    must_in=_FINAL_SI,
                    note="Write n/a if not applicable. An FSCA is reported separately.",
                ),
                Field("4_2H", "4.2h", "Time schedule for the implementation of the identified actions"),
                Field(
                    "4_2I",
                    "4.2i",
                    "Final comments from the manufacturer on the cause investigation and conclusion",
                    None,
                    LATER,
                    must_in=() if gb else _FINAL_SI,
                ),
            ),
        ),
        Section(
            "4_3",
            "4.3 Similar serious incidents (final reports)",
            (
                Field(
                    "4_3_1A",
                    "4.3.1a",
                    "Similar serious incidents identified by IMDRF codes (Annex A, Annex C, or other, with the "
                    "rationale)",
                    None,
                    INITIAL if gb else LATER,
                    # B8-D6: the help text's "mandatory in final reports" is stricter than the XSD's optional.
                    must_in=() if gb else _FINAL_SI,
                ),
                Field(
                    "4_3_3A",
                    "4.3.3a",
                    "On which basis similar serious incidents were identified, and its details",
                    None,
                    LATER,
                    must_in=_FINAL_SI,
                    options=_MIR_VARIANT,
                ),
                Field(
                    "4_3_3B",
                    "4.3.3b",
                    "On which criteria the number of devices on the market is based",
                    None,
                    LATER,
                    must_in=_FINAL_SI,
                    options=_MIR_DENOMINATOR,
                ),
                Field(
                    "4_3_3C",
                    "4.3.3c",
                    "Number of similar serious incidents and of devices on the market per time period (N to N-3): the "
                    "incident's country, EEA + TR + XI, and the world",
                    None,
                    LATER,
                    must_in=_FINAL_SI,
                ),
                Field(
                    "4_3_3D",
                    "4.3.3d",
                    "How similar incidents and the number of devices on the market were determined",
                    None,
                    LATER,
                    must_in=() if gb else _FINAL_SI,
                ),
            ),
        ),
        Section("5", "5. General comments", (Field("5", "5", "General comments"),)),
    )


_MIR_EVIDENCE = {
    "SUBMITTED_CONTENT": (_CONTENT,),
    "SENT_EMAIL": (_RECEIPT,),
    "REFERENCE": (_RECEIPT,),
    "ACCEPTANCE": (_ACCEPTED,),
    "REJECTION": (_REJECTED,),
    "OTHER": (_RECEIPT,),
}

EU_MIR = Form(
    "EU_MIR",
    "EU_NI",
    "EU Manufacturer Incident Report (MIR) worksheet",
    "MIR form 7.3.1 (SB-11154, 06-05-2026)",
    "The national competent authority of the country where the incident occurred (EU MDR / IVDR)",
    "Manufacturer Incident Report (MIR) for Serious Incidents (MDR/IVDR), version 7.3.1, build SB-11154 (6 May 2026), "
    "and its help text v7.3.1, European Commission (health.ec.europa.eu, PMSV reporting forms; mandatory from 1 May "
    "2026), read 3 Nov 2026",
    (
        Section(
            "1_1",
            "1.1 Responsible competent authority in the country where the incident occurred",
            (
                Field(
                    "1_1A",
                    "1.1a",
                    "Name of the receiving national competent authority (NCA)",
                    "eu_nca",
                    MUST,
                    note="From the incident country (the Commission's vigilance contact points); Northern Ireland: ask "
                    "MHRA.",
                ),
                Field("1_1B", "1.1b", "EUDAMED number of the NCA", note="Mandatory once available in EUDAMED."),
                Field(
                    "1_1C",
                    "1.1c",
                    "Reference number assigned by the NCA for this incident",
                    "nca_reference",
                    INITIAL,
                    must_in=_AFTER_INITIAL,
                    note="Write Unknown if the NCA gave none.",
                ),
                Field("1_1D", "1.1d", "Reference number assigned by EUDAMED for this incident"),
            ),
        ),
        Section(
            "1_2",
            "1.2 Date, type and classification of the incident report",
            (
                Field(
                    "1_2A",
                    "1.2a",
                    "Date of report submission",
                    "sent_day",
                    MUST,
                    note="The day sent for approval (B8-D1): record the real day at submission.",
                ),
                Field("1_2B", "1.2b", "Date of the incident (from … to …)", "event_date", MUST),
                Field("1_2C", "1.2c", "Manufacturer awareness date of the incident", "aware_date", MUST),
                Field(
                    "1_2D",
                    "1.2d",
                    "Manufacturer awareness date of reportability",
                    None,
                    INITIAL,
                    must_in=_NOT_NON,
                    # 0.10.81 (F12): not the signing day; the MIR help text (7.3.1) asks for this date.
                    note="The date you received the information that showed the incident is reportable.",
                ),
                Field("1_2E", "1.2e", "Type of report", "report_type", MUST, options=MIR_TYPES),
                Field(
                    "1_2F",
                    "1.2f",
                    "Expected date of the next report (initial and follow-up reports)",
                    None,
                    INITIAL,
                    must_in=_NEXT_REPORT,
                ),
                Field(
                    "1_2G",
                    "1.2g",
                    "Classification of serious incident",
                    "mir_classification",
                    INITIAL,
                    must_in=_NOT_NON,
                    options=_MIR_CLASSES,
                ),
            ),
        ),
        Section(
            "1_3",
            "1.3 Submitter information",
            (
                Field(
                    "1_3_1A",
                    "1.3.1a",
                    "Submitter of the report",
                    None,
                    MUST,
                    options=("Manufacturer", "Authorised representative", "Other"),
                ),
                Field(
                    "1_3_1B",
                    "1.3.1b",
                    "Manufacturer's reference number for this incident",
                    "complaint_ref",
                    MUST,
                    note="Unique for each incident: the complaint's ID, the same on every report of the chain.",
                ),
                Field(
                    "1_3_1C",
                    "1.3.1c",
                    "Reference numbers of the other MIR forms for the same incident (multiple "
                    "devices of the same manufacturer): NCA, EUDAMED, manufacturer",
                ),
                Field(
                    "1_3_1D",
                    "1.3.1d",
                    "If the incident is covered by an FSCA: its NCA, EUDAMED and manufacturer reference numbers",
                ),
                Field("1_3_1E", "1.3.1e", "Periodic Summary Report (PSR) ID"),
                Field(
                    "1_3_1F",
                    "1.3.1f",
                    "The incident occurred within a PMCF/PMPF investigation (if yes, its EUDAMED ID)",
                    options=("No", "Yes"),
                ),
                Field("1_3_2A", "1.3.2a", "Manufacturer organisation name", "manufacturer_name", MUST),
                Field(
                    "1_3_2B",
                    "1.3.2b",
                    "Manufacturer's single registration number (SRN)",
                    "manufacturer_srn",
                    MUST,
                    note="Unknown is allowed until EUDAMED is in place.",
                ),
                Field(
                    "1_3_2C",
                    "1.3.2c-m",
                    "Manufacturer contact and address (contact's names, e-mail, phone, "
                    "country, street, city, postal code)",
                    "manufacturer",
                    MUST,
                ),
                Field(
                    "1_3_3",
                    "1.3.3",
                    "Authorised representative: organisation name, SRN, contact and address",
                    "authorised_rep",
                    MUST,
                    note="Mandatory when the manufacturer is not in the EU/EEA, Turkey or Northern Ireland (to "
                    "confirm for your organization).",
                ),
                Field(
                    "1_3_4",
                    "1.3.4",
                    "Submitter's details if not the manufacturer or the authorised representative",
                    note="Only when 1.3.1a is Other.",
                ),
            ),
        ),
        Section(
            "2_1",
            "2.1 Unique Device Identification (UDI)",
            (
                Field(
                    "2_1A",
                    "2.1a",
                    "(Master) UDI-DI / EUDAMED ID, and its issuing entity",
                    "udi",
                    INITIAL,
                    must_in=_WITH_UDI,
                ),
                Field(
                    "2_1B",
                    "2.1b",
                    "UDI production identifier",
                    None,
                    INITIAL,
                    must_in=_WITH_UDI,
                    note="Unknown by default.",
                ),
                Field(
                    "2_1C",
                    "2.1c",
                    "Basic UDI-DI / EUDAMED DI, and its issuing entity",
                    "basic_udi",
                    INITIAL,
                    must_in=_WITH_UDI,
                ),
                Field("2_1D", "2.1d", "Unit of use UDI-DI, and its issuing entity"),
            ),
        ),
        Section(
            "2_2",
            "2.2 Categorisation of the device",
            (
                Field(
                    "2_2A",
                    "2.2a",
                    "Medical device nomenclature",
                    "eu_nomenclature_system",
                    options=("EMDN", "GMDN", "UMDNS (ECRI)", "GIVD/EDMS", "Other"),
                ),
                Field(
                    "2_2B",
                    "2.2b",
                    "Medical device nomenclature code",
                    "eu_nomenclature_code",
                    note="Mandatory once 2.2a is chosen.",
                ),
            ),
        ),
        Section("2_3", "2.3-2.6 Description of the device, risk class and market distribution", _mir_device("EU_NI")),
        *_mir_incident("EU_NI"),
        *_mir_analysis("EU_NI"),
    ),
    (
        Route(
            "EU_NCA",
            "EUDAMED, or the national competent authority's channel (the MIR form)",
            _MIR_EVIDENCE,
            note="Starter, for your consultant to confirm: keep what you sent and the authority's reference; for Northern Ireland, MHRA's MORE "
            "portal with the EU form.",
        ),
    ),
    ("MDR_87", "IVDR_82", "MDCG_2023_3"),
    report_types=MIR_TYPES,
    type_field="1_2E",
    starter=True,
)

GB_MIR = Form(
    "GB_MIR",
    "GB",
    "Great Britain Manufacturer Incident Report (MHRA, GB MIR) worksheet",
    "GB MIR 7.2.1 (04/06/2025)",
    "Medicines and Healthcare products Regulatory Agency (MHRA)",
    "MHRA: GB Manufacturer Incident Report (MIR) 7.2.1 (changelog 04/06/2025, its five GB schemas and its help text), "
    "the GB MIR and FSCA schema implementation guide (updated 9 Jun 2025) and Vigilance reporting requirements "
    "(updated 5 Sep 2025), gov.uk, read 3 Nov 2026. Field labels follow the EU MIR where MHRA gives none (to confirm)",
    (
        Section(
            "1_1",
            "1.1 Corresponding competent authority",
            (
                Field("1_1A", "1.1", "Name of the receiving national competent authority", "gb_nca", MUST),
                Field(
                    "1_1C",
                    "1.1",
                    "Reference number assigned by the MHRA for this incident",
                    None,
                    INITIAL,
                    must_in=_AFTER_INITIAL,
                    note="MORE generates it for a web-form initial or combined report; keep the same number on every "
                    "version.",
                ),
            ),
        ),
        Section(
            "1_2",
            "1.2 Date, type and classification of the incident report",
            (
                Field("1_2A", "1.2", "Date of this report", None, MUST, note="The day you submit."),
                Field("1_2B", "1.2", "Date of the incident (from … to …)", "event_date", MUST),
                Field("1_2C", "1.2", "Manufacturer awareness date", "aware_date", MUST),
                Field("1_2E", "1.2", "Type of report", "report_type", MUST, options=MIR_TYPES),
                Field("1_2F", "1.2", "Expected date of the next report", None, INITIAL, must_in=_NEXT_REPORT),
                Field(
                    "1_2G",
                    "1.2",
                    "Classification of the incident",
                    "mir_classification",
                    INITIAL,
                    must_in=_NOT_NON,
                    options=_MIR_CLASSES,
                    note="Mandatory in a follow-up and a combined report: to confirm.",
                ),
            ),
        ),
        Section(
            "1_3",
            "1.3 Submitter information",
            (
                Field(
                    "1_3_1A",
                    "1.3.1",
                    "Submitter of the report",
                    None,
                    MUST,
                    options=(
                        "Manufacturer",
                        "Authorised representative",
                        "United Kingdom Responsible Person",
                        "Others",
                    ),
                ),
                Field(
                    "1_3_1D",
                    "1.3.1",
                    "Submitter's details (organisation, contact's names, city, country, postcode, phone, e-mail)",
                    "manufacturer",
                    MUST,
                ),
                Field("1_3_2A", "1.3.2", "Manufacturer name", "manufacturer_name", MUST),
                Field("1_3_2B", "1.3.2", "Manufacturer's single registration number (SRN)"),
                Field(
                    "1_3_2C",
                    "1.3.2",
                    "Manufacturer contact and address (contact's names, city, country, postcode, phone, e-mail)",
                    "manufacturer",
                    MUST,
                ),
                Field(
                    "1_3_3",
                    "1.3.3",
                    "Authorised representative / United Kingdom Responsible Person: organisation name, SRN, contact "
                    "and address",
                    "uk_responsible_person",
                    MUST,
                    note="For a manufacturer outside the UK (to confirm for your organization).",
                ),
                Field("1_3_1B", "1.3", "Manufacturer's reference number for this incident", None, MUST),
                Field(
                    "1_3_1C",
                    "1.3",
                    "Reference numbers of the other reports for the same incident (multiple "
                    "devices): MHRA and manufacturer",
                ),
                Field(
                    "1_3_1E",
                    "1.3",
                    "If the incident is covered by an FSCA: its MHRA and manufacturer reference numbers",
                ),
                Field("1_3_1F", "1.3", "Periodic Summary Report (PSR) ID"),
                Field("1_3_1G", "1.3", "PMCF/PMPF investigation ID"),
            ),
            "MHRA removed the EUDAMED numbers from the GB form.",
        ),
        Section(
            "2_1",
            "2.1 UDI",
            (
                Field(
                    "2_1A",
                    "2.1",
                    "UDI-DI",
                    "udi",
                    MUST,
                    note="MHRA: where the device has a UDI it must be given; if it has none, enter Unknown.",
                ),
                Field("2_1B", "2.1", "UDI production identifier"),
                Field("2_1C", "2.1", "Basic UDI-DI"),
                Field("2_1D", "2.1", "Unit of use UDI-DI"),
                Field("2_1E", "2.1", "UDI issuing entity", options=("GS1", "HIBCC", "ICCBBA", "IFA")),
            ),
        ),
        Section(
            "2_2",
            "2.2 Categorisation of the device",
            (
                Field(
                    "2_2A",
                    "2.2",
                    "Medical device nomenclature (GMDN only on the GB form)",
                    "gmdn_system",
                    options=("GMDN",),
                ),
                Field("2_2B", "2.2", "Medical device nomenclature code", "gmdn_code"),
            ),
        ),
        Section("2_3", "2.3-2.6 Description of the device, risk class and market distribution", _mir_device("GB")),
        *_mir_incident("GB"),
        *_mir_analysis("GB"),
    ),
    (
        Route(
            "MHRA_MORE",
            "MHRA's MORE portal (Manufacturer's On-line Reporting Environment): web form, XML or API",
            {key: value for key, value in _MIR_EVIDENCE.items() if key != "SENT_EMAIL"},
            note="MHRA accepts no other route. Starter, for your consultant to confirm: keep the MORE reference and the submitted copy.",
        ),
    ),
    ("UK_MDR",),
    report_types=MIR_TYPES,
    type_field="1_2E",
    starter=True,
)

CA_PRELIMINARY, CA_UPDATE, CA_FINAL, CA_BOTH = "Preliminary", "Update", "Final", "Preliminary & Final"
CA_TYPES = (CA_PRELIMINARY, CA_UPDATE, CA_FINAL, CA_BOTH)
# "Preliminary reports require that all sections (except E2 & E3) be filled"; the starred fields on every report.
_CA_PRELIM = (CA_PRELIMINARY, CA_BOTH)
_CA_FINALS = (CA_FINAL, CA_BOTH)
_CA_LATER = (CA_UPDATE, CA_FINAL)


def _ca(id_: str, number: str, label: str, source: str | None = None, **extra) -> Field:
    """A Canada field mandatory in a preliminary report (the form: every section but E2 and E3)."""
    return Field(id_, number, label, source, extra.pop("missing", INITIAL), must_in=_CA_PRELIM, **extra)


HC_MDPR = Form(
    "HC_MDPR",
    "CA",
    "Health Canada mandatory medical device problem report worksheet",
    "HC Pub. 110180 (April 2018)",
    "Health Canada: Canada Vigilance, Medical Device Problem Reporting (MedEffect Canada)",
    "Mandatory Medical Device Problem Reporting Form for Industry, HC Pub. 110180 (April 2018), and Incident reporting "
    "for medical devices: Guidance document (in effect 23 June 2021), canada.ca; Medical Devices Regulations "
    "SOR/98-282 ss. 59-61.1 (current to 2026-10-19), read 3 Nov 2026",
    (
        Section(
            "A",
            "A. Reporter information",
            (
                # B9 step 11: from the organization's role in Canada (Manufacturer or Importer).
                _ca("A1", "A1 i", "Reporter type", "role_reporter", options=("Manufacturer", "Importer")),
                Field(
                    "A1_II",
                    "A1 ii",
                    "If the importer reports: did the importer report the incident to the manufacturer?",
                    options=_YES_NO,
                ),
                Field(
                    "A1_III",
                    "A1 iii",
                    "If the importer reports: is the importer also submitting the report on "
                    "behalf of the manufacturer?",
                    options=_YES_NO,
                ),
                Field(
                    "A2", "A2", "Reporter contact information (name, e-mail, telephone, fax)", "contact_office", MUST
                ),
                Field(
                    "A3",
                    "A3",
                    "Reporter file no.",
                    None,
                    MUST,
                    note="A final report keeps the preliminary report's number.",
                ),
                Field(
                    "A4",
                    "A4",
                    "Health Canada file no. (if applicable)",
                    "ca_hc_file",
                    INITIAL,
                    must_in=_CA_LATER,
                    note="From Health Canada's acknowledgement of the preliminary report, carried to every later report.",
                ),
                Field("A5", "A5", "Type of report", "report_type", MUST, options=CA_TYPES),
                Field(
                    "A5_FINAL_DATE",
                    "A5",
                    "Anticipated date of the final report (preliminary only)",
                    None,
                    INITIAL,
                    must_in=(CA_PRELIMINARY,),
                ),
                Field(
                    "A5_PREVIOUS",
                    "A5",
                    "Date the previous report was submitted to Health Canada (update or final)",
                    "ca_previous",
                    INITIAL,
                    must_in=_CA_LATER,
                ),
                Field(
                    "A6",
                    "A6",
                    "Date submitted",
                    "sent_day",
                    INITIAL,  # filled at Send for approval: as FDA's B4, it never blocks sending
                    note="Filled in with the day you send the report for approval.",
                ),
                _ca("A7_MFR", "A7", "Name and address: manufacturer", "manufacturer"),
                Field("A7_IMP", "A7", "Name and address: importer", "importer"),
                Field(
                    "A8",
                    "A8",
                    "Health Canada assigned company identification number, if known (manufacturer, importer)",
                ),
                Field("A9", "A9", "Establishment licence number (MDEL), if applicable (manufacturer, importer)"),
            ),
        ),
        Section(
            "B",
            "B. Incident information",
            (
                Field(
                    "B1",
                    "B1",
                    "Classification of incident: 10-day or 30-day; Canadian or foreign; investigational "
                    "testing, Special Access Program or radiation emitting device, if applicable",
                    "ca_classification",
                    MUST,
                ),
                _ca("B2", "B2", "Date of incident", "event_date"),
                _ca("B3", "B3", "Reporter's awareness date", "aware_date"),
                _ca(
                    "B4",
                    "B4",
                    "Patient consequences: the consequences, or potential consequences, to the patient, "
                    "user or other person(s)",
                    "consequences",
                ),
                _ca(
                    "B5",
                    "B5",
                    "Details of incident: the device(s), equipment or drugs involved, and what happened",
                    "description",
                ),
            ),
        ),
        Section(
            "C",
            "C. Medical device information",
            (
                Field("C1", "C1", "Trade/brand name", "brand_name", MUST),
                _ca("C2", "C2", "Control/lot/serial no.", "lot_serial"),
                _ca("C3", "C3", "Expiration date", "lot_expiry"),
                _ca("C4_I", "C4 i", "Device classification", "risk_class", options=("I", "II", "III", "IV")),
                _ca("C4_II", "C4 ii", "Device licence no.", "ca_licence"),
                _ca("C4_III", "C4 iii", "Device identification no.", "udi"),
                _ca("C4_IV", "C4 iv", "Manufacturer's medical device identifier (catalogue/model no.)", "model"),
                _ca("C5", "C5", "Software version", "software_version"),
                _ca("C6", "C6", "Age of device (years since the manufacturing date)"),
                _ca("C7", "C7", "How long was the device in use?"),
                _ca("C8", "C8", "Was the device labelled as sterile?", options=_YES_NO),
                _ca(
                    "C9",
                    "C9",
                    "Availability of device for evaluation",
                    "ca_available",
                    options=("Destroyed", "Returned to Manufacturer/Importer", "Neither"),
                ),
            ),
        ),
        Section(
            "D",
            "D. Complainant information",
            (
                _ca(
                    "D1",
                    "D1",
                    "Complainant is a",
                    "ca_complainant",
                    options=("Consumer", "Health professional", "Other"),
                ),
                Field("D2", "D2", "Name of complainant", personal=REPORTER),
                Field("D3", "D3", "Name of health care facility (if applicable)", personal=REPORTER),
                Field("D4", "D4", "Address", personal=REPORTER),
                Field("D5", "D5", "Telephone no. and/or e-mail address", personal=REPORTER),
            ),
        ),
        Section(
            "E",
            "E. Investigation information",
            (
                _ca(
                    "E1",
                    "E1",
                    "Investigative actions and timeline (a rationale if no investigation is done)",
                    "case",
                    missing=LATER,
                ),
                Field("E2", "E2", "Root cause of problem (final reports only)", None, LATER, must_in=_CA_FINALS),
                Field(
                    "E3",
                    "E3",
                    "Corrective actions taken as a result of the investigation, with a rationale (final reports only)",
                    "capas",
                    LATER,
                    must_in=_CA_FINALS,
                ),
            ),
            'The form prints "This section only applies for preliminary & final, and final reports" between E1 and '
            "E2: read here as E2 and E3 (to confirm).",
        ),
    ),
    (
        Route(
            "HC_EMAIL",
            "Health Canada (Canada Vigilance, MDPR) by e-mail or fax, as the form names it",
            {
                "SUBMITTED_CONTENT": (_CONTENT,),
                "SENT_EMAIL": (_RECEIPT,),
                "REFERENCE": (_RECEIPT,),
                "BOUNCE": (_REJECTED,),
                "REJECTION": (_REJECTED,),
                "OTHER": (_RECEIPT,),
            },
            note="Starter, for your consultant to confirm: the form and Health Canada's pages give different addresses (to confirm). Keep the "
            "sent e-mail and the acknowledgement letter with its Health Canada file number.",
        ),
    ),
    ("CA_MDR",),
    report_types=CA_TYPES,
    type_field="A5",
    starter=True,
)


# The response to an authority's request for information (G2b): its content is written by a person.
RESPONSE = Form(
    "RESPONSE",
    "",
    "Response to a request for information",
    "response-starter-1",
    "",
    "",
    (
        Section(
            "RESPONSE",
            "Response",
            (
                Field("REQUEST", "", "What the authority asked", "request", MUST),
                Field("RESPONSE", "", "Your response", None, MUST),
            ),
        ),
    ),
    (),
    (),
)

FORMS = {form.code: form for form in (FDA_3500A, MVPI_MDAE, EU_MIR, GB_MIR, HC_MDPR, RESPONSE)}
# The worksheet each market has (0.10.76: EU / NI, Great Britain and Canada join, on the new navigation only).
BY_MARKET = {"US": FDA_3500A, "IN": MVPI_MDAE, "EU_NI": EU_MIR, "GB": GB_MIR, "CA": HC_MDPR}
# The markets whose worksheet the classic navigation (and every pilot on it) keeps: its 0.10.58 rules.
CLASSIC_MARKETS = ("US", "IN")
ROUTE_LABELS = {route.code: route.label for form in FORMS.values() for route in form.routes}
EVIDENCE_LABELS = {
    "SUBMITTED_CONTENT": "Submitted content (the portal's copy, export or a reconstruction)",
    "ACK1": "Ack1: received by FDA's gateway",
    "ACK2": "Ack2: sent on to CDRH",
    "ACK3": "Ack3: load result (pass or fail)",
    "ACK4": "Ack4: load result (XML)",
    "SENT_EMAIL": "The sent e-mail with its headers",
    "REFERENCE": "The authority's reference",
    "ACCEPTANCE": "The authority's acceptance",
    "BOUNCE": "Delivery failure (bounce)",
    "REJECTION": "The authority's rejection",
    "OTHER": "Other evidence",
}


# Fields as they were before B9 (typed), in force again while their part's switch is off (spec 6.4: "today's
# worksheet stays"): India's P1; Canada's A4, A5 previous date and A6.
_BEFORE_B9 = {
    ("MVPI_MDAE", "P1"): (
        "MDARIX_B9_INDIA",
        Field("P1", "1", "Date of report", None, MUST, note="The day you submit."),
    ),
    ("HC_MDPR", "A4"): (
        "MDARIX_B9_CANADA",
        Field(
            "A4",
            "A4",
            "Health Canada file no. (if applicable)",
            None,
            INITIAL,
            must_in=_CA_LATER,
            note="From Health Canada's acknowledgement of the preliminary report.",
        ),
    ),
    ("HC_MDPR", "A5_PREVIOUS"): (
        "MDARIX_B9_CANADA",
        Field(
            "A5_PREVIOUS",
            "A5",
            "Date the previous report was submitted to Health Canada (update or final)",
            None,
            INITIAL,
            must_in=_CA_LATER,
        ),
    ),
    ("HC_MDPR", "A6"): (
        "MDARIX_B9_CANADA",
        Field("A6", "A6", "Date submitted", None, MUST, note="The day you submit."),
    ),
    ("MVPI_MDAE", "R1"): ("MDARIX_B9_INDIA", Field("R1", "1", "Type of reporter", None, MUST)),
    ("HC_MDPR", "A1"): (
        "MDARIX_B9_CANADA",
        Field("A1", "A1 i", "Reporter type", None, INITIAL, must_in=_CA_PRELIM, options=("Manufacturer", "Importer")),
    ),
}


def switched_on(name: str) -> bool:
    from backend.app import feature_set

    return feature_set.switched_on(name)


def india_derived() -> bool:
    """B9 step 14 is in force: India's P1 is the day sent for approval and P2 follows the chain. Off, both are typed
    as before B9 (today's worksheet stays)."""
    return switched_on("MDARIX_B9_INDIA")


def in_force(form: Form, field: Field) -> Field:
    """The field as the switches have it now: a field B9 derives is typed again while its part's switch is off."""
    before = _BEFORE_B9.get((form.code, field.id))
    return before[1] if before and not switched_on(before[0]) else field


def form_for(market: str, new_navigation: bool) -> Form | None:
    """The market's worksheet, or None: the classic navigation keeps the US and India ones only."""
    return BY_MARKET.get(market) if new_navigation or market in CLASSIC_MARKETS else None


def report_kind(form: Form, entries: dict) -> str | None:
    """The report type a worksheet is (its type field's entered choice, else the form's first type), or None for a
    form without report types."""
    if not form.report_types:
        return None
    chosen = (entries.get(form.type_field) or {}).get("value")
    return chosen if chosen in form.report_types else form.report_types[0]


def missing_class(item: Field, kind: str | None) -> str:
    """A field's missing class in a report of this type: mandatory where its form says so."""
    return MUST if item.must_in and kind in item.must_in else item.missing


def routes_for(form: Form) -> tuple[Route, ...]:
    """A response goes back by the route its obligation's report went (the parent's routes)."""
    return form.routes or tuple(route for item in BY_MARKET.values() for route in item.routes)


def route_of(form: Form, code: str) -> Route | None:
    return next((route for route in routes_for(form) if route.code == code), None)
