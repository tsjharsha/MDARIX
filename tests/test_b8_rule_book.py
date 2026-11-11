"""B8 step 2: the EU MIR rule book (rules/eu_mir.csv, register entry eu-mir-rule-book-1) is the one source of what each
report type must hold; forms.py agrees with it field by field. No database."""

from __future__ import annotations

import pytest

from backend.app.authority_reports import forms, mir_rules, worksheet
from backend.app.rule_register import register

pytestmark = pytest.mark.unit

EU = forms.EU_MIR


def _required(item: forms.Field, kind: str) -> bool:
    return forms.missing_class(item, kind) == forms.MUST


@pytest.mark.parametrize("form", [EU, forms.GB_MIR], ids=["EU", "GB"])
def test_b8_forms_and_rule_book_agree(form):
    by_field: dict[str, list[dict]] = {}
    for row in mir_rules.rows(form.code):
        for field in filter(None, row["fields"].split(";")):
            by_field.setdefault(field, []).append(row)
    fields = {item.id: item for item in form.fields()}
    assert set(by_field) <= set(fields), "the rule book names a field the form does not have"
    unmapped = set(fields) - set(by_field)
    assert not unmapped, f"form fields with no rule-book row: {sorted(unmapped)}"
    for field_id, found in by_field.items():
        if any(mir_rules.need(row, forms.MIR_INITIAL) == "C" for row in found):
            continue  # conditional blocks: the condition is the person's (the field's note says when)
        for kind in forms.MIR_TYPES:
            expected = any(mir_rules.need(row, kind) == "M" for row in found)
            assert _required(fields[field_id], kind) == expected, (field_id, kind)


def _every_mandatory_row_is_enforced(form, kind):
    required = mir_rules.mandatory_fields(form.code, kind)
    assert required, kind
    for field_id in required:
        sections = [
            {
                "fields": [
                    {
                        "id": item.id,
                        "missing_class": forms.missing_class(item, kind),
                        "status": forms.missing_class(item, kind) if item.id == field_id else worksheet.ENTERED,
                    }
                    for item in section.fields
                ]
            }
            for section in form.sections
        ]
        assert worksheet.mandatory(sections)["missing"] == [field_id], (kind, field_id)


@pytest.mark.parametrize("kind", forms.MIR_TYPES)
def test_b8_every_mandatory_eu_row_is_enforced(kind):
    """Per type, a report with every value but one mandatory block's names that block's fields as missing."""
    _every_mandatory_row_is_enforced(EU, kind)


@pytest.mark.parametrize("kind", forms.MIR_TYPES)
def test_b8_every_mandatory_gb_row_is_enforced(kind):
    _every_mandatory_row_is_enforced(forms.GB_MIR, kind)


def test_b8_gb_annex_b_c_d_and_g_codes_are_mandatory_in_every_gb_type():
    """B8-D3: MHRA's GB help text says Y in every type; kept although the GB changelog fixed minOccurs=0."""
    for kind in forms.MIR_TYPES:
        assert {"4_2E_B", "4_2E_C", "4_2E_D", "4_2F"} <= set(mir_rules.mandatory_fields(forms.GB_MIR.code, kind))
    rows = {row["block"]: row for row in mir_rules.rows(forms.GB_MIR.code)}
    assert not {"1.1b", "1.1d", "1.2d", "2.4e", "2.4f", "4.1b"} & set(rows)  # EU-only blocks: not in MHRA's schemas


def test_b8_the_help_texts_mandatory_4_3_1a_holds_in_final_reports_only():
    """B8-D6: the help text makes 4.3.1a mandatory in a Combined and a Final (Reportable) report; the XSD does not."""
    item = next(item for item in EU.fields() if item.id == "4_3_1A")
    assert [kind for kind in forms.MIR_TYPES if _required(item, kind)] == [forms.MIR_COMBINED, forms.MIR_FINAL]


def test_b8_the_rule_book_and_edition_are_offered_only_while_the_switch_is_on(monkeypatch):
    for code, switch in (("eu-mir-rule-book-1", "MDARIX_B8_EU_MIR"), ("eu-mir-7.3.1-SB-11252", "MDARIX_B8_EU_MIR"),
                         ("gb-mir-rule-book-1", "MDARIX_B8_GB_MIR"), ("gb-mir-7.2.1", "MDARIX_B8_GB_MIR")):  # fmt: skip
        entry = register.get(code)
        assert entry["switch"] == switch
        monkeypatch.delenv(switch, raising=False)
        assert register.offered(entry)
        monkeypatch.setenv(switch, "off")
        assert not register.offered(entry)
    assert not register.pin_problems()
