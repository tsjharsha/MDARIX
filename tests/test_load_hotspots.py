"""DEV-13 (0.10.88): the hotspots the load measurement found, each held to its fixed cost."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.session import SessionLocal
from tests.test_free_trial import _approved_trial_client


@pytest.fixture(scope="module")
def team():
    """A trial with its owner and four colleagues."""
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    for index in range(4):
        response = user.post(
            "/api/v1/trial/team",
            json={"email": f"hot{index}-{tenant_id.hex[:6]}@example.invalid", "display_name": f"Colleague {index}"},
        )
        assert response.status_code == 200, response.text
    try:
        yield user
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:load-hotspots-cleanup")


@pytest.mark.db
def test_the_complaint_page_reads_each_persons_permissions_once_not_once_per_step(team, monkeypatch):
    """Who may sign each of the complaint's seven steps was asked person by person, step by step: seven reads of every
    colleague's roles per page (about 1,000 queries for a trial at its cap of 50). Now each person is read once."""
    from backend.app.workflow import people

    calls = []
    real = people.permissions_of
    monkeypatch.setattr(people, "permissions_of", lambda db, user: calls.append(user.id) or real(db, user))
    response = team.get("/api/v1/oversight/events/SAMPLE-RV-11")
    assert response.status_code == 200, response.text
    signers = response.json().get("signers") or {}
    assert signers, "the page still names who may sign"
    assert max(calls.count(person) for person in set(calls)) <= 2


def test_the_watch_normalizes_each_market_and_country_name_once(monkeypatch):
    """For a trial of 5,000 complaints the reportability watch normalized the same few names millions of times (100 s
    of a 173 s read of Getting started's story). The names read the same; each is normalized once."""
    import re

    from backend.app.reportability import markets, rules

    windows = [{"markets": ["United States", "EU"]}, {"markets": ["India"]}]
    before = [markets.market_of(name) for name in ("U.S.A.", "usa", "Germany", "India", "Mars")]
    calls = []
    real = re.sub
    monkeypatch.setattr(re, "sub", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    for _ in range(2000):
        assert markets.market_of("U.S.A.") == "US" and markets.enabled_markets(windows)
    assert [markets.market_of(name) for name in ("U.S.A.", "usa", "Germany", "India", "Mars")] == before
    assert rules.normalize("U.S.A.") == rules.normalize(" usa ") == "usa"
    assert len(calls) < 100
