"""B8 step 10 (B8-24): 4.3 similar incidents as one structured entry. Periods N to N-3, each with its dates and, for
the incident's country, EEA + CH + TR and the world, the similar incidents and the devices on the market: every
number a person's (B8-D7). A Final needs every period and region; the table lands in the XML in order. No database."""

from __future__ import annotations

import json

import pytest
from lxml import etree

from backend.app.authority_reports import forms, mir_xml, worksheet
from tests.test_authority_reports_api import _empty_context
from tests.test_b8_mir_xml import FULL, NOW, PARTIES, TABLE

pytestmark = pytest.mark.unit


def _row(entries: dict) -> tuple[dict, dict]:
    sections = worksheet.build(forms.EU_MIR, _empty_context(), entries, {})
    field = next(item for section in sections for item in section["fields"] if item["id"] == "4_3_3C")
    return field, worksheet.mandatory(sections)


def test_b8_a_final_needs_every_period_and_region():
    final = {"1_2E": {"value": forms.MIR_FINAL}}
    field, meter = _row(final)
    assert field["kind"] == forms.TABLE and field["missing_class"] == forms.MUST and "4_3_3C" in meter["missing"]
    no_world = [{k: v for k, v in row.items() if k != "world_devices"} for row in TABLE]
    three = TABLE[:3]
    late = [dict(TABLE[0], end="2025-12-31", start="2026-01-01"), *TABLE[1:]]
    typed = [dict(TABLE[0], eea_incidents="2"), *TABLE[1:]]
    for broken, words in (
        (no_world, "Period N: every count"),
        (three, "four periods"),
        (late, "Period N: a start and an end date"),
        (typed, "Period N: every count"),
        ("12 incidents", "four periods"),
    ):
        text = broken if isinstance(broken, str) else json.dumps(broken)
        field, meter = _row(final | {"4_3_3C": {"value": text}})
        assert words in (field["problem"] or ""), broken
        assert "4_3_3C" in meter["missing"]
    field, meter = _row(final | {"4_3_3C": {"value": json.dumps(TABLE)}})
    assert field["problem"] is None and "4_3_3C" not in meter["missing"]
    zeros = [dict(row, **dict.fromkeys(forms.SIMILAR_COUNTS, 0)) for row in TABLE]  # none found: 0, entered
    assert _row(final | {"4_3_3C": {"value": json.dumps(zeros)}})[0]["problem"] is None
    assert "4_3_3C" not in _row({"1_2E": {"value": forms.MIR_INITIAL}})[1]["missing"]  # an Initial: not yet


def test_b8_the_table_lands_in_the_xml_in_order():
    xml = mir_xml.build(FULL | {"1_2E": forms.MIR_FINAL}, PARTIES, report_type=forms.MIR_FINAL, now=NOW)
    similar = etree.fromstring(xml).find("mfr_invest/similarIncidents")
    periods = [child for child in similar if child.tag.startswith("timePeriod")]
    assert [child.tag for child in periods] == list(mir_xml.PERIODS)
    order = ["startDate", "endDate", "countrySimInc", "eeaChTrSimInc", "worldSimInc", "countrySimDev"]
    for period, row in zip(periods, TABLE):
        assert [child.tag for child in period] == [*order, "eeaChTrSimDev", "worldSimDev"]
        assert period.findtext("startDate") == row["start"] and period.findtext("worldSimInc") == str(
            row["world_incidents"]
        )
    assert similar.findtext("howWereDetermined") == FULL["4_3_3D"]
