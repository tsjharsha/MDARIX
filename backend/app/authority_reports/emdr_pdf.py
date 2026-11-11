"""The approved US report as a readable PDF of its eMDR file (0.10.96, decision D1): FDA's Form 3500A blocks, labels
and order, as eSubmitter lays out a report's content, in MDARIX's clean text layout (owner Q4), with the values read
back from the file itself through FDA's XPaths (emdr.POINTERS). What the PDF shows is what the file says.

The title says who made it: "Form FDA 3500A – eMDR content, prepared by MDARIX". It never claims FDA or eSubmitter
made it. After the blocks comes MDARIX's record page: who prepared it, the source records, the approved values the
file does not carry, the approval and the file's SHA-256. A report not yet approved is marked DRAFT - NOT APPROVED
(D7). No date or time is written into the PDF, so the same file renders the same bytes.
"""

from __future__ import annotations

from datetime import date

from backend.app.authority_reports import emdr
from backend.app.authority_reports import fda_3500a as fda

TITLE = "Form FDA 3500A – eMDR content, prepared by MDARIX"
RECORD_TITLE = "MDARIX record - not part of the eMDR file"
# What the PDF reads beyond the blocks compared with FDA's examples (emdr.POINTERS): units, the birth date, the
# manufacturer (D3), the contact office's name (G1), the PMA/510(k) (G4) and the follow-up type (H2).
_UNIT = emdr.IE + "/trigger/reaction/subject/investigativeSubject/subjectOf/observation/code[@code='{}']/../value/@unit"
_MAKER = emdr.DEV + "/identifiedDevice/asManufacturedProduct/manufacturerOrReprocessor[code/@code='C53616']"
_F = emdr.IE + "/pertinentInformation1[sequenceNumber]/secondaryCaseNotification"
EXTRA = {
    "A2 unit": _UNIT.format("C25150"),
    "A2 born": emdr.IE + "/trigger/reaction/subject/investigativeSubject/subjectAffectedPerson/birthTime/@value",
    "A4 unit": _UNIT.format("C25208"),
    "D3 name": _MAKER + "/name/text()",
    "D3 email": _MAKER + "/telecom[starts-with(@value, 'mailto:')]/@value",
    "G1 name": _MAKER + "/contactParty[1]/addr/additionalLocator/text()",
    "G4": emdr.DEV + "/identifiedDevice/inventoryItem/manufacturedDeviceModel/asRegulatedProduct/id/@extension",
    "H2": "//message/controlActProcess/reasonOf/detectedIssueEvent/code[@code='C53584']/../value/@code",
    "G6 follow-up #": "//message/controlActProcess/reasonOf/detectedIssueEvent/value[@code='C53579']/../text/text()",
    # D8 "unknown" goes as FDA's null flavour, not a value.
    "D8 null": emdr.POINTERS["D8"].removesuffix("@value") + "@nullFlavor",
    # Section F (B9 step 7): an importer's or user facility's report.
    "F3": _F + "/author/assignedEntity/assignedOrganization/addr/additionalLocator/text()",
    "F5": _F + "/author/assignedEntity/assignedOrganization/contactParty/contactPerson/telecom"
    "[starts-with(@value, 'tel:')]/@value",
    "F9 unit": emdr.POINTERS["F9"].removesuffix("@value") + "@unit",
    "F11 sent": _F + "/receiver/@negationInd",
    "F12 other": emdr.POINTERS["F12"].removesuffix("@code") + "originalText/text()",
    "F13 sent": emdr.IE + "/pertinentInformation1/secondaryCaseNotification/receiver[time/low]/@negationInd",
    "F14 email": emdr.IE + "/pertinentInformation1/secondaryCaseNotification/receiver/assignedEntity"
    "/assignedOrganization/telecom[starts-with(@value, 'mailto:')]/@value",
}
UNITS = {"YR": "Year(s)", "MO": "Month(s)", "WK": "Week(s)", "DA": "Day(s)", "KG": "Kilogram(s)", "LBS": "Pound(s)"}
# FDA's choices in its order and words; their codes are fda_3500a.CHOICES' (one table for the form, file and PDF).
OPTIONS = {
    "A3": ("Male", "Female"),
    "B2": (
        "Death",
        "Life-threatening",
        "Hospitalization (initial or prolonged)",
        "Disability or Permanent Damage",
        "Congenital Anomaly/Birth Defects",
        "Required Intervention to Prevent Permanent Impairment/Damage",
        "Other Serious or Important Medical Events",
    ),
    "D5": ("Health Professional", "Patient/Consumer"),
    "D7A": ("Yes", "No"),
    "D8": ("Yes", "No", "Unknown"),
    "D9": ("Yes", "No"),
    "E4": ("Yes", "No", "Unknown"),
    "G2": (
        "Foreign",
        "Study",
        "Literature",
        "Consumer",
        "Health Professional",
        "User Facility",
        "Company Representative",
        "Distributor/Importer",
    ),
    "G6": ("5-day", "7-day", "15-day", "30-day", "Non-expedited (Periodic)", "Initial"),
    "H1": ("Death", "Serious Injury", "Malfunction"),
    "H3": ("Yes", "No"),
    "H5": ("Yes", "No"),
    "H7": (
        "Recall",
        "Repair",
        "Replace",
        "Relabeling",
        "Notification",
        "Inspection",
        "Patient Monitoring",
        "Modification/Adjustment",
    ),
    "H8": ("Initial Use of Device", "Reuse", "Unknown"),
}
# FDA's own codes outside the form's choices: H2's follow-up types (HL7Medwatch.xlsx, VOCAB).
H2 = (
    ("Correction", "C53585"),
    ("Additional Information", "C53586"),
    ("Response to FDA Request", "C53587"),
    ("Device Evaluation", "C53588"),
)
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def read(xml: bytes) -> dict[str, list[str]]:
    """Every block's values as the file holds them (FDA's XPaths), empty blocks left out."""
    doc = emdr.plain(xml)
    found = {
        block: [str(value).strip() for value in doc.xpath(path)] for block, path in {**emdr.POINTERS, **EXTRA}.items()
    }
    return {block: values for block, values in found.items() if any(values)}


