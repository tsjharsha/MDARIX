"""The approved Canada report on Health Canada's own Mandatory Medical Device Problem Reporting Form for Industry, HC
Pub. 110180 (April 2018) (B9 step 10).

**The form file is needed from the owner.** Its download from canada.ca failed (11 Nov 2026), and a copy from another
site is never used. ``data/hc_forms/manifest.json`` lists no file and ``field_map.json`` maps nothing yet, so
``render`` refuses with ``FormFileNeeded`` (the route answers 409 FORM_FILE_NEEDED) and the read-back tests are skipped.
When the file arrives: vendor it byte-identical with its SHA-256 in the manifest, fill the map from the form's own
field names, and have a person check the map once against the printed form (B9-D17).

Values come only from the approved snapshot, as the US and India forms do: a box is ticked only when the value is one
of the form's own choices, word for word, ignoring case; every other value is listed on MDARIX's record page. Nothing
is guessed. Complainant boxes (D2-D5) stay blank unless the snapshot holds them (B9-D9). MDARIX never submits: the
customer e-mails the form to Health Canada.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[3] / "data" / "hc_forms"
EDITION = "hc-mdpr-2018-04"
RECORD_TITLE = "MDARIX record - not part of the Health Canada form"
ON = "\x00on"


class FormFileNeeded(Exception):
    """The blank HC Pub. 110180 form (or its field map) is not in ``data/hc_forms`` yet."""


def manifest() -> dict:
    return json.loads((FOLDER / "manifest.json").read_text(encoding="utf-8"))


def field_map() -> dict:
    return json.loads((FOLDER / "field_map.json").read_text(encoding="utf-8"))


def form_file() -> Path:
    """The vendored blank form, checked against its manifest's SHA-256; ``FormFileNeeded`` without one."""
    files = manifest()["files"]
    mapped = field_map()
    if not files or not (mapped["text"] or mapped["choices"]):
        raise FormFileNeeded("The Health Canada form file (HC Pub. 110180) is needed from the owner")
    path = FOLDER / files[0]["file"]
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != files[0]["sha256"]:
        raise FormFileNeeded("The Health Canada form file does not match its manifest")
    return path


def field_names() -> set[str]:
    """Every form field name the map uses (a test checks each one is a real field of the form)."""
    mapped = field_map()
    return set(mapped["text"].values()) | {box for table in mapped["choices"].values() for box in table.values()}


def placements(sections: list[dict]) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Where each approved value goes ({field name: text}, a ticked box holds ``ON``) and the values not placed."""
    from backend.app.authority_reports.fda_3500a import labels, values

    mapped = field_map()
    vals, names = values(sections), labels(sections)
    out: dict[str, str] = {}
    left: list[tuple[str, str, str]] = []
    for field_id, text in vals.items():
        label = names.get(field_id, field_id)
        if field_id in mapped["choices"]:
            box = mapped["choices"][field_id].get(text.strip().lower())
            if box:
                out[box] = ON
            else:
                left.append((label, text, "not one of the form's choices"))
        elif field_id in mapped["text"]:
            shown = text
            if field_id in mapped["dates"] and mapped.get("date_format"):
                try:
                    shown = date.fromisoformat(text.strip()[:10]).strftime(mapped["date_format"])
                except ValueError:
                    left.append((label, text, "not a date"))
                    continue
            out[mapped["text"][field_id]] = shown
        else:
            left.append((label, text, "the form has no box for it"))
    return out, left


def record_page(view: dict, organization: str | None, left: list[tuple[str, str, str]]) -> bytes:
    from backend.app.authority_reports.fda_3500a import PRACTICE
    from backend.app.authority_reports.render import manifestation
    from reports import pdf

    snapshot = view.get("snapshot") or {}
    complaint = view["complaint"]
    header = [
        "This page is MDARIX's record of the report. It is not part of the Health Canada form and is not sent.",
        f"Organization: {organization or '-'}",
        f"Form: HC Pub. 110180 (April 2018), filled from approved snapshot {snapshot.get('version')}",
        f"Complaint {complaint['ref']}: {complaint['product_name'] or '-'} {complaint['version'] or ''}".rstrip(),
        "MDARIX never submits. You e-mail the form to Health Canada and record the submission in MDARIX.",
    ]
    if not field_map()["checked_by_a_person"]:
        header.append("The form's field map is still to be checked once by a person. Check every box before sending.")
    if view.get("practice_label"):
        header.insert(0, PRACTICE)
    body: list[tuple[str, str]] = [("Prepared by", "heading"), (", ".join(view.get("preparers") or []) or "-", "body")]
    if left:
        body += [("", "body"), ("Approved values the form has no place for", "heading")]
        body += [(f"{label}: {value} ({why})", "body") for label, value, why in left]
    body += [("", "body"), ("Approval", "heading")]
    body += [(line, "body") for line in manifestation(view)]
    watermark = "PRACTICE RECORD - NOT YOUR REGULATORY RECORD" if view.get("practice_label") else "MDARIX RECORD"
    footer = f"{complaint['ref']} - HC Pub. 110180 - MDARIX's record, not part of the Health Canada form"
    return pdf.render(RECORD_TITLE, header, body, watermark=watermark, footer=footer)


def render(view: dict, organization: str | None) -> bytes:
    """Health Canada's form filled from the approved snapshot, then MDARIX's record page. ``FormFileNeeded`` until the
    form file and its map are in ``data/hc_forms``."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject

    from backend.app.authority_reports.mvpi_mdae import _on_state

    source = form_file()
    fields, left = placements(view["sections"])
    writer = PdfWriter(clone_from=PdfReader(source))
    writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
    for page in writer.pages:
        on = {}
        for name in (name for name, text in fields.items() if text == ON):
            try:
                on[name] = _on_state(page, name)
            except (KeyError, StopIteration):
                continue  # the box is on another page
        texts = {name: text for name, text in fields.items() if text != ON}
        writer.update_page_form_field_values(page, {**texts, **on}, auto_regenerate=None)
    writer.add_metadata(
        {"/Title": f"HC MDPR form - {view['complaint']['ref']}", "/Producer": "MDARIX", "/Creator": "MDARIX"}
    )
    writer.append(PdfReader(io.BytesIO(record_page(view, organization, left))))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
