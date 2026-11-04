"""0.10.85, first of round D3 (the owner's report on live 0.10.84): Getting started's story always works.

The story's ticks read as a story: a step is ticked only once the steps before it are; work the team did out of order
is flagged "done earlier by your team"; the count, the ticks and the current step agree.
"""

from __future__ import annotations

import uuid

import pytest

from tests.test_free_trial import _approved_trial_client
from tests.test_release_c3_0_10_75 import _purge

pytestmark = pytest.mark.db


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def test_the_story_ticks_in_order_and_flags_work_done_out_of_order():
    """Owner report on 0.10.84: "1 of 10 done", step 1 current, step 2 not done, yet step 3 "Tree" ticked (a tree the
    team signed before the triage). The local sample read "5 of 10 done" with Form open and Fill ticked."""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from backend.app.trial.one_story import in_order, steps_done

    signed = SimpleNamespace(signed_at=datetime.now(timezone.utc), superseded_by=None, conclusion="REPORTABLE")
    # A signed tree, no triage, no marks: the call was read (later work shows it); triage waits; the tree and the
    # decision are the team's, out of order.
    raw = steps_done({}, False, [signed], None)
    ticked, earlier = in_order(raw)
    assert ticked[:4] == [True, False, False, False] and earlier[:4] == [False, False, True, True]
    assert sum(value is True for value in ticked) == 1
    # A report past "Created" (fields complete): its form was opened, so Form is ticked with Fill.
    ticked, earlier = in_order(steps_done({}, True, [signed], "COMPLETE"))
    assert ticked[:6] == [True] * 6 and not any(earlier)
    # "Not needed" stays not needed after a gap, and is no tick.
    no = SimpleNamespace(signed_at=datetime.now(timezone.utc), superseded_by=None, conclusion="NOT_REPORTABLE")
    ticked, earlier = in_order(steps_done({}, False, [no], None))
    assert ticked[4:8] == ["skip"] * 4 and ticked[1] is False and earlier[2:4] == [True, True]


def test_the_story_count_ticks_and_current_step_agree(trial):
    run = _ok(trial["user"].get("/api/v1/trial/one-story"))["sample"]
    ticks = [step["done"] for step in run["steps"]]
    current = run["current"]
    assert all(step["done"] or step["skipped"] for step in run["steps"][:current])
    assert current == len(ticks) or not (ticks[current] or run["steps"][current]["skipped"])
    assert not any(step["earlier"] for step in run["steps"][:current])
