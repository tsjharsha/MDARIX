"""R14: rows a workspace import sets aside are stored with their reasons, personal data masked, and a row that
suggests harm carries its harm words for triage (A2). Pure functions and a stand-in session: no database. The
database path (store, list, re-process) is exercised through the import tests that need PostgreSQL.
"""

import uuid

import pytest

from backend.app import import_quarantine as quarantine
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.trial import imports

pytestmark = pytest.mark.unit


def test_harm_from_flags_and_words():
    assert quarantine.harm_words({"death": "Yes", "description": "pump alarm"}) == ["death"]
    assert quarantine.harm_words({"description": "Patient taken to hospital after overdose"}) == [
        "hospital",
        "overdose",
    ]
    # A failure alone is not harm.
    assert quarantine.harm_words({"description": "Display failed, alarm sounded", "serious_injury": "no"}) == []


def test_personal_data_is_masked_before_storing():
    row = {"complaint_id": "C-1", "description": "User emailed jane.doe@example.com from +91 9876543210 about the leak"}
    stored = quarantine.stored_values(row, imports.stored_value)
    assert stored["complaint_id"] == "C-1"
    assert "jane.doe@example.com" not in stored["description"] and "9876543210" not in stored["description"]
    assert imports._personal_data(stored["description"], labels=False) is None


def test_workspace_and_trial_imports_store_rows():
    # The trial and the MVP behave the same once the data is in (0.10.56).
    assert imports.WORKSPACE_POLICY.quarantine is True
    assert imports.TRIAL_POLICY.quarantine is True


def test_a_file_name_keeps_its_last_part_without_personal_data():
    assert imports.file_label("C:\\exports\\complaints-2026.xlsx") == "complaints-2026.xlsx"
    assert imports.file_label("/tmp/a/b.csv") == "b.csv"
    assert imports.file_label("  ") is None and imports.file_label(None) is None
    assert "jane.doe@example.com" not in imports.file_label("from jane.doe@example.com.csv")


class _Session:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


def test_store_keeps_reasons_and_flags_harm():
    session = _Session()
    tenant = uuid.uuid4()
    set_aside = [
        (
            3,
            {"complaint_id": "C-3", "product_id": "UNKNOWN", "description": "burned the patient"},
            ["product_id: not found"],
        ),
        (5, {"complaint_id": "C-5", "product_id": "P-1", "description": ""}, ["description: required"]),
    ]
    ref = uuid.uuid4()
    quarantine.store(session, tenant, ref, "complaints", "CSV_IMPORT", set_aside, imports.stored_value)
    assert all(isinstance(item, ImportQuarantineRow) for item in session.added)
    first, second = session.added
    assert (first.line, first.problems, first.harm_words, first.status) == (
        3,
        ["product_id: not found"],
        ["burned"],
        "OPEN",
    )
    assert second.harm_words == [] and {first.import_ref, second.import_ref} == {ref}


def test_every_free_text_value_is_stored_masked_and_identifiers_are_kept():
    """J7: values the second net did not flag were stored as sent ("Mr. John Smith", "67-year-old male at Riverside
    Hospital", "mr. smith"); the set-aside view says personal details are kept only as placeholders."""
    row = {
        "complaint_id": "C-7",
        "serial_number": "9845012345",
        "description": "Mr. John Smith called on 98450 12345 about the pump",
        "complaint_type": "67-year-old male at Riverside Hospital",
        "problem_code": "Caller mr. smith said it stopped",
        "product_name": "Dr Trust BP monitor",
    }
    stored = quarantine.stored_values(row, imports.stored_value)
    assert stored["description"] == "[PERSON] called on [PHONE] about the pump"
    assert stored["complaint_type"] == "[AGE_SEX] at [FACILITY]"
    assert "smith" not in stored["problem_code"].lower() and "[PERSON]" in stored["problem_code"]
    # Identifiers stay (a person finds and fixes the row by them); a brand is not a person.
    assert stored["complaint_id"] == "C-7" and stored["serial_number"] == "9845012345"
    assert stored["product_name"] == "Dr Trust BP monitor"


def test_a_stored_reason_leaves_out_the_words_a_check_quoted():
    session = _Session()
    problem = "description: This looks like it contains a phone number (“98450 12345”). Remove personal data and retry."
    row = {"complaint_id": "C-8", "description": "Call 98450 12345"}
    quarantine.store(
        session, uuid.uuid4(), uuid.uuid4(), "complaints", "CSV_IMPORT", [(4, row, [problem])], imports.stored_value
    )
    (item,) = session.added
    assert item.problems == ["description: This looks like it contains a phone number. Remove personal data and retry."]
    assert "98450" not in str(item.row) and "98450" not in str(item.problems)


def _checked(row: dict, mask: bool = False) -> list[dict]:
    report = imports._Report()
    imports._check_values("complaints", [(2, row)], report, mask_personal_data=mask)
    return report.issues


BASE = {"complaint_id": "C-9", "product_id": "PUMP-200", "description": "Occlusion alarm during infusion"}


def test_device_identifiers_are_checked_as_identifiers():
    """J8: a ten-digit serial read as a phone number, a GTIN-14 that passes the Luhn check as a card number, and a
    HIBC UDI starting with "+" as a spreadsheet formula."""
    gtin = "08848380001093"  # a valid GS1 check digit that also passes Luhn
    assert _checked({**BASE, "serial_number": "9845012345", "udi": gtin}) == []
    assert _checked({**BASE, "udi": "+H123PUMP2001/$$3261120L24-0815"}) == []
    assert _checked({**BASE, "udi": "(01)00884838000292(17)261120(10)L24-0815"}) == []
    assert _checked({**BASE, "description": f"UDI-DI {gtin} on the label"}) == []
    refused = _checked({**BASE, "udi": "=HYPERLINK(1)"})
    assert [issue["column"] for issue in refused] == ["udi"]


def test_a_brand_in_a_product_name_is_not_a_person():
    for name in ("Dr Trust BP monitor", "Dr. Morepen"):
        row = {**BASE, "product_name": name}
        assert _checked(dict(row)) == []
        masked = dict(row)
        assert _checked(masked, mask=True) == [] and masked["product_name"] == name


def test_every_personal_data_refusal_quotes_the_words_it_found():
    issues = _checked({**BASE, "description": "Mr. John Smith called on 98450 12345"})
    assert issues[0]["message"] == (
        "This looks like it contains a person's name and a phone number (“Mr. John Smith, 98450 12345”). "
        "Remove personal data and retry, or choose to mask it."
    )
    second_net = _checked({**BASE, "description": "caller mr smith"})
    assert "(“mr smith”)" in second_net[0]["message"]
