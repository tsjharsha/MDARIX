"""A CAPA's effectiveness check as the Product Lifecycle Twin reads it: a signed result is never read as planned."""

from backend.app.product360.links import check_state


def test_a_signed_inconclusive_round_reads_inconclusive_not_planned():
    state = check_state({"check_status": "INCONCLUSIVE", "planned_on": "2027-01-31", "signed_by": "Meera Nair"})
    assert state["state"] == "INCONCLUSIVE"
    assert state["label"] == "Inconclusive, signed by Meera Nair"


def test_planned_and_none_are_unchanged():
    assert check_state({"check_status": "PLANNED", "planned_on": "2027-01-31"})["state"] == "PLANNED"
    assert check_state({"check_status": "EFFECTIVE", "signed_by": "A"})["label"] == "Effective, signed by A"
    assert check_state({})["state"] == "NONE"
