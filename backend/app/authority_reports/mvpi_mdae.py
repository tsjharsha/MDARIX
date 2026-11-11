"""The approved India report on MvPI's own Medical Device Adverse Event Reporting Form, Version 1.2 (B9 step 12).

The blank form is kept byte-identical in ``data/mvpi_forms`` (its manifest names the edition and the source). Its 172
fields have generic names (``checkbox_1jeo``, ``text_98sygn``), so the map below was made **by position**: each field
was matched to the printed label beside it. **The map is to be checked once by a person against the printed form
(B9-D17); it is not checked yet** (``MAP_CHECKED`` is False and the record page says so).

Values come only from the approved snapshot, as the US form does (``fda_3500a``): a box is ticked only when the value
is one of the form's own choices, word for word, ignoring case; anything else, and every value the form has no box
for, is listed on MDARIX's record page. Nothing is guessed. Patient (C) and healthcare facility (D) boxes stay blank
unless the snapshot holds them (B9-D9: entered at the report step only, never stored elsewhere). E3, the association
judgement, is ticked only when a person entered one of the form's four words. MDARIX never submits: the customer
e-mails the form to MvPI or enters it in ADRMS.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

FORM_FILE = Path(__file__).resolve().parents[3] / "data" / "mvpi_forms" / "MvPI-MDAE-Reporting-Form-v1.2.pdf"
EDITION = "mvpi-mdae-1.2"
MAP_CHECKED = False  # B9-D17: set True only after a person checks the map against the printed form
RECORD_TITLE = "MDARIX record - not part of the MvPI form"

# Text boxes: field id -> (page, field name). R3, A_MANUFACTURER, A_IMPORTER and A_DISTRIBUTOR hold one text each in
# MDARIX; it goes in the form's Name box (the address box beside it stays for a person, or for later B9 work).
TEXT = {
    "P1": (1, "text_98sygn"),
    "P4": (1, "text_99jppv"),
    "R3": (1, "text_104vmdb"),
    "A_COMMON": (2, "text_109uxol"),
    "A_BRAND": (2, "text_110wxft"),
    "A_MANUFACTURER": (2, "text_111amfr"),
    "A_IMPORTER": (2, "text_112bakh"),
    "A_DISTRIBUTOR": (2, "text_113deli"),
    "A3": (2, "text_117nptl"),
    "A4": (2, "text_118wanp"),
    "A5": (2, "text_119cehl"),
    "A6": (2, "text_120vuhf"),
    "A7": (2, "text_121gwjc"),
    "A8": (2, "text_122powp"),
    "A9": (2, "text_123eylm"),
    "A10": (2, "text_124lohn"),
    "A11": (2, "text_125ogwh"),
    "A12": (2, "text_126qayo"),
    "A13": (2, "text_127djhp"),
    "A14": (2, "text_128tvoo"),
    "A15": (2, "text_129coda"),
    "A16": (2, "text_130bnhf"),
    "A17": (2, "text_131ctkf"),
    "B1": (3, "text_133uhoa"),
    "B12": (3, "textarea_162kblv"),
    "C1": (3, "text_146rsdw"),
    "C2": (3, "text_147kmpk"),
    "C3": (3, "text_148ipyg"),
    "C5": (3, "text_149bzjk"),
    "D1": (4, "text_152ayga"),
    "D2": (4, "text_153hcqk"),
    "D3": (4, "text_154ona"),
    "D4": (4, "text_155gttd"),
    "D5": (4, "text_156fpqf"),
    "E1": (4, "textarea_161xutl"),
    "E2": (4, "textarea_160ifxj"),
    "F2": (4, "textarea_159jrxe"),
    "F3": (4, "textarea_158vget"),
    "F4": (4, "textarea_157gpbx"),
}
DATES = {"P1", "B1", "A12", "A13", "A14", "A15"}
# Choice boxes: field id -> (page, {the form's words: box}).
CHOICES = {
    "P2": (
        1,
        {
            "initial": "checkbox_1jeo",
            "follow up": "checkbox_2hhdc",
            "final": "checkbox_3nvzq",
            "trend": "checkbox_4fhpc",
        },
    ),
    "R1": (
        1,
        {
            "manufacturer": "checkbox_9kjrf",
            "importer": "checkbox_12mniw",
            "distributor": "checkbox_10mdee",
            "healthcare professional": "checkbox_13xqbq",
        },
    ),
    "R2A": (1, {"yes": "checkbox_5fsbs", "no": "checkbox_6xmqc"}),
    "R2B": (1, {"yes": "checkbox_8mhq", "no": "checkbox_7hmws"}),
    "CAT1": (
        1,
        {
            "therapeutic": "checkbox_14desv",
            "diagnostic": "checkbox_15knll",
            "therapeutic & diagnostic": "checkbox_16oag",
            "assistive": "checkbox_17touz",
            "preventive": "checkbox_18noti",
            "imaging": "checkbox_19mfho",
        },
    ),
    "CAT2": (1, {"implantable device": "checkbox_21dolc", "non-implantable device": "checkbox_20pkus"}),
    "CAT3": (1, {"invasive": "checkbox_22qgay", "non-invasive": "checkbox_24oppq"}),
    "CAT4": (
        1,
        {
            "single use": "checkbox_23tkfn",
            "reusable": "checkbox_25kkug",
            "reuse of manufacturer-marked single use device": "checkbox_26wthf",
        },
    ),
    "CAT5": (1, {"sterile": "checkbox_28mzpy", "non sterile": "checkbox_27odan"}),
    "CAT6": (1, {"personal use / homecare use": "checkbox_29tcsk", "yes": "checkbox_29tcsk"}),
    "A1": (2, {"a": "checkbox_36pfhs", "b": "checkbox_37bwpo", "c": "checkbox_38ywsc", "d": "checkbox_39vdeg"}),
    "A18": (2, {"yes": "checkbox_44vtqd", "no": "checkbox_45bdig"}),
    "A19": (2, {"yes": "checkbox_50lzrw", "no": "checkbox_49cscm"}),
    "B2": (
        3,
        {
            "adverse event": "checkbox_55tdbr",
            "product problem (e.g., defects/malfunctions)": "checkbox_56awmb",
            "product problem": "checkbox_56awmb",
        },
    ),
    "B4": (
        3,
        {
            "hospital": "checkbox_52tegc",
            "manufacture/distributor premises": "checkbox_51qzpe",
            "home": "checkbox_53lict",
        },
    ),
    "B5": (3, {"healthcare professional": "checkbox_58jbwy", "patient": "checkbox_60olb"}),
    "B9": (3, {"yes": "checkbox_80lako"}),
    "C4": (3, {"male": "checkbox_84yzho", "female": "checkbox_85lzgy", "transgender": "checkbox_86qgmo"}),
    "E3": (
        4,
        {
            "not related": "checkbox_92cgs",
            "possible": "checkbox_93rnum",
            "probable": "checkbox_94rgi",
            "related": "checkbox_95cu",
        },
    ),
    "F1": (4, {"yes": "checkbox_96pkyh", "no": "checkbox_97ozos"}),
}
# B8 "Yes: a) Death; b) ..." (worksheet._in_serious): the Yes box, then each reason by its letter.
SERIOUS_YES = (3, "checkbox_74eopa")
SERIOUS_REASONS = {
    "a": "checkbox_166atgx",
    "b": "checkbox_75lbzv",
    "c": "checkbox_76njyq",
    "d": "checkbox_77mltv",
    "e": "checkbox_78fuis",
    "f": "checkbox_79oydw",
    "g": "checkbox_81yffu",
}
# "Others" with the words after it: B4 location and B5 operator ("Others: clinic").
OTHERS = {"B4": (3, "checkbox_54fbdm", "text_136cxwr"), "B5": (3, "checkbox_59xrd", "text_171htgq")}
ON = "\x00on"
_REASON = re.compile(r"^([a-g])\)")
_CLASS = re.compile(r"^(?:class\s+)?([a-d])$", re.I)


def field_names() -> set[str]:
    """Every field name the map uses (a test checks each one is a real field of the form)."""
    names = {name for _, name in TEXT.values()} | {SERIOUS_YES[1], *SERIOUS_REASONS.values()}
    names |= {box for _, table in CHOICES.values() for box in table.values()}
    names |= {name for _, box, text in OTHERS.values() for name in (box, text)}
    return names


def _form_day(text: str) -> str | None:
    try:
        found = date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None
    return f"{found.day:02d}/{found.month:02d}/{found.year}"


def placements(sections: list[dict]) -> tuple[dict[int, dict[str, str]], list[tuple[str, str, str]]]:
    """Where each approved value goes ({page: {field name: text}}, a ticked box holds ``ON``) and the values not placed
    (label, value, why)."""
    from backend.app.authority_reports.fda_3500a import labels, values

    vals, names = values(sections), labels(sections)
    pages: dict[int, dict[str, str]] = {}
    left: list[tuple[str, str, str]] = []

    def put(page: int, field: str, text: str) -> None:
        pages.setdefault(page, {})[field] = text

    for field_id, text in vals.items():
        label = names.get(field_id, field_id)
        if field_id == "B8":
            head, _, rest = text.partition(":")
            if head.strip().lower() != "yes":
                left.append((label, text, "not one of the form's choices"))
                continue
            put(*SERIOUS_YES, ON)
            for part in (piece.strip() for piece in rest.split(";") if piece.strip()):
                letter = _REASON.match(part)
                if letter:
                    put(3, SERIOUS_REASONS[letter.group(1)], ON)
                else:
                    left.append((label, part, "not one of the form's reasons"))
        elif field_id in OTHERS and text.lower().startswith("others"):
            page, box, specify = OTHERS[field_id]
            put(page, box, ON)
            put(page, specify, text.partition(":")[2].strip() or text)
        elif field_id in CHOICES:
            page, table = CHOICES[field_id]
            words = text.strip()
            if field_id == "A1":
                found = _CLASS.match(words)
                words = found.group(1) if found else words
            whole = table.get(words.lower())
            parts = [whole] if whole else [table.get(p.strip().lower()) for p in words.split(";") if p.strip()]
            if parts and all(parts):
                for box in parts:
                    put(page, box, ON)
            else:
                left.append((label, text, "not one of the form's choices"))
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


def record_page(view: dict, organization: str | None, left: list[tuple[str, str, str]]) -> bytes:
    from backend.app.authority_reports.fda_3500a import PRACTICE
    from backend.app.authority_reports.render import LABELS, _sources, manifestation
    from reports import pdf

    snapshot = view.get("snapshot") or {}
    complaint = view["complaint"]
    header = [
        "This page is MDARIX's record of the report. It is not part of the MvPI form and is not sent to MvPI.",
        f"Organization: {organization or '-'}",
        f"Form: MvPI MDAE Reporting Form, Version 1.2, filled from approved snapshot {snapshot.get('version')}",
        f"Complaint {complaint['ref']}: {complaint['product_name'] or '-'} {complaint['version'] or ''}".rstrip(),
        "MDARIX never submits. You e-mail the form to MvPI (mvpi-ipc@gov.in) or enter it in ADRMS.",
    ]
    if not MAP_CHECKED:
        header.append(
            "The form's boxes were matched to MDARIX's fields by position; the map is still to be checked once by a "
            "person against the printed form. Check every box before sending."
        )
    if view.get("practice_label"):
        header.insert(0, PRACTICE)
    body: list[tuple[str, str]] = [("Prepared by", "heading"), (", ".join(view.get("preparers") or []) or "-", "body")]
    sources = _sources(view)
    if sources:
        body += [("", "body"), ("Source records", "heading")]
        body += [(f"{LABELS.get(kind, kind)}: {', '.join(refs)}", "body") for kind, refs in sources.items()]
    if left:
        body += [("", "body"), ("Approved values the form has no place for", "heading")]
        body.append(("Write these on the form, or enter them in ADRMS, as you decide.", "muted"))
        body += [(f"{label}: {value} ({why})", "body") for label, value, why in left]
    body += [("", "body"), ("Approval", "heading")]
    body += [(line, "body") for line in manifestation(view)]
    watermark = "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "MDARIX RECORD"
    footer = f"{complaint['ref']} - MvPI MDAE v1.2 - MDARIX's record, not part of the MvPI form"
    return pdf.render(RECORD_TITLE, header, body, watermark=watermark, footer=footer)


def render(view: dict, organization: str | None) -> bytes:
    """MvPI's form filled from the approved snapshot, then MDARIX's record page."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject

    pages, left = placements(view["sections"])
    writer = PdfWriter(clone_from=PdfReader(FORM_FILE))
    writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
    for number, fields in sorted(pages.items()):
        page = writer.pages[number - 1]
        on = {name: _on_state(page, name) for name, text in fields.items() if text == ON}
        texts = {name: text for name, text in fields.items() if text != ON}
        writer.update_page_form_field_values(page, {**texts, **on}, auto_regenerate=None)
    writer.add_metadata(
        {"/Title": f"MvPI MDAE form - {view['complaint']['ref']}", "/Producer": "MDARIX", "/Creator": "MDARIX"}
    )
    writer.append(PdfReader(io.BytesIO(record_page(view, organization, left))))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _on_state(page, name: str) -> str:
    """A box's own "on" name: the form's boxes keep their name on the widget or on its parent field."""
    for annotation in page["/Annots"]:
        widget = annotation.get_object()
        parent = widget.get("/Parent")
        if name in (widget.get("/T"), parent and parent.get_object().get("/T")):
            return next(key for key in widget["/AP"]["/N"] if key != "/Off")
    raise KeyError(name)


