"""B9 step 10 (B9-10): Health Canada's own form, HC Pub. 110180, filled from the approved snapshot.

The form file is needed from the owner (its canada.ca download failed; no other site's copy is used), so the read-back
tests are skipped until ``data/hc_forms`` holds the file, its SHA-256 and a field map. What runs now: without the file
the module refuses, and the placement logic puts each value only in a mapped field or on the record page."""

from __future__ import annotations

import pytest

from backend.app.authority_reports import hc_mdpr

pytestmark = pytest.mark.unit

try:
    hc_mdpr.form_file()
    HELD = True
except hc_mdpr.FormFileNeeded:
    HELD = False
NEEDED = pytest.mark.skipif(not HELD, reason="HC Pub. 110180 form file needed from the owner (data/hc_forms)")
SECTION = {"fields": [{"id": "A5", "number": "A5", "label": "Type of report", "value": "Preliminary"}]}


def test_without_the_form_file_the_official_form_is_refused():
    if HELD:
        pytest.skip("the form file is here")
    with pytest.raises(hc_mdpr.FormFileNeeded):
        hc_mdpr.render({"sections": [], "complaint": {"ref": "X"}}, None)


def test_an_unmapped_value_goes_to_the_record_page(monkeypatch):
    monkeypatch.setattr(
        hc_mdpr,
        "field_map",
        lambda: {"text": {}, "choices": {"A5": {"preliminary": "box_prelim"}}, "dates": [], "date_format": None},
    )
    placed, left = hc_mdpr.placements([SECTION])
    assert placed == {"box_prelim": hc_mdpr.ON} and left == []
    monkeypatch.setattr(hc_mdpr, "field_map", lambda: {"text": {}, "choices": {}, "dates": [], "date_format": None})
    assert hc_mdpr.placements([SECTION]) == ({}, [("A5 Type of report", "Preliminary", "the form has no box for it")])


@NEEDED
def test_every_map_entry_names_a_real_field_of_the_form():
    from pypdf import PdfReader

    assert hc_mdpr.field_names() <= set(PdfReader(hc_mdpr.form_file()).get_fields())


@NEEDED
def test_each_mapped_value_reads_back_from_its_field():
    import io

    from pypdf import PdfReader

    mapped = hc_mdpr.field_map()
    sections = [
        {"fields": [{"id": key, "number": key, "label": key, "value": f"Value {key}"} for key in mapped["text"]]}
    ]
    view = {"sections": sections, "complaint": {"ref": "SAMPLE", "product_name": "-", "version": ""}}
    fields = PdfReader(io.BytesIO(hc_mdpr.render(view, "Sample org"))).get_fields()
    for key, name in mapped["text"].items():
        if key not in mapped["dates"]:
            assert fields[name].get("/V") == f"Value {key}"
