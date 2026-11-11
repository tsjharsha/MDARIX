"""B8 run 6 (tr30, B9-D9 / B8-D9): patient and reporter details typed at Send for approval reach the EU and GB MIR
files only for a snapshot sent with the setting on, each in its schema's place; a masked export never holds them."""

from __future__ import annotations

from lxml import etree

from backend.app import tenant_export
from backend.app.authority_reports import forms, mir_xml
from tests.test_b8_gb_mir_xml import GB, GB_FULL
from tests.test_b8_gb_mir_xml import PARTIES as GB_PARTIES
from tests.test_b8_mir_xml import FULL, NOW, PARTIES

TYPED = {
    "3_3B": "64 years",
    "3_3C": "Female",
    "3_3D": "71 kg",
    "3_3F": "None reported (fictional)",
    "3_4B": "Sample Ward Planted (fictional)",
    "3_4C": "HF-0042",
    "3_4D": "Alex Plantedname, alex.planted@example.invalid, +44 20 7946 0000",
    "3_4I": "1 Sample Street, London, SW1A 1AA (fictional)",
}


def _text(root, name: str) -> str | None:
    found = next(root.iter(name), None)
    return found.text if found is not None else None


def test_b8_personal_details_reach_the_eu_file_only_when_sent_with_the_setting_on():
    values = FULL | TYPED | {"3_3E": "170 cm", "1_2E": forms.MIR_FINAL}
    off = mir_xml.build(values, PARTIES, report_type=forms.MIR_FINAL, now=NOW)
    assert b"Planted" not in off and b"patientAgeAtEvent" not in off
    on = mir_xml.build(values, PARTIES, report_type=forms.MIR_FINAL, now=NOW, personal=True)  # XSD-valid or raises
    root = etree.fromstring(on)
    assert _text(next(root.iter("patientAgeAtEvent")), "numYears") == "64" and _text(root, "Gender") == "Female"
    assert _text(root, "massKG") == "71" and _text(root, "heightCM") == "170"
    assert _text(root, "healthcareFacilityName") == "Sample Ward Planted (fictional)"
    assert _text(root, "healthcareFacilityRepNum") == "HF-0042"
    assert _text(root, "healthcareFacilityContactPersonFirstName") == "Alex"
    assert _text(root, "healthcareFacilityContactPersonSecondName") == "Plantedname"
    assert _text(root, "healthcareFacilityEmail") == "alex.planted@example.invalid"
    assert _text(root, "healthcareFacilityPhone") == "+44 20 7946 0000"
    assert _text(root, "healthcareFacilityAddress") == "1 Sample Street, London, SW1A 1AA (fictional)"
    assert _text(root, "patientPriorMedication") == "None reported (fictional)"


def test_b8_personal_details_reach_the_gb_file_in_mhras_places():
    values = GB_FULL | TYPED | {"3_3C": "Unknown", "1_2E": forms.MIR_INITIAL}
    root = etree.fromstring(
        mir_xml.build(values, GB_PARTIES, report_type=forms.MIR_INITIAL, now=NOW, form=GB, personal=True)
    )
    assert _text(root, "Gender") == "Unknown" and _text(root, "massKG") == "71"
    assert _text(root, "healthcareFacilityName") == "Sample Ward Planted (fictional)"
    assert next(root.iter("heightCM"), None) is None  # GB has no 3.3e


def test_b8_a_gender_outside_the_schemas_list_is_refused_naming_its_block():
    found = mir_xml.prepare(
        FULL | {"1_2E": forms.MIR_FINAL, "3_3C": "F"},
        PARTIES,
        report_type=forms.MIR_FINAL,
        now=NOW,
        personal=True,
    )
    assert found["xml"] is None and found["errors"]


def test_b8_the_worksheet_offers_each_schemas_own_gender_list():
    eu = {item.id: item for item in forms.EU_MIR.fields()}["3_3C"].options
    gb = {item.id: item for item in forms.GB_MIR.fields()}["3_3C"].options
    assert eu == ("Female", "Male", "Other", "Not specified")
    assert gb == ("Male", "Female", "Other", "Unknown", "Not applicable")


