"""0.10.88 (DEV-10): Getting started's ten steps on a trial's own data, as the browser journey walks them."""

from types import SimpleNamespace

from backend.app.trial.one_story import in_order, steps_done


def test_an_imported_complaint_not_flagged_for_triage_does_not_hold_the_story_at_step_2():
    """An imported complaint with no harm and no malfunction is not on the triage list ("Triage: not needed" on its
    page), so it has no triage form: step 2 waited for a triage record that could never be made, its button opened
    the page already open, and every later step stayed "done earlier", never ticked."""
    signed = SimpleNamespace(signed_at="2026-11-04", superseded_by=None, conclusion="NOT_REPORTABLE")
    raw = steps_done({"call": "x", "records": "x", "trends": "x"}, False, [signed], None, triage_needed=False)
    ticked, earlier = in_order(raw)
    assert raw[1] == "skip"
    assert ticked == [True, "skip", True, True, "skip", "skip", "skip", "skip", True, True]
    assert not any(earlier)


def test_a_complaint_on_the_triage_list_still_needs_its_triage_record():
    assert steps_done({"call": "x"}, False, [], None, triage_needed=True)[:2] == [True, False]
    assert steps_done({"call": "x"}, False, [], None)[:2] == [True, False]


# The your-data journey (e2e/your-data-journey.spec.ts) walked two uploads: the first complaint's ten steps done, a
# second, more urgent, then concluded "not reportable". Its clock closed with that conclusion, so the walkthrough went
# back to the first complaint in the middle of the second's steps, and the first's steps 9 and 10 read as not done:
# the marks were kept for one complaint per run, and the second's replaced them.


def _row(name: str, *, death=False, serious=False, malfunction=True):
    return SimpleNamespace(
        id=name, death=death, serious_injury=serious, malfunction=malfunction, patient_involved=False
    )


def test_marks_on_an_earlier_complaint_are_kept_when_the_story_moves_on():
    from datetime import datetime, timezone

    from backend.app.trial.one_story import record_mark, team_marks

    request = SimpleNamespace(profile={})
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    for step in ("call", "form", "records", "trends"):
        record_mark(request, "u1", "yours", "A", step, now)
    record_mark(request, "u1", "yours", "B", "call", now)
    assert set(team_marks(request, "yours", "A")) == {"call", "form", "records", "trends"}
    assert set(team_marks(request, "yours", "B")) == {"call"}
    # Back on A, a mark adds to what A had; B's stay too.
    record_mark(request, "u1", "yours", "A", "call", now)
    assert set(team_marks(request, "yours", "A")) == {"call", "form", "records", "trends"}
    assert set(team_marks(request, "yours", "B")) == {"call"}


def test_the_walkthrough_stays_on_the_complaint_under_way_until_its_last_step():
    from datetime import datetime, timezone

    from backend.app.trial.one_story import record_mark, under_way

    request = SimpleNamespace(profile={})
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    first, second = _row("A"), _row("B")
    assert under_way(request, "yours", [first, second]) is None
    record_mark(request, "u1", "yours", "B", "call", now)
    # B's walkthrough is under way: it is followed, whatever the clocks now say.
    assert under_way(request, "yours", [first, second]) is second
    # A more serious complaint still takes over (a death imported meanwhile).
    assert under_way(request, "yours", [first, second, _row("C", death=True)]) is None
    # A complaint no longer there is not followed.
    assert under_way(request, "yours", [first]) is None
    # Its last step done, the walkthrough follows the most urgent again.
    record_mark(request, "u1", "yours", "B", "trends", now)
    assert under_way(request, "yours", [first, second]) is None
