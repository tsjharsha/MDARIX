"""B8 step 14: the GB MIR file. The same builder as the EU file, with MHRA's GB 7.2.1 schemas: every GB type valid
against its own XSD, no EU-only element in a GB file, the UK Responsible Person, one UDI issuing entity, the UK
approved body. No database."""

from __future__ import annotations

import pytest
from lxml import etree

from backend.app.authority_reports import forms, mir_rules, mir_xml
from tests.test_b8_mir_xml import FULL, NOW, _party

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.unit, pytest.mark.requirement("B8-05", "B8-15", "B8-24", "B8-26")]

GB = forms.GB_MIR.code
# The GB form's own fields: 1.3.1c-g are numbered apart from the EU form's (1.3.1d is the submitter's details).
GB_FULL = {key: value for key, value in FULL.items() if key in {item.id for item in forms.GB_MIR.fields()}} | {
    "1_1A": "Medicines and Healthcare products Regulatory Agency (MHRA)",
    "1_3_1A": "United Kingdom Responsible Person",
    "1_3_1D": "Orbit Medical Devices (Sample), Springfield, US",
    "1_3_1E": "MHRA-FSCA-7",
    "1_3_1F": "PSR-1",
    "1_3_1G": "PMCF-2026-01",
    "1_3_3": "UK Representative (Sample), London, GB",
    "2_1E": "GS1",
    "2_2A": "GMDN",
    "2_2B": "47769",
    "2_3_UKAB": "0086",
    "2_3_UKAB_CERT": "UKCA-2025-001",
    "2_4": "MDR class IIb",
    "2_5": "United Kingdom, France",
}
PARTIES = [
    _party("MANUFACTURER", "Orbit Medical Devices (Sample)", srn="US-MF-000012345", country_code="US"),
    _party(
        "UK_RESPONSIBLE_PERSON", "UK Representative (Sample)", city="London", postcode="SW1A 1AA", country_code="GB"
    ),
]
# Places in the EU schemas that MHRA's GB schemas do not have.
EU_ONLY = ("ncaEudamedNum", "refNumEudamed", "mfrAwarenessReportDate", "pmcfpmpfQuestion", "eudamedRefFSCALI")
EU_ONLY += ("udiDI_Entity", "Basic_Entity", "UnitofUse_Entity", "deviceNomenclature", "AppLegislationUnknown")
EU_ONLY += (
    "DevicePlacedMarket",
    "DeviceFulfill",
    "heightCM",
    "suspicionRelationShip",
    "healthcareFacilityCountryOther",
)


def _minimal(report_type: str) -> dict:
    needed = mir_rules.mandatory_fields(GB, report_type)
    return {key: text for key, text in GB_FULL.items() if key in needed} | {
        "1_2E": report_type,
        "1_3_1A": "Manufacturer",
    }


def _build(values: dict, report_type: str, parties=PARTIES) -> bytes:
    return mir_xml.build(values, parties, report_type=report_type, now=NOW, form=GB)


@pytest.mark.parametrize("report_type", forms.MIR_TYPES)
def test_b8_each_gb_type_validates_against_its_own_xsd(report_type):
    for values in (_minimal(report_type), GB_FULL | {"1_2E": report_type}):
        xml = _build(values, report_type)
        assert mir_xml.validate(xml, report_type, GB) == []
        root = etree.fromstring(xml)
        assert root.get(f"{{{mir_xml.XSI}}}noNamespaceSchemaLocation") == mir_xml.GB_FILES[report_type]
        assert root.findtext("admin_info/reportType") == report_type
        # The GB file is not the EU one: the EU schema of the same type refuses it, or it holds a GB-only place.
        assert mir_xml.GB_FILES[report_type].endswith("GB-v7.2.1.xsd")


def test_b8_eu_only_elements_are_never_in_a_gb_file():
    root = etree.fromstring(_build(GB_FULL | {"1_2E": forms.MIR_FINAL}, forms.MIR_FINAL))
    names = {element.tag for element in root.iter()}
    assert not names & set(EU_ONLY), names & set(EU_ONLY)
    # An EU value a GB report cannot hold is refused, naming its block, never dropped.
    with pytest.raises(mir_xml.MirRefused) as refused:
        _build(_minimal(forms.MIR_INITIAL) | {"1_2D": "2026-10-30"}, forms.MIR_INITIAL)
    assert any("not a place" in error for error in refused.value.errors)


