"""The approved US report on FDA's own Form FDA 3500A (09/2025), and how its values read as FDA's choices.

The blank form is FDA's fillable PDF, kept byte-identical in ``data/fda_forms`` (its manifest names the edition and
the source). It is a static XFA form with an AcroForm copy of every field: MDARIX fills the AcroForm fields, drops the
XFA layer and the form's version-check scripts (so every viewer shows the AcroForm values: Chrome, Edge and Acrobat
alike), writes each field's appearance and sets NeedAppearances, and appends MDARIX's record page: who prepared it,
who approved it and when, the snapshot's checksum, and any approved value the form has no box for.

Values come only from the approved snapshot, block by block. A choice box is ticked only when the value is FDA's own
choice, word for word ("Unknown" ticks Unknown, never No); a value that is not, or a text too long for its box, is not
placed and is listed on the record page instead. Nothing is guessed. The eMDR XML (emdr.py) reads the same choices.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

FORM_FILE = Path(__file__).resolve().parents[3] / "data" / "fda_forms" / "FDA-3500A_Eng_Stat_Sec_Ext_09-15-2025.pdf"
RECORD_TITLE = "MDARIX record - not part of Form FDA 3500A"
PRACTICE = "Practice record: free trial. Made with sample or de-identified data; not your regulatory record."

# FDA's choices per block: the words a value holds (as MDARIX writes them, or as a person types FDA's own label), the
# form's check box and FDA's eMDR code (HL7Medwatch.xlsx, VOCAB sheet). Matching ignores case, nothing else.
CHOICES: dict[str, dict[str, tuple[str, str]]] = {
    "A3": {"male": ("sexM", "C20197"), "female": ("sexF", "C16576")},
    "B1": {
        "adverse event": ("adverse", "C41331"),
        "product problem (e.g., defects/malfunctions)": ("prodProblem", "C53054"),
        "product problem": ("prodProblem", "C53054"),
    },
    "B2": {
        "death": ("death", "C28554"),
        "life-threatening": ("lifeThr", "C41337"),
        "hospitalization (initial or prolonged)": ("hospital", "C25179"),
        "hospitalization": ("hospital", "C25179"),
        "disability or permanent damage": ("disability", "C21007"),
        "congenital anomaly/birth defects": ("congenital", "C2849"),
        "required intervention to prevent permanent impairment/damage": ("reqInterv", "C52668"),
        "other serious or important medical events": ("otherOutcome", "C17649"),
    },
    "D5": {"health professional": ("devOpHP", "C53287"), "patient/consumer": ("devOpPat", "C16960")},
    "D7A": {"yes": ("singleUseY", "true"), "no": ("singleUseN", "false")},
    "D8": {"yes": ("thirdParY", "true"), "no": ("thirdParN", "false"), "unknown": ("thirdParU", "ASKU")},
    # FDA's own example sends "returned to manufacturer" as not available (false) with the return date.
    "D9": {"yes": ("evalY", "true"), "no": ("evalN", "false"), "returned to manufacturer": ("evalRet", "false")},
    "E2": {"yes": ("repHPY", "true"), "no": ("repHPN", "false")},
    # E4 is sent as a negation (HL7Medwatch.xlsx): "true" means the reporter did not send it.
    "E4": {"yes": ("reportFDAY", "false"), "no": ("reportFDAN", "true"), "unknown": ("reportFDAU", "")},
    "G2": {
        "foreign": ("repsrcFor", "C25512"),
        "study": ("rptsrcStu", "C15206"),
        "literature": ("repsrcLit", "C48471"),
        "consumer": ("repsrcCons", "C53568"),
        "health professional": ("repsrcHP", "C53287"),
        "user facility": ("repsrcUF", "C53567"),
        "company representative": ("repsrcCR", "C51968"),
        "distributor/importer": ("repsrcDI", "C48289"),
    },
    "G6": {
        "5-day": ("rep5", "C53573"),
        "7-day": ("rep7", "C53574"),
        "15-day": ("rep15", "C53576"),
        "30-day": ("rep30", "C53577"),
        "non-expedited (periodic)": ("repPer", "C53578"),
        "initial": ("repInit", "C53620"),
    },
    "H1": {
        "death": ("eventDeath", "C28554"),
        "serious injury": ("eventSInj", "C53569"),
        "malfunction": ("eventMal", "C25745"),
    },
    # H2, a follow-up's type(s) (0.10.96, B3 group B): FDA's Type_of_Follow-up codes (C53584).
    "H2": {
        "correction": ("correction", "C53585"),
        "additional information": ("addlInfo", "C53586"),
        "response to fda request": ("reqResp", "C53587"),
        "device evaluation": ("devEval", "C53588"),
    },
    # Section F (B9 steps 6-7): an importer's or user facility's report. F12: FDA's Location_Where_Event_Occurred.
    "F1": {"importer": ("userImport", "C53617"), "user facility": ("userFac", "C53567")},
    "F12": {
        "hospital": ("locHosp", "C16696"),
        "home": ("locHome", "C18002"),
        "nursing home": ("locNurs", "C53533"),
        "outpatient treatment facility": ("locTreat", "C53549"),
        "outpatient diagnostic facility": ("locDiag", "C53548"),
        "ambulatory surgical facility": ("locAmb", "C51945"),
        "other": ("locOther", "C17649"),
    },
    "H3": {"yes": ("evalManuY", "true"), "no": ("evalManuN", "false")},
    "H5": {"yes": ("singleUseY2", "true"), "no": ("singleUseN2", "false")},
    "H7": {
        "recall": ("remRecall", "C53609"),
        "repair": ("remRepair", "C53611"),
        "replace": ("remReplace", "C53610"),
        "relabeling": ("remRel", "C53608"),
        "notification": ("remNot", "C25297"),
        "inspection": ("remInsp", "C53604"),
        "patient monitoring": ("remMonitor", "C53607"),
        "modification/adjustment": ("remMod", "C53606"),
    },
    "H8": {
        "initial use of device": ("useInit", "C53612"),
        "reuse": ("useRe", "C53613"),
        "unknown": ("useUnk", "C17998"),
    },
}
# Text blocks and their box on the form (page, field). D6a and D6b: FDA's form names the boxes the other way round;
# these are the boxes printed under "6a. If Implanted" and "6b. If Explanted" (their tooltips say so too).
TEXT = {
    "MFR_REPORT": (1, "mfr"),
    "A1": (1, "patID"),
    "B3": (1, "dateAdvEvent"),
    "B4": (1, "dateReport"),
    "B6": (3, "addComm"),
    "B7": (3, "otherHist"),
    "D1": (6, "brandName"),
    "D2A": (6, "proCode"),
    "D2B": (6, "commonName"),
    "D3": (6, "manuNameAddr"),
    "D4_MODEL": (6, "modelNum"),
    "D4_LOT": (6, "lotNum"),
    "D4_CATALOG": (6, "catNum"),
    "D4_EXPIRY": (6, "expDate"),
    "D4_SERIAL": (6, "serNum"),
    "D4_UDI": (6, "udi"),
    "D6A": (7, "explantDate"),
    "D6B": (7, "implantDate"),
    "D7B": (7, "reproAddr"),
    "D10": (7, "cProdName1"),
    "G1": (8, "manuName"),
    "G3": (8, "reportManuRecDate"),
    "G4": (8, "numPMA"),
    "G8": (8, "manuRepNum"),
    "H4": (9, "devDate"),
    "H6_CLINICAL": (9, "healthClinCode2"),
    "H6_IMPACT": (9, "healthImpCode2"),
    "H6_PROBLEM": (9, "devProbCode2"),
    "H6_COMPONENT": (9, "compCode2"),
    "H6_TYPE": (9, "investCodes"),
    "H6_FINDINGS": (9, "invFindings"),
    "H6_CONCLUSIONS": (9, "invConc"),
    "H9": (9, "rep21USC"),
    "H10": (9, "relRepNum"),
    "H11": (9, "addNarr"),
    # Section F (B9 step 7): an importer's or user facility's report.
    "F2": (8, "reportNum"),
    "F3": (8, "facilityNAddr"),
    "F4": (8, "facPOC"),
    "F5": (8, "facPhone"),
    "F6": (8, "userAwareDate"),
    "F14": (8, "manuNameAddr2"),
}
# F10's code boxes (page 8), and F11/F13's yes, no and date boxes.
F10_BOXES = {
    "F10_CLINICAL": "healthClinCode",
    "F10_IMPACT": "healthImpCode",
    "F10_PROBLEM": "devProbCode",
    "F10_COMPONENT": "compCode",
}
SENT_BOXES = {
    "F11": ("reptFDAY", "reptFDAN", "reportSentDate"),
    "F13": ("reptManuY", "reptManuN", "reportManuSentDate"),
}
# E3: the form's occupation list (its export value) and FDA's code for each.
OCCUPATIONS = {
    label.lower(): (label, code)
    for label, code in (
        ("Administrator/Supervisor", "C134832"),
        ("Biomedical Engineer", "C51960"),
        ("Dentist", "C52654"),
        ("Non-Health Professional", "C134833"),
        ("Nurse", "C20821"),
        ("Nurse Practitioner", "C20852"),
        ("Other Health Professional", "C53289"),
        ("Pharmacist", "C51840"),
        ("Physician", "C25741"),
        ("Physician Assistant", "C53423"),
        ("Risk Manager", "C53448"),
        ("Third Party Servicer", "C85488"),
    )
}
# The form's character limits (its fields' MaxLen); a longer value is not placed.
LIMITS = {"D2A": 3, "D2B": 32, "D4_UDI": 1000, "B6": 2000, "B7": 2000, "H11": 450}
BOX_PAGE = {"A3": 1, "B1": 1, "B2": 1, "D5": 7, "D7A": 7, "D8": 7, "D9": 7, "E2": 7, "E4": 7, "G2": 8, "G6": 8}
BOX_PAGE |= {"F1": 8, "F12": 8}
BOX_PAGE |= {key: 9 for key in ("H1", "H2", "H3", "H5", "H7", "H8")}
DATES = {"B3", "B4", "D4_EXPIRY", "D6A", "D6B", "G3", "H4", "F6"}
CODES = {"H6_CLINICAL", "H6_IMPACT", "H6_PROBLEM", "H6_COMPONENT", "H6_TYPE", "H6_FINDINGS", "H6_CONCLUSIONS"}
# The event description: page 1's box, then page 2's continuation (FDA's 10,000 characters).
DESCRIPTION = ((1, "advEvDesc", 2500), (2, "advEvDescribe", 7500))
ON = "\x00on"  # a ticked box, in placements()
_FDA_CODE = re.compile(r"\(FDA (\w+)\)")
_AGE = re.compile(r"^(\d{1,3})\s*(year|month|week|day)s?$", re.I)
_WEIGHT = re.compile(r"^(\d{1,3}(?:\.\d+)?)\s*(kg|lb|lbs)$", re.I)
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def values(sections: list[dict]) -> dict[str, str]:
    """The approved snapshot's values by field id (only the ones that hold one)."""
    return {item["id"]: str(item["value"]).strip() for s in sections for item in s["fields"] if item.get("value")}


