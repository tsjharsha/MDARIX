"""Signals from an import are found after the import answers (0.10.40; backend/app/trial/imports.py after_import,
backend/app/signals/hooks.py detect_after_import), like the embeddings: the answer no longer waits for detection.

Checked through the real API with the route's background tasks held back until the answer is in: no new signal exists
when the import answers; while detection waits, the import says so (``signals: "FINDING"``), the signal inbox and the
trial's story say so too; then the held-back step finds exactly the signals the old in-request detection found, in a
session bound to the organization (row-level security, not system scope), and the "finding" state ends.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from starlette.background import BackgroundTasks

from backend.app.db.data_plane import open_tenant_data_session
from backend.app.db.models.signals import Signal
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.signals import detection, hooks
from backend.app.trial import story as trial_story
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

IMPORT = "/api/v1/trial/imports/complaints"


def _export(prefix: str) -> str:
    """Twelve recent complaints of one problem on one pump version: enough for a threshold signal."""
    recent = date.today() - timedelta(days=3)
    rows = "".join(
        f"{prefix}-{number},{prefix}-PUMP,Aster Pump,Pressure alarm sounded during priming,Rev C,{prefix}-LOT-1,"
        f"{(recent - timedelta(days=number % 5)).isoformat()}\n"
        for number in range(12)
    )
    return "complaint_id,product_id,product_name,description,version,lot_id,received_date\n" + rows


@pytest.fixture
def held_back(monkeypatch):
    """The route's background tasks, kept instead of run, to run when the test says."""
    tasks = []
    monkeypatch.setattr(
        BackgroundTasks, "add_task", lambda self, func, *args, **kwargs: tasks.append((func, args, kwargs))
    )
    return tasks


def _signals(tenant_id) -> list[tuple]:
    with SessionLocal() as db:
        bind_system(db, "test: the organization's signals")
        rows = db.query(Signal).filter(Signal.tenant_id == uuid.UUID(str(tenant_id))).all()
        return sorted(
            (row.title, row.complaint_count, row.suggested_priority, row.status, row.origin)
            for row in rows
            if "Aster Pump" in str(row.title)
        )


def test_signals_are_found_after_the_answer_and_are_the_ones_found_before(held_back, monkeypatch):
    user, approval, _ = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    seen = []
    real_detect = detection.detect

    def spy(db, tenant, **kwargs):
        scope = db.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar()
        seen.append({"tenant": str(tenant), "bound": scope, "system": db.info.get("mdarix_system_reason")})
        return real_detect(db, tenant, **kwargs)

    monkeypatch.setattr(detection, "detect", spy)

    held_back.clear()  # the sign-up's own background steps
    imported = user.post(IMPORT, content=_export("ASTER"), headers={"Content-Type": "text/csv"})
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["created"] >= 12 and body["signals"] == "FINDING" and "insights" not in body
    # Answered before any detection: no signal of the new complaints yet, and every screen says they are coming.
    assert seen == [] and _signals(tenant_id) == []
    inbox = user.get("/api/v1/triage/signals").json()
    assert inbox["detection_pending"] is True
    assert user.get("/api/v1/triage/detection").json() == {"pending": True}
    story = user.get("/api/v1/trial/story").json()
    assert story["signals_pending"] is True
    trends = next(chapter for chapter in story["chapters"] if chapter["code"] == "TRENDS_TO_CASES")
    assert trends["finding"]["text"] == trial_story.FINDING_SIGNALS
    # The insights do not wait for detection either.
    assert user.get("/api/v1/trial/insights").json()["scope"] == "your data"

    # Detection first, then the embeddings, each after the answer.
    assert [func.__name__ for func, _, _ in held_back] == ["detect_after_import", "embed_tenant_evidence"]
    for func, args, kwargs in held_back:
        func(*args, **kwargs)
    found = _signals(tenant_id)
    assert found and all(count >= 3 for _, count, *_ in found)
    # In a session bound to the organization, never in system scope.
    assert seen == [{"tenant": tenant_id, "bound": tenant_id, "system": None}]
    assert user.get("/api/v1/triage/signals").json()["detection_pending"] is False
    assert user.get("/api/v1/triage/detection").json() == {"pending": False}
    story = user.get("/api/v1/trial/story").json()
    assert story["signals_pending"] is False
    trends = next(chapter for chapter in story["chapters"] if chapter["code"] == "TRENDS_TO_CASES")
    assert "waiting for a decision or a case" in trends["finding"]["text"]

    # The same file in another trial, with detection run in the request as in 0.10.39: the same signals.
    held_back.clear()
    other, other_approval, _ = _approved_trial_client()
    held_back.clear()
    assert other.post(IMPORT, content=_export("ASTER"), headers={"Content-Type": "text/csv"}).status_code == 200
    with open_tenant_data_session(uuid.UUID(other_approval["tenant_id"])) as data:
        hooks.after_complaints_saved(data, uuid.UUID(other_approval["tenant_id"]), source="trial import")
    assert _signals(other_approval["tenant_id"]) == found


def test_a_failed_detection_never_fails_the_import_and_the_finding_state_ends(held_back, monkeypatch):
    user, approval, _ = _approved_trial_client()
    held_back.clear()  # the sign-up's own background steps
    imported = user.post(IMPORT, content=_export("FAIL"), headers={"Content-Type": "text/csv"})
    assert imported.status_code == 200 and imported.json()["signals"] == "FINDING"

    def broken(*_args, **_kwargs):
        raise RuntimeError("detection is down")

    monkeypatch.setattr(detection, "detect", broken)
    detect_after = next(task for task in held_back if task[0].__name__ == "detect_after_import")
    assert detect_after[0](*detect_after[1], **detect_after[2]) is None  # logged, never raised
    assert user.get("/api/v1/trial/status").json()["own_data"]["complaints"] >= 12
    # Waited for a few minutes at most: a run that failed is not announced for ever.
    later = hooks.PENDING_AT_MOST + timedelta(seconds=1)
    with SessionLocal() as db:
        bind_system(db, "test: the pending state later")
        tenant = uuid.UUID(approval["tenant_id"])
        assert hooks.detection_pending(db, db, tenant) is True
        assert hooks.detection_pending(db, db, tenant, now=datetime.now(timezone.utc) + later) is False


def test_an_import_without_complaints_finds_no_signals_and_says_nothing_about_them(held_back):
    user, _approval, _ = _approved_trial_client()
    products = "product_id,product_name,version\nNOSIG-1,Quiet Pump,Rev A\n"
    held_back.clear()  # the sign-up's own background steps
    imported = user.post("/api/v1/trial/imports/products", content=products, headers={"Content-Type": "text/csv"})
    assert imported.status_code == 200, imported.text
    assert "signals" not in imported.json()
    assert [func.__name__ for func, _, _ in held_back] == ["embed_tenant_evidence"]
    assert user.get("/api/v1/triage/signals").json()["detection_pending"] is False


def test_the_workspace_import_finds_signals_after_the_answer_too(held_back):
    user, _approval, _ = _approved_trial_client()
    held_back.clear()  # the sign-up's own background steps
    imported = user.post("/api/v1/data/import/complaints", content=_export("WS"), headers={"Content-Type": "text/csv"})
    assert imported.status_code == 200, imported.text
    assert imported.json()["signals"] == "FINDING"
    assert [func.__name__ for func, _, _ in held_back] == ["detect_after_import", "embed_tenant_evidence"]
    assert user.get("/api/v1/triage/signals").json()["detection_pending"] is True
