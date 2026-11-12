"""B7a on/off switch (owner decision 1, run 4): ``MDARIX_ROUTINE_PATH``, on unless ``off``. Off, the B7a routes answer
404 (a file already on a Case stays readable, a closed complaint can still reopen), the session says so for the
screens, the next step is not "Resolve and close", the Cases template is not offered and the closure checklist has no
CUSTOMER_TOLD item (closing behaves as before B7)."""

from __future__ import annotations

import uuid

import pytest

from backend.app import feature_set
from backend.app.complaint_disposition import resolve
from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

C = "/api/v1/complaints/00000000-0000-0000-0000-000000000001"
CASE = "/api/v1/intake/00000000-0000-0000-0000-000000000001"


# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = pytest.mark.requirement("RT-13", "RT-14", "RT-18", "RT-19", "RT-22", "RT-24")


@pytest.mark.unit
@pytest.mark.parametrize("value", ["", "on", "off"])
def test_serves_path_follows_the_switch(monkeypatch, value):
    monkeypatch.delenv("MDARIX_FEATURE_SET", raising=False)
    monkeypatch.setenv("MDARIX_ROUTINE_PATH", value)
    on = value != "off"
    assert feature_set.routine_path() is on
    for method, path in (
        ("GET", f"{C}/resolve-and-close"),
        ("POST", f"{C}/resolve-and-close"),
        ("GET", "/api/v1/intake/cases/export.csv"),
        ("GET", "/api/v1/intake/qms-entry/export.csv"),
        ("POST", f"{CASE}/attachments"),
        ("PUT", "/api/v1/oversight/settings/alerts-and-files"),
    ):
        assert feature_set.serves_path(path, method) is on, (method, path)
    # Always served: reading files already on a Case, reopening, the plain disposition.
    for method, path in (("GET", f"{CASE}/attachments"), ("POST", f"{C}/reopen"), ("GET", f"{C}/disposition")):
        assert feature_set.serves_path(path, method), (method, path)


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rt01 = (
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == "SAMPLE-RT-01")
            .scalar()
        )
    try:
        yield {"user": user, "rt01": str(rt01)}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:routine-switch-cleanup")


def _seen(trial) -> dict:
    user, rt01 = trial["user"], trial["rt01"]
    event = user.get(f"/api/v1/oversight/events/{rt01}")
    assert event.status_code == 200, event.text
    templates = user.get("/api/v1/data/import/templates").json()["templates"]
    return {
        "screen": user.get(f"/api/v1/complaints/{rt01}/resolve-and-close").status_code,
        "plain": user.get(f"/api/v1/complaints/{rt01}/disposition").status_code,
        "export": user.get("/api/v1/intake/cases/export.csv").status_code,
        "session": user.get("/api/v1/session/context").json()["routine_path"],
        "told": [item for item in event.json()["checklist"] if item["code"] == "CUSTOMER_TOLD"],
        "next": (event.json()["summary"]["next_action"] or {}).get("label"),
        "cases_template": any(item["entity"] == "cases" for item in templates),
    }


@pytest.mark.db
def test_on_and_off_through_the_api(trial, monkeypatch):
    monkeypatch.delenv("MDARIX_ROUTINE_PATH", raising=False)
    on = _seen(trial)
    assert on["screen"] == 200 and on["session"] is True and on["cases_template"]
    assert on["told"] and on["told"][0]["result"] == "BLOCKED"
    assert on["next"] in resolve.BUTTONS.values()

    monkeypatch.setenv("MDARIX_ROUTINE_PATH", "off")
    off = _seen(trial)
    assert off["screen"] == 404 and off["export"] == 404
    assert off["plain"] == 200  # the disposition reads as before B7
    assert off["session"] is False and not off["cases_template"]
    assert off["told"] == []  # closing behaves as before B7
    assert off["next"] not in resolve.BUTTONS.values()
