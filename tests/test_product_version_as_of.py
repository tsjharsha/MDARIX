"""A date never chooses a product version (owner, 12 Nov 2026, DB-1 "as of" fix): a unit built before a later release
keeps its own version, and an unknown one is said to be unknown, with the candidates."""

from datetime import datetime, timezone

import pytest

from backend.app.product360.service import Product360Service

pytestmark = pytest.mark.unit

REV_A = {"id": "a", "version_identifier": "Rev A", "release_timestamp": datetime(2026, 1, 10, tzinfo=timezone.utc)}
REV_B = {"id": "b", "version_identifier": "Rev B", "release_timestamp": datetime(2026, 3, 1, tzinfo=timezone.utc)}
REV_C = {"id": "c", "version_identifier": "Rev C", "release_timestamp": datetime(2026, 6, 1, tzinfo=timezone.utc)}
VERSIONS = [REV_A, REV_B, REV_C]
# A complaint about a unit built with Rev A, received after Rev B was released.
EVENT = datetime(2026, 4, 2, tzinfo=timezone.utc)


def test_the_event_date_does_not_pick_the_latest_release_for_a_unit_built_earlier():
    assert Product360Service().select_version(VERSIONS, None, EVENT) is None


def test_the_recorded_version_is_kept_whatever_the_date():
    assert Product360Service().select_version(VERSIONS, "Rev A", EVENT) is REV_A


def test_an_unknown_unit_version_is_said_to_be_unknown_with_the_candidates():
    limitation = Product360Service.version_not_known(VERSIONS, EVENT)
    assert limitation["code"] == "VERSION_NOT_KNOWN_FOR_UNIT"
    assert limitation["description"].startswith("Version not known for this unit")
    assert [v["version_identifier"] for v in limitation["candidate_versions"]] == ["Rev A", "Rev B"]


def test_without_a_date_the_product_page_still_opens_on_the_latest_version():
    assert Product360Service().select_version(VERSIONS, None, None) is REV_C
