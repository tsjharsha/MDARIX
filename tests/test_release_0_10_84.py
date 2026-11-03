"""0.10.84: the independent rating's defects on the combined D1 (0.10.82) and D2 (0.10.83) build.

Each test fails on the code before its fix.
"""

from __future__ import annotations

import uuid

import pytest

from tests.test_free_trial import _approved_trial_client
from tests.test_release_c3_0_10_75 import _purge

pytestmark = pytest.mark.db

STORY = "/api/v1/trial/one-story"

# FIC-2001 as the rating imported it: a serious injury with no country and no dates.
FIC = (
    "complaint_id,product_id,description,event_date,received_date,awareness_date,country,patient_involved,"
    "serious_injury,death,malfunction\n"
    "FIC-2001,FIC-PUMP,The pump over-infused and the patient was admitted to intensive care.,,,,,Y,Y,N,Y\n"
)


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture()
def fic():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _ok(user.post("/api/v1/data/import/complaints?file_name=fic.csv", content=FIC.encode()))
        complaint_id = _ok(user.get("/api/v1/oversight/events/FIC-2001"))["event"]["complaint_id"]
        yield {"user": user, "tenant_id": tenant_id, "complaint_id": complaint_id}
    finally:
        _purge(tenant_id)


def _triage_row(user, complaint_id: str) -> dict:
    (row,) = [
        item
        for item in _ok(user.get("/api/v1/triage", params={"show": "all"}))["items"]
        if f"COMPLAINT:{complaint_id}" in item["members"]
    ]
    return row


def test_once_the_country_is_known_the_header_clock_is_that_markets_deadline(fic):
    """H3: FIC-2001 with no country read "Shortest possible: … Mon 9 Nov" (Great Britain's clock). Once the country is
    entered as the United States, the header names the US clock, the deadline its triage table gives the US, and Home
    says the same: one calculation."""
    user, complaint_id = fic["user"], fic["complaint_id"]
    _ok(user.put(f"/api/v1/complaints/{complaint_id}/reporting-facts", json={"country": "United States"}))
    event = _ok(user.get("/api/v1/oversight/events/FIC-2001"))
    (header,) = [item for item in event["work"]["due"] if item["key"].endswith(":facts")]
    (us,) = [deadline for deadline in _triage_row(user, complaint_id)["deadlines"] if deadline["own"]]
    assert us["market"] == "US" and event["event"]["market"] == "US"
    # The US clock, still provisional while the awareness date is asked: no market on the line (0.10.81 F4), the
    # complaint's own market beside it names it ("United States, provisional").
    assert (header["market"], header["due_at"]) == (None, us["due_at"])
    assert header["title"].startswith("Enter the awareness date")
    home = _ok(user.get("/api/v1/oversight", params={"show": "all"}))["items"]
    (line,) = [item for item in home if item["key"] == f"watch:{complaint_id}:facts"]
    assert line["due_at"] == us["due_at"]
    # Not the shortest of every market any more (Great Britain's 10 days): the US clock is later.
    assert header["due_at"] > min(d["due_at"] for d in _triage_row(user, complaint_id)["deadlines"] if d["due_at"])


def test_a_complaint_waiting_for_its_country_never_says_no_market_to_assess(fic):
    """M2: FIC-2001's page asked for the country while its details said "Decision path: No market to assess"."""
    import json

    event = _ok(fic["user"].get("/api/v1/oversight/events/FIC-2001"))
    assert "No market to assess" not in json.dumps(event)
    (group,) = [group for group in event["related"] if group["key"] == "assessments"]
    assert group["lines"] == ["Waits for the incident country, asked on the complaint's page"]


def test_the_story_names_its_products_identifier_so_step_10_opens_your_own_trend(fic):
    """M4: Your data's step 10 opened the sample's OrbitCare rise; the story now carries each run's product identifier,
    which the trend check opens on."""
    story = _ok(fic["user"].get(STORY))
    assert story["yours"]["complaint"]["ref"] == "FIC-2001"
    assert story["yours"]["complaint"]["product_ref"] == "FIC-PUMP"
    assert story["sample"]["complaint"]["product_ref"].startswith("SAMPLE-")


def test_home_can_tell_the_samples_trends_and_lists_from_your_data(fic):
    """M5: on Your data, Home's Overdue tile counted SAMPLE-RV-08 and its trend card showed the sample's OrbitCare.
    The tiles read the complaint list views with the data's source, and each trend row names its product's own
    identifier, so Home keeps the sample's apart."""
    user = fic["user"]
    overdue = {"view": "overdue", "page": 1, "page_size": 200}
    sample = _ok(user.get("/api/v1/complaints", params={**overdue, "source_system": "MDARIX_SAMPLE"}))["items"]
    yours = _ok(user.get("/api/v1/complaints", params={**overdue, "source_system": "TRIAL_UPLOAD"}))["items"]
    assert any(row["complaint_identifier"].startswith("SAMPLE-") for row in sample)
    assert not any(row["complaint_identifier"].startswith("SAMPLE-") for row in yours)
    board = _ok(user.get("/api/v1/triage/trends", params={"group": "version"}))["items"]
    assert board and all(row["product"]["identifier"] for row in board)
    assert any(row["product"]["identifier"] == "SAMPLE-ORBIT-300" for row in board)


