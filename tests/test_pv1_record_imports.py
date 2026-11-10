"""PV-1 (0.10.95): an investigation links complaints of its own product and keeps its product, a CAPA's product is its
investigation's (F8), and a re-upload that changes a risk's version leaves a field-change row (F7)."""

import uuid

import pytest

from backend.app.db.models.intake import RecordFieldChange
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

pytestmark = pytest.mark.db

IMPORTS = "/api/v1/trial/imports"


def _post(user, entity: str, csv: str, check: bool = False):
    path = f"{IMPORTS}/{entity}/check" if check else f"{IMPORTS}/{entity}"
    return user.post(path, params={"date_column": "none"}, content=csv, headers={"Content-Type": "text/csv"})


def _ok(user, entity: str, csv: str) -> dict:
    response = _post(user, entity, csv)
    assert response.status_code == 200, response.text
    return response.json()


def _issues(user, entity: str, csv: str) -> list[tuple[str, str]]:
    response = _post(user, entity, csv, check=True)
    assert response.status_code == 200, response.text
    return [(issue["column"], issue["message"]) for issue in response.json()["issues"]]


@pytest.fixture
def loaded():
    user, _, _ = _approved_trial_client()
    t = uuid.uuid4().hex[:6].upper()
    _ok(
        user,
        "complaints",
        "complaint_id,product_id,product_name,version,description\n"
        f"R{t}-1,R{t}-PUMP,PV Pump,Rev A,Alarm at start-up\n"
        f"R{t}-2,R{t}-PUMP,PV Pump,Rev B,Alarm at start-up\n"
        f"R{t}-9,R{t}-OTHER,Other Pump,Rev X,Battery\n",
    )
    _ok(
        user,
        "investigations",
        f"investigation_id,product_id,question,complaint_ids\nI{t},R{t}-PUMP,Why the alarm?,R{t}-1\n",
    )
    return user, t


def test_an_investigation_links_only_complaints_of_its_product_and_keeps_it(loaded):  # F8, F7
    user, t = loaded
    head = "investigation_id,product_id,question,complaint_ids\n"
    issues = _issues(user, "investigations", head + f"I{t}-2,R{t}-PUMP,Why?,R{t}-9\n")
    assert issues and issues[0][0] == "complaint_ids" and f"R{t}-9" in issues[0][1]
    issues = _issues(user, "investigations", head + f"I{t},R{t}-OTHER,Why the alarm?,\n")
    assert issues and issues[0][0] == "product_id" and "held for another product" in issues[0][1]


def test_a_capa_is_for_its_investigations_product(loaded):  # F8
    user, t = loaded
    issues = _issues(user, "capas", f"capa_id,title,product_id,investigation_id\nC{t},Fix,R{t}-OTHER,I{t}\n")
    assert issues and issues[0][0] == "product_id"
    assert _ok(user, "capas", f"capa_id,title,product_id,investigation_id\nC{t},Fix,R{t}-PUMP,I{t}\n")["created"] == 1


def test_a_risk_version_change_by_reupload_is_recorded(loaded):  # F7
    user, t = loaded
    head = "risk_id,product_id,description,version\n"
    _ok(user, "risks", head + f"K{t},R{t}-PUMP,Delayed therapy,Rev A\n")
    _ok(user, "risks", head + f"K{t},R{t}-PUMP,Delayed therapy,Rev B\n")
    with SessionLocal() as db:
        bind_system(db, "test: read the field changes")
        rows = db.query(RecordFieldChange).filter(RecordFieldChange.record_key == f"K{t}").all()
    assert [(row.entity, row.field) for row in rows] == [("risks", "product_version_id")]
    assert rows[0].before and rows[0].after and rows[0].before != rows[0].after
