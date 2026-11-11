"""B9 step 12 (B9-05): the approved India report on MvPI's own MDAE form v1.2, filled by position and read back. The
field map is still to be checked once by a person against the printed form (B9-D17). No database."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from backend.app.authority_reports import forms, mvpi_mdae
from tests.test_fda_3500a_emdr import SIGNATURE

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REPORT = {
    "P1": "2026-11-04",
    "P2": "Initial",
    "P4": "SAMPLE-RV-10",
    "R1": "Manufacturer",
    "R3": "Orbit Medical Devices India (Sample), Pune",
    "CAT2": "Non-implantable device",
    "CAT4": "Reusable",
    "A_COMMON": "Pulse oximeter",
    "A_BRAND": "PulseWatch 410",
    "A1": "Class B",
    "A3": "MFG/MD/2026/000001",
    "A4": "PW-410",
    "A6": "LOT-2026-07",
    "A13": "2028-01-31",
    "B1": "2026-10-30",
    "B2": "Adverse event; Product problem (e.g., defects/malfunctions)",
    "B4": "Others: clinic",
    "B5": "Healthcare professional",
    "B8": "Yes: c) Disability or permanent damage; f) Required intervention to prevent permanent impairment / damage",
    "B9": "No",
    "B12": "The probe overheated during use and burned the patient's finger.",
    "F1": "Yes",
    "A18": "Returned to manufacturer",
}


def _sections(values: dict) -> list[dict]:
    return [
        {
            "fields": [
                {"id": field.id, "number": field.number, "label": field.label, "value": values.get(field.id)}
                for field in section.fields
            ]
        }
        for section in forms.MVPI_MDAE.sections
    ]


def _view(values: dict) -> dict:
    return {
        "sections": _sections(values),
        "complaint": {"ref": "SAMPLE-RV-10", "product_name": "PulseWatch 410", "version": "Rev A"},
        "form": {"version": "MDAE Reporting Form, Version 1.2"},
        "snapshot": {"version": 2, "same_person": False},
        "preparers": ["Asha Rao"],
        "practice_label": "Practice record",
        "signature": SIGNATURE,
        "signatures": [],
    }


def _fields(pdf: bytes) -> dict[str, str]:
    """Every filled field's value by name (the form keeps some values on the parent field)."""
    found = PdfReader(io.BytesIO(pdf)).get_fields() or {}
    return {name: str(field["/V"]) for name, field in found.items() if field.get("/V") not in (None, "", "/Off")}


def test_the_blank_form_is_the_pinned_file_and_every_map_entry_names_a_real_field():
    entry = json.loads((ROOT / "data/mvpi_forms/manifest.json").read_text(encoding="utf-8"))["files"][0]
    assert hashlib.sha256(mvpi_mdae.FORM_FILE.read_bytes()).hexdigest() == entry["sha256"]
    assert entry["field_map_checked_by_a_person"] is False and mvpi_mdae.MAP_CHECKED is False
    real = set(PdfReader(mvpi_mdae.FORM_FILE).get_fields())
    assert len(real) == 172
    assert mvpi_mdae.field_names() <= real, mvpi_mdae.field_names() - real
    # Every MDARIX field the map names exists in the worksheet.
    ids = {field.id for section in forms.MVPI_MDAE.sections for field in section.fields}
    assert set(mvpi_mdae.TEXT) | set(mvpi_mdae.CHOICES) | {"B8"} <= ids


def test_each_approved_value_lands_in_its_box_and_the_record_page_follows():
    pdf = mvpi_mdae.render(_view(REPORT), "Orbit Medical Devices India (Sample)")
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 5  # MvPI's four pages, then MDARIX's record page
    fields = _fields(pdf)
    assert fields["text_98sygn"] == "04/11/2026" and fields["text_133uhoa"] == "30/10/2026"
    assert fields["checkbox_1jeo"] != "/Off" and "checkbox_3nvzq" not in fields  # Initial, not Final
    assert fields["text_99jppv"] == "SAMPLE-RV-10" and "checkbox_9kjrf" in fields  # P4, R1 manufacturer
    assert {"checkbox_20pkus", "checkbox_25kkug", "checkbox_37bwpo"} <= set(fields)  # non-implantable, reusable, B
    assert (fields["text_109uxol"], fields["text_110wxft"]) == ("Pulse oximeter", "PulseWatch 410")
    assert (fields["text_117nptl"], fields["text_118wanp"], fields["text_120vuhf"]) == (
        "MFG/MD/2026/000001",
        "PW-410",
        "LOT-2026-07",
    )
    assert fields["text_127djhp"] == "31/01/2028"
    assert {"checkbox_55tdbr", "checkbox_56awmb", "checkbox_58jbwy", "checkbox_96pkyh"} <= set(fields)
    assert fields["text_136cxwr"] == "clinic" and "checkbox_54fbdm" in fields  # B4 Others, specified
    # B8: Yes, c) and f); never a reason the answers did not give.
    assert {"checkbox_74eopa", "checkbox_76njyq", "checkbox_79oydw"} <= set(fields)
    assert not {"checkbox_166atgx", "checkbox_75lbzv", "checkbox_77mltv"} & set(fields)
    assert fields["textarea_162kblv"].startswith("The probe overheated")
    # Personal boxes stay blank (B9-D9), and E3 (a judgement) is never ticked without a person's word.
    assert not {"text_146rsdw", "text_152ayga", "checkbox_92cgs", "checkbox_95cu"} & set(fields)
    record = reader.pages[-1].extract_text().replace("\n", " ")
    assert "not part of the MvPI form" in record and "checked once by a person" in record
    assert "Returned to manufacturer" in record and "MDARIX never submits" in record


def test_a_value_that_is_none_of_the_forms_choices_ticks_nothing():
    pages, left = mvpi_mdae.placements(_sections({"P2": "Interim", "A1": "Class E", "B8": "Unknown"}))
    assert pages == {}
    assert [why for _, _, why in left] == ["not one of the form's choices"] * 3


def test_the_same_snapshot_gives_the_same_values():
    first = _fields(mvpi_mdae.render(_view(REPORT), "Org"))
    assert first == _fields(mvpi_mdae.render(_view(REPORT), "Org"))