def test_the_story_is_the_teams_one_step_for_every_colleague():
    """M6: Rahul's banner said "Step 5 of 10: Form" while the shared record was at the approval step, because opening
    the report was Asha's own mark. The story is the team's: a step any colleague opened counts for everyone."""
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from tests.test_free_trial import PASSWORD, _activation_token

    owner, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        mail = f"m6-{uuid.uuid4().hex[:6]}@example.invalid"
        invited = _ok(
            owner.post(
                "/api/v1/trial/team", json={"email": mail, "display_name": "Rahul Iyer", "persona": "regulatory"}
            )
        )
        colleague = TestClient(app)
        _ok(
            colleague.post(
                "/api/v1/auth/activate-account", json={"token": _activation_token(invited, mail), "password": PASSWORD}
            )
        )
        _ok(colleague.post("/api/v1/auth/signin", json={"email": mail, "password": PASSWORD}))
        _ok(owner.post(f"{STORY}/marks", json={"run": "sample", "step": "call"}))
        _ok(colleague.post(f"{STORY}/marks", json={"run": "sample", "step": "trends"}))
        mine, theirs = _ok(owner.get(STORY))["sample"], _ok(colleague.get(STORY))["sample"]
        done = lambda run: [step["key"] for step in run["steps"] if step["done"]]  # noqa: E731
        assert done(mine) == done(theirs) == ["call", "trends"]
        assert mine["current"] == theirs["current"] == 1
    finally:
        _purge(tenant_id)


def test_every_deadline_a_person_reads_is_in_the_organizations_time_zone(fic):
    """The same clock read "EST" on the complaint page and "GMT" in its triage table. Every deadline label is now
    written in the organization's time zone (Settings' working calendar), whichever market's it is."""
    from backend.app.db.session import SessionLocal
    from backend.app.reportability import deadlines

    user, complaint_id = fic["user"], fic["complaint_id"]
    db = SessionLocal()
    try:
        zone = deadlines.org_zone(db, fic["tenant_id"])
    finally:
        db.close()
    row = _triage_row(user, complaint_id)
    event = _ok(user.get("/api/v1/oversight/events/FIC-2001"))
    labels = [d["due_label"] for d in row["deadlines"] if d["due_label"]] + [
        item["due_label"] for item in event["work"]["due"]
    ]
    from datetime import datetime

    for deadline in [d for d in row["deadlines"] if d["due_at"]]:
        at = datetime.fromisoformat(deadline["due_at"])
        assert deadline["due_label"] == deadlines.moment_label(at, zone)
    suffixes = {label.rsplit(" ", 1)[1] for label in labels}
    assert len(suffixes) == 1, labels
    (header,) = [item for item in event["work"]["due"] if item["key"].endswith(":facts")]
    earliest = min((d for d in row["deadlines"] if d["due_at"]), key=lambda d: d["due_at"])
    assert header["due_label"] == earliest["due_label"]


def test_an_import_run_keeps_the_products_its_complaints_created(fic):
    """L1: after a complaints import that created its product, Import's checklist still said "Products and versions:
    not loaded". The run's report keeps what it created, so the checklist counts it."""
    (run,) = [run for run in _ok(fic["user"].get("/api/v1/data/import/runs"))["runs"] if not run["sample"]]
    assert run["entity"] == "complaints" and run["report"]["also_created"] == {"products": 1}


def test_a_signed_conclusion_names_who_signed_it_on_the_record(fic):
    """M4 follow-up: Records' finished record listed "United States (FDA): Reportable, signed <day>" and nothing under
    who signed (a conclusion is not a disposition or a report approval). The conclusion's line names its signer."""
    from tests.test_release_c3_0_10_75 import _flagship, _sign_us

    user = fic["user"]
    complaint = _flagship(user)
    _ok(_sign_us(user, complaint, "REPORTABLE"))
    me = _ok(user.get("/api/v1/session/context"))["display_name"]
    related = {g["key"]: g for g in _ok(user.get("/api/v1/oversight/events/SAMPLE-RV-11"))["related"]}
    (line,) = related["assessments"]["lines"][:1]
    assert line.startswith("United States (FDA): Reportable, signed") and line.endswith(f" by {me}")


def test_the_report_approval_reasons_say_report_not_snapshot():
    """D2's miss: the report page's Next step said "a second person must approve the snapshot"."""
    from backend.app.authority_reports.rules import approver_problem

    reasons = [
        approver_problem("u1", "LEADER", {"u1"}, None),
        approver_problem("u2", "LEADER", {"u1"}, "u2"),
        approver_problem("u3", "ADMINISTRATOR", set(), None),
    ]
    assert all(reason and "snapshot" not in reason for reason in reasons), reasons
    assert reasons[0] == "You prepared this report: a second person must approve it"