# ------------------------------------------------------------------------------------- the ADRMS entry sheet (step 13)
ENTER = "enter in ADRMS"
SHEET_TITLE = "ADRMS entry sheet - MDARIX's aid, not an MvPI form"
# ADRMS's 16 mandatory fields (marked * on its screens), in its screen order, each with the form fields it reads
# (ADRMS User Manual for Stakeholders, 18 Aug 2025, and the MDAE capture SOP of 3 Feb 2026: starter, for your
# consultant to confirm against the portal).
ADRMS_FIELDS = (
    ("Patient involved", ()),
    ("Report type", ("P2",)),
    ("Date of report", ("P1",)),
    ("Serious case, with its reasons", ("B8",)),
    ("Reporter department", ()),
    ("Reporter country", ()),
    ("Reporter mobile", ()),
    ("Reported by", ("R1",)),
    ("Primary reporter", ("R1", "R3")),
    ("Device category", ("CAT1", "CAT2", "CAT3", "CAT4", "CAT5", "CAT6")),
    ("Device name", ("A_COMMON", "A_BRAND")),
    ("Device information", ("A1", "A3", "A4", "A6", "A7", "A10", "A11")),
    ("Event date", ("B1",)),
    ("Adverse event category", ("B2",)),
    ("Description", ("B12",)),
    ("Patient outcome", ("C7",)),
)


