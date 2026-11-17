"""Review P6: a Platform Administrator's approval can answer at once and run right after the answer, with the same
all-or-nothing result as the click that waits."""

import pytest

from backend.app.db.models.foundation import AuthUser
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.trial.sample_data import SAMPLE_SOURCE
from tests.conftest import authenticated_client
from tests.test_free_trial import _request_id, _request_trial

pytestmark = pytest.mark.db


def test_a_background_approval_answers_202_then_approves_with_the_sample():
    from backend.app.db.models.foundation import Complaint
    from backend.app.trial.retention import purge_trial

    admin = authenticated_client()
    email = _request_trial()
    request_id = _request_id(admin, email)
    answer = admin.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve", params={"background": "true"})
    assert answer.status_code == 202 and answer.json()["status"] == "APPROVING", answer.text
    # The test client runs the response's background work before it returns: the approval is done now.
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.query(OnboardingRequest).filter(OnboardingRequest.id == request_id).one()
        assert row.status == "APPROVED" and row.tenant_id is not None
        owner = db.query(AuthUser).filter(AuthUser.username == email).one()
        assert owner.status == "INVITED"
        assert (
            db.query(Complaint)
            .filter(Complaint.tenant_id == row.tenant_id, Complaint.source_system == SAMPLE_SOURCE)
            .count()
        )
        tenant_id = row.tenant_id
    again = admin.post(f"/api/v1/platform-admin/trial-requests/{request_id}/approve", params={"background": "true"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "TRIAL_REQUEST_ALREADY_REVIEWED"
    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:background-approval-cleanup")
