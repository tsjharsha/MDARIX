"""Which registration an official form reads (device-classification spec, gaps G6 and G7; owner: "fix now").

- G6: two registrations of a product in one market give a field the same value: it is used (from the most recently
  updated one); different values: nothing is guessed, the field is left for a person with a note naming both.
- G7: the EU/NI form on a Northern Ireland event reads NI's registrations first, then the EU's; on an EU event the EU's
  only, never NI's.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.app.authority_reports import forms, worksheet
from backend.app.reportability import markets
from tests.test_authority_reports_api import _empty_context

pytestmark = pytest.mark.unit
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def _reg(market="EU", number="CE-1", risk_class="IIa", kind="CE", body="2797", age_days=0):
    return SimpleNamespace(
        id=uuid.uuid4(),
        market=market,
        registration_type=kind,
        registration_number=number,
        body_number=body,
        risk_class=risk_class,
        updated_at=NOW - timedelta(days=age_days),
    )


def _context(*registrations):
    return {**_empty_context(), "registrations": list(registrations)}


def _field(context, field_id):
    sections = worksheet.build(forms.EU_MIR, context, {}, {})
    return next(item for section in sections for item in section["fields"] if item["id"] == field_id)


def _risk_field_id():
    return next(item.id for section in forms.EU_MIR.sections for item in section.fields if item.source == "risk_class")


def test_two_registrations_same_market_same_class_is_used_from_the_most_recent():
    older, newer = _reg(number="CE-OLD", age_days=30), _reg(number="CE-NEW")
    for order in ((older, newer), (newer, older)):
        value, source = worksheet.SOURCES["risk_class"](_context(*order))
        assert value == "IIa"
        assert source["id"] == str(newer.id)  # the same one whatever order the database returns


def test_two_registrations_same_market_different_class_are_left_for_a_person():
    context = _context(_reg(number="CE-1", risk_class="IIa"), _reg(number="CE-2", risk_class="III", age_days=5))
    value, note = worksheet.SOURCES["risk_class"](context)
    assert value is None
    assert note.startswith(worksheet.CHOOSE_REGISTRATION) and "CE-1" in note and "CE-2" in note
    field = _field(context, _risk_field_id())
    assert field["value"] is None and field["source"] is None
    assert field["problem"].startswith(worksheet.CHOOSE_REGISTRATION)
    # A person's own choice clears the note.
    entered = worksheet.build(forms.EU_MIR, context, {_risk_field_id(): {"value": "III", "by": "x"}}, {})
    chosen = next(item for section in entered for item in section["fields"] if item["id"] == _risk_field_id())
    assert chosen["value"].endswith("III") and chosen["problem"] is None  # B8 writes the MIR's own "MDR class III"


def test_two_registrations_with_different_numbers_are_left_for_a_person():
    context = _context(_reg(number="CE-1"), _reg(number="CE-2"))
    value, note = worksheet.SOURCES["eu_certificate"](context)
    assert value is None and note.startswith(worksheet.CHOOSE_REGISTRATION)
    # Same class on both: the class is still used.
    assert worksheet.SOURCES["risk_class"](context)[0] == "IIa"


def test_ni_only_registration_is_used_on_a_northern_ireland_report():
    assert worksheet.registry_markets(markets.EU_NI, "Northern Ireland") == ("NI", "EU")
    assert worksheet.registry_markets(markets.EU_NI, "NI") == ("NI", "EU")
    assert worksheet.registry_markets(markets.EU_NI, "United Kingdom - Northern Ireland") == ("NI", "EU")
    ni = _reg(market="NI", number="UKNI-9", kind="UKNI", risk_class="IIb", body="0086")
    context = _context(ni)
    assert worksheet.SOURCES["risk_class"](context)[0] == "IIb"
    assert worksheet.SOURCES["eu_certificate"](context)[0] == "UKNI-9"
    assert worksheet.SOURCES["nb_number"](context)[0] == "0086"
    # NI's registration before the EU's, even when they differ.
    eu = _reg(market="EU", number="CE-1", risk_class="III")
    assert worksheet.SOURCES["risk_class"](_context(eu, ni))[0] == "IIb"
    # No NI registration: the EU's.
    assert worksheet.SOURCES["risk_class"](_context(eu))[0] == "III"


def test_ni_registration_is_never_read_on_an_eu_report():
    for country in ("Germany", "Ireland", "Germany, Northern Ireland", None, "United Kingdom"):
        assert worksheet.registry_markets(markets.EU_NI, country) == ("EU",)
    assert worksheet.registry_markets(markets.GB, "Northern Ireland") == ("GB",)
    assert worksheet.registry_markets(markets.US, "Germany") == ("US",)
