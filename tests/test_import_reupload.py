"""0.10.62 (J9, J10): a re-upload sets only the columns its file holds, never reopens a closed complaint or CAPA when
the status column is absent, and "updated" counts only the rows that changed a field; a value longer than its
database column holds is refused by the check instead of failing the import."""

import uuid

import pytest

from backend.app.db.models.foundation import Complaint, LotBatch
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.trial import imports
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

pytestmark = pytest.mark.db

UPLOAD = "/api/v1/trial/imports/complaints"
FULL = (
    "complaint_id,product_id,product_name,version,lot_id,description,event_date,received_date,status\n"
    "RU-1,RU-PUMP,Reupload Pump,Rev A,RU-LOT-1,Alarm at start-up,2026-10-01,2026-10-02,Closed - no action\n"
    "RU-2,RU-PUMP,Reupload Pump,Rev A,RU-LOT-1,Door latch loose,2026-10-03,2026-10-04,open\n"
)


def _upload(user, csv: str, **params) -> dict:
    response = user.post(UPLOAD, params=params, content=csv, headers={"Content-Type": "text/csv"})
    assert response.status_code == 200, response.text
    return response.json()


def _stored(identifier: str) -> Complaint:
    with SessionLocal() as db:
        bind_system(db, "test: read the complaint")
        complaint = (
            db.query(Complaint)
            .filter(Complaint.complaint_identifier == identifier)
            .order_by(Complaint.created_at.desc())
            .first()
        )
        lot = db.get(LotBatch, complaint.lot_batch_id) if complaint.lot_batch_id else None
        db.expunge(complaint)
        return complaint, (lot.lot_identifier if lot else None)


def test_a_reupload_sets_only_its_columns_and_counts_only_real_changes():
    user, _, _ = _approved_trial_client()
    first = _upload(user, FULL)
    assert first["created"] >= 2
    same = _upload(user, FULL)
    assert same["updated"] == 0  # 0.10.61 said "2 updated" with nothing changed
    assert same["quality_report"]["rows_unchanged"] == 2 and same["quality_report"]["rows_changed"] == 0

    edited = (
        "complaint_id,product_id,product_name,description\n"
        "RU-1,RU-PUMP,Reupload Pump,Alarm at start-up; the line was clear\n"
        "RU-2,RU-PUMP,Reupload Pump,Door latch loose\n"
    )
    # A re-upload without any date column, said so (0.10.65: "none" dates nothing; the stored dates stay).
    result = _upload(user, edited, date_column="none")
    assert result["updated"] == 1 and result["quality_report"]["rows_changed"] == 1
    assert result["quality_report"]["rows_unchanged"] == 1
    complaint, lot = _stored("RU-1")
    # The file had no status, lot, version or date columns: the stored values stay (0.10.61 reopened it).
    assert complaint.status == "closed - no action" and lot == "RU-LOT-1"
    assert complaint.event_timestamp.date().isoformat() == "2026-10-01"
    assert complaint.complaint_timestamp.date().isoformat() == "2026-10-02"
    assert complaint.description == "Alarm at start-up; the line was clear"

    blank_status = "complaint_id,product_id,product_name,description,status\nRU-1,RU-PUMP,Reupload Pump,Alarm at start-up; the line was clear,\n"
    assert _upload(user, blank_status, date_column="none")["updated"] == 0
    assert _stored("RU-1")[0].status == "closed - no action"


def test_a_value_longer_than_its_column_is_refused_by_the_check():
    user, _, _ = _approved_trial_client()
    long = "x" * 41
    csv = f"complaint_id,product_id,product_name,description,severity\nRL-{uuid.uuid4().hex[:6]},RL-PUMP,Long Pump,Alarm,{long}\n"
    refused = user.post(UPLOAD, params={"date_column": "none"}, content=csv, headers={"Content-Type": "text/csv"})
    assert refused.status_code == 422, refused.text  # 0.10.61: "ready", then 500 "The import failed"
    issues = refused.json()["detail"]["report"]["issues"]
    assert [(issue["column"], issue["message"]) for issue in issues] == [
        ("severity", "Keep this to 40 characters or fewer.")
    ]


def test_each_column_takes_its_database_limit():
    assert imports.column_limit("complaints", "status") == 40
    assert imports.column_limit("complaints", "country") == 80
    assert imports.column_limit("complaints", "description") == 4000
    assert imports.column_limit("capas", "action_type") == 40
    assert imports.column_limit("components", "component_name") == 255


def test_a_closed_capa_is_not_reopened_by_a_file_without_a_status_column():
    from backend.app.db.models.foundation import Capa

    user, _, _ = _approved_trial_client()
    capa = f"CAPA-RU-{uuid.uuid4().hex[:6]}"
    url = "/api/v1/trial/imports/capas"
    first = user.post(
        url,
        content=f"capa_id,title,status,action_type\n{capa},Seal the door latch,Closed,Corrective\n",
        headers={"Content-Type": "text/csv"},
    )
    assert first.status_code == 200, first.text
    again = user.post(url, content=f"capa_id,title\n{capa},Seal the door latch\n", headers={"Content-Type": "text/csv"})
    assert again.status_code == 200 and again.json()["updated"] == 0, again.text
    with SessionLocal() as db:
        bind_system(db, "test: read the CAPA")
        row = db.query(Capa).filter(Capa.capa_identifier == capa).one()
        assert (row.status, row.action_type) == ("closed", "Corrective")
