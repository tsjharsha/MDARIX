"""R16: every row a workspace import writes carries its import and mapping version. Pure functions and a stand-in
session: no database."""

import uuid

import pytest

from backend.app import import_lineage as lineage
from backend.app.db.models.ingestion import ImportLineage
from backend.app.trial.imports import TEMPLATES

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.unit, pytest.mark.requirement("IN-13", "TR-21", "TR-36")]


def test_mapping_version_is_stable_and_follows_the_headers():
    plain = lineage.mapping_version("complaints", [], "ISO")
    assert plain == lineage.mapping_version("complaints", [], "ISO")
    assert plain.startswith("complaints-template:")
    renamed = [{"header": "Complaint No", "column": "complaint_id"}]
    assert lineage.mapping_version("complaints", renamed, "ISO") != plain
    assert lineage.mapping_version("complaints", [], "DMY") != plain


def test_record_key_uses_identifier_columns():
    assert (
        lineage.record_key(TEMPLATES["complaints"]["required"], {"complaint_id": "C-1", "product_id": "P"}) == "C-1:P"
    )
    lot = {"lot_id": "L1", "product_id": "P", "version": "Rev B"}
    assert lineage.record_key(TEMPLATES["lots"]["required"], lot) == "L1:P:Rev B"


class _Session:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


def test_every_row_gets_a_lineage_row():
    session, ref = _Session(), uuid.uuid4()
    rows = [(2, {"complaint_id": "C-1", "product_id": "P"}), (3, {"complaint_id": "C-2", "product_id": "P"})]
    lineage.write(session, uuid.uuid4(), ref, "complaints", ["complaint_id", "product_id"], rows, "v", "CSV_IMPORT")
    assert [(item.line, item.record_key, item.import_ref) for item in session.added] == [
        (2, "C-1:P", ref),
        (3, "C-2:P", ref),
    ]
    assert all(isinstance(item, ImportLineage) and item.mapping_version == "v" for item in session.added)