def adrms_rows(sections: list[dict]) -> list[tuple[str, str]]:
    """(ADRMS field, value): each value from the same approved snapshot as the form, or "enter in ADRMS"."""
    from backend.app.authority_reports.fda_3500a import labels, values

    vals, names = values(sections), labels(sections)
    rows = []
    for name, ids in ADRMS_FIELDS:
        parts = [f"{names[i]}: {vals[i]}" if len(ids) > 1 else vals[i] for i in ids if vals.get(i)]
        if name == "Patient involved" and "adverse event" in vals.get("B2", "").lower():
            parts = ["Yes (an adverse event is recorded)"]
        if name == "Serious case, with its reasons" and not parts and vals.get("B9", "").lower() == "yes":
            parts = ["No (non-serious event)"]
        rows.append((name, "; ".join(parts) or ENTER))
    return rows


def adrms_sheet(view: dict, organization: str | None) -> bytes:
    """The values in ADRMS screen order, for fast copying (ADRMS has no import), then the approval."""
    from backend.app.authority_reports.fda_3500a import PRACTICE
    from backend.app.authority_reports.render import manifestation
    from reports import pdf

    snapshot = view.get("snapshot") or {}
    header = [
        "MDARIX's aid for entering the approved report in ADRMS. It is not an MvPI form and is not sent to MvPI.",
        f"Organization: {organization or '-'}",
        f"From approved snapshot {snapshot.get('version')}: the same values as the filled MvPI form v1.2",
        "* = mandatory in ADRMS (starter, for your consultant to confirm against the portal).",
        "MDARIX never submits. You enter the report in ADRMS yourself.",
    ]
    if view.get("practice_label"):
        header.insert(0, PRACTICE)
    body: list[tuple[str, str]] = [("ADRMS fields, in screen order", "heading")]
    body += [(f"{n}. {name} *: {value}", "body") for n, (name, value) in enumerate(adrms_rows(view["sections"]), 1)]
    body += [("", "body"), ("Approval", "heading")]
    body += [(line, "body") for line in manifestation(view)]
    watermark = "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "MDARIX RECORD"
    footer = f"{view['complaint']['ref']} - ADRMS entry sheet - MDARIX's aid, not an MvPI form"
    return pdf.render(SHEET_TITLE, header, body, watermark=watermark, footer=footer)
