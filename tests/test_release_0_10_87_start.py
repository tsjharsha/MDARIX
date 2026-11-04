"""0.10.87: Getting started v2 (the owner's specification, 5 Nov 2026). The walkthrough card's complaint summary reads
the product's name, the harm the record states and the service status from the story itself; harm the record does not
state is said as not recorded, never as "None reported".

Each test fails on the code before the change.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.app.trial.one_story import reported_harm
from tests.test_free_trial import _approved_trial_client
from tests.test_release_c3_0_10_75 import _purge

STORY = "/api/v1/trial/one-story"

# A complaint whose file leaves the harm columns empty.
BLANK_HARM = (
    "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
    "serious_injury,death,malfunction\n"
    "GS-3001,GS-PUMP,The pump alarmed during set-up.,,,,United States,,,,Y\n"
)


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.parametrize(
    ("death", "serious", "harm"),
    [
        (True, False, "DEATH"),
        (None, True, "SERIOUS_INJURY"),
        (False, False, "NONE"),
        (None, None, None),
        (False, None, None),
        (None, False, None),
    ],
)
def test_the_harm_is_what_the_record_states_and_unknown_stays_unknown(death, serious, harm):
    assert reported_harm(SimpleNamespace(death=death, serious_injury=serious)) == harm


@pytest.mark.db
def test_the_story_carries_the_product_name_the_harm_and_the_service_status():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        sample = _ok(user.get(STORY))["sample"]["complaint"]
        # SAMPLE-RV-11: no serious injury and no death, both stated; the monitor is in service.
        assert sample["ref"] == "SAMPLE-RV-11"
        assert sample["product_name"]
        assert sample["harm"] == "NONE"
        assert sample["service_status"] == "IN_PROGRESS"
        _ok(user.post("/api/v1/data/import/complaints?file_name=gs.csv", content=BLANK_HARM.encode()))
        yours = _ok(user.get(STORY))["yours"]["complaint"]
        assert yours["ref"] == "GS-3001"
        assert yours["harm"] is None
        assert yours["service_status"] is None
    finally:
        _purge(tenant_id)
