"""0.10.92 (development cycle 1, step 1): the fixes a pure test proves, with no database.

1.5 (A5): the contact office FDA's eMDR file needs (G1, from the US responsible party with an e-mail) is asked for
while the report is a draft, as a mandatory field with its reason, so Send for approval waits for it; approval froze the
report before, and only the XML then said it was missing.

1.6 (A7): a report sent back for correction says one status on its chip, its path and its next step.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.authority_reports import emdr, forms, rules, worksheet

pytestmark = pytest.mark.unit


def _party(**extra):
    base = dict(
        id=None,
        market="US",
        role="MANUFACTURER",
        organisation="Medisynth Devices (Sample)",
        address="Plot 4, MIDC, Pune, India",
        contact_name="Jane Doe",
        contact_phone="+1(240)276-0001",
        contact_email="mdr@example.invalid",
    )
    return SimpleNamespace(**{**base, **extra})


def _g1(parties, entries=None, draft=True) -> tuple[dict, list[str], list[dict]]:
    from tests.test_authority_reports_api import _empty_context

    context = {**_empty_context(), "parties": parties, "check_contact_office": draft}
    sections = worksheet.build(forms.FDA_3500A, context, entries or {}, {})
    field = next(item for part in sections for item in part["fields"] if item["id"] == "G1")
    return field, worksheet.mandatory(sections)["missing"], sections


def test_a_contact_office_without_an_email_holds_send_for_approval_and_says_where_to_add_it():
    field, missing, sections = _g1([_party(contact_email=None)])
    assert field["value"] and "e-mail" in field["problem"] and "Settings › Products" in field["problem"]
    assert "G1" in missing and field["ask"] == worksheet.CONTACT_EMAIL  # asked for beside the field
    assert "ask" not in worksheet.frozen(sections)[0]["fields"][0]
    # The same thing the eMDR check would have said after approval.
    assert [line for line in emdr.check(sections, [_party(contact_email=None)])[0] if "needs an email" in line]
    # An e-mail longer than FDA's 50 characters is no better.
    assert "G1" in _g1([_party(contact_email="x" * 45 + "@example.invalid")])[1]


def test_a_contact_office_the_emdr_can_carry_is_not_asked_for():
    field, missing, sections = _g1([_party()])
    assert field["problem"] is None and "G1" not in missing
    assert not [line for line in emdr.check(sections, [_party()])[0] if "contact office" in line]


def test_a_typed_contact_office_that_differs_from_the_responsible_party_is_asked_for():
    typed = {"G1": {"value": "Someone else, somewhere; contact: nobody", "by": "u1", "at": "2026-11-07T10:00:00Z"}}
    field, missing, _ = _g1([_party()], typed)
    assert field["status"] == "ENTERED" and field["problem"].startswith("Differs from your US responsible party")
    assert field["ask"] is None  # an e-mail alone would not make the two read the same
    assert "G1" in missing
    # Typed with no responsible party at all: the file has nowhere to take it from either.
    assert "G1" in _g1([], typed)[1]


def test_an_approved_report_is_never_asked_again():
    # After approval the report is frozen: the check belongs to the draft (an acknowledged sample report stays done).
    field, missing, _ = _g1([_party(contact_email=None)], draft=False)
    assert field["problem"] is None and "G1" not in missing


def test_a_report_sent_back_for_correction_says_so_on_its_path_as_its_status_does():
    view = rules.stage_view(rules.CORRECTION, 0, False)
    first = view["stages"][0]
    assert first["state"] == "CURRENT" and first["label"] == view["stage_label"] == "Draft: correction required"
    assert [step["label"] for step in view["stages"][1:]] == [label for _, label in rules.STAGES[1:]]
    # Sent for approval again, the path is at Approval and the first stage reads as always.
    again = rules.stage_view(rules.CORRECTION, 0, True)
    assert again["stages"][0]["label"] == "Created" and again["stages"][2]["state"] == "CURRENT"
    assert rules.stage_view(rules.DRAFT, 2, False)["stages"][0]["label"] == "Created"
