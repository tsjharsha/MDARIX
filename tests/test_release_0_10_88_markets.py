"""0.10.88, owner decision OD-2: "United Kingdom" or "UK" is asked, Great Britain or Northern Ireland."""

import pytest

from backend.app.reportability import facts, markets

DEATH = {"death": True, "serious_injury": False, "malfunction": True, "patient_involved": True}


def test_the_united_kingdom_names_no_market_until_the_person_chooses_its_part():
    for name in ("United Kingdom", "UK", "united kingdom", "U.K."):
        assert markets.markets_of(name) == [], name
        assert markets.market_of(name) is None, name
    assert markets.market_of("Great Britain") == markets.GB
    assert markets.market_of("England") == markets.GB
    assert markets.market_of("Northern Ireland") == markets.EU_NI


def test_the_complaint_page_asks_great_britain_or_northern_ireland():
    needs = facts.needed({**DEATH, "country": "United Kingdom"}, awareness_given=True)
    assert [item["fact"] for item in needs] == [facts.COUNTRY]
    assert needs[0]["choices"] == ["Great Britain", "Northern Ireland"]
    assert "Northern Ireland follows the EU MDR" in needs[0]["message"]
    assert facts.needed({**DEATH, "country": "Northern Ireland"}, awareness_given=True) == []
    assert facts.needed({**DEATH, "country": "Great Britain"}, awareness_given=True) == []
    assert not facts.country_known("UK") and facts.country_known("GB")


UK_CSV = (
    "complaint_id,product_id,description,event_date,awareness_date,received_date,country,"
    "patient_involved,serious_injury,death,malfunction\n"
    "UK-1,UK-PUMP,Patient died; pump free-flowed.,2026-10-01,2026-10-02,2026-10-02,United Kingdom,Y,N,Y,Y\n"
)


@pytest.mark.db
def test_a_uk_complaint_is_asked_its_part_and_northern_ireland_is_assessed_under_the_eu_mdr():
    import uuid

    from tests.test_free_trial import _approved_trial_client
    from tests.test_release_0_10_81 import _facts, _import, _ok, _purge, _watch

    user, approval, _ = _approved_trial_client()
    try:
        _import(user, UK_CSV)
        item = _watch(user, "UK-1")
        # Asked, with every market's provisional clock meanwhile; never read as Great Britain.
        assert [need["fact"] for need in item["needs"]] == ["COUNTRY"] and item["provisional"]
        assert item["needs"][0]["choices"] == ["Great Britain", "Northern Ireland"]
        assert item["clocks"] and "GB" not in [market["market"] for market in item["markets"]]
        refused = _facts(user, item["id"], country="UK")
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "COUNTRY_UK_PART_NEEDED"
        _ok(_facts(user, item["id"], country="Northern Ireland"))
        chosen = _watch(user, "UK-1")
        assert chosen["needs"] == [] and [market["market"] for market in chosen["markets"]] == ["EU_NI"]
    finally:
        _purge(uuid.UUID(approval["tenant_id"]))