def day(value: str) -> str:
    """FDA's dd-mmm-yyyy from the file's yyyymmdd."""
    found = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    return f"{found.day:02d}-{_MONTHS[found.month - 1]}-{found.year}"


def _ticks(block: str, held: list[str], *, many: bool) -> str:
    """FDA's choices with the held ones ticked: [X] where several may apply, (X) where one does."""
    table = fda.CHOICES[block]
    marks = ("[X]", "[ ]") if many else ("(X)", "( )")
    return " ".join(f"{marks[table[label.lower()][1] not in held]} {label}" for label in OPTIONS[block])


def _flag(block: str, held: list[str]) -> str:
    """A yes/no block: the file holds true, false or (D8) ASKU for unknown; E4's negation reads through CHOICES."""
    return _ticks(block, held, many=False)


def body(values: dict[str, list[str]]) -> list[tuple[str, str]]:
    """Blocks A to H with FDA's numbers, labels and order; a block the file does not hold shows as a dash."""
    one = lambda block: (values.get(block) or [""])[0]  # noqa: E731
    lines: list[tuple[str, str]] = []

    def section(title: str) -> None:
        lines.extend((("", "body"), (title, "heading")))

    def item(label: str, *shown: str) -> None:
        lines.append((label, "body"))
        lines.extend((f"    {text}", "body") for text in (shown or ("-",)) if text is not None)

    def dated(block: str) -> str:
        return day(one(block)) if one(block) else "-"

    section("A. PATIENT INFORMATION")
    item("1. Patient Identifier (In confidence)", one("A1") or "-")
    age = f"{one('A2')} {UNITS.get(one('A2 unit'), one('A2 unit'))}" if one("A2") else ""
    item(
        "2. Age at Time of Event, Date of Birth",
        ", ".join(filter(None, (age, one("A2 born") and day(one("A2 born"))))) or "-",
    )
    item("3a. Sex", _ticks("A3", values.get("A3", []), many=False))
    item("3b. Gender")
    weight = f"{one('A4')} {UNITS.get(one('A4 unit'), one('A4 unit'))}" if one("A4") else "-"
    item("4. Weight", weight)
    item("5. Ethnicity")
    item("6. Race")

    section("B. ADVERSE EVENT OR PRODUCT PROBLEM")
    held = values.get("B1", [])
    adverse, problem = (
        ("[X]" if fda.CHOICES["B1"][key][1] in held else "[ ]") for key in ("adverse event", "product problem")
    )
    lines.append((f"1. {adverse} Adverse Event and/or {problem} Product Problem (e.g., defects/malfunctions)", "body"))
    item(
        "2. Outcomes Attributed to Adverse Event (Check all that apply)", _ticks("B2", values.get("B2", []), many=True)
    )
    item("3. Date of Event (dd-mmm-yyyy)", dated("B3"))
    # FDA's follow-up leaves B4 out (0.10.96): not applicable, never a dash that reads as missing.
    follow_up = one("G6 follow-up #") or one("F7 number")
    item("4. Date of this Report (dd-mmm-yyyy)", "Not applicable (follow-up)" if follow_up else dated("B4"))
    item("5. Describe Event or Problem", one("B5") or "-")
    item("6. Relevant Tests/Laboratory Data, Including Dates", one("B6") or "-")
    item(
        "7. Other Relevant History, Including Preexisting Medical Conditions (e.g., allergies, race, pregnancy, "
        "smoking and alcohol use, hepatic/renal dysfunction, etc.)",
        one("B7") or "-",
    )

    section("C. SUSPECT PRODUCT(S)")
    lines.append(("Not used for a device report.", "muted"))

    section("D. SUSPECT MEDICAL DEVICE")
    item("1. Brand Name", one("D1") or "-")
    procode = one("D2 procode")
    item(
        "2. Common Device Name",
        ", ".join(filter(None, (one("D2 common name"), procode and f"Product Code: {procode}"))) or "-",
    )
    maker = one("D3 email").removeprefix("mailto:")
    item("3. Manufacturer Name, City and State", one("D3 name") or "-", maker and f"Email: {maker}" or None)
    item(
        "4. Model #, Catalog #, Serial #, Lot #, Expiration Date (dd-mmm-yyyy), Unique Identifier (UDI) #",
        f"Model #: {one('D4 model') or '-'}",
        f"Catalog #: {one('D4 catalog') or '-'}",
        f"Serial #: {one('D4 serial') or '-'}",
        f"Lot #: {one('D4 lot') or '-'}",
        f"Expiration Date: {dated('D4 expiry')}",
        f"Unique Identifier (UDI) #: {one('D4 UDI') or '-'}",
    )
    item("5. Operator of Device", _ticks("D5", values.get("D5", []), many=False))
    item("6a. If Implanted, Give Date (dd-mmm-yyyy)", dated("D6A"))
    item("6b. If Explanted, Give Date (dd-mmm-yyyy)", dated("D6B"))
    item(
        "7a. Is this a Single-Use Device that was Reprocessed and Reused on a Patient?",
        _flag("D7A", values.get("D7A", [])),
    )
    item("7b. If Yes, Enter Name and Address of Reprocessor")
    item("8. Was this device serviced by a third party?", _flag("D8", values.get("D8", []) + values.get("D8 null", [])))
    item("9. Device Available for Evaluation? (Do not send to FDA)", _flag("D9", values.get("D9", [])))
    item("10. Concomitant Medical Products and Therapy Dates (Excludes treatment of event)", one("D10") or "-")

    section("E. INITIAL REPORTER")
    item("1. Name and Address")
    item("2. Health Professional?")
    occupation = {code: label for label, code in fda.OCCUPATIONS.values()}
    item("3. Occupation", occupation.get(one("E3"), one("E3")) or "-")
    item("4. Initial Reporter Also Sent Report to FDA?", _flag("E4", values.get("E4", [])))

    section("F. FOR USE BY USER FACILITY/IMPORTER (Devices Only)")
    role = one("F1")
    if not role:
        lines.append(("Not used in a manufacturer's report.", "muted"))
    else:
        _section_f(values, one, item, dated)
        for title in ("G. ALL MANUFACTURERS", "H. DEVICE MANUFACTURERS ONLY"):
            section(title)
            lines.append(("Not used in an importer's or user facility's report.", "muted"))
        lines.extend((("", "body"), ("File Attachments: none", "body")))
        return lines

    section("G. ALL MANUFACTURERS")
    contact = [one("G1 name") or "-"]
    contact += [f"Telephone: {one('G1 phone').removeprefix('tel:')}"] if one("G1 phone") else []
    contact += [f"Email: {one('G1 email').removeprefix('mailto:')}"] if one("G1 email") else []
    item("1. Contact Office (and Manufacturing Site for Devices)", *contact)
    item("2. Report Source (Check all that apply)", _ticks("G2", values.get("G2", []), many=True))
    item("3. Date Received by Manufacturer (dd-mmm-yyyy)", dated("G3"))
    item("4. Premarket Identification PMA/510(k)", one("G4") or "-")
    item("5. If IND/PreANDA, Give Protocol #")
    number = one("G6 follow-up #")
    follow = f"[X] Follow-up #: {number}" if number else "[ ] Follow-up"
    item("6. Type of Report", f"{_ticks('G6', values.get('G6', []), many=True)} {follow}")
    item("7. Adverse Event Term(s)")
    item("8. Manufacturer Report Number", one("G8") or "-")

    section("H. DEVICE MANUFACTURERS ONLY")
    item("1. Type of Reportable Event", _ticks("H1", values.get("H1", []), many=False))
    held = values.get("H2", [])
    item("2. If Follow-up, What Type?", " ".join(f"{'[X]' if code in held else '[ ]'} {label}" for label, code in H2))
    item("3. Device Evaluated by Manufacturer?", _flag("H3", values.get("H3", [])))
    item("4. Device Manufacture Date (dd-mmm-yyyy)", dated("H4"))
    item("5. Labeled for Single Use?", _flag("H5", values.get("H5", [])))
    item(
        "6. Adverse Event Problem (Refer to coding manual)",
        *(
            f"{label}: {' - '.join(values.get(block, [])) or '-'}"
            for label, block in (
                ("Health Effect - Clinical Code", "H6 clinical"),
                ("Health Effect - Impact Code", "H6 impact"),
                ("Medical Device Problem Code", "H6 problem"),
                ("Component Code", "H6 component"),
                ("Type of Investigation", "H6 type"),
                ("Investigation Findings", "H6 findings"),
                ("Investigation Conclusions", "H6 conclusions"),
            )
        ),
    )
    item("7. If Remedial Action Initiated, Check Type", _ticks("H7", values.get("H7", []), many=True))
    item("8. Usage of Device", _ticks("H8", values.get("H8", []), many=False))
    item(
        "9. If action reported to FDA under 21 USC 360i(f), list correction/removal reporting number", one("H9") or "-"
    )
    item("10. Related Report Numbers", ", ".join(values.get("H10", [])) or "-")
    item("11. Additional Manufacturer Narrative", one("H11") or "-")
    lines.extend((("", "body"), ("File Attachments: none", "body")))
    return lines


