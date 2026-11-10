"""PV-1 (0.10.95): a complaints import keeps a complaint's version in step with its lot (F4), a blank version cell keeps
the stored version (F5), and a re-upload never moves a complaint to another product (F6)."""

import uuid

import pytest

from backend.app.db.models.foundation import Complaint, ProductVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

pytestmark = pytest.mark.db

UPLOAD = "/api/v1/trial/imports/complaints"
HEAD = "complaint_id,product_id,product_name,version,lot_id,description,event_date\n"


def _post(user, path: str, csv: str):
    return user.post(path, params={"date_column": "event_date"}, content=csv, headers={"Content-Type": "text/csv"})


def _upload(user, csv: str) -> dict:
    response = _post(user, UPLOAD, csv)
    assert response.status_code == 200, response.text
    return response.json()


def _issues(user, csv: str) -> list[tuple[str, str]]:
    response = _post(user, f"{UPLOAD}/check", csv)
    assert response.status_code == 200, response.text
    return [(issue["column"], issue["message"]) for issue in response.json()["issues"]]


def _version_of(identifier: str) -> str | None:
    with SessionLocal() as db:
        bind_system(db, "test: read the complaint")
        complaint = (
            db.query(Complaint)
            .filter(Complaint.complaint_identifier == identifier)
            .order_by(Complaint.created_at.desc())
            .first()
        )
        version = db.get(ProductVersion, complaint.product_version_id) if complaint.product_version_id else None
        return version.version_identifier if version else None


@pytest.fixture
def loaded():
    user, _, _ = _approved_trial_client()
    tag = uuid.uuid4().hex[:6].upper()
    _upload(
        user,
        HEAD + f"PV{tag}-1,PV{tag}-PUMP,PV Pump,Rev A,PV{tag}-LA,Alarm at start-up,2026-10-01\n"
        f"PV{tag}-2,PV{tag}-PUMP,PV Pump,Rev B,PV{tag}-LB,Door latch loose,2026-10-02\n"
        # A lot loaded without a version (its version is unknown), and a complaint on Rev A naming it.
        f"PV{tag}-3,PV{tag}-PUMP,PV Pump,,PV{tag}-LN,Screen flicker,2026-10-03\n"
        f"PV{tag}-4,PV{tag}-PUMP,PV Pump,Rev A,PV{tag}-LN,Screen flicker,2026-10-04\n"
        f"PV{tag}-5,PV{tag}-OTHER,Other Pump,Rev X,PV{tag}-LX,Battery,2026-10-05\n",
    )
    return user, tag


def test_a_version_other_than_its_lots_is_refused(loaded):  # F4
    user, tag = loaded
    issues = _issues(user, HEAD + f"PV{tag}-9,PV{tag}-PUMP,PV Pump,Rev B,PV{tag}-LA,Alarm,2026-10-06\n")
    assert issues and issues[0][0] == "version" and "is of version 'Rev A'" in issues[0][1]
    # A version the file would add is never the lot's either.
    issues = _issues(user, HEAD + f"PV{tag}-9,PV{tag}-PUMP,PV Pump,Rev Z,PV{tag}-LA,Alarm,2026-10-06\n")
    assert issues and issues[0][0] == "version"


def test_a_blank_version_cell_keeps_the_stored_version(loaded):  # F5
    user, tag = loaded
    assert _version_of(f"PV{tag}-4") == "Rev A"
    _upload(user, HEAD + f"PV{tag}-4,PV{tag}-PUMP,PV Pump,,PV{tag}-LN,Screen flicker,2026-10-04\n")
    assert _version_of(f"PV{tag}-4") == "Rev A"


def test_a_reupload_cannot_move_a_complaint_to_another_product(loaded):  # F6
    user, tag = loaded
    issues = _issues(user, HEAD + f"PV{tag}-1,PV{tag}-OTHER,Other Pump,Rev X,PV{tag}-LX,Alarm at start-up,2026-10-01\n")
    assert (
        "product_id",
        f"Complaint 'PV{tag}-1' is held for another product; a file cannot move it to 'PV{tag}-OTHER'.",
    ) in issues
