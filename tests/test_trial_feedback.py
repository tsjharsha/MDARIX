"""Trial feedback: a trial user answers the questionnaire and chooses how their words may be shown on the website."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role
from tests.test_free_trial import PASSWORD, _activation_token, _request_id, _request_trial


@pytest.fixture(autouse=True, scope="module")
def _remove_test_feedback():
    """Feedback from these tests (companies ending in " fbt") never stays on the shared test database's website."""
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM trial_feedback WHERE organization_name LIKE '% fbt'"))


def _trial_user(organization: str) -> TestClient:
    admin = authenticated_client()
    email = _request_trial(organization)
    approval = admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve")
    assert approval.status_code == 200, approval.text
    user = TestClient(app)
    token = _activation_token(approval.json(), email)
    assert user.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}).status_code == 200
    assert user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200
    return user


def _answers(**fields):
    return {
        "role_area": "QUALITY",
        "job_title": "Director of Quality",
        "rating_overall": 5,
        "rating_ease": 4,
        "rating_ai_trust": 5,
        "recommend_score": 9,
        "features_used": ["PRODUCT_360", "ASK_MDARIX"],
        "liked": "Every answer cites its evidence.",
        "improve": "Faster CSV import.",
        "adoption": "YES",
        "quote": "We traced a complaint trend to one supplier lot in an afternoon.",
        "publish_consent": "NAMED",
        "contact_ok": True,
        **fields,
    }


def _published() -> list:
    return TestClient(app).get("/api/v1/public/testimonials").json()["items"]


def test_feedback_is_for_trial_workspaces_only():
    assert TestClient(app).get("/api/v1/trial/feedback").status_code == 401
    regular = _client_with_role("INVESTIGATOR")
    assert regular.get("/api/v1/trial/feedback").status_code == 404
    assert regular.post("/api/v1/trial/feedback", json=_answers()).status_code == 404


def test_named_feedback_is_shown_with_the_company_only_after_review():
    company = f"Zephyr Valve {uuid.uuid4().hex[:6]} fbt"
    user = _trial_user(company)
    form = user.get("/api/v1/trial/feedback").json()
    assert form["organization_name"] == company
    assert company in form["consent_wording"]["NAMED"]

    sent = user.post("/api/v1/trial/feedback", json=_answers())
    assert sent.status_code == 200, sent.text
    assert sent.json()["publication_status"] == "PENDING"
    quote = _answers()["quote"]
    assert all(item["quote"] != quote for item in _published())  # nothing is public before review

    admin = authenticated_client()
    listed = admin.get("/api/v1/platform-admin/feedback").json()
    item = next(i for i in listed["items"] if i["id"] == sent.json()["id"])
    assert item["consent_text"] == form["consent_wording"]["NAMED"] and item["contact_ok"] is True
    assert listed["summary"]["responses"] >= 1 and listed["summary"]["nps"] is not None

    assert (
        admin.post(f"/api/v1/platform-admin/feedback/{item['id']}/publication", json={"action": "PUBLISH"}).status_code
        == 200
    )
    shown = next(i for i in _published() if i["quote"] == quote)
    assert shown["attribution"] == f"Director of Quality, {company}"

    # Withdrawing consent takes it off the website at once.
    withdrawn = user.post(f"/api/v1/trial/feedback/{item['id']}/withdraw-consent")
    assert withdrawn.status_code == 200 and withdrawn.json()["publish_consent"] == "PRIVATE"
    assert all(i["quote"] != quote for i in _published())
    refused = admin.post(f"/api/v1/platform-admin/feedback/{item['id']}/publication", json={"action": "PUBLISH"})
    assert refused.status_code == 409


def test_anonymous_feedback_never_shows_the_company():
    company = f"Quillon Instruments {uuid.uuid4().hex[:6]} fbt"
    user = _trial_user(company)
    naming = user.post(
        "/api/v1/trial/feedback",
        json=_answers(publish_consent="ANONYMOUS", quote="Quillon cut our investigation time in half."),
    )
    assert naming.status_code == 422 and naming.json()["detail"]["code"] == "FEEDBACK_QUOTE_NAMES_COMPANY"

    quote = f"Investigation time cut in half ({uuid.uuid4().hex[:6]})."
    sent = user.post("/api/v1/trial/feedback", json=_answers(publish_consent="ANONYMOUS", quote=quote))
    assert sent.status_code == 200, sent.text
    admin = authenticated_client()
    assert (
        admin.post(
            f"/api/v1/platform-admin/feedback/{sent.json()['id']}/publication", json={"action": "PUBLISH"}
        ).status_code
        == 200
    )
    shown = next(i for i in _published() if i["quote"] == quote)
    assert company.split()[0] not in shown["attribution"] and "Director" not in shown["attribution"]
    assert shown["attribution"] == "Quality lead, medical-device company"


def test_private_feedback_cannot_be_published_and_quote_is_needed_to_publish():
    user = _trial_user(f"Corvant Labs {uuid.uuid4().hex[:6]} fbt")
    assert user.post("/api/v1/trial/feedback", json=_answers(quote=" ")).status_code == 422
    private = user.post("/api/v1/trial/feedback", json=_answers(publish_consent="PRIVATE", quote=None))
    assert private.status_code == 200 and private.json()["publication_status"] == "NOT_REQUESTED"
    admin = authenticated_client()
    response = admin.post(
        f"/api/v1/platform-admin/feedback/{private.json()['id']}/publication", json={"action": "PUBLISH"}
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "FEEDBACK_NOT_CONSENTED"


def test_answers_outside_the_lists_are_refused_and_only_platform_admins_review():
    user = _trial_user(f"Merrow Fluidics {uuid.uuid4().hex[:6]} fbt")
    assert user.post("/api/v1/trial/feedback", json=_answers(rating_overall=6)).status_code == 422
    assert user.post("/api/v1/trial/feedback", json=_answers(features_used=["DROP TABLE"])).status_code == 422
    assert user.post("/api/v1/trial/feedback", json=_answers(role_area="CEO")).status_code == 422
    assert user.get("/api/v1/platform-admin/feedback").status_code == 403


def test_a_person_cannot_withdraw_someone_elses_feedback():
    owner = _trial_user(f"Talbrook Medical {uuid.uuid4().hex[:6]} fbt")
    other = _trial_user(f"Ostend Surgical {uuid.uuid4().hex[:6]} fbt")
    sent = owner.post("/api/v1/trial/feedback", json=_answers()).json()
    assert other.post(f"/api/v1/trial/feedback/{sent['id']}/withdraw-consent").status_code == 404
    with engine.connect() as conn:
        consent = conn.execute(
            text("SELECT publish_consent FROM trial_feedback WHERE id = :id"), {"id": sent["id"]}
        ).scalar_one()
    assert consent == "NAMED"
