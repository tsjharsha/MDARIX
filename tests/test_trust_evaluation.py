"""The Trust page shows the latest honest evaluation of the real pipeline, read safely from the golden tenant."""

import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.db.models.foundation import EvaluationRun
from backend.app.db.session import SessionLocal
from backend.app.main import app
from evaluation.real_pipeline import EVALUATION_VERSION, record_run
from tests.conftest import authenticated_client

REPORT = {
    "evaluation_version": EVALUATION_VERSION,
    "model": "groq:test-model",
    "passed": 9,
    "total": 12,
    "model_written": 12,
    "with_specific_expectations": 4,
    "passed_with_specific_expectations": 1,
    "thresholds": {"match": 0.75, "prohibited": 0.85},
    "results": [
        {
            "scenario_id": "VS001",
            "title": "Supplier Change Correlation",
            "status": "PASS",
            "specific_expectations": 6,
            "analysis_author": "LANGUAGE_MODEL",
            "seconds": 9.5,
            "checks": [
                {
                    "check": "CONTRADICTIONS_FOUND",
                    "status": "PASS",
                    "details": [{"expected": "Rev B validation passed", "similarity": 0.8, "matched": "text"}],
                },
                {"check": "NO_PROHIBITED", "status": "PASS", "details": []},
            ],
        }
    ],
}


@pytest.mark.db
def test_the_latest_recorded_evaluation_is_shown_on_the_trust_page():
    db = SessionLocal()
    try:
        run_id = record_run(db, REPORT, datetime.now(timezone.utc))
    finally:
        db.close()
    try:
        body = authenticated_client().get("/api/v1/evaluations/golden/latest").json()
        assert body["status"] == "AVAILABLE"
        evaluation = body["evaluation"]
        assert (evaluation["passed"], evaluation["total"]) == (9, 12)
        assert (evaluation["passed_with_specific_expectations"], evaluation["with_specific_expectations"]) == (1, 4)
        scenario = evaluation["scenarios"][0]
        assert scenario["written_by"] == "LANGUAGE_MODEL" and scenario["specific_expectations"] == 6
        assert scenario["checks"][0]["matches"] == [{"expected": "Rev B validation passed", "similarity": 0.8}]
        assert "Synthetic" in evaluation["data_notice"]
    finally:
        db = SessionLocal()
        db.query(EvaluationRun).filter(EvaluationRun.id == run_id).delete()
        db.commit()
        db.close()


def test_the_evaluation_needs_a_signed_in_user():
    assert TestClient(app).get("/api/v1/evaluations/golden/latest").status_code == 401