def _section_f(values: dict[str, list[str]], one, item, dated) -> None:
    """Section F's blocks in FDA's order (B9 step 7), read back from the file."""
    reporter = {"C53617": "Importer", "C53567": "User Facility"}.get(one("F1"), "-")
    item(
        "1. Check One",
        " ".join(f"{'(X)' if label == reporter else '( )'} {label}" for label in ("User Facility", "Importer")),
    )
    item("2. UF/Importer Report Number", one("F2") or "-")
    item("3. User Facility or Importer Name/Address", one("F3") or "-")
    item("4. Contact Person", one("F4 email").removeprefix("mailto:") or "-")
    item("5. Phone Number", one("F5").removeprefix("tel:") or "-")
    item("6. Date User Facility or Importer Became Aware of Event (dd-mmm-yyyy)", dated("F6"))
    number = one("F7 number")
    item(
        "7. Type of Report",
        f"[{' ' if number else 'X'}] Initial [{'X' if number else ' '}] Follow-up #: {number or '-'}",
    )
    item("8. Date of This Report (dd-mmm-yyyy)", "-")
    age = f"{one('F9')} {UNITS.get(one('F9 unit'), one('F9 unit'))}" if one("F9") else "-"
    item("9. Approximate Age of Device", age)
    item(
        "10. Event Problem Codes (Refer to coding manual)",
        *(
            f"{label}: {' - '.join(values.get(block, [])) or '-'}"
            for label, block in (
                ("Health Effect - Clinical Code", "H6 clinical"),
                ("Health Effect - Impact Code", "H6 impact"),
                ("Medical Device Problem Code", "H6 problem"),
                ("Component Code", "H6 component"),
            )
        ),
    )
    sent = {"false": "Yes", "true": "No"}
    fda_sent = sent.get(one("F11 sent"), "-")
    item("11. Report Sent to FDA?", f"{fda_sent}" + (f", {dated('F11')}" if one("F11") else ""))
    place = {code: label for label, (_, code) in fda.CHOICES["F12"].items()}.get(one("F12"), "-")
    item(
        "12. Location Where Event Occurred", place.capitalize() + (f": {one('F12 other')}" if one("F12 other") else "")
    )
    maker_sent = sent.get(one("F13 sent"), "-")
    item("13. Report Sent to Manufacturer?", f"{maker_sent}" + (f", {dated('F13')}" if one("F13") else ""))
    email = one("F14 email").removeprefix("mailto:")
    item("14. Manufacturer Name/Address", one("F14") or "-", email and f"Email: {email}" or None)