def labels(sections: list[dict]) -> dict[str, str]:
    """ "H6 Component code": how a field is named in a message, by its id."""
    return {
        item["id"]: " ".join(part for part in (item.get("number"), item["label"]) if part)
        for section in sections
        for item in section["fields"]
    }


def day(text: str) -> date | None:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def choices(field_id: str, text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """The FDA choices a value holds (box, code), and its parts that are none of FDA's choices."""
    table = CHOICES[field_id]
    whole = table.get(text.strip().lower())
    if whole:
        return [whole], []
    found, other = [], []
    for part in (piece.strip() for piece in text.split(";")):
        hit = table.get(part.lower())
        if hit is None and part:
            other.append(part)
        elif hit and hit not in found:
            found.append(hit)
    return found, other


def fda_codes(text: str) -> tuple[list[str], list[str]]:
    """The FDA codes in a code field's value ("A0101 Term (FDA 2896); ..."), and the codes that have none."""
    found, other = [], []
    for part in (piece.strip() for piece in text.split(";")):
        if part:
            hit = _FDA_CODE.search(part)
            (found if hit else other).append(hit.group(1) if hit else part)
    return found, other


def _form_day(text: str) -> str | None:
    found = day(text)
    return f"{found.day:02d}-{_MONTHS[found.month - 1]}-{found.year}" if found else None


def _name(field: str) -> str:
    """A field's own name (its /T), unique on its page: the form nests some fields deeper than others."""
    return f"{field}[0]"


def placements(
    sections: list[dict], contact: dict | None = None
) -> tuple[dict[int, dict[str, str]], list[tuple[str, str, str]]]:
    """Where each approved value goes on the form ({page: {field name: text}}; a ticked box holds ``ON``), and the
    values not placed (label, value, why). ``contact``: G1's contact office in parts (emdr.office), for its four
    boxes; without it G1's text goes in the Name box."""
    vals, names = values(sections), labels(sections)
    pages: dict[int, dict[str, str]] = {}
    left: list[tuple[str, str, str]] = []

    def put(page: int, field: str, text: str) -> None:
        pages.setdefault(page, {})[_name(field)] = text

    for field_id, text in vals.items():
        label = names.get(field_id, field_id)
        if field_id == "B5":
            rest = text
            for page, field, limit in DESCRIPTION:
                if rest:
                    # The box ends at a space where one is near: a word is never cut in two.
                    cut = limit if len(rest) <= limit else (rest.rfind(" ", limit - 200, limit) + 1 or limit)
                    put(page, field, rest[:cut])
                    rest = rest[cut:]
            if rest:
                left.append((label, rest, "the rest of the description, beyond the form's 10,000 characters"))
        elif field_id in ("F7", "F9", "F11", "F12", "F13") or field_id in F10_BOXES:
            _section_f(field_id, text, put, left, label)
        elif field_id in CHOICES:
            follow_up = re.search(r"follow-up #?(\d+)", text, re.IGNORECASE) if field_id == "G6" else None
            if follow_up:  # G6 "Follow-up #n" (0.10.96, B3 B2): its box and number box
                put(8, "repFollow", ON)
                put(8, "repFollowNum", follow_up.group(1))
                put(1, "dateReport", "N/A")  # FDA's follow-up leaves B4 out (0.10.96)
                text = text.replace(follow_up.group(0), "")
            found, other = choices(field_id, text)
            for box, _ in found:
                put(BOX_PAGE[field_id], box, ON)
            if other:
                left.append((label, "; ".join(other), "not one of the form's choices"))
        elif field_id in CODES:
            codes, other = fda_codes(text)
            if codes:
                put(9, TEXT[field_id][1], ", ".join(codes))
            if other:
                left.append((label, "; ".join(other), "no FDA code is mapped to it"))
        elif field_id == "A2":
            age, born = _AGE.match(text), _form_day(text)
            if age:
                put(1, "patAge", age.group(1))
                unit = {"year": "ageYrs", "month": "ageMons", "week": "ageWks", "day": "ageDays"}
                put(1, unit[age.group(2).lower()], ON)
            elif born:
                put(1, "patDOB", born)
            else:
                left.append((label, text, "neither an age in years, months, weeks or days nor a date"))
        elif field_id == "A4":
            weight = _WEIGHT.match(text)
            if weight:
                put(1, "patWeight", weight.group(1))
                put(1, "weightKG" if weight.group(2).lower() == "kg" else "weightLB", ON)
            else:
                left.append((label, text, "not a weight in kg or lb"))
        elif field_id == "G1" and contact:
            name = f"{contact['name']} (contact: {contact['person']})" if contact["person"] else contact["name"]
            parts = {"manuName": name, "manuAddr": contact["address"], "manuEmail": contact["email"]}
            for field, part in {**parts, "manuPhone": contact["phone"]}.items():
                if part:
                    put(8, field, part)
        elif field_id == "E3":
            option = OCCUPATIONS.get(text.lower())
            if option:
                put(7, "repOccupation", option[0])
            else:
                left.append((label, text, "not one of the form's occupations"))
        elif len(text) > LIMITS.get(field_id, len(text)):
            left.append((label, text, f"longer than the form's {LIMITS[field_id]} characters"))
        elif field_id in TEXT:
            page, field = TEXT[field_id]
            shown = _form_day(text) if field_id in DATES else text
            if shown is None:
                left.append((label, text, "not a date"))
            else:
                put(page, field, shown)
        else:
            left.append((label, text, "the form has no box for it"))
    return pages, left


def _section_f(field_id: str, text: str, put, left: list, label: str) -> None:
    """Section F's boxes that are not plain text (B9 step 7): F7's type and follow-up number, F9's age, F10's codes,
    F11/F13 sent (yes or no, with the day) and F12's location ("Other: ..." with its words)."""
    if field_id in F10_BOXES:
        codes, other = fda_codes(text)
        if codes:
            put(8, F10_BOXES[field_id], ", ".join(codes))
        if other:
            left.append((label, "; ".join(other), "no FDA code is mapped to it"))
    elif field_id == "F7":
        follow_up = re.search(r"follow-up #?(\d+)", text, re.IGNORECASE)
        put(8, "reptFollowUp" if follow_up else "reptInitial", ON)
        if follow_up:
            put(8, "followUpNum", follow_up.group(1))
    elif field_id == "F9":
        age = _AGE.match(text)
        if age and age.group(2).lower() in ("year", "month"):
            unit = age.group(2).lower() == "year"
            put(8, "deviceAgeYears" if unit else "deviceAgeMonth", ON)
            put(8, "ageYears" if unit else "ageMonths", age.group(1))
        else:
            left.append((label, text, "the form takes the age in years or months"))
    elif field_id in SENT_BOXES:
        yes, no, when = SENT_BOXES[field_id]
        words = text.strip().lower()
        if words.startswith(("yes", "no")):
            put(8, yes if words.startswith("yes") else no, ON)
            found = re.search(r"\d{4}-\d{2}-\d{2}", words)
            if found and words.startswith("yes"):
                put(8, when, _form_day(found.group(0)))
    else:  # F12
        place, _, words = text.partition(":")
        hit = CHOICES["F12"].get(place.strip().lower())
        if hit:
            put(8, hit[0], ON)
            if words.strip():
                put(8, "locOtherSpec", words.strip())
        else:
            left.append((label, text, "not one of the form's locations"))


def record_lines(view: dict, organization: str | None, left: list[tuple[str, str, str]]) -> tuple[list, list]:
    """The record page's header and body: who prepared it, the records its values came from, the values not on the
    form, and the approval."""
    from backend.app.authority_reports.render import LABELS, _sources, manifestation

    snapshot = view.get("snapshot") or {}
    complaint = view["complaint"]
    header = [
        "This page is MDARIX's record of the report. It is not part of FDA's form and is not sent to FDA.",
        f"Organization: {organization or '-'}",
        f"Form: {view['form']['version']}, FDA's fillable form, filled from approved snapshot {snapshot.get('version')}",
        f"Complaint {complaint['ref']}: {complaint['product_name'] or '-'} {complaint['version'] or ''}".rstrip(),
        "MDARIX never submits. You submit the report through FDA's eSubmitter or your ESG account.",
    ]
    if view.get("practice_label"):
        header.insert(0, PRACTICE)
    body: list[tuple[str, str]] = [("Prepared by", "heading"), (", ".join(view.get("preparers") or []) or "-", "body")]
    sources = _sources(view)
    if sources:
        body += [("", "body"), ("Source records", "heading")]
        body += [(f"{LABELS.get(kind, kind)}: {', '.join(refs)}", "body") for kind, refs in sources.items()]
    if left:
        body += [("", "body"), ("Approved values the form has no place for", "heading")]
        body.append(("Give these in eSubmitter, or attach them, as you decide.", "muted"))
        body += [(f"{label}: {value} ({why})", "body") for label, value, why in left]
    body += [("", "body"), ("Approval", "heading")]
    body += [(line, "body") for line in manifestation(view)]
    return header, body


def record_page(view: dict, organization: str | None, left: list[tuple[str, str, str]]) -> bytes:
    from reports import pdf

    header, body = record_lines(view, organization, left)
    watermark = "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "MDARIX RECORD"
    footer = f"{view['complaint']['ref']} - {view['form']['version']} - MDARIX's record, not part of FDA's form"
    return pdf.render(RECORD_TITLE, header, body, watermark=watermark, footer=footer)


def render(view: dict, organization: str | None, contact: dict | None = None) -> bytes:
    """FDA's Form 3500A filled from the approved snapshot, then MDARIX's record page."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject

    pages, left = placements(view["sections"], contact)
    writer = PdfWriter(clone_from=PdfReader(FORM_FILE))
    root = writer._root_object
    form = root["/AcroForm"]
    # Without the XFA layer every viewer reads the AcroForm values; the scripts only checked for an XFA viewer.
    form.pop("/XFA", None)
    names = root.get("/Names")
    if names is not None:
        names.get_object().pop("/JavaScript", None)
    form[NameObject("/NeedAppearances")] = BooleanObject(True)
    for number, fields in sorted(pages.items()):
        page = writer.pages[number - 1]
        # A box takes its own "on" name ("/1" or "/Yes"); a text its value at size 0, which fits and wraps it.
        on = {name: _on_state(page, name) for name, text in fields.items() if text == ON}
        texts = {name: (text, "", 0) for name, text in fields.items() if text != ON}
        writer.update_page_form_field_values(page, {**texts, **on}, auto_regenerate=None)
    writer.add_metadata(
        {"/Title": f"Form FDA 3500A - {view['complaint']['ref']}", "/Producer": "MDARIX", "/Creator": "MDARIX"}
    )
    writer.append(PdfReader(io.BytesIO(record_page(view, organization, left))))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _on_state(page, name: str) -> str:
    for annotation in page["/Annots"]:
        widget = annotation.get_object()
        if widget.get("/T") == name:
            return next(key for key in widget["/AP"]["/N"] if key != "/Off")
    raise KeyError(name)
