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


def test_possible_duplicates_are_found_without_comparing_every_record_with_every_other():
    """The triage list's possible duplicates compared every record with every other (2,500 records: 3 million pairs,
    about 12 s a read on 5,000 imported complaints). Only records of one product with the same lot or serial number
    can be duplicates, so only those are paired: the same pairs, in the same order."""
    import random
    from datetime import date, timedelta

    from backend.app.intake import rules
    from backend.app.intake.service import candidate_pairs

    pick = random.Random(88)
    fields = [
        {
            "product_id": pick.choice(["p1", "p2", "p3", None]),
            "lot_id": pick.choice(["LOT-1", "lot 1", "LOT-2", "", None]),
            "serial": pick.choice(["SN-9", "sn 9", "SN-7", None]),
            "site": pick.choice(["Ward 3", None]),
            "country": pick.choice(["US", "IN"]),
            "event_on": pick.choice([date(2026, 10, 1) + timedelta(days=pick.randint(0, 60)), None]),
        }
        for _ in range(400)
    ]
    every = [(i, j) for i in range(len(fields)) for j in range(i + 1, len(fields))]
    found = [(i, j) for i, j in every if rules.duplicate_reasons(fields[i], fields[j])]
    candidates = candidate_pairs(fields)
    assert [(i, j) for i, j in candidates if rules.duplicate_reasons(fields[i], fields[j])] == found
    assert len(candidates) < len(every) / 3


def test_an_upload_the_person_abandons_is_not_a_server_error():
    """A browser that leaves during an upload made the import routes answer 500 with a traceback (seen in the DEV-10
    journeys under load): it counted against the server-error target and would alert. It is a 400 now."""
    import asyncio

    from fastapi import HTTPException
    from starlette.requests import Request

    from backend.app.request_body import read_limited

    async def receive():
        return {"type": "http.disconnect"}

    request = Request({"type": "http", "method": "POST", "headers": []}, receive)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(read_limited(request, 1024))
    assert refused.value.status_code == 400 and refused.value.detail["code"] == "UPLOAD_INTERRUPTED"
