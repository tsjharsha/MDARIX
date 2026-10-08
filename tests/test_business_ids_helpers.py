"""The lookup helpers that put referenced objects' business identifiers into API responses (no database needed)."""

import uuid

import pytest

from backend.app.business_ids import as_uuid, business_id_map, business_id_of, wanted_ids
from backend.app.db.models.foundation import Investigation

pytestmark = pytest.mark.unit

KNOWN = uuid.UUID("11111111-1111-1111-1111-111111111111")


class RecordingSession:
    """Stands in for a SQLAlchemy session: records each statement and answers with fixed rows."""

    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return self

    def all(self):
        return self.rows


def test_as_uuid_accepts_uuids_and_their_strings():
    assert as_uuid(KNOWN) is KNOWN
    assert as_uuid(str(KNOWN)) == KNOWN
    assert as_uuid(str(KNOWN).upper()) == KNOWN


@pytest.mark.parametrize("value", [None, "", "not-a-uuid", "CMP000001", 42, object()])
def test_as_uuid_rejects_empty_and_malformed_values(value):
    assert as_uuid(value) is None


def test_wanted_ids_drops_duplicates_and_bad_values():
    assert wanted_ids([KNOWN, str(KNOWN), None, "", "nope"]) == {KNOWN}


def test_business_id_map_reads_all_ids_in_one_query():
    other = uuid.uuid4()
    db = RecordingSession([(KNOWN, "INV000001"), (other, "INV000002")])
    result = business_id_map(db, Investigation, [KNOWN, str(other), KNOWN, None])
    assert result == {str(KNOWN): "INV000001", str(other): "INV000002"}
    assert len(db.statements) == 1
    sql = str(db.statements[0])
    assert "investigations.business_id" in sql and "investigations.id IN" in sql


def test_business_id_map_skips_the_query_when_there_is_nothing_to_look_up():
    db = RecordingSession([])
    assert business_id_map(db, Investigation, [None, "", "bad"]) == {}
    assert db.statements == []


def test_business_id_of_returns_the_identifier_or_none():
    assert business_id_of(RecordingSession([(KNOWN, "INV000007")]), Investigation, str(KNOWN)) == "INV000007"
    assert business_id_of(RecordingSession([]), Investigation, KNOWN) is None
    empty = RecordingSession([])
    assert business_id_of(empty, Investigation, None) is None
    assert empty.statements == []
