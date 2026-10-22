"""The trial's story reads less, with the same result (0.10.43; backend/app/trial/story.py, readiness_home/service.py,
complaint_review/service.py backlog, signals/insight.py trend_board).

After a large import Getting started's story took seconds on a production-sized server, and every open trial page read
it again every half minute for the "Chapter done" notice. Checked here on a trial with the sample data and complaints
of its own: Readiness reads the trend board once for its two checks that use it, with the checks unchanged; the
backlog board reads whole complaints only for the page it shows, with the same page; and the story read without
findings (``GET /api/v1/trial/story?findings=false``) gives the same chapters, tries and next step without reading
Readiness.
"""

import uuid
from datetime import date, timedelta

import pytest

from backend.app.complaint_review import service as review_service
from backend.app.db.data_plane import open_tenant_data_session
from backend.app.readiness_home import service as readiness_service
from backend.app.signals import insight
from backend.app.trial import story as trial_story
from tests.test_free_trial import _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

IMPORT = "/api/v1/trial/imports/complaints"
TODAY = date.today()


def _export(rows: int = 30) -> str:
    """Complaints of the trial's own, received over the last months, most of them past the backlog target."""
    lines = "".join(
        f"OWN-{number},OWN-PUMP,Own Pump,Display flickers after a firmware update number {number},Rev {number % 3},"
        f"OWN-LOT-{number % 4},{(TODAY - timedelta(days=2 + number * 6)).isoformat()}\n"
        for number in range(rows)
    )
    return "complaint_id,product_id,product_name,description,version,lot_id,received_date\n" + lines


@pytest.fixture(scope="module")
def trial():
    user, approval, _email = _approved_trial_client()
    imported = user.post(IMPORT, content=_export(), headers={"Content-Type": "text/csv"})
    assert imported.status_code == 200, imported.text
    return user, uuid.UUID(approval["tenant_id"])


def test_readiness_reads_the_trend_board_once_with_the_same_checks(trial, monkeypatch):
    _user, tenant_id = trial
    with open_tenant_data_session(tenant_id) as db:
        # Each check on its own, as before: the trend check and the risk file check each read the board.
        separately = [step(db, tenant_id, TODAY) for step in readiness_service.CHECKS]
        boards = []
        real = insight._trend_board
        monkeypatch.setattr(insight, "_trend_board", lambda *args: boards.append(args[2]) or real(*args))
        together = readiness_service.readiness(db, tenant_id, TODAY)
    assert boards == ["problem"]
    assert together["checks"] == separately
    # Outside a readiness read nothing is kept: each read reads the records again.
    with open_tenant_data_session(tenant_id) as db:
        insight.trend_board(db, tenant_id, grouping="problem", today=TODAY)
        insight.trend_board(db, tenant_id, grouping="problem", today=TODAY)
    assert boards == ["problem", "problem", "problem"]


def test_the_backlog_reads_whole_complaints_only_for_the_page_it_shows(trial, monkeypatch):
    _user, tenant_id = trial
    with open_tenant_data_session(tenant_id) as db:
        everything = review_service.backlog(db, tenant_id, page=1, page_size=10**6, today=TODAY)
        assert everything["total"] >= 20 and everything["summary"]["past_target"] >= 10
        read_whole = []
        real = review_service.record_of
        monkeypatch.setattr(review_service, "record_of", lambda *row: read_whole.append(row) or real(*row))
        for show in ("all", "past_target", "due_soon"):
            for page in (1, 2):
                read_whole.clear()
                found = review_service.backlog(db, tenant_id, show=show, page=page, page_size=5, today=TODAY)
                assert len(read_whole) == len(found["items"]) <= 5
                chosen = [item for item in everything["items"] if show == "all" or item["state"] == show.upper()]
                # The same page, each complaint whole (its record and what the board says of it), in the same order.
                assert found["items"] == chosen[(page - 1) * 5 : page * 5]
                assert found["summary"] == everything["summary"] and found["total"] == len(chosen)
    item = everything["items"][0]
    assert {"id", "business_id", "complaint_identifier", "product_name", "description", "received_date"} <= set(item)
    assert {"age_days", "days_past_target", "state", "band", "confirmed_on_second_look"} <= set(item)
    assert [entry["age_days"] for entry in everything["items"]] == sorted(
        (entry["age_days"] for entry in everything["items"]), reverse=True
    )


def test_the_story_without_findings_gives_the_same_chapters_without_reading_readiness(trial, monkeypatch):
    user, _tenant_id = trial
    full = user.get("/api/v1/trial/story")
    assert full.status_code == 200, full.text
    calls = []
    real = readiness_service.readiness
    monkeypatch.setattr(
        readiness_service, "readiness", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs)
    )
    progress = user.get("/api/v1/trial/story", params={"findings": "false"})
    assert progress.status_code == 200, progress.text
    assert calls == []
    full, progress = full.json(), progress.json()
    assert full["findings"] is True and progress["findings"] is False
    for key in ("acted", "total", "next", "signals_pending", "as_of"):
        assert progress[key] == full[key], key
    assert len(progress["chapters"]) == len(full["chapters"]) == len(trial_story.CHAPTERS)
    for light, whole in zip(progress["chapters"], full["chapters"]):
        assert {k: v for k, v in light.items() if k != "finding"} == {k: v for k, v in whole.items() if k != "finding"}
        assert light["finding"] == {"value": None, "text": None, "state": "NOT_SET"}
    # The full story still reads Readiness, and still names what the records show.
    assert user.get("/api/v1/trial/story").status_code == 200 and calls == [1]
    assert any(chapter["finding"]["text"] for chapter in full["chapters"])