def record(view: dict, left: list[str], sha256: str, note: str) -> list[tuple[str, str]]:
    """MDARIX's record page: who prepared it, the source records, what the file leaves out, the approval, the hash."""
    from backend.app.authority_reports.render import LABELS, _sources, manifestation
    from reports.pdf import PAGE_BREAK

    out: list[tuple[str, str]] = [("", PAGE_BREAK), (RECORD_TITLE, "heading")]
    out.append(
        ("This page is MDARIX's record of the report. It is not part of the eMDR file and is not sent.", "muted")
    )
    out += [("", "body"), ("Prepared by", "heading"), (", ".join(view.get("preparers") or []) or "-", "body")]
    sources = _sources(view)
    if sources:
        out += [("", "body"), ("Source records", "heading")]
        out += [(f"{LABELS.get(kind, kind)}: {', '.join(refs)}", "body") for kind, refs in sources.items()]
    if left:
        out += [("", "body"), ("Approved values the file does not carry", "heading")]
        out.append(("Give these in eSubmitter, or attach them, as you decide.", "muted"))
        out += [(line, "body") for line in left]
    out += [("", "body"), ("Approval", "heading"), *((line, "body") for line in manifestation(view))]
    out += [("", "body"), ("The eMDR file", "heading"), (f"SHA-256 of the eMDR file: {sha256}", "body")]
    out.append((note, "muted"))
    return out


