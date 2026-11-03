"""0.10.82, round D1 "One story" of the approved redesign.

- D1.1-D1.4: Getting started tells one complaint's story in ten steps, on the sample (SAMPLE-RV-11) and then on the
  trial's own most urgent imported complaint (the most serious harm, then the shortest clock). Each tick is read from
  the saved record or the person's own mark, never from the screen on show; a step a complaint cannot take yet says
  which fact the import lacks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from tests.report_fill import fill
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_release_c3_0_10_75 import _flagship, _purge, _reports, _sign_us

pytestmark = pytest.mark.db

STORY = "/api/v1/trial/one-story"
REPORTS = "/api/v1/reports"


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def _done(run: dict) -> list[str]:
    return [step["key"] for step in run["steps"] if step["done"]]


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def test_the_sample_story_ticks_each_step_from_the_saved_record(trial):
    user = trial["user"]
    first = _ok(user.get(STORY))
    sample = first["sample"]
    assert sample["complaint"]["ref"] == "SAMPLE-RV-11" and sample["market"] == "US"
    assert [step["label"] for step in sample["steps"]] == [
        "The call",
        "Triage",
        "Tree",
        "Reportable?",
        "Form",
        "Fill",
        "Approval",
        "Submit",
        "Records",
        "Trends",
    ]
    # Nothing imported yet: no second run.
    assert (first["yours"], sample["current"], _done(sample)) == (None, 0, [])
    # Opening a later step's screen ticks nothing ahead of the record: Trends is marked, Records is not done
    # until a submission is recorded.
    _ok(user.post(f"{STORY}/marks", json={"run": "sample", "step": "records"}))
    after = _ok(user.post(f"{STORY}/marks", json={"run": "sample", "step": "trends"}))["sample"]
    assert _done(after) == ["trends"] and after["current"] == 0
    # Step 1 is the person's own mark; step 2 is the triage record.
    assert _done(_ok(user.post(f"{STORY}/marks", json={"run": "sample", "step": "call"}))["sample"])[:1] == ["call"]
    complaint = _flagship(user)
    run = _ok(user.get(STORY))["sample"]
    assert _done(run) == ["call", "triage", "trends"] and run["current"] == 2
    # Steps 3 and 4: signing the US conclusion "reportable" (the report is created with it).
    _ok(_sign_us(user, complaint, "REPORTABLE"))
    run = _ok(user.get(STORY))["sample"]
    assert run["conclusion"] == "REPORTABLE" and run["report_id"] and run["current"] == 4
    # Step 5 waits for the person to open the report; steps 6 to 8 follow its status path.
    run = _ok(user.post(f"{STORY}/marks", json={"run": "sample", "step": "form"}))["sample"]
    assert run["current"] == 5
    (report,) = _reports(user, complaint)
    fill(user, REPORTS, report["id"], _ok(user.get(f"{REPORTS}/{report['id']}"))["mandatory"]["missing"])
    assert _ok(user.get(STORY))["sample"]["current"] == 6
    pending = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots"))["pending_snapshot"]["id"]
    _ok(user.post(f"{REPORTS}/{report['id']}/snapshots/{pending}/approve", json={"password": PASSWORD}))
    assert _ok(user.get(STORY))["sample"]["current"] == 7
    _ok(
        user.post(
            f"{REPORTS}/{report['id']}/submissions",
            json={
                "route": "EMDR",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "no_differences": True,
                "content_note": "As approved.",
            },
        )
    )
    run = _ok(user.get(STORY))["sample"]
    # Records was opened before the submission: it counts now that the submission is recorded.
    assert run["current"] == 10 and run["finished"] and all(step["done"] for step in run["steps"])


CSV = (
    "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
    "serious_injury,death,malfunction\n"
    "OS-1001,OS-NEB,Stopped misting after five minutes; no harm.,2026-10-28,2026-10-29,2026-10-29,US,N,N,N,Y\n"
    "OS-1002,OS-NEB,The casing overheated and burned the child's hand.,2026-10-30,,,,Y,Y,N,Y\n"
)


def test_your_data_runs_on_the_most_serious_complaint_and_says_what_the_file_did_not_give():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _ok(user.post("/api/v1/data/import/complaints?file_name=own.csv", content=CSV.encode()))
        yours = _ok(user.get(STORY))["yours"]
        # The serious injury outranks the earlier malfunction, though it has no country and no awareness date.
        assert yours["complaint"]["ref"] == "OS-1002" and yours["market"] is None
        assert {need["fact"] for need in yours["needs"]} == {"COUNTRY", "AWARENESS_DATE"}
        assert yours["current"] == 0 and not yours["finished"]
        # The sample run is apart: its marks are not this run's.
        _ok(user.post(f"{STORY}/marks", json={"run": "yours", "step": "call"}))
        both = _ok(user.get(STORY))
        assert _done(both["yours"]) == ["call"] and _done(both["sample"]) == []
    finally:
        _purge(tenant_id)


def test_the_story_rules_skip_the_report_steps_after_a_signed_not_reportable_conclusion():
    from types import SimpleNamespace

    from backend.app.trial.one_story import steps_done

    signed = SimpleNamespace(signed_at=datetime.now(timezone.utc), superseded_by=None, conclusion="NOT_REPORTABLE")
    done = steps_done({"call": "x", "records": "x"}, True, [signed], None)
    assert done == [True, True, True, True, "skip", "skip", "skip", "skip", True, False]
    # A draft only: the tree is answered, nothing is signed, the report steps wait.
    draft = SimpleNamespace(signed_at=None, superseded_by=None, conclusion=None)
    assert steps_done({}, True, [draft], None)[:5] == [True, True, True, False, False]
