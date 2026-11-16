"""B9 step 14 (B9-07, B9-08): India's follow-up and final reports, created on demand only (D15), with P2 from the
chain, an optional next-report date labelled "No legal clock: your date", one open at a time, and a Final that ends
the chain. On the sample's India report (SAMPLE-RV-10), set to accepted here."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_authority_reports_api import REPORTS, _fields, _items, _ok, trial  # noqa: F401

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.db, pytest.mark.requirement("B9-13", "B9-17", "B9-18", "B9-19", "B9-20", "B9-23", "B9-33")]

WHAT = "The returned probe was examined: the heating element had a cracked seal."


def _state(tenant_id, report_id: str, state: str) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(ReportObligation, uuid.UUID(report_id)).state = state
        db.commit()


def _children(tenant_id, report_id: str) -> list[ReportObligation]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return db.query(ReportObligation).filter_by(parent_id=uuid.UUID(report_id)).all()


def _create(user, report_id: str, kind: str, **extra):
    return user.post(f"{REPORTS}/{report_id}/india-chain", json={"type": kind, "what_is_new": WHAT, **extra})


def test_follow_up_and_final_on_demand_one_open_at_a_time_and_a_final_ends_the_chain(trial, monkeypatch):  # noqa: F811
    user, tenant_id = trial["user"], trial["tenant_id"]
    initial = _items(user)[("SAMPLE-RV-10", "IN", "INITIAL")]["id"]
    # Never automatic: the sample's initial report has no follow-up of its own; not yet accepted, none can be made.
    assert _children(tenant_id, initial) == []
    assert _create(user, initial, "Follow up").json()["detail"]["code"] == "NOT_SUBMITTED"
    view = _ok(user.get(f"{REPORTS}/{initial}"))
    assert _fields(view)["P2"]["value"] == "Initial" and view["india_chain"]["can_create"] is False
    _state(tenant_id, initial, "ACCEPTED")
    assert _ok(user.get(f"{REPORTS}/{initial}"))["india_chain"]["can_create"] is True

    follow = _ok(_create(user, initial, "Follow up", next_report_on="2027-01-15"))
    assert follow["parent_id"] == initial and follow["kind"] == "RESPONSE"
    assert follow["india_chain"] == {
        "type": "Follow up",
        "next_report_on": "2027-01-15",
        "note": "No legal clock: your date",
    }
    fields = _fields(follow)
    assert fields["P2"]["value"] == "Follow up" and fields["P2"]["editable"] is False
    assert fields["P1"]["value"] is None  # filled in with the day it is sent for approval
    assert fields["A_BRAND"]["value"] == _fields(view)["A_BRAND"]["value"]  # starts from the initial report
    # P2 is never typed: it follows the chain.
    typed = user.put(f"{REPORTS}/{follow['id']}/fields/P2", json={"value": "Final"})
    assert typed.status_code == 422 and typed.json()["detail"]["code"] == "FOLLOWS_CHAIN"
    assert _create(user, initial, "Final").json()["detail"]["code"] == "CHAIN_OPEN"
    # An unsent one is cancelled with a reason (step 15's card): the chain is free again.
    spare = user.post(f"{REPORTS}/{follow['id']}/cancel", json={"reason": "Started by mistake, not needed."})
    assert spare.status_code == 200 and spare.json()["state"] == "CANCELLED", spare.text
    assert _ok(user.get(f"{REPORTS}/{initial}"))["india_chain"]["can_create"] is True
    follow = _ok(_create(user, initial, "Follow up"))

    _state(tenant_id, follow["id"], "ACCEPTED")
    final = _ok(_create(user, initial, "Final"))
    assert _fields(final)["P2"]["value"] == "Final" and final["india_chain"]["next_report_on"] is None
    _state(tenant_id, final["id"], "ACCEPTED")
    assert _create(user, initial, "Follow up").json()["detail"]["code"] == "CHAIN_ENDED"
    view = _ok(user.get(f"{REPORTS}/{initial}"))
    assert view["india_chain"]["ended"] is True and view["india_chain"]["can_create"] is False
    assert [item["type"] for item in view["india_chain"]["items"]] == ["Follow up", "Final"]

    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert _create(user, initial, "Follow up").status_code == 404


def test_only_an_india_initial_report_takes_a_chain(trial):  # noqa: F811
    user = trial["user"]
    us = next(item["id"] for key, item in _items(user).items() if item["id"] and key[1] != "IN")
    refused = _create(user, us, "Final")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "NOT_AN_INDIA_INITIAL"
    assert _create(user, us, "Trend").status_code == 422  # only Follow up and Final are made here


def test_b9_india_sample_gives_form_and_sheet(trial):  # noqa: F811
    """Step 16 (B9-05, B9-06 on the sample): SAMPLE-RV-10's approved snapshot downloads as MvPI's own form v1.2 and as
    the ADRMS entry sheet; neither before approval."""
    import io

    from pypdf import PdfReader

    user = trial["user"]
    initial = _items(user)[("SAMPLE-RV-10", "IN", "INITIAL")]["id"]
    detail = _ok(user.get(f"{REPORTS}/{initial}"))
    snapshot = next(row for row in detail["snapshots"] if row["state"] == "APPROVED")["id"]
    url = f"{REPORTS}/{initial}/worksheet.pdf"
    official = user.get(url, params={"snapshot": snapshot, "form": "official"})
    assert official.status_code == 200, official.text
    assert "official-form" in official.headers["content-disposition"]
    fields = PdfReader(io.BytesIO(official.content)).get_fields()
    assert fields["text_110wxft"].get("/V") and fields["checkbox_9kjrf"].get("/V") not in (None, "/Off")  # R1
    assert fields["checkbox_37bwpo"].get("/V") not in (None, "/Off")  # A1 "Class B (sample)": class B
    sheet = user.get(url, params={"snapshot": snapshot, "form": "adrms"})
    assert sheet.status_code == 200 and "adrms-entry-sheet" in sheet.headers["content-disposition"]
    assert "ADRMS fields, in screen order" in PdfReader(io.BytesIO(sheet.content)).pages[0].extract_text()
    refused = user.get(url, params={"form": "official"})  # the working draft: not approved
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "APPROVE_FIRST"


def test_p1_and_p2_follow_the_india_switch_off_on_off(trial, monkeypatch):  # noqa: F811
    """Spec 6.4: off, today's worksheet stays (P1 and P2 typed); on, P1 is the day sent and P2 follows the chain."""
    user, tenant_id = trial["user"], trial["tenant_id"]
    initial = _items(user)[("SAMPLE-RV-10", "IN", "INITIAL")]["id"]
    _state(tenant_id, initial, "DRAFT")

    def put(field: str, value: str):
        return user.put(f"{REPORTS}/{initial}/fields/{field}", json={"value": value})

    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert put("P1", "2026-11-02").status_code == 200
    assert put("P2", "Follow up").status_code == 200
    fields = _fields(_ok(user.get(f"{REPORTS}/{initial}")))
    assert fields["P1"]["editable"] and fields["P1"]["value"] == "2026-11-02"
    assert fields["P2"]["editable"] and fields["P2"]["value"] == "Follow up"

    monkeypatch.setenv("MDARIX_B9_INDIA", "on")
    fields = _fields(_ok(user.get(f"{REPORTS}/{initial}")))
    assert not fields["P1"]["editable"] and fields["P1"]["value"] != "2026-11-02"
    assert not fields["P2"]["editable"] and fields["P2"]["value"] == "Initial"
    assert put("P2", "Final").json()["detail"]["code"] == "FOLLOWS_CHAIN"
    assert put("P1", "2026-11-03").json()["detail"]["code"] == "FILLED_AT_SEND"

    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    fields = _fields(_ok(user.get(f"{REPORTS}/{initial}")))
    assert fields["P1"]["value"] == "2026-11-02" and fields["P2"]["value"] == "Follow up"
