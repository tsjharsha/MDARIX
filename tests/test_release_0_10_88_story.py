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
