"""Work-notice emails name a record by its business id, never by a UUID or part of one."""

import re
import uuid

import pytest

from backend.app.notifications import _reference

pytestmark = pytest.mark.unit


def test_the_producer_reference_wins():
    assert (
        _reference({"reference": "INV000012", "investigation_id": str(uuid.uuid4())}, "investigation_id") == "INV000012"
    )


def test_the_business_id_in_the_event_is_used_next():
    payload = {"decision_id": str(uuid.uuid4()), "decision_business_id": "DEC000003"}
    assert _reference(payload, "decision_id") == "DEC000003"


def test_without_either_no_part_of_the_uuid_is_shown():
    record = uuid.uuid4()
    text = _reference({"risk_id": str(record)}, "risk_id")
    assert str(record)[:8] not in text and not re.search(r"[0-9a-f]{8}", text)
