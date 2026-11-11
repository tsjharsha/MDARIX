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

pytestmark = pytest.mark.db

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
