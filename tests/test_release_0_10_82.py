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
        "Call",
        "Triage",
        "Tree",
        "Decide",
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
    # 0.10.85: a step opened out of order is not ticked ahead of the story; it is flagged "done earlier".
    assert _done(after) == [] and after["current"] == 0
    assert [step["key"] for step in after["steps"] if step["earlier"]] == ["trends"]
    # Step 1 is the person's own mark; step 2 is the triage record.
    assert _done(_ok(user.post(f"{STORY}/marks", json={"run": "sample", "step": "call"}))["sample"])[:1] == ["call"]
    complaint = _flagship(user)
    run = _ok(user.get(STORY))["sample"]
    assert _done(run) == ["call", "triage"] and run["current"] == 2
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


def test_home_tiles_are_the_counts_of_the_lists_they_open_and_open_complaints_are_most_urgent_first(trial):
    """D1.6 and U-08: "Overdue" is a list view, so the tile and the list are one number; "All open complaints" lists
    the overdue first, then the nearest clock, the undated last."""
    user = trial["user"]
    listed = _ok(user.get("/api/v1/complaints", params={"view": "open", "work": "true", "page_size": 200}))["items"]
    nearest = [(item["work"]["due"] or [None])[0] for item in listed]
    dated = [due["due_at"] for due in nearest if due]
    assert dated and dated == sorted(dated)
    # Every dated complaint comes before every undated one.
    assert all(due for due in nearest[: len(dated)]) and not any(nearest[len(dated) :])
    overdue = {item["id"] for item in listed if any(due["state"] == "OVERDUE" for due in item["work"]["due"])}
    tile = _ok(user.get("/api/v1/complaints", params={"view": "overdue", "page": 1, "page_size": 200}))
    assert overdue and tile["total"] == len(overdue) == len({item["id"] for item in tile["items"]} & overdue)


def test_the_complaint_page_gives_the_harm_in_words_apart_from_patient_involvement(trial):
    """D1.7, U-18: "Patient involved" is never the harm; a blank serious-injury flag is "Not known yet"."""
    from types import SimpleNamespace

    from backend.app.oversight.router import harm_words

    event = _ok(trial["user"].get("/api/v1/oversight/events/SAMPLE-RV-11"))["event"]
    assert (event["harm_words"], event["patient_involved"]) == ("No harm reported", True)
    flags = [(True, None), (None, True), (None, None), (False, False)]
    assert [harm_words(SimpleNamespace(death=d, serious_injury=s)) for d, s in flags] == [
        "Death",
        "Serious injury",
        "Not known yet",
        "No harm reported",
    ]


def test_a_colleague_holds_several_personas_switches_between_them_and_never_approves_their_own_work():
    """D1.9: the owner ticks several personas; the colleague gets every matching role (rights add up), switches
    "Viewing as" only between their own, the owner can change the set later (audited before and after), and the
    colleague still never approves a report they prepared."""
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from tests.test_free_trial import _activation_token
    from tests.test_release_c3_0_10_75 import _audit

    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        mail = f"d19-{uuid.uuid4().hex[:6]}@example.invalid"
        invited = _ok(
            owner.post(
                "/api/v1/trial/team",
                json={"email": mail, "display_name": "Rahul Iyer", "personas": ["decision", "regulatory"]},
            )
        )
        assert invited["personas"] == ["regulatory", "decision"] and invited["role"] == "REGULATORY_REVIEWER"
        colleague = TestClient(app)
        _ok(
            colleague.post(
                "/api/v1/auth/activate-account", json={"token": _activation_token(invited, mail), "password": PASSWORD}
            )
        )
        _ok(colleague.post("/api/v1/auth/signin", json={"email": mail, "password": PASSWORD}))
        me = _ok(colleague.get("/api/v1/session/context"))
        assert [item["code"] for item in me["persona_options"]] == ["regulatory", "decision"]
        assert me["persona"] == "regulatory" and not me["persona_locked"]
        # Rights add up: the Regulatory Reviewer's review and the Approver's signature.
        assert {"regulatory.review", "decision.sign"} <= set(me["business_permissions"])
        # They switch between their own personas, never to one they do not hold.
        assert _ok(colleague.post("/api/v1/me/persona", json={"persona": "decision"}))["persona"] == "decision"
        assert colleague.post("/api/v1/me/persona", json={"persona": "quality"}).status_code == 403
        team = _ok(owner.get("/api/v1/trial/team"))
        member = next(item for item in team["members"] if item["email"] == mail)
        assert [item["code"] for item in member["personas"]] == ["regulatory", "decision"]
        # The owner changes the set later; it is audited before and after, and one persona is locked again.
        _ok(owner.post(f"/api/v1/trial/team/{invited['id']}/persona", json={"personas": ["handler"]}))
        last = [e for e in _audit(tenant_id, "TRIAL_PERSONA_ASSIGNED") if e.details.get("how") == "changed"][-1]
        assert last.old_values["personas"] == ["regulatory", "decision"] and last.new_values["personas"] == ["handler"]
        again = _ok(colleague.get("/api/v1/session/context"))
        assert again["persona"] == "handler" and again["persona_locked"]
        assert "decision.sign" not in again["business_permissions"]
        assert colleague.post("/api/v1/me/persona", json={"persona": "regulatory"}).status_code == 403
        # Back to Regulatory + Decision Maker: they prepare a report and may not approve it themselves while a
        # colleague may (alone in a trial, the practice approval of 0.10.75 still applies).
        _ok(owner.post(f"/api/v1/trial/team/{invited['id']}/persona", json={"personas": ["regulatory", "decision"]}))
        third = f"d19-b-{uuid.uuid4().hex[:6]}@example.invalid"
        other = _ok(
            owner.post("/api/v1/trial/team", json={"email": third, "display_name": "Meera Das", "persona": "decision"})
        )
        _ok(
            TestClient(app).post(
                "/api/v1/auth/activate-account", json={"token": _activation_token(other, third), "password": PASSWORD}
            )
        )
        complaint = _flagship(owner)
        _ok(_sign_us(owner, complaint, "REPORTABLE"))
        (report,) = _reports(owner, complaint)
        fill(colleague, REPORTS, report["id"], _ok(colleague.get(f"{REPORTS}/{report['id']}"))["mandatory"]["missing"])
        detail = _ok(colleague.post(f"{REPORTS}/{report['id']}/snapshots"))
        assert not detail["approval"]["may_approve"]
        refused = colleague.post(
            f"{REPORTS}/{report['id']}/snapshots/{detail['pending_snapshot']['id']}/approve",
            json={"password": PASSWORD},
        )
        assert refused.status_code == 403
    finally:
        _purge(tenant_id)


