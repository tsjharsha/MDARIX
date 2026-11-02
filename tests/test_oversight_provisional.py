"""0.10.69 (owner decision pending, in its own commit): Oversight lists an unassessed market's provisional clock, so it
says what Reporting and the complaint page say. SAMPLE-RV-06's FDA provisional deadline was on the complaint page and
the reportability watch but not in Oversight (stage 7 left it to the owner). Once the market's assessment is started,
its own clock stands in for it: one line per market, never two."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.session import SessionLocal
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    try:
        yield user
    finally:
        with SessionLocal() as db:
            purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:oversight-provisional-cleanup")


def test_oversight_lists_the_watch_clock_of_a_market_not_assessed_yet(trial):
    items = trial.get("/api/v1/oversight?show=all").json()["items"]
    page = trial.get("/api/v1/oversight/events/SAMPLE-RV-06").json()
    (on_page,) = [item for item in page["work"]["due"] if item["category"] == "REPORTING"]
    mine = [item for item in items if item["ref"] == "SAMPLE-RV-06" and item["category"] == "REPORTING"]
    assert [(item["market"], item["title"], item["due_at"]) for item in mine] == [
        ("US", "United States (FDA): not assessed yet, provisional deadline", on_page["due_at"])
    ]
    # One line per complaint and market: RV-08, whose US assessment is started, keeps its own line only.
    rv08 = [(item["market"], item["key"].split(":")[0]) for item in items if item["ref"] == "SAMPLE-RV-08"]
    assert rv08.count(("US", "watch")) == 0 and ("US", "assessment") in rv08
