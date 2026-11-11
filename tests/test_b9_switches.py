"""B9 step 17 (B9-26, B9-28): the four B9 switches, their defaults (B9-D18), the routes they refuse and the session
flags the screens follow."""

from __future__ import annotations

import pytest

from backend.app import feature_set
from tests.test_b4_register_api import viewer  # noqa: F401

pytestmark = pytest.mark.db

CHAIN = "/api/v1/reports/00000000-0000-0000-0000-000000000001/india-chain"


@pytest.mark.unit
def test_defaults_india_canada_importer_on_user_facility_off(monkeypatch):
    for name in feature_set.B9_SWITCHES:
        monkeypatch.delenv(name, raising=False)
    assert [feature_set.switched_on(name) for name in feature_set.B9_SWITCHES] == [True, True, True, False]
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")
    assert feature_set.switched_on("MDARIX_B9_INDIA") is False
    assert feature_set.switched_on("MDARIX_B9_US_USER_FACILITY") is True
    assert feature_set.switched_on(None) is True


@pytest.mark.unit
def test_the_india_routes_are_served_only_while_india_is_on(monkeypatch):
    assert feature_set.serves_path(CHAIN, "POST")
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert not feature_set.serves_path(CHAIN, "POST")
    assert feature_set.serves_path("/api/v1/reports/x/follow-ups", "POST")  # the US chain is not B9's


def test_the_session_names_each_switch_off_on_off(viewer, monkeypatch):  # noqa: F811
    def flags() -> dict:
        return viewer["client"].get("/api/v1/session/context").json()["b9"]

    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert flags()["india"] is False
    monkeypatch.setenv("MDARIX_B9_INDIA", "on")
    assert flags() == {"india": True, "canada": True, "us_importer": True, "us_user_facility": False}
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert flags()["india"] is False
