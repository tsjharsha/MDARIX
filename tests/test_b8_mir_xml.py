"""B8 step 7: the EU MIR file. One builder for the five report types, valid against each type's own XSD (SB-11252),
never a partial file, blanks left blank, personal fields never written ("off", B8-D9). No database."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from lxml import etree

from backend.app.authority_reports import forms, mir_rules, mir_xml

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 12, 9, 30, tzinfo=timezone.utc)
PERIOD = {"country_incidents": 1, "eea_incidents": 2, "world_incidents": 3}
PERIOD |= {"country_devices": 400, "eea_devices": 2500, "world_devices": 9000}
TABLE = [
    {"start": f"{2026 - n}-01-01", "end": f"{2026 - n}-12-31", **{k: v * (n + 1) for k, v in PERIOD.items()}}
    for n in range(4)
]
FULL = {
    "1_1A": "ANSM - Agence nationale de sécurité du médicament et des produits de santé",
    "1_1B": "NCA-EUD-1",
    "1_1C": "FR-2026-00123",
    "1_1D": "EUD-INC-1",
    "1_2A": "2026-11-12",
    "1_2B": "2026-10-28",
    "1_2C": "2026-10-29",
    "1_2D": "2026-10-30",
    "1_2F": "2026-12-15",
    "1_2G": "All other reportable incidents",
    "1_3_1A": "Authorised representative",
    "1_3_1B": "C-2026-0042",
    "1_3_1C": "MFR-REF-2",
    "1_3_1D": "FSCA-7",
    "1_3_1E": "PSR-1",
    "1_3_1F": "Yes, PMCF-2026-01",
    "1_3_2A": "Orbit Medical Devices (Sample)",
    "1_3_2B": "US-MF-000012345",
    "1_3_2C": "Springfield, US; contact: Alex Martin",
    "2_1A": "04012345678901",
    "2_1B": "(10)LOT42(17)271231",
    "2_1C": "4012345VL250QH",
    "2_1D": "04012345678918",
    "2_2A": "EMDN",
    "2_2B": "Z12030182",
    "2_3B_TEXT": "Ventilators for intensive care",
    "2_3A": "VentraLink 250",
    "2_3B": "Intensive-care ventilator for adults",
    "2_3C": "VL-250 Rev B",
    "2_3D": "VL250-B",
    "2_3E": "SN-0042",
    "2_3F": "LOT42",
    "2_3G": "4.2.1",
    "2_3H": "1.9",
    "2_3I": "2025-03-01",
    "2_3J": "2030-03-01",
    "2_3K": "2025-04-01 to 2025-04-02",
    "2_3L": "2026-10-28",
    "2_3M": "1 year, 6 months, 2 days",
    "2_3N": "Sample University Hospital",
    "2_3O": "Sample University Hospital",
    "2_3P_NB": "NB 0123",
    "2_3P_CERT": "CE-2025-001; CE-2025-002",
    "2_3Q": "First placed on the market 2025-05",
    "2_4": "IIb",
    "2_4E": "No",
    "2_4F": "No",
    "2_5": "France, Germany, IT, United States",
    "2_6A": "Breathing circuit",
    "2_6B": "Humidifier",
    "3_1A": "The flow sensor showed zero flow for 40 seconds; staff switched to manual ventilation. No harm.",
    "3_2A": "A0401 Flow problem; A090807 High Readings",
    "3_2B": "1",
    "3_2C": "Manufacturer",
    "3_2D": "Healthcare professional",
    "3_2E": "Initial use",
    "3_2F": "Manual ventilation",
    "3_3A_E": "E0101 Example sign",
    "3_3A_F": "F27 No health consequences",
    "3_3B": "Fictional sample value",
    "3_3C": "Fictional sample value",
    "3_4A": "Healthcare professional",
    "3_4B": "Fictional sample value",
    "3_4H": "France",
    "4_1A": "Sensor drift suspected; units returned.",
    "4_1B": "No",
    "4_1C": "Field check of sensors in the same lot.",
    "4_1D": "Teardown of the returned sensor.",
    "4_2A": "Sensor contamination from humidifier condensate.",
    "4_2B": "Not reportable: the alarm worked as designed.",
    "4_2C": "Yes",
    "4_2D": "Yes, still adequate: occurrence within the estimate.",
    "4_2E_B": "B01 Testing of actual device",
    "4_2E_C": "C04 Contamination",
    "4_2E_D": "D01 Cause traced to component",
    "4_2F": "G04010 Sensor",
    "4_2G": "CAPA-12: sensor shield added.",
    "4_2H": "Q1 2027",
    "4_2I": "Closed with the shield change.",
    "4_3_1A": "Annex A and Annex C codes of this report",
    "4_3_3A": "Model: every VentraLink 250 revision",
    "4_3_3B": "Units distributed within each time period",
    "4_3_3C": json.dumps(TABLE),
    "4_3_3D": "Complaint database search by product and Annex A code, per period.",
    "5": "1.2d is later than 1.2c: the investigation showed reportability on 30 Oct.",
}


def _party(role: str, organisation: str, **extra) -> SimpleNamespace:
    parts = {
        "srn": "XX-AR-000000001",
        "street": "1 Rue de l'Exemple",
        "city": "Lyon",
        "postcode": "69001",
        "country_code": "FR",
        "contact_first_name": "Alex",
        "contact_last_name": "Martin",
        "contact_phone": "+33 1 00 00 00 00",
        "contact_email": "vigilance@example.com",
    }
    return SimpleNamespace(role=role, organisation=organisation, **(parts | extra))


PARTIES = [
    _party(
        "MANUFACTURER", "Orbit Medical Devices (Sample)", srn="US-MF-000012345", city="Springfield", country_code="US"
    ),
    _party("AUTHORISED_REPRESENTATIVE", "EU Representative (Sample)"),
]


def _minimal(report_type: str) -> dict:
    needed = mir_rules.mandatory_fields(forms.EU_MIR.code, report_type)
    return {key: text for key, text in FULL.items() if key in needed} | {"1_2E": report_type, "1_3_1A": "Manufacturer"}


def _tree(xml: bytes):
    return etree.fromstring(xml)


@pytest.mark.parametrize("report_type", forms.MIR_TYPES)
def test_b8_each_type_validates_against_its_own_xsd(report_type):
    for values in (_minimal(report_type), FULL | {"1_2E": report_type}):
        xml = mir_xml.build(values, PARTIES[:1] if values is not FULL else PARTIES, report_type=report_type, now=NOW)
        assert mir_xml.validate(xml, report_type) == []
        root = _tree(xml)
        assert root.tag == "incident" and root.get("sFormLanguage") == "en"
        assert root.get("sCreateTimeStamp") == "2026-11-12T09:30:00+00:00"
        assert root.get(f"{{{mir_xml.XSI}}}noNamespaceSchemaLocation") == mir_xml.FILES[report_type]
        assert root.findtext("admin_info/reportType") == report_type


def test_b8_the_maximal_file_holds_every_value_in_its_place():
    root = _tree(mir_xml.build(FULL | {"1_2E": forms.MIR_FINAL}, PARTIES, report_type=forms.MIR_FINAL, now=NOW))
    contact = root.find("admin_info/contact_info/reporterAR")
    assert contact.findtext("statusReporter") == "Authorised representative"
    assert contact.findtext("mfrDetails/mfrCountry") == "US" and contact.findtext("arDetails/ARPostCode") == "69001"
    assert [e.text for e in root.find("incident_info/clinical_event_info").iter() if "CodeChoice" in e.tag] == [
        "A0401",
        "A090807",
    ]
    device = root.find("device_info")
    assert device.findtext("udiDI_Entity") == "GS1" and device.findtext("nbIdNum") == "0123"
    assert device.findtext("deviceClassMDR") == "class IIb" and device.findtext("nomenclatureSystem") == "EMDN"
    assert [e.text for e in device.findall("distribution/distributionEEA")] == ["FR", "DE", "IT"]
    assert device.findtext("distribution/otherCountries") == "United States"
    assert device.findtext("deviceMarketDate/year") == "2025" and device.findtext("deviceMarketDate/month") == "5"
    assert root.findtext("incident_info/initial_reporter_info/healthcareFacilityCountry") == "FR"
    similar = root.find("mfr_invest/similarIncidents")
    assert similar.findtext("similarVariant") == "Model" and similar.findtext("timePeriodN-3/worldSimDev") == "36000"
    assert root.findtext("mfr_invest/riskAssReviewed") == "Yes"
    assert root.findtext("admin_info/pmcfpmpfId") == "PMCF-2026-01"


def test_b8_blank_stays_blank_never_unknown_unless_the_help_text_says_so():
    values = _minimal(forms.MIR_INITIAL)
    xml = mir_xml.build(values, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW)
    assert b"Unknown" not in xml and b"N/A" not in xml
    root = _tree(xml)
    for blank in ("admin_info/ncaReportNo", "device_info/catalogNum", "device_info/udiDI", "other_reporting_info"):
        assert root.find(blank) is None, blank
    assert root.find("admin_info/contact_info/reporterMfr/arDetails") is None
    # 1.1c: "Unknown" when the NCA gave no number (the help text's rule), only when the report says so.
    root = _tree(mir_xml.build(values | {"1_1C": "Unknown"}, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW))
    assert root.findtext("admin_info/ncaReportNo") == "Unknown"


def test_b8_personal_fields_never_reach_the_file_while_the_setting_is_off():
    xml = mir_xml.build(FULL | {"1_2E": forms.MIR_FINAL}, PARTIES, report_type=forms.MIR_FINAL, now=NOW)
    root = _tree(xml)
    assert b"Fictional" not in xml
    for element in ("patientAgeAtEvent", "Gender", "massKG", "healthcareFacilityName", "healthcareFacilityStreet"):
        assert next(root.iter(element), None) is None, element


def test_b8_the_same_snapshot_builds_the_same_bytes():
    values = FULL | {"1_2E": forms.MIR_FOLLOW_UP}
    first = mir_xml.build(values, PARTIES, report_type=forms.MIR_FOLLOW_UP, now=NOW)
    assert mir_xml.build(dict(reversed(values.items())), PARTIES, report_type=forms.MIR_FOLLOW_UP, now=NOW) == first
    later = mir_xml.build(values, PARTIES, report_type=forms.MIR_FOLLOW_UP, now=NOW.replace(minute=31))
    assert later != first  # sCreateTimeStamp: the moment sent


def test_b8_a_file_the_schema_refuses_is_never_built():
    values = _minimal(forms.MIR_INITIAL)
    with pytest.raises(mir_xml.MirRefused) as refused:
        mir_xml.build(values | {"1_2F": ""}, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW)
    assert any(error.startswith("1.2f ") for error in refused.value.errors)
    with pytest.raises(mir_xml.MirRefused) as refused:
        mir_xml.build(values | {"1_2C": "last week"}, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW)
    assert any(error.startswith("1.2c ") for error in refused.value.errors)
    with pytest.raises(mir_xml.MirRefused) as refused:  # seven codes: the file has six places
        mir_xml.build(values | {"3_2A": "; ".join(["A0401"] * 7)}, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW)
    assert any("3.2a" in error and "not a place" in error for error in refused.value.errors)
    with pytest.raises(mir_xml.MirRefused):  # a class the form does not have
        mir_xml.build(values | {"2_4": "Class V"}, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW)
    # Final: no UDI issuing entity (an ambiguous UDI, none set on the product): refused, naming 2.1a.
    final = _minimal(forms.MIR_FINAL) | {"2_1A": "VL250-UDI"}
    with pytest.raises(mir_xml.MirRefused) as refused:
        mir_xml.build(final, PARTIES[:1], report_type=forms.MIR_FINAL, now=NOW)
    assert any(error.startswith("2.1a ") for error in refused.value.errors)
    assert mir_xml.build(final, PARTIES[:1], report_type=forms.MIR_FINAL, now=NOW, udi_entity="IFA")


def test_b8_send_checks_name_the_missing_blocks_and_parts():
    found = mir_xml.prepare({"1_2E": forms.MIR_INITIAL}, [], report_type=forms.MIR_INITIAL, now=NOW)
    assert found["xml"] is None and any(item.startswith("1.2f ") for item in found["missing"])
    assert "1.3.2 the manufacturer (Settings, Products)" in found["missing"]
    found = mir_xml.prepare(_minimal(forms.MIR_INITIAL), PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW)
    assert [item[:6] for item in found["missing"]] == ["1.3.3 "]  # a US manufacturer needs an EU representative
    bare = SimpleNamespace(role="MANUFACTURER", organisation="Orbit", srn=None, contact_phone="1", contact_email=None)
    found = mir_xml.prepare(_minimal(forms.MIR_INITIAL), [bare], report_type=forms.MIR_INITIAL, now=NOW)
    assert found["missing"] == [
        "1.3.2 Orbit: contact's first name, contact's last name, street, city, postcode, country, e-mail "
        "(Settings, Products)"
    ]
    found = mir_xml.prepare(_minimal(forms.MIR_INITIAL), PARTIES, report_type=forms.MIR_INITIAL, now=NOW)
    assert found["missing"] == [] and found["errors"] == [] and found["xml"].startswith(b"<?xml")


def test_b8_every_eu_field_has_its_place_in_the_file():
    placed = set(mir_xml.PLAIN) | set(mir_xml.CODES) | mir_xml.SHAPED | mir_xml.NOT_IN_FILE | mir_xml.PARTY_FIELDS
    for field in forms.EU_MIR.fields():
        assert field.personal or field.id in placed, field.id


def test_b8_every_choice_on_the_worksheet_is_one_the_schema_takes():
    choices = {}

    def walk(layout, prefix):
        for name, kids, enum, _ in layout:
            if kids is not None:
                walk(kids, prefix + name + "/")
            elif enum:
                choices[prefix + name] = enum

    walk(mir_xml._layout(forms.MIR_INITIAL), "")
    for field in forms.EU_MIR.fields():
        for option in field.options:
            path = mir_xml.file_values({field.id: option}, [])
            for where, text in path.items():
                if where in choices:
                    assert mir_xml._fit(text, choices[where]) in choices[where], (field.id, option)


def test_b8_every_risk_class_on_the_list_is_one_the_schema_takes():
    """2.4 is a fixed list (B8 run 4): every entry builds a valid file; GB's list has no "legislation unknown"."""
    for label in forms.EU_RISK_CLASSES:
        values = _minimal(forms.MIR_INITIAL) | {"2_4": label}
        assert (
            mir_xml.validate(mir_xml.build(values, PARTIES[:1], report_type=forms.MIR_INITIAL, now=NOW), "Initial")
            == []
        )
    assert "Applicable legislation unknown" not in forms.GB_RISK_CLASSES
    assert next(f for f in forms.GB_MIR.fields() if f.id == "2_4").options == forms.GB_RISK_CLASSES


@pytest.mark.parametrize(
    ("text", "choice"),
    [
        ("IIb", "MDR class IIb"),
        ("class iii", "MDR class III"),
        ("B", "IVDR class B"),
        ("MDD class IIb", "MDD class IIb"),
        ("mdd IIa", "MDD class IIa"),
        ("Is", "MDR class Is"),
        ("ivdr class c", "IVDR class C"),
        ("Class V", None),
        ("IV", None),
        ("", None),
    ],
)
def test_b8_a_class_typed_before_the_list_maps_to_it_or_is_chosen_again(text, choice):
    assert forms.risk_class_choice(text) == choice
