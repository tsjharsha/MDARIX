"""B6a P2 (D9) through the API: the baseline is the first 30 days after go-live and is fixed once they have passed;
the QMS's own triage history is shown apart; sample records never count; no per-person figure; Leaders, quality
reviewers and approvers only; another organization sees only its own; switched off, 404 (B6-43, B6-44, B6-45)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint, Tenant
from backend.app.db.models.intake import TriageRecord
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client
from tests.test_reporting_capa_api import _client

pytestmark = pytest.mark.db
URL = "/api/v1/oversight/value-centre"


def _triage(db, tenant_id, opened, hours, source=None, subject=None, qms_at=None) -> None:
    db.add(
        TriageRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            subject_kind="COMPLAINT" if subject else "INTAKE",
            subject_id=subject or uuid.uuid4(),
            opened_at=opened,
            completed_at=opened + timedelta(hours=hours),
            completed_by="someone",
            source_system=source,
            qms_triaged_at=qms_at,
            created_by="test",
            created_at=opened,
            updated_at=opened,
        )
    )


def _go_live(tenant_id, at) -> None:
    with SessionLocal() as db:
        bind_system(db, "test: value centre go-live")
        db.get(Tenant, tenant_id).activated_at = at
        db.commit()


def _metric(found: dict, code: str) -> dict:
    return next(item for item in found["metrics"] if item["code"] == code)


def test_the_baseline_the_qms_history_and_who_reads_it(monkeypatch):
    _, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    leader, investigator = _client(tenant_id, "LEADER", "Value Leader"), _client(tenant_id, "INVESTIGATOR")
    now = datetime.now(timezone.utc)
    go_live = now - timedelta(days=45)
    _go_live(tenant_id, go_live)
    with SessionLocal() as db:
        bind_system(db, "test: value centre records")
        triaged = db.query(TriageRecord.subject_id).filter(TriageRecord.tenant_id == tenant_id)
        complaint = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_timestamp.isnot(None))
            .filter(~Complaint.id.in_(triaged))
            .first()
        )
        received = complaint.complaint_timestamp
        _triage(db, tenant_id, go_live + timedelta(days=1), 6)  # in the baseline
        _triage(db, tenant_id, go_live + timedelta(days=2), 10)  # in the baseline
        _triage(db, tenant_id, go_live + timedelta(days=40), 30)  # after it: its month only
        _triage(db, tenant_id, go_live + timedelta(days=3), 500, source="MDARIX_SAMPLE")  # never counted
        # The QMS's own dates: received -> triaged in the QMS, 48 h (completed at import time is not counted).
        _triage(db, tenant_id, now, 0, source="QMS", subject=complaint.id, qms_at=received + timedelta(hours=48))
        db.commit()

    found = leader.get(URL)
    assert found.status_code == 200, found.text
    found = found.json()
    assert found["baseline"]["fixed"] is True
    triage = _metric(found, "TIME_TO_TRIAGE")
    assert triage["baseline"] == {"count": 2, "median": 8.0, "p90": 10.0}
    assert triage["imported"] == {"count": 1, "median": 48.0, "p90": 48.0}
    assert sum(item["count"] for item in triage["months"]) == 3
    assert {item["code"] for item in found["metrics"]} == {
        "TIME_TO_TRIAGE",
        "TIME_TO_DECISION",
        "TIME_TO_APPROVED_REPORT",
        "REPORT_COMPLETENESS",
    }
    # B6-44: no person anywhere: no name, no account, no "by".
    text = json.dumps(found)
    assert "Value Leader" not in text and "someone" not in text and '"by"' not in text and "actor" not in text

    # Within the first 30 days the baseline is not fixed yet.
    _go_live(tenant_id, now - timedelta(days=5))
    assert leader.get(URL).json()["baseline"]["fixed"] is False

    # The CSV: numbers and counts, audited.
    csv = leader.get(f"{URL}.csv")
    assert csv.status_code == 200 and "Your baseline (first 30 days after go-live)" in csv.content.decode("utf-8-sig")
    with SessionLocal() as db:
        bind_system(db, "test: value centre audit")
        assert db.query(AuditEvent).filter_by(tenant_id=tenant_id, action="VALUE_CENTRE_EXPORTED").count() == 1

    # Roles: an investigator is refused, the screen and the CSV.
    assert investigator.get(URL).status_code == 403 and investigator.get(f"{URL}.csv").status_code == 403
    # Another organization reads only its own (none of these triage times).
    _, other_approval, _ = _approved_trial_client()
    other = _client(uuid.UUID(other_approval["tenant_id"]), "LEADER")
    mine = _metric(other.get(URL).json(), "TIME_TO_TRIAGE")
    assert mine["imported"]["count"] == 0 and all(item["count"] == 0 for item in [mine["baseline"]] if item)
    # Switched off: 404, and the session hides the screen.
    monkeypatch.setenv("MDARIX_B6_VALUE_CENTRE", "off")
    assert leader.get(URL).status_code == 404 and leader.get(f"{URL}.csv").status_code == 404
    assert leader.get("/api/v1/session/context").json()["b6"]["value_centre"] is False