def render(xml: bytes, view: dict, organization: str | None, left: list[str], *, note: str = "") -> bytes:
    """The PDF of a report's eMDR file. ``view``: the report as the screen reads it, with the snapshot's sections and,
    once approved, its signature (without one, the PDF is a DRAFT preview). ``left``: emdr.check's left-out values; ``note``: how the file was made."""
    import hashlib

    from backend.app.authority_reports.render import PREVIEW_LINE, PREVIEW_MARK
    from reports import pdf

    values = read(xml)
    complaint = view["complaint"]
    header = [
        f"Mfr Report #: {(values.get('G8') or ['-'])[0]} · UF/Importer Report #: - · Form Code: - · Exemption Number: -",
        f"Organization: {organization or '-'} · Complaint {complaint['ref']}: "
        f"{complaint['product_name'] or '-'} {complaint['version'] or ''}".rstrip(),
        "Prepared by MDARIX from the report's eMDR file, in the blocks, labels and order of Form FDA 3500A.",
        "MDARIX never submits: you send the eMDR file through your ESG account or eSubmitter.",
    ]
    draft = not view.get("signature")
    if view.get("practice_label"):
        header.insert(0, fda.PRACTICE)
    if draft:
        header.insert(0, PREVIEW_LINE)
    watermark = (
        PREVIEW_MARK
        if draft
        else "PRACTICE RECORD - NOT YOUR REGULATORY RECORD"
        if view.get("practice_label")
        else "eMDR CONTENT - PREPARED BY MDARIX"
    )
    lines = body(values) + record(view, left, hashlib.sha256(xml).hexdigest(), note)
    footer = f"{complaint['ref']} - Form FDA 3500A eMDR content - prepared by MDARIX, which never submits"
    return pdf.render(TITLE, header, lines, watermark=watermark, footer=footer)
