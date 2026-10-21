"""DEV-027: Platform Admin > Onboarding shows who approved or declined a trial request (a Platform Administrator, or
the automatic approval for a company email), with the request's recorded legal acceptance."""

from backend.app.db.models.foundation import AuthUser
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.trial import auto_approval
from tests.conftest import authenticated_client
from tests.test_free_trial import _platform_organization, _request_id, _request_trial


def _queued(admin, email: str) -> dict:
    items = admin.get("/api/v1/platform-admin/trial-requests", params={"q": email}).json()["items"]
    return next(item for item in items if item["email"] == email)


def test_the_queue_names_who_reviewed_each_request():
    admin = authenticated_client()
    pending, approved, declined = _request_trial(), _request_trial(), _request_trial()
    assert _queued(admin, pending)["reviewed_by_name"] is None
    assert (
        admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, approved)}/approve").status_code == 200
    )
    refused = admin.post(
        f"/api/v1/platform-admin/trial-requests/{_request_id(admin, declined)}/decline",
        json={"reason": "Not a medical device company"},
    )
    assert refused.status_code == 200, refused.text
    with SessionLocal() as db:
        bind_system(db, "test: the reviewer's name")
        reviewer = db.get(
            AuthUser, db.query(OnboardingRequest).filter(OnboardingRequest.email == approved).one().reviewed_by
        )
        name = reviewer.display_name
    for email in (approved, declined):
        item = _queued(admin, email)
        assert item["reviewed_by_name"] == name and item["reviewed_at"]
    # The legal acceptance stays as recorded, with each text's full fingerprint and the time.
    acceptance = _queued(admin, approved)["legal_acceptance"]
    assert acceptance["accepted_at"]
    assert all(len(text["sha256"]) == 64 for text in acceptance["documents"].values() if text["available"])


def test_the_automatic_approval_is_named_as_such():
    """The automatic approval is made by the platform's own account (auto_approval._approver), so the queue reads its
    name; its sign-up path is tested in test_free_trial."""
    _platform_organization()
    admin = authenticated_client()
    email = _request_trial()
    with SessionLocal() as db:
        bind_system(db, "test: an automatic approval")
        row = db.query(OnboardingRequest).filter(OnboardingRequest.email == email).one()
        row.reviewed_by = auto_approval._approver(db).id
        db.commit()
    assert _queued(admin, email)["reviewed_by_name"] == "Automatic approval (company email)"
