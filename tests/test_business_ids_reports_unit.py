"""Reports, the risk register export and Product 360 show each record's business identifier (no database needed)."""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.product360.service import Product360Service
from backend.app.risk.service import register_csv_rows
from reports.content import _case_labels, with_decision_business_ids

pytestmark = pytest.mark.unit

DECISION = uuid.UUID("22222222-2222-2222-2222-222222222222")


class FixedSession:
    """Stands in for a SQLAlchemy session whose one query returns ``rows``."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    def execute(self, statement):
        self.queries += 1
        return self

    def all(self):
        return self.rows


def _risk_item(**overrides):
    item = {
        "business_id": "RSK000007",
        "risk_identifier": "R-1",
        "description": "=cmd",
        "status": "OPEN",
        "product": {"business_id": "PROD000001", "product_identifier": "P-1"},
        "product_version": None,
        "residual_risk": {"state": "NO_CONTROLS_LINKED"},
        "failure_modes": [],
        "controls": [],
        "requirements": [],
        "open_complaints_on_product": 0,
    }
    item.update(overrides)
    return item


def test_the_risk_export_starts_with_the_business_id_column():
    header, row = register_csv_rows([_risk_item()])
    assert header[:3] == ["business_id", "risk_identifier", "description"]
    assert row[:2] == ["RSK000007", "R-1"]
    assert len(row) == len(header)


def test_case_labels_give_the_source_and_business_identifier_of_a_records_case():
    case = uuid.uuid4()
    labels = {case: ("INV-ACME-7", "INV000003")}
    assert _case_labels(labels, case) == {
        "investigation_identifier": "INV-ACME-7",
        "investigation_business_id": "INV000003",
    }
    assert _case_labels(labels, uuid.uuid4()) == {"investigation_identifier": None, "investigation_business_id": None}


def test_signatures_gain_their_decisions_business_id_in_one_lookup():
    signatures = [
        {"business_id": "ESIG000001", "decision_id": str(DECISION)},
        {"business_id": "ESIG000002", "decision_id": str(uuid.uuid4())},
    ]
    db = FixedSession([(DECISION, "DEC000004")])
    result = with_decision_business_ids(db, signatures)
    assert [item["decision_business_id"] for item in result] == ["DEC000004", None]
    assert result[0]["business_id"] == "ESIG000001" and "decision_business_id" not in signatures[0]
    assert db.queries == 1
    assert with_decision_business_ids(FixedSession([]), []) == []


def test_product360_sites_and_timeline_events_carry_business_ids():
    service = object.__new__(Product360Service)  # the pure helpers need no graph or database
    lots = [{"site_identifier": "SITE-A", "site_business_id": "SITE000002", "site_name": "Plant A"}]
    assert service.sites_for_lots(lots) == [
        {"business_id": "SITE000002", "site_identifier": "SITE-A", "name": "Plant A"}
    ]
    stamp = datetime(2026, 1, 5, tzinfo=timezone.utc)
    version = {"id": uuid.uuid4(), "business_id": "PV000001", "version_identifier": "A", "release_timestamp": stamp}
    complaint = {
        "id": uuid.uuid4(),
        "business_id": "CMP000009",
        "complaint_identifier": "ACD-CMP-0001",
        "event_timestamp": stamp,
        "recorded_timestamp": stamp,
        "ingestion_timestamp": stamp,
        "status": "OPEN",
    }
    events = service.timeline({}, [version], [], [], [], [], [complaint], [], [], [], [])
    assert {event.related_entity_type: event.related_entity_business_id for event in events} == {
        "product_version": "PV000001",
        "complaint": "CMP000009",
    }
