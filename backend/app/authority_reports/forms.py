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

Each field names where its value comes from (``source``, worksheet.py) and, when the records hold none, its missing
class (G2b): must have before submission, may be unknown in an initial report, or follow up later. Patient and reporter
fields keep their place: the sample fills them with fictional values; for any other data they stay blank, marked
"enter in the authority's route" (T-B9), and MDARIX never stores them. Which record feeds which field is MDARIX's
starter mapping, marked starter text until the regulatory consultant reviews it (T-B6).
"""

from __future__ import annotations

from dataclasses import dataclass

MUST, INITIAL, LATER, NOT_USED = "MUST_HAVE", "MAY_BE_UNKNOWN", "FOLLOW_UP", "NOT_APPLICABLE"
MISSING_LABELS = {
    MUST: "Missing: must have before submission",
    INITIAL: "Missing: may be unknown in an initial report",
    LATER: "Missing: follow up later",
    NOT_USED: "Not used in this report",
}
PATIENT, REPORTER = "PATIENT", "REPORTER"


@dataclass(frozen=True)
class Field:
    id: str
    number: str
    label: str
    source: str | None = None  # a key of worksheet.SOURCES, or None: a person enters it
    missing: str = INITIAL
    personal: str | None = None  # PATIENT or REPORTER
    note: str = ""


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
            (Field("MFR_REPORT", "Mfr report #", "Manufacturer report number", None, MUST),),
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
                Field("B4", "B4", "Date of this report", None, MUST, note="The day you submit."),
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
            (),
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
                Field("G8", "G8", "Manufacturer report number", None, MUST, note="The same number as the front page."),
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
                Field("H5", "H5", "Labeled for single use?", None, INITIAL),
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
            "H6 codes come from your approved IMDRF mappings of the complaint's problem code (Records > Reference data).",
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
                Field("P1", "1", "Date of report", None, MUST, note="The day you submit."),
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
                Field("R1", "1", "Type of reporter", None, MUST),
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
                Field("A1", "1", "Device risk classification as per India MDR 2017 (A, B, C, D)", None, MUST),
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
                    "B3", "3", "For implantable medical devices only: implanted and explanted dates",
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
                Field("F3", "3", "Root cause of problem (applicable for follow up / final reports)", missing=NOT_USED),
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
            note="Starter text: keep the sent e-mail with its headers and any reference that comes back. A bounce is "
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
            note="Starter text: the online form may differ from Version 1.2; check it against the portal.",
        ),
    ),
    ("IN_MDR",),
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

FORMS = {form.code: form for form in (FDA_3500A, MVPI_MDAE, RESPONSE)}
# The worksheet each market has in this release; EU/NI and GB come with MVP set 5, Canada and Australia with 1.0.1.
BY_MARKET = {"US": FDA_3500A, "IN": MVPI_MDAE}
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


def routes_for(form: Form) -> tuple[Route, ...]:
    """A response goes back by the route its obligation's report went (the parent's routes)."""
    return form.routes or FDA_3500A.routes + MVPI_MDAE.routes


def route_of(form: Form, code: str) -> Route | None:
    return next((route for route in routes_for(form) if route.code == code), None)