def test_b8_a_masked_export_never_holds_a_snapshots_personal_values():
    fields = {
        "sections": [
            {
                "fields": [
                    {"id": "3_3B", "personal": "PATIENT", "value": "64 years Planted"},
                    {"id": "3_3A_E", "personal": None, "value": "E0101"},
                    {"id": "3_4B", "personal": "REPORTER", "value": None},
                ]
            }
        ],
        "mir_xml": "<incident>Planted</incident>",
        "mir_sha256": "abc",
    }
    row = tenant_export.masked_row("report_snapshots", {"id": "x", "fields": fields})
    text = str(row)
    assert "Planted" not in text and "E0101" in text and "abc" in text
    assert tenant_export.PERSONAL_HELD in text
    # A snapshot without personal values is exported as it is.
    plain = {"sections": [{"fields": [{"id": "3_3A_E", "personal": None, "value": "E0101"}]}], "mir_xml": "<x/>"}
    assert tenant_export.masked_row("report_snapshots", {"fields": plain})["fields"] == plain


def test_b8_no_ai_or_search_code_reads_a_report_snapshot():
    """Personal details live only in report snapshots: no AI context builder or search reads them (tr30)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    places = [root / name for name in ("ai", "ask_mdarix", "genai", "retrieval")]
    files = [path for place in places if place.exists() for path in place.rglob("*.py")]
    files += [*(root / "backend" / "app").glob("ai_*.py"), root / "backend" / "app" / "data_plane_router.py"]
    assert len(files) > 5
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert "ReportSnapshot" not in text and "report_snapshots" not in text, path


def test_b8_gb_rows_only_the_eu_help_text_makes_mandatory_warn_never_block():
    """Owner, 11 Nov (follow MHRA): SRN, 2.1b-c, 2.3p, 2.4, 4.2i, 4.3.1a and 4.3.3d stay optional on GB with a "to
    confirm with your consultant" warning in the report types the EU help text names; 3.4h stays mandatory."""
    from backend.app.authority_reports import mir_rules

    every = mir_rules.to_confirm(GB, None)
    assert set(every) == {"1_3_2B", "2_1B", "2_1C", "2_3P_NB", "2_3P_CERT", "2_4", "4_2I", "4_3_1A", "4_3_3D"}
    assert set(mir_rules.to_confirm(GB, forms.MIR_INITIAL)) == {"1_3_2B", "2_4"}
    assert "4_2I" in mir_rules.to_confirm(GB, forms.MIR_COMBINED)
    assert "4_2I" not in mir_rules.to_confirm(GB, forms.MIR_FINAL_NON)
    assert mir_rules.to_confirm(forms.EU_MIR.code, forms.MIR_FINAL) == {}
    for report_type in forms.MIR_TYPES:
        mandatory = mir_rules.mandatory_fields(GB, report_type)
        assert not set(every) & set(mandatory) and "3_4H" in mandatory
    assert "consultant" in mir_rules.CONFIRM_WARNING


def test_b8_a_stored_4_3_3c_table_prints_as_plain_lines_never_json():
    """Run 5's risk: with a B8 switch off, a stored 4.3.3c table printed as its JSON text in the worksheet PDF."""
    import json

    from backend.app.authority_reports import render
    from tests.test_b8_mir_xml import TABLE

    stored = json.dumps(TABLE)
    text = forms.table_text(stored)
    assert text.count("\n") == 3 and text.startswith("N ") and "{" not in text and "worldwide" in text
    assert forms.table_text("not a table") == "not a table"
    view = {
        "form": {"clauses": [], "source_document": "EU MIR 7.3.1"},
        "starter_mark": "",
        "never_submits": "",
        "sections": [
            {
                "title": "4.3",
                "fields": [
                    {
                        "id": "4_3_3C",
                        "number": "4.3.3c",
                        "label": "Similar incidents",
                        "value": stored,
                        "kind": "TABLE",
                        "status_label": "Entered",
                    }
                ],
            }
        ],
    }
    printed = [line for line, _ in render.lines(view)]
    table = [line for line in printed if "incident(s)" in line]
    assert len(table) == 4 and not any("{" in line or '"start"' in line for line in printed)
