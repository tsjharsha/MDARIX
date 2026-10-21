"""The support-access rule on its own (backend/app/support_access.py): what a scope may name, and exactly when a
grant opens an area of an organization's data. No database: the rule is a pure function of the grant and the time."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app import support_access as access
from backend.app.support_access import ScopeInvalid, SupportScope, evaluate

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
STAFF, TENANT = uuid.uuid4(), uuid.uuid4()


def _grant(**overrides):
    values = {
        "tenant_id": TENANT,
        "platform_user_id": STAFF,
        "status": access.APPROVED,
        "customer_decided_by": uuid.uuid4(),
        "starts_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(hours=1),
        "scope": {"areas": [access.CONFIGURATION, access.AUDIT], "write": False},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _verdict(grant, area=access.CONFIGURATION, *, write=False, user=STAFF, tenant=TENANT, now=NOW):
    return evaluate(grant, platform_user_id=user, tenant_id=tenant, area=area, write=write, now=now)


def test_a_scope_names_known_areas_and_says_whether_changes_are_allowed():
    scope = SupportScope.parse({"areas": ["configuration", " AUDIT "], "write": True})
    assert scope.areas == {access.CONFIGURATION, access.AUDIT} and scope.write
    assert scope.as_dict() == {"areas": ["AUDIT", "CONFIGURATION"], "write": True}
    assert [item["code"] for item in scope.describe()] == [access.CONFIGURATION, access.AUDIT]  # in AREAS order
    assert SupportScope.parse({"areas": [access.PEOPLE]}).write is False  # read-only unless asked
    for invalid in (
        None,
        {},
        {"areas": []},
        {"areas": ["EVERYTHING"]},
        {"areas": [access.AUDIT], "write": "yes"},
        {"areas": [access.AUDIT], "customer_360": True},  # the scope of the old request form
        {"areas": "AUDIT"},
    ):
        with pytest.raises(ScopeInvalid):
            SupportScope.parse(invalid)
    # A grant stored before areas existed covers nothing at all.
    assert SupportScope.stored({"customer_360": True, "read_only": True}).areas == frozenset()


def test_a_grant_opens_only_its_areas_for_its_person_in_its_organization_inside_its_window():
    grant = _grant()
    assert _verdict(grant) == "ALLOWED"
    assert _verdict(grant, access.AUDIT) == "ALLOWED"
    assert _verdict(grant, access.PEOPLE) == "AREA_NOT_GRANTED"
    assert _verdict(grant, access.DATA_EXPORT) == "AREA_NOT_GRANTED"
    assert _verdict(grant, write=True) == "READ_ONLY"
    assert _verdict(_grant(scope={"areas": [access.CONFIGURATION], "write": True}), write=True) == "ALLOWED"
    assert _verdict(grant, user=uuid.uuid4()) == "NOT_THIS_GRANT"
    assert _verdict(grant, tenant=uuid.uuid4()) == "NOT_THIS_GRANT"
    assert _verdict(grant, now=NOW - timedelta(hours=2)) == "NOT_YET_STARTED"
    assert _verdict(grant, now=NOW + timedelta(hours=1)) == "EXPIRED"  # the end is exclusive
    assert _verdict(None) == "NO_GRANT"


def test_only_the_customer_s_approval_opens_anything():
    # Approved by MDARIX only, as every grant was before md38: never enough.
    assert _verdict(_grant(customer_decided_by=None)) == "NOT_APPROVED_BY_CUSTOMER"
    for status in (access.PENDING, access.AWAITING_CUSTOMER, access.DENIED, access.REVOKED, access.EXPIRED):
        assert _verdict(_grant(status=status)) == "NOT_APPROVED_BY_CUSTOMER", status


def test_naive_stored_times_are_read_as_utc():
    grant = _grant(
        starts_at=(NOW - timedelta(hours=1)).replace(tzinfo=None),
        expires_at=(NOW + timedelta(hours=1)).replace(tzinfo=None),
    )
    assert _verdict(grant) == "ALLOWED"


def test_every_area_has_words_for_the_customer():
    assert set(access.AREAS) == {access.CONFIGURATION, access.AUDIT, access.PEOPLE, access.RECORDS, access.DATA_EXPORT}
    assert all(":" in label for label in access.AREAS.values())  # "Name: what it covers"
    assert access.OPEN == {access.PENDING, access.AWAITING_CUSTOMER, access.APPROVED}
