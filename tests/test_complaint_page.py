"""0.10.68, quality plan stage 7: one complaint's page (/app/complaints/<ref>) and the new navigation's lists.

- The page opens a complaint by the reference people read (the customer's own, else its MDARIX ID) and by its id
  (stage 6's links), never another organization's.
- For the sample's SAMPLE-RV-06, SAMPLE-RV-08 and SAMPLE-RV-11 the page shows the same deadline, owner, stage and next
  action as the complaint list, My work (the reminders) and Oversight. SAMPLE-URG-01 is an urgent intake, a call that is
  not a complaint yet: it has no complaint page, and its triage target is the same on Triage, Oversight and My work.
- Who signs each step is told before the work starts, and "Send to" puts a step in a signer's My work only.
- The Dismissed view lists only the records decided as not complaints.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

EVENTS = "/api/v1/oversight/events"
SAMPLE = ("SAMPLE-RV-06", "SAMPLE-RV-08", "SAMPLE-RV-11")


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:complaint-page-cleanup")


def _complaint(tenant_id, ref: str) -> Complaint:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == ref).one()


@pytest.mark.db
def test_a_complaint_opens_by_its_reference_its_mdarix_id_and_its_id(trial):
    user = trial["user"]
    row = _complaint(trial["tenant_id"], "SAMPLE-RV-06")
    by_ref = user.get(f"{EVENTS}/SAMPLE-RV-06")
    assert by_ref.status_code == 200, by_ref.text
    view = by_ref.json()
    assert view["event"]["ref"] == "SAMPLE-RV-06" and view["event"]["complaint_id"] == str(row.id)
    # What happened, for the page's header.
    assert view["event"]["description"] == row.description
    assert view["event"]["problem_code"] == row.problem_code
    for other in (str(row.id), row.business_id):
        again = user.get(f"{EVENTS}/{other}")
        assert again.status_code == 200 and again.json()["event"]["complaint_id"] == str(row.id), other
    for missing in ("SAMPLE-RV-99", str(uuid.uuid4())):
        assert user.get(f"{EVENTS}/{missing}").status_code == 404, missing


@pytest.mark.db
def test_another_organization_cannot_open_the_page(trial):
    other, _, _ = _approved_trial_client()
    assert other.get(f"{EVENTS}/{_complaint(trial['tenant_id'], 'SAMPLE-RV-06').id}").status_code == 404


@pytest.mark.db
@pytest.mark.parametrize("ref", SAMPLE)
def test_the_page_lists_my_work_and_oversight_show_the_same_deadline_owner_and_next_action(trial, ref):
    user = trial["user"]
    page = user.get(f"{EVENTS}/{ref}").json()
    work = page["work"]
    complaint_id = page["event"]["complaint_id"]
    # The complaint list of the new navigation.
    listed = user.get("/api/v1/complaints", params={"q": ref, "work": "1"}).json()["items"]
    row = next(item for item in listed if item["complaint_identifier"] == ref)
    assert row["work"] == work
    # Oversight: its dated items for the complaint, and its event row.
    oversight = user.get("/api/v1/oversight", params={"show": "all"}).json()
    items = [item for item in oversight["items"] if item["complaint_id"] == complaint_id]
    # Oversight lists the reportability watch's provisional clock of a market not assessed yet too (0.10.69, pending
    # the owner's approval): the page, the list and Oversight say the same dated items.
    listed_due = work["due"]
    assert [item["due_at"] for item in items] == [item["due_at"] for item in listed_due]
    assert [item["title"] for item in items] == [item["title"] for item in listed_due]
    watch = user.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 200}).json()["items"]
    running = next((item["binding"] for item in watch if item["complaint_identifier"] == ref), None)
    if running and running.get("due_at"):
        market_due = [
            item
            for item in work["due"]
            if item["market"] == running["market"] and item["category"] in ("REPORTING", "OBLIGATION")
        ]
        assert market_due and market_due[0]["due_label"] == running["due_label"], ref
    event = next((item for item in oversight["events"] if item["complaint_id"] == complaint_id), None)
    if event is not None:
        assert (event["owner_name"], event["stage"], event["next"]) == (
            work["owner_name"],
            work["stage"],
            work["next"],
        )
    # The page's own header agrees with its work line: the next action, the nearest deadline.
    next_action = page["summary"]["next_action"]
    assert (next_action["label"] if next_action else None) == work["next"]
    if work["due"]:
        assert page["summary"]["nearest_deadline"]["due_at"] == work["due"][0]["due_at"]
    # My work: every reminder about this complaint names a due time the page shows.
    alerts = user.get("/api/v1/oversight/alerts").json()["items"]
    due = {item["due_at"] for item in work["due"]}
    for alert in alerts:
        if alert["ref"] == ref:
            assert alert["due_at"] in due, (ref, alert["title"])


@pytest.mark.db
def test_the_urgent_intake_is_a_call_whose_triage_target_agrees_everywhere(trial):
    user = trial["user"]
    # Not a complaint yet: no complaint page.
    assert user.get(f"{EVENTS}/SAMPLE-URG-01").status_code == 404
    triage = next(item for item in user.get("/api/v1/triage").json()["items"] if item["ref"] == "SAMPLE-URG-01")
    oversight = [item for item in user.get("/api/v1/oversight", params={"show": "all"}).json()["items"]]
    target = next(item for item in oversight if item["ref"] == "SAMPLE-URG-01" and item["category"] == "TRIAGE")
    assert triage["triage_clock"]["due_at"] == target["due_at"]
    for alert in user.get("/api/v1/oversight/alerts").json()["items"]:
        if alert["ref"] == "SAMPLE-URG-01" and alert["category"] == "TRIAGE":
            assert alert["due_at"] == target["due_at"]


@pytest.mark.db
def test_who_signs_each_step_is_told_first_and_a_step_goes_to_a_signer_only(trial):
    user = trial["user"]
    page = user.get(f"{EVENTS}/SAMPLE-RV-06").json()
    signers = page["signers"]
    assert set(signers) == {"TRIAGE", "FIRST_CONTACT", "MARKETS", "OBLIGATIONS", "DECISION", "CAPA", "READY"}
    # The trial owner is a Leader: a signer of every step; a report is approved by another person.
    assert all(step["you"] for step in signers.values())
    assert signers["OBLIGATIONS"]["second_person"] and not signers["MARKETS"]["second_person"]
    me = signers["MARKETS"]["people"][0]["id"]
    complaint_id = page["event"]["complaint_id"]
    refused = user.post(f"{EVENTS}/{complaint_id}/send", json={"step": "MARKETS", "to_user_id": str(uuid.uuid4())})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_A_SIGNER"
    sent = user.post(f"{EVENTS}/{complaint_id}/send", json={"step": "MARKETS", "to_user_id": me})
    assert sent.status_code == 200, sent.text
    tasks = user.get("/api/v1/tasks", params={"view": "assigned", "page_size": 200}).json()["items"]
    task = next(item for item in tasks if item["task_type"] == "COMPLAINT_STEP")
    assert "SAMPLE-RV-06" in task["title"]
    assert task["details"]["complaint_id"] == complaint_id


@pytest.mark.db
def test_the_dismissed_view_lists_only_records_decided_as_not_complaints(trial):
    user = trial["user"]
    dismissed = user.get("/api/v1/complaints/second-look", params={"state": "dismissed"}).json()
    assert dismissed["state"] == "dismissed"
    assert dismissed["total"] == dismissed["summary"]["dismissed"]
    assert all(item["decision"]["decision"] == "DISMISSED" for item in dismissed["items"])
    decided = user.get("/api/v1/complaints/second-look", params={"state": "decided"}).json()
    assert decided["total"] == decided["summary"]["dismissed"] + decided["summary"]["confirmed"]


@pytest.mark.db
def test_a_backlog_complaint_shows_the_backlog_note_and_target_not_an_overdue_market(trial):  # section Q decision 3
    """Owner, 10 Nov: an old flagged import is Imported backlog work; its page's legal clocks show the backlog note
    and target (the reportability decision was the QMS's), never its market window read overdue."""
    from datetime import date, timedelta

    from tests.test_intake_triage_api import _upload

    user = trial["user"]
    aware = (date.today() - timedelta(days=200)).isoformat()
    _upload(
        user,
        "complaint_id,product_id,product_name,description,status,awareness_date,country,death\n"
        + f"CP-BL-1,CP-PUMP,CP Pump,Patient died after the pump stopped,open,{aware},US,Y\n",
    )
    page = user.get(f"{EVENTS}/CP-BL-1").json()
    due = page["work"]["due"]
    assert due and not [item for item in due if item["state"] == "OVERDUE"], due
    line = next(item for item in due if item["key"].endswith(":backlog"))
    assert line["title"] == "Imported: check the reportability decision in your QMS (Imported backlog target)"
    assert line["market"] == "US" and line["opens"]["target"]["tab"] == "Imported backlog"
    assert page["summary"]["nearest_deadline"]["title"] == line["title"]


def test_a_backlog_complaint_missing_a_fact_asks_for_it_as_home_does(trial):
    """Gap-matrix S: an old flagged import with no country keeps its backlog line and gets Home's "Enter the ..." line
    (same key, title and date), never a market window read overdue."""
    from datetime import date, timedelta

    from tests.test_intake_triage_api import _upload

    user = trial["user"]
    aware = (date.today() - timedelta(days=200)).isoformat()
    _upload(
        user,
        "complaint_id,product_id,product_name,description,status,awareness_date,country,death\n"
        + f"CP-BL-2,CP-PUMP,CP Pump,Patient died after the pump stopped,open,{aware},,Y\n",
    )
    page = user.get(f"{EVENTS}/CP-BL-2").json()
    due = page["work"]["due"]
    assert not [item for item in due if item["state"] == "OVERDUE"], due
    assert any(item["key"].endswith(":backlog") for item in due), due
    (asks,) = [item for item in due if item["key"].endswith(":facts")]
    assert asks["title"].startswith("Enter the incident country") and asks["market"] is None
    home = {item["key"]: item for item in user.get("/api/v1/oversight", params={"show": "all"}).json()["items"]}
    assert home[asks["key"]]["title"] == asks["title"] and home[asks["key"]]["due_at"] == asks["due_at"]
