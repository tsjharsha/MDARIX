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
    stored = quarantine.stored_values(row, imports._personal_data, imports._mask)
    assert stored["complaint_id"] == "C-1"
    assert "jane.doe@example.com" not in stored["description"] and "9876543210" not in stored["description"]
    assert imports._personal_data(stored["description"], labels=False) is None


def test_only_workspace_imports_store_rows():
    assert imports.WORKSPACE_POLICY.quarantine is True
    assert imports.TRIAL_POLICY.quarantine is False


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
    quarantine.store(session, tenant, ref, "complaints", "CSV_IMPORT", set_aside, imports._personal_data, imports._mask)
    assert all(isinstance(item, ImportQuarantineRow) for item in session.added)
    first, second = session.added
    assert (first.line, first.problems, first.harm_words, first.status) == (
        3,
        ["product_id: not found"],
        ["burned"],
        "OPEN",
    )
    assert second.harm_words == [] and {first.import_ref, second.import_ref} == {ref}