def test_one_drop_zone_detects_which_object_a_file_is_and_flags_what_it_did_not_give(trial):
    """D1.10: the detect read names the template a file fits (any of the 18 objects), and the check flags every fact
    the file leaves out, a blank serious-injury flag included, so it never reads as nothing missing."""
    user = trial["user"]
    detect = "/api/v1/data/import/detect"
    assert _ok(user.post(detect, content=CSV.encode()))["entity"] == "complaints"
    products = "product_id,product_name,version,product_family\nOS-NEB,BreezeMist 50,Rev B,Nebulisers\n"
    assert _ok(user.post(detect, content=products.encode()))["entity"] == "products"
    titled = "Batch register exported 2 Nov\n\nlot_id,product_id,version,manufacture_date,quantity\nL1,OS-NEB,Rev B,2026-01-01,10\n"
    assert _ok(user.post(detect, content=titled.encode()))["entity"] == "lots"
    assert _ok(user.post(detect, content=b"colour,size\nred,big\n"))["entity"] is None
    checked = _ok(user.post("/api/v1/data/import/complaints/check", content=CSV.encode()))
    flags = [flag["message"] for flag in checked["row_flags"] if flag["complaint_id"] == "OS-1002"]
    assert any("No country" in text for text in flags) and any("awareness" in text for text in flags)
    blank = CSV.replace("Y,Y,N,Y\n", "Y,,N,Y\n")
    flagged = _ok(user.post("/api/v1/data/import/complaints/check", content=blank.encode()))["row_flags"]
    assert any(flag["message"].startswith("Serious injury left blank") for flag in flagged)


def test_a_call_not_yet_a_complaint_opens_its_own_triage_card_from_home(trial):
    """Navigation M5 and U-20: SAMPLE-URG-01 is an urgent call; Home's next action opens its triage card by its
    reference, not the bare list, and its title says what to do without repeating codes."""
    items = _ok(trial["user"].get("/api/v1/oversight", params={"show": "all"}))["items"]
    calls = [item for item in items if item.get("ref") == "SAMPLE-URG-01" and item["key"].startswith("triage:")]
    assert calls and all(
        call["opens"]["tab"] == f"Triage?intake={call['opens']['target']['record']['id']}" for call in calls
    )
    assert all(call["title"].startswith("Triage not done yet (") for call in calls)


def test_the_shortest_possible_clock_is_the_earliest_deadline_the_triage_table_shows():
    """A complaint waiting for its country and awareness date: the complaint page's one clock line, Home's next action
    and the story's hero all read "shortest possible" from one calculation, the earliest per-market deadline of its
    triage table (GB's 10 days counted from the awareness day), never a later window's (0.10.82)."""
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _ok(user.post("/api/v1/data/import/complaints?file_name=own.csv", content=CSV.encode()))
        event = _ok(user.get("/api/v1/oversight/events/OS-1002"))
        complaint_id = event["event"]["complaint_id"]
        (header,) = [item for item in event["work"]["due"] if item["key"].endswith(":facts")]
        triage = _ok(user.get("/api/v1/triage", params={"show": "all"}))["items"]
        (row,) = [item for item in triage if f"COMPLAINT:{complaint_id}" in item["members"]]
        earliest = min((deadline for deadline in row["deadlines"] if deadline["due_at"]), key=lambda d: d["due_at"])
        # The same moment and day; each screen writes the time in its own zone (the organization's or the market's).
        assert header["due_at"] == earliest["due_at"]
        assert header["due_label"].split(",")[0] == earliest["due_label"].split(",")[0]
        home = _ok(user.get("/api/v1/oversight", params={"show": "all"}))["items"]
        (line,) = [item for item in home if item["key"] == f"watch:{complaint_id}:facts"]
        assert line["due_at"] == earliest["due_at"]
    finally:
        _purge(tenant_id)
