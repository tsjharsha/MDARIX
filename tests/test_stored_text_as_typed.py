"""H1 item 4, server side: text with markup is stored and returned exactly as typed. Escaping is the screens' job
(frontend storedXss.test.tsx); the API neither strips nor encodes it, so nothing a person wrote is lost or changed."""

import uuid

import pytest

from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)
from tests.test_intake_triage_api import INTAKE, _all_no, _ok

pytestmark = pytest.mark.db

HOSTILE = '<img src=x onerror="alert(1)"><script>alert(2)</script><a href="javascript:alert(3)">x</a> & &amp;'
CELL = '"' + HOSTILE.replace('"', '""') + '"'  # one CSV cell


def _import(user, entity: str, csv: str) -> None:
    response = user.post(
        f"/api/v1/trial/imports/{entity}",
        params={"date_column": "none"},
        content=csv,
        headers={"Content-Type": "text/csv"},
    )
    assert response.status_code == 200, response.text


def test_markup_is_stored_and_returned_as_typed():
    user, _, _ = _approved_trial_client()
    tag = uuid.uuid4().hex[:6].upper()

    # A complaint's words typed on Log a case.
    event = _ok(user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": HOSTILE, "answers": _all_no()}))
    assert event["reporter_words"] == HOSTILE
    assert _ok(user.get(f"{INTAKE}/{event['id']}"))["reporter_words"] == HOSTILE

    # Imported complaint fields: its description and product name, on the complaint page.
    _import(
        user,
        "complaints",
        f"complaint_id,product_id,product_name,description\nX{tag}-1,X{tag}-PUMP,{CELL},{CELL}\n",
    )
    page = _ok(user.get(f"/api/v1/oversight/events/X{tag}-1"))
    assert page["event"]["description"] == HOSTILE and page["event"]["product"] == HOSTILE

    # An imported evidence record's name and description.
    _import(user, "evidence", f"evidence_id,title,evidence_type,content\nE{tag},{CELL},Test result,{CELL}\n")
    found = [
        item
        for item in _ok(user.get("/api/v1/evidence", params={"limit": 200}))
        if item["evidence_identifier"] == f"E{tag}"
    ]
    assert [item["title"] for item in found] == [HOSTILE]
    assert _ok(user.get(f"/api/v1/evidence/{found[0]['id']}/content"))["content"] == HOSTILE