def test_b8_the_gb_file_holds_mhras_own_places():
    root = etree.fromstring(_build(GB_FULL | {"1_2E": forms.MIR_FINAL}, forms.MIR_FINAL))
    ukrp = root.find("admin_info/contact_info/reporterUKRP")
    assert ukrp.findtext("statusReporter") == "United Kingdom Responsible Person"
    assert ukrp.findtext("arDetails/ARName") == "UK Representative (Sample)"
    assert ukrp.findtext("arDetails/ARCountry") == "GB"
    assert ukrp.findtext("mfrDetails/mfrCountry") == "US"
    device = root.find("device_info")
    assert device.findtext("udiIssueEntity") == "GS1" and device.findtext("nomenclatureSystem") == "GMDN"
    assert (device.findtext("UKABIdNum"), device.findtext("UKABCertNum")) == ("0086", "UKCA-2025-001")
    admin = root.find("admin_info")
    assert (admin.findtext("mfrRefFSCA"), admin.findtext("psrId"), admin.findtext("pmcfpmpfId")) == (
        "MHRA-FSCA-7",
        "PSR-1",
        "PMCF-2026-01",
    )
    # The UDI issuing entity, when the person gave none, is read from an unambiguous UDI only (B8-D11).
    values = _minimal(forms.MIR_INITIAL) | {"2_1A": "04012345678901"}
    derived = etree.fromstring(_build({k: v for k, v in values.items() if k != "2_1E"}, forms.MIR_INITIAL))
    assert derived.findtext("device_info/udiIssueEntity") == "GS1"


def test_b8_a_gb_maker_outside_the_uk_needs_a_uk_responsible_person():
    lacking = mir_xml.missing(_minimal(forms.MIR_INITIAL), PARTIES[:1], forms.MIR_INITIAL, GB)
    assert "1.3.3 the UK Responsible Person: the manufacturer is outside the UK (Settings, Products)" in lacking
    at_home = [_party("MANUFACTURER", "UK Maker (Sample)", country_code="GB")]
    assert not [line for line in mir_xml.missing(_minimal(forms.MIR_INITIAL), at_home, forms.MIR_INITIAL, GB)
                if "UK Responsible Person" in line]  # fmt: skip


def test_b8_gb_annex_b_c_d_and_g_codes_are_named_when_missing():
    """B8-D3: Annex B, C, D and G on every GB type, named at Send as the rule book's blocks."""
    values = {k: v for k, v in _minimal(forms.MIR_INITIAL).items() if k not in ("4_2E_B", "4_2F")}
    lacking = mir_xml.missing(values, PARTIES, forms.MIR_INITIAL, GB)
    assert any(line.startswith("4.2e ") for line in lacking) and any(line.startswith("4.2f ") for line in lacking)


def test_b8_gb_risk_classes_are_the_ones_mhras_schema_takes():
    for label in forms.GB_RISK_CLASSES:
        xml = _build(_minimal(forms.MIR_INITIAL) | {"2_4": label}, forms.MIR_INITIAL)
        assert mir_xml.validate(xml, forms.MIR_INITIAL, GB) == []
    with pytest.raises(mir_xml.MirRefused):  # EU only: MHRA's schema has no "legislation unknown"
        _build(_minimal(forms.MIR_INITIAL) | {"2_4": "Applicable legislation unknown"}, forms.MIR_INITIAL)


def test_b8_every_gb_field_has_its_place_in_the_file():
    placed = set(mir_xml.GB_PLAIN) | set(mir_xml.CODES) | mir_xml.SHAPED | mir_xml.GB_PARTY_FIELDS
    for field in forms.GB_MIR.fields():
        assert field.personal or field.id in placed, field.id


def test_b8_the_gb_pdf_says_it_is_a_record_copy():
    """B8 step 15 (B8-D18): the GB PDF is MDARIX's record copy, read back from the GB file; MHRA takes reports only
    through MORE. Every value of the file is in it."""
    import io

    from pypdf import PdfReader

    from backend.app.authority_reports import mir_pdf
    from tests.test_b8_mir_pdf import SIGNED

    xml = _build(GB_FULL | {"1_2E": forms.MIR_FINAL}, forms.MIR_FINAL)
    lines = "\n".join(text for text, _ in mir_pdf.body(xml))
    leaves = [e for e in etree.fromstring(xml).iter() if len(e) == 0 and (e.text or "").strip()]
    assert all(leaf.text.strip() in lines for leaf in leaves)
    pdf = mir_pdf.render(xml, SIGNED, "Orbit Medical Devices (Sample)")
    text = " ".join(" ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Record copy: MHRA takes reports only through MORE." in text and "upload the XML in MHRA's MORE" in text
    assert "GB MIR RECORD COPY - PREPARED BY MDARIX" in text and "EU MIR 7.3.1" not in text
    assert not any(claim in text.lower() for claim in ("generated by mhra", "made by mhra", "mhra's official pdf"))
    assert pdf == mir_pdf.render(xml, SIGNED, "Orbit Medical Devices (Sample)")  # same file, same bytes


def test_b8_a_gb_incident_country_is_written_as_its_iso_code():
    # Run 5: the GB file's country elements take ISO codes; MDARIX names the GB market "Great Britain".
    assert [mir_xml.country_code(name) for name in ("Great Britain", "United Kingdom", "England", "GB")] == ["GB"] * 4
    assert mir_xml.country_code("Northern Ireland") == "XI"  # the Commission's code, for the EU file in MORE
    assert mir_xml.country_code("France") == "FR" and mir_xml.country_code("Atlantis") == "Atlantis"
    xml = _build(GB_FULL | {"1_2E": forms.MIR_INITIAL, "3_4H": "Great Britain"}, forms.MIR_INITIAL)
    assert mir_xml.validate(xml, forms.MIR_INITIAL, form=GB) == []
