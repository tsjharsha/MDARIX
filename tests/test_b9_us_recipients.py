"""B9 step 8 (B9-23, B9-24): who must receive a US importer's or user facility's report, and the routes its
submission may be recorded by. Death: FDA and the manufacturer; serious injury: FDA and the manufacturer (importer) or
the manufacturer, FDA when it is unknown (user facility); an importer's malfunction: the manufacturer only, no FDA
route. Unknown is never No: a rule that could apply names its recipients too. No database."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.authority_reports import router, worksheet
from backend.app.rule_register import engine, register

pytestmark = pytest.mark.unit

DEATH = {"US1": "YES", "US3": "YES"}
INJURY = {"US1": "NO", "US2C": "YES", "US3": "YES"}
MALFUNCTION = {"US1": "NO", "US2A": "NO", "US2B": "NO", "US2C": "NO", "US3": "NO", "US4": "YES", "US5": "YES"}
MAKER = SimpleNamespace(
    id=None,
    market="US",
    role="MANUFACTURER",
    organisation="Orbit Medical Devices (Sample)",
    address=None,
    contact_name=None,
    contact_phone=None,
    contact_email="mdr@example.invalid",
)


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.delenv("MDARIX_B9_US_IMPORTER", raising=False)
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")


def _context(role: str, answers: dict, parties=(MAKER,)) -> dict:
    content = register.floor("US", role=role)["content"]
    applied = engine.applied(content, {key: {"answer": value} for key, value in answers.items()})
    return {"us_role": role, "current": SimpleNamespace(rules_applied=applied), "parties": list(parties)}


@pytest.mark.parametrize(
    "role, answers, parties, expected",
    [
        ("IMPORTER", DEATH, (MAKER,), ["FDA", "MANUFACTURER"]),
        ("IMPORTER", INJURY, (MAKER,), ["FDA", "MANUFACTURER"]),
        ("IMPORTER", MALFUNCTION, (MAKER,), ["MANUFACTURER"]),
        ("USER_FACILITY", DEATH, (MAKER,), ["FDA", "MANUFACTURER"]),
        ("USER_FACILITY", INJURY, (MAKER,), ["MANUFACTURER"]),
        ("USER_FACILITY", INJURY, (), ["FDA", "MANUFACTURER"]),  # the manufacturer unknown: FDA too
    ],
)
def test_the_recipient_table(role, answers, parties, expected):
    assert worksheet.us_recipients(_context(role, answers, parties)) == expected


def test_unknown_is_never_no_a_rule_that_could_apply_names_its_recipients():
    # Death unknown, serious injury unknown, caused unknown: the importer's death/injury rule could apply.
    could = _context("IMPORTER", {"US4": "YES", "US5": "YES"})
    assert worksheet.us_recipients(could) == ["FDA", "MANUFACTURER"]
    # A conclusion that names no recipient (signed before B9): both, the safe direction.
    assert worksheet.us_recipients({"current": None, "parties": []}) == ["FDA", "MANUFACTURER"]


def _report(report_type: str):
    return SimpleNamespace(form_code="FDA_3500A", report_type=report_type, kind="INITIAL", parent_id=None)


def test_the_routes_offered_follow_the_recipients_and_the_switches(monkeypatch):
    malfunction = _context("IMPORTER", MALFUNCTION)
    injury = _context("IMPORTER", INJURY)
    codes = lambda report, context: [route.code for route in router.offered_routes(report, context)]  # noqa: E731
    assert codes(_report("US_IMP_30_DAY"), malfunction) == ["MFR_COPY"]  # no FDA route for an importer malfunction
    assert codes(_report("US_IMP_30_DAY"), injury) == ["EMDR", "MFR_COPY"]
    assert codes(_report("US_30_DAY"), injury) == ["EMDR"]  # a manufacturer's report never offers the copy
    assert (
        router.number_key(_report("US_IMP_30_DAY")) == "F2" and router.number_key(_report("US_30_DAY")) == "MFR_REPORT"
    )
    # Off, a role reads as Manufacturer: the FDA route only, the number on the front page, a manufacturer's file.
    monkeypatch.setenv("MDARIX_B9_US_IMPORTER", "off")
    assert codes(_report("US_IMP_30_DAY"), injury) == ["EMDR"] and router.us_role(_report("US_IMP_30_DAY")) is None
    assert router._emdr_kind(_report("US_IMP_30_DAY")) == "M-I"
    monkeypatch.delenv("MDARIX_B9_US_USER_FACILITY")  # its default: off
    assert router.us_role(_report("US_UF_10_WORK_DAY")) is None


def test_india_r1_and_canada_a1_read_the_organizations_role_and_are_typed_again_while_off(monkeypatch):
    from backend.app.authority_reports import forms

    for market, form, field in (("IN", forms.MVPI_MDAE, "R1"), ("CA", forms.HC_MDPR, "A1")):
        monkeypatch.delenv(
            "MDARIX_B9_INDIA" if market == "IN" else "MDARIX_B9_CANADA", raising=False
        )  # its default: on
        item = next(entry for entry in form.fields() if entry.id == field)
        context = {"market": market, "seen": {"roles": {market: "IMPORTER"}}}
        assert forms.in_force(form, item).source == "role_reporter"
        assert worksheet.SOURCES["role_reporter"](context)[0] == "Importer"
        assert worksheet.SOURCES["role_reporter"]({"market": market, "seen": {}})[0] == "Manufacturer"
        monkeypatch.setenv("MDARIX_B9_INDIA" if market == "IN" else "MDARIX_B9_CANADA", "off")
        assert forms.in_force(form, item).source is None  # off: typed, as before B9
