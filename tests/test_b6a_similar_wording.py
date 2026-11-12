# ruff: noqa: F811  (the trial fixture is imported from the intake tests)
"""B6a P1 (D8) through the API: a pair with similar wording is suggested beside today's rule, a person dismisses it
with today's audited decision and it is not shown again; unrelated wording is not suggested; the escalation check
adds the reason without pre-selecting; another organization sees none of it (B6-41, B6-42, B6-45)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.intake import service
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _log, _ok, trial  # noqa: F401

pytestmark = pytest.mark.db
TAG = uuid.uuid4().hex[:6]
FIRST = f"Infusion pump occlusion alarm sounded repeatedly while delivering saline to the patient {TAG}"
SECOND = f"Pump occlusion alarm sounded repeatedly while delivering saline infusion {TAG}"
UNRELATED = "Display cracked after the device fell from the trolley in the corridor"


def _pairs(user, ref: str) -> list[dict]:
    items = _ok(user.get(f"{INTAKE}/duplicates"))["items"]
    return [item for item in items if ref in (item["left"]["ref"], item["right"]["ref"])]


def test_similar_wording_is_suggested_and_a_dismissed_pair_is_not_shown_again(trial, monkeypatch):
    user = trial["user"]
    first, second, unrelated = (_log(user, reporter_words=text) for text in (FIRST, SECOND, UNRELATED))
    refs = {item["reference"] for item in (first, second)}

    # B6-41: suggested with the reason and the percentage; nothing merged.
    (pair,) = [item for item in _pairs(user, first["reference"]) if {item["left"]["ref"], item["right"]["ref"]} == refs]
    assert pair["reasons"] == ["similar description (90 % words in common)"]
    assert not [item for item in _pairs(user, unrelated["reference"]) if "similar description" in str(item["reasons"])]

    # Switched off: only today's rule reasons, so no pair for these Cases.
    monkeypatch.setenv("MDARIX_B6_SIMILAR_WORDING", "off")
    assert not [item for item in _pairs(user, first["reference"]) if "similar" in str(item["reasons"])]
    monkeypatch.setenv("MDARIX_B6_SIMILAR_WORDING", "on")

    # Another organization sees none of it.
    other, _, _ = _approved_trial_client()
    assert _pairs(other, first["reference"]) == []

    # B6-42: a person dismisses it with today's audited decision; it is not suggested again.
    body = {
        "left_kind": pair["left"]["kind"],
        "left_id": pair["left"]["id"],
        "right_kind": pair["right"]["kind"],
        "right_id": pair["right"]["id"],
        "decision": "DISMISSED",
        "reason": "Two different pumps on two different wards.",
    }
    link = _ok(user.post(f"{INTAKE}/links", json=body))
    assert not [
        item for item in _pairs(user, first["reference"]) if {item["left"]["ref"], item["right"]["ref"]} == refs
    ]
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        event = db.query(AuditEvent).filter(AuditEvent.entity_id == uuid.UUID(link["id"])).one()
        assert event.action == "DUPLICATE_DISMISSED" and event.reason == body["reason"]


def test_the_escalation_check_adds_similar_wording_without_preselecting(trial):
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        complaint = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == trial["tenant_id"], Complaint.product_id.isnot(None))
            .filter(Complaint.description.isnot(None), Complaint.event_timestamp.isnot(None))
            .first()
        )
        # A Case of the same product and day, another country and no lot: today's rule finds nothing; the words do.
        case = SimpleNamespace(
            id=uuid.uuid4(),
            product_id=complaint.product_id,
            lot_batch_id=None,
            serial_number=None,
            reporter_site=None,
            country="Nowhere",
            event_at=complaint.event_timestamp,
            received_at=complaint.event_timestamp,
            reporter_words=complaint.description,
        )
        found = {item["id"]: item for item in service.likely_complaints(db, trial["tenant_id"], case)}
        item = found[str(complaint.id)]
        assert item["reasons"] == ["similar description (100 % words in common)"] and item["same_day"] is False
        assert item["wording_only"] is True  # offered, never pre-selected (preselected() in FirstContact.tsx)
