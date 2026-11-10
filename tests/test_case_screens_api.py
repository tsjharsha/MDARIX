"""0.10.93 (B2) step 5: what the Case screens need from the API. Log a case keeps a product or lot that is not in the
organization's master data as typed, flagged (spec 4.2), with its ID-1 entry and the S-1 category."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_case_addenda_api import _log
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _all_no, _ok, _sign

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-screens-cleanup")


def test_a_typed_product_and_an_unknown_lot_are_kept_as_typed_and_flagged(trial):  # spec 4.2, ID-1
    event = _log(
        trial["user"],
        product_text="OrbitCare infusion pump (older model)",
        lot="LOT-NOT-LOADED-7",
        identifiers={"lot": {"source": "LABEL_OR_PHOTO", "status": "CONFIRMED"}, "serial": {"not_sure": True}},
        issue_category="hardware",
    )
    assert (event["product_name"], event["lot"]) == ("OrbitCare infusion pump (older model)", "LOT-NOT-LOADED-7")
    assert sorted(event["not_in_master"]) == ["lot", "product"]
    assert event["identifiers"]["lot"] == {"not_sure": False, "status": "CONFIRMED", "source": "LABEL_OR_PHOTO"}
    assert event["identifiers"]["serial"]["not_sure"] is True
    assert event["issue_category"] == "HARDWARE"
    missing = {item["code"] for item in event["missing"]}
    assert {"IDENTIFIER_NOT_SURE:serial", "IDENTIFIER_UNCONFIRMED:product"} <= missing
    assert "IDENTIFIER_UNCONFIRMED:lot" not in missing


def test_the_cases_list_pages_filters_and_searches_on_the_server(trial):  # A5, spec 4.3
    user = trial["user"]
    made = [_log(user, serial_number=f"SN-PAGE-{index}") for index in range(4)]
    first = _ok(user.get(f"{INTAKE}/cases?size=2"))
    second = _ok(user.get(f"{INTAKE}/cases?size=2&page=2"))
    assert first["total"] >= 4 and len(first["items"]) == len(second["items"]) == 2
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
    found = _ok(user.get(f"{INTAKE}/cases?q=SN-PAGE-1"))
    assert [row["reference"] for row in found["items"]] == [made[1]["reference"]]
    header = found["items"][0]["header"]  # A3
    assert header["owner"] and header["next_action"] == "Answer and sign the Case check" and header["due_at"]
    assert header["escalation"]["state"] in ("NONE", "TRIAGE")
    assert _ok(user.get(f"{INTAKE}/cases?view=mine&q=SN-PAGE"))["total"] == 4
    assert _ok(user.get(f"{INTAKE}/cases?view=closed&q=SN-PAGE"))["total"] == 0
    assert _ok(user.get(f"{INTAKE}/cases?view=to_check&q=SN-PAGE"))["counts"]["OPEN"] == 4
    refused = user.get(f"{INTAKE}/cases?view=everything")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "UNKNOWN_VIEW"
    detail = _ok(user.get(f"{INTAKE}/{made[0]['id']}"))
    assert detail["header"]["next_action"] == header["next_action"]


def test_the_cases_list_reads_the_same_number_of_queries_whatever_the_page_size(trial):  # A5, B2-15 (budget)
    from sqlalchemy import event

    from backend.app.intake import cases_list

    user, tenant_id = trial["user"], trial["tenant_id"]
    for index in range(3):
        _log(user, serial_number=f"SN-BUDGET-{index}")

    def statements(size: int) -> int:
        seen = []
        with SessionLocal() as db:
            bind_system(db, "test:case-screens-budget")
            engine = db.get_bind()
            listener = lambda *args, **kwargs: seen.append(1)  # noqa: E731
            event.listen(engine, "before_cursor_execute", listener)
            try:
                page = cases_list.cases_page(db, None, tenant_id, "nobody", "all", "SN-BUDGET", 1, size)
            finally:
                event.remove(engine, "before_cursor_execute", listener)
        assert len(page["items"]) == min(size, 3)
        return len(seen)

    assert statements(1) == statements(3) <= 12


def test_the_case_check_drawer_reads_its_six_choices_its_clock_and_the_complaints_to_attach_to(trial):  # spec 4.4/4.5
    user = trial["user"]
    event = _log(user)
    detail = _ok(user.get(f"{INTAKE}/{event['id']}"))
    codes = [item["code"] for item in detail["choices"]]
    assert len(codes) == 6 and codes[:2] == ["COMPLAINT", "BOTH"] and codes[-1] == "NOT_A_COMPLAINT"
    assert [item["code"] for item in detail["choices"] if item["escalates"]] == ["COMPLAINT", "BOTH"]
    assert [item["code"] for item in detail["choices"] if item["suggested"]] in ([], [detail["suggestion"]])
    # The provisional clock chip: a market, its days and the due time, counted from the Case's awareness.
    assert detail["clock"]["market"] and detail["clock"]["days"] and detail["clock"]["due_label"]
    # No product: nothing to attach to; not escalated: no complaint yet.
    assert detail["likely_complaints"] == [] and detail["complaint_ref"] is None and detail["row_version"] >= 1


def test_the_complaint_page_of_an_escalated_case_shows_its_origin_its_case_and_the_stage_case(trial):  # spec 4.6
    user = trial["user"]
    event = _log(
        user,
        answers=_all_no(Q2="YES"),
        troubleshooting="Restarted the pump; the alarm came back",
        channel="phone",
        channel_ref="call 4471",
        patients="ONE",
        harm_text="Infusion delayed; call the nurse on nurse.lee@example.com",
        first_knowledge_party="IMPORTER",
        first_knowledge_basis="ACTS_FOR_MANUFACTURER",
    )
    # Spec 4.2: channel, patients, harm (masked) and who knew first are kept.
    assert (event["channel"], event["channel_label"], event["channel_ref"]) == ("PHONE", "Phone", "call 4471")
    assert event["patients"] == "ONE" and "nurse.lee@example.com" not in event["harm_text"]
    assert event["times"]["first_knowledge"]["party"] == "IMPORTER"
    unknown = _ok(
        user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": "Display flickers on start", "channel": "pigeon"})
    )
    assert unknown["channel"] is None  # an unknown channel is not kept, as the other choices
    signed = _ok(_sign(user, event, "COMPLAINT"))
    assert signed["complaint_ref"] == event["reference"]
    page = _ok(user.get(f"/api/v1/oversight/events/{event['reference']}"))
    assert page["stages"][0] == {"code": "CASE", "label": "Case", "state": "DONE"}
    assert page["origin"]["from_case"] is True and page["origin"]["case_ref"] == event["reference"]
    assert page["origin"]["record_owner"] == "MDARIX"  # a trial: Complete
    case = page["case"]
    assert (case["id"], case["reference"], case["escalation"]) == (event["id"], event["reference"], "CREATED")
    assert case["signed"]["outcome"] == "Complaint" and case["words"] == event["reporter_words"]
    assert case["troubleshooting"] == "Restarted the pump; the alarm came back"
    # The Case check after the escalation: no clock chip and nothing to attach to (its life continues on the page).
    assert signed["clock"] is None and signed["likely_complaints"] == []
