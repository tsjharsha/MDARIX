"""Column sorting of the platform administration lists covers every page, not only the page on screen.

Each list sent one page at a time takes ``sort`` (a column key) and ``order`` (asc/desc). Page 2 continues where page
1 stopped in that order, an unknown key keeps the list's usual order, and the parameters each list already took still
mean what they meant. Text is compared on rows this module creates (names differing only in their last letter), so the
database's collation and Python agree on the expected order.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from tests.conftest import authenticated_client

CUSTOMER_ACCOUNTS = "/api/v1/platform-admin/customer-accounts"
TENANTS = "/api/v1/platform-admin/tenants"
SUBSCRIPTIONS = "/api/v1/platform-admin/customers"
CUSTOMER_USERS = "/api/v1/platform-admin/customer-users"
RUNS = "/api/v1/platform-admin/console/integration-runs"
AUDIT = "/api/v1/platform-admin/console/audit"


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture(scope="module")
def prefix():
    return f"SRT{uuid.uuid4().hex[:6].upper()}"


@pytest.fixture(scope="module")
def tenants(platform, prefix):
    """Three new customers, each with one tenant: names "Sort Test <prefix> A", "... B", "... C", created in order."""
    created = []
    for suffix in "ABC":
        response = platform.post(
            SUBSCRIPTIONS,
            json={
                "company_name": f"Sort Test {prefix} {suffix}",
                "tenant_code": f"{prefix}{suffix}",
                "plan_code": "STARTER",
            },
        )
        assert response.status_code == 200, response.text
        created.append(response.json())
    return created


def _names(prefix, suffixes):
    return [f"Sort Test {prefix} {suffix}" for suffix in suffixes]


def _add(*rows):
    db = SessionLocal()
    try:
        for row in rows:
            db.add(row)
        db.commit()
        for row in rows:
            db.refresh(row)
            db.expunge(row)
    finally:
        db.close()


def _get(client, path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _when(value):
    return datetime.fromisoformat(value) if value else None


def _comparable(value):
    return value.casefold() if isinstance(value, str) else value


def _assert_ordered(values, descending=False):
    present = [value for value in values if value is not None and value != ""]
    assert values[: len(present)] == present, f"empty values come last: {values}"
    keys = [_comparable(value) for value in present]
    assert keys == sorted(keys, reverse=descending), values


def _pages(client, path, sort, order="asc", value=None, **params):
    """Pages 1 and 2 (two rows each) in the requested order. They must be the start of the same order as one big page,
    the last row of page 1 must not come after the first row of page 2, and (with ``value``) the values are in order."""
    first = _get(client, path, sort=sort, order=order, page=1, page_size=2, **params)["items"]
    second = _get(client, path, sort=sort, order=order, page=2, page_size=2, **params)["items"]
    whole = _get(client, path, sort=sort, order=order, page=1, page_size=100, **params)["items"]
    assert [row["id"] for row in first + second] == [row["id"] for row in whole[:4]]
    if value:
        _assert_ordered([value(row) for row in whole], descending=order == "desc")
        if first and second and value(first[-1]) is not None and value(second[0]) is not None:
            last, next_first = _comparable(value(first[-1])), _comparable(value(second[0]))
            assert (last >= next_first) if order == "desc" else (last <= next_first)
    return first, second


def _ids(client, path, **params):
    return [row["id"] for row in _get(client, path, page=1, page_size=100, **params)["items"]]


# Customer directory --------------------------------------------------------------------------------------------


def test_customer_directory_sorts_every_page_by_name(platform, tenants, prefix):
    first, second = _pages(platform, CUSTOMER_ACCOUNTS, "customer", "asc", q=prefix)
    assert [row["name"] for row in first + second] == _names(prefix, "ABC")
    first, second = _pages(platform, CUSTOMER_ACCOUNTS, "customer", "desc", q=prefix)
    assert [row["name"] for row in first] == _names(prefix, "CB") and [row["name"] for row in second] == _names(
        prefix, "A"
    )
    # A leading minus also means descending.
    descending = _get(platform, CUSTOMER_ACCOUNTS, sort="-customer", q=prefix)["items"]
    assert [row["name"] for row in descending] == _names(prefix, "CBA")


def test_customer_directory_sorts_by_dates_and_counts(platform, tenants, prefix):
    first, second = _pages(
        platform, CUSTOMER_ACCOUNTS, "created_at", "asc", lambda row: _when(row["created_at"]), q=prefix
    )
    assert [row["name"] for row in first + second] == _names(prefix, "ABC")
    _pages(platform, CUSTOMER_ACCOUNTS, "created_at", "desc", lambda row: _when(row["created_at"]))
    _pages(platform, CUSTOMER_ACCOUNTS, "tenants", "desc", lambda row: row["tenant_count"])
    _pages(platform, CUSTOMER_ACCOUNTS, "admins", "asc", lambda row: row["active_admins"])
    _pages(platform, CUSTOMER_ACCOUNTS, "status", "asc", q=prefix)


def test_customer_directory_unknown_key_keeps_the_usual_order(platform, tenants, prefix):
    usual = _ids(platform, CUSTOMER_ACCOUNTS, q=prefix)
    assert _ids(platform, CUSTOMER_ACCOUNTS, q=prefix, sort="no_such_column", order="desc") == usual
    assert [row["name"] for row in _get(platform, CUSTOMER_ACCOUNTS, q=prefix)["items"]] == _names(prefix, "ABC")


# Tenant directory ----------------------------------------------------------------------------------------------


def test_tenant_directory_sorts_every_page(platform, tenants, prefix):
    first, second = _pages(platform, TENANTS, "tenant", "asc", q=prefix)
    assert [row["name"] for row in first + second] == _names(prefix, "ABC")
    first, second = _pages(platform, TENANTS, "customer", "desc", q=prefix)
    assert [row["customer_name"] for row in first + second] == _names(prefix, "CBA")
    _pages(platform, TENANTS, "environments", "desc", lambda row: row["environment_count"])
    _pages(platform, TENANTS, "seat_usage", "asc", lambda row: row["seat_usage"])
    _pages(platform, TENANTS, "last_activity", "desc", lambda row: _when(row["last_activity"]))
    _pages(platform, TENANTS, "plan", "asc", q=prefix)
    _pages(platform, TENANTS, "region", "asc")


def test_tenant_directory_keeps_its_existing_sort_values(platform, tenants, prefix):
    descending = _get(platform, TENANTS, q=prefix, sort="name", order="desc")["items"]
    assert [row["name"] for row in descending] == _names(prefix, "CBA")
    for sort in ("status", "created_at", "region"):
        assert len(_get(platform, TENANTS, q=prefix, sort=sort)["items"]) == 3
    # Unknown keys, and no sort at all, keep the usual order (by name).
    assert [row["name"] for row in _get(platform, TENANTS, q=prefix, sort="no_such_column")["items"]] == _names(
        prefix, "ABC"
    )
    assert [row["name"] for row in _get(platform, TENANTS, q=prefix)["items"]] == _names(prefix, "ABC")


def test_tenant_directory_filters_before_paging(platform, tenants, prefix):
    everything = _get(platform, TENANTS, q=prefix)
    healthy = _get(platform, TENANTS, q=prefix, health="HEALTHY")
    review = _get(platform, TENANTS, q=prefix, health="REVIEW")
    assert all(row["health_status"] == "HEALTHY" for row in healthy["items"])
    assert all(row["health_status"] == "REVIEW" for row in review["items"])
    # The total counts exactly the rows sent, so the pager and the page agree.
    assert healthy["total"] == len(healthy["items"]) and review["total"] == len(review["items"])
    assert healthy["total"] + review["total"] == everything["total"] == 3
    over = _get(platform, TENANTS, q=prefix, seat_status="OVER")
    assert over["items"] == [] and over["total"] == 0


# Plans & Licensing: subscriptions ------------------------------------------------------------------------------


def test_subscriptions_sort_every_page(platform, tenants, prefix):
    first, second = _pages(platform, SUBSCRIPTIONS, "tenant", "asc", q=prefix)
    assert [row["name"] for row in first + second] == _names(prefix, "ABC")
    first, second = _pages(platform, SUBSCRIPTIONS, "tenant", "desc", q=prefix)
    assert [row["name"] for row in first + second] == _names(prefix, "CBA")
    _pages(platform, SUBSCRIPTIONS, "seats", "desc", lambda row: row["seat_usage"])
    _pages(platform, SUBSCRIPTIONS, "created_at", "asc", lambda row: _when(row["created_at"]))
    _pages(platform, SUBSCRIPTIONS, "period", "asc", lambda row: _when(row["expires_at"]))
    _pages(platform, SUBSCRIPTIONS, "plan", "asc", q=prefix)


def test_subscriptions_keep_their_existing_sort_values(platform, tenants, prefix):
    descending = _get(platform, SUBSCRIPTIONS, q=prefix, sort="tenant_key", order="desc")["items"]
    _assert_ordered([row["tenant_key"] for row in descending], descending=True)
    assert len(descending) == 3
    by_name = _get(platform, SUBSCRIPTIONS, q=prefix, sort="name")["items"]
    assert [row["name"] for row in by_name] == _names(prefix, "ABC")
    assert _ids(platform, SUBSCRIPTIONS, q=prefix, sort="no_such_column") == [row["id"] for row in by_name]


def test_subscriptions_seat_filters_apply_before_paging(platform, tenants, prefix):
    over = _get(platform, SUBSCRIPTIONS, q=prefix, seat_status="OVER")
    assert over["items"] == [] and over["total"] == 0
    available = _get(platform, SUBSCRIPTIONS, q=prefix, seat_status="AVAILABLE")
    assert available["total"] == len(available["items"]) == 3
    at_least = _get(platform, SUBSCRIPTIONS, q=prefix, seat_min="1000000")
    assert at_least["items"] == [] and at_least["total"] == 0
    at_most = _get(platform, SUBSCRIPTIONS, q=prefix, seat_max="1000000")
    assert at_most["total"] == len(at_most["items"]) == 3
    assert platform.get(SUBSCRIPTIONS, params={"seat_min": "many"}).status_code == 422


# Identity & Access: customer users -----------------------------------------------------------------------------


def test_customer_users_sort_every_page(platform):
    _pages(platform, CUSTOMER_USERS, "created_at", "asc", lambda row: _when(row["created_at"]))
    _pages(platform, CUSTOMER_USERS, "created_at", "desc", lambda row: _when(row["created_at"]))
    _pages(platform, CUSTOMER_USERS, "user", "asc")
    _pages(platform, CUSTOMER_USERS, "organization", "desc")
    _pages(platform, CUSTOMER_USERS, "status", "asc")
    _pages(platform, CUSTOMER_USERS, "role", "asc")


def test_customer_users_unknown_key_keeps_the_usual_order(platform):
    assert _ids(platform, CUSTOMER_USERS, sort="no_such_column", order="desc") == _ids(platform, CUSTOMER_USERS)


# Integrations: runs and reconciliation -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def runs(tenants):
    tenant = tenants[0]
    now = datetime.now(timezone.utc)
    rows = [
        ConnectorRun(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant["id"]),
            connection_id=f"conn-{tenant['tenant_key'].lower()}",
            source_system=source,
            status="SUCCEEDED",
            records_received=received,
            records_accepted=received,
            reconciliation_status=reconciliation,
            started_at=now - timedelta(minutes=minutes),
            created_at=now,
        )
        for source, received, minutes, reconciliation in (
            ("Alpha", 30, 3, "MATCH"),
            ("Bravo", 10, 2, "MISMATCH"),
            ("Charlie", 20, 1, "MATCH"),
        )
    ]
    _add(*rows)
    return tenant


def test_integration_runs_sort_every_page(platform, runs):
    first, second = _pages(platform, RUNS, "records", "asc", lambda row: row["records_received"], tenant_id=runs["id"])
    assert [row["records_received"] for row in first + second] == [10, 20, 30]
    first, second = _pages(platform, RUNS, "source", "desc", tenant_id=runs["id"])
    assert [row["source_system"] for row in first + second] == ["Charlie", "Bravo", "Alpha"]
    first, second = _pages(platform, RUNS, "when", "asc", lambda row: _when(row["started_at"]), tenant_id=runs["id"])
    assert [row["source_system"] for row in first + second] == ["Alpha", "Bravo", "Charlie"]
    _pages(platform, RUNS, "when", "desc", lambda row: _when(row["started_at"]))
    _pages(platform, RUNS, "tenant", "asc")


def test_reconciled_runs_sort_every_page(platform, runs):
    first, second = _pages(
        platform,
        RUNS,
        "reconciliation",
        "desc",
        lambda row: row["reconciliation_status"],
        tenant_id=runs["id"],
        reconciled="true",
    )
    assert [row["reconciliation_status"] for row in first + second] == ["MISMATCH", "MATCH", "MATCH"]


def test_integration_runs_unknown_key_keeps_newest_first(platform, runs):
    newest_first = _get(platform, RUNS, tenant_id=runs["id"])["items"]
    assert [row["source_system"] for row in newest_first] == ["Charlie", "Bravo", "Alpha"]
    assert _ids(platform, RUNS, tenant_id=runs["id"], sort="no_such_column", order="asc") == [
        row["id"] for row in newest_first
    ]


# Security: audit trail -----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def audit_events(tenants, prefix):
    tenant = tenants[1]
    now = datetime.now(timezone.utc)
    _add(
        *[
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(tenant["id"]),
                action=f"SORTTEST{prefix}{suffix}",
                entity_type="SortTest",
                reason=f"Reason {suffix}",
                created_at=now - timedelta(minutes=minutes),
            )
            for suffix, minutes in (("A", 3), ("B", 2), ("C", 1))
        ]
    )
    return {"tenant_id": tenant["id"], "q": f"sorttest{prefix.lower()}"}


def test_audit_trail_sorts_every_page(platform, audit_events, prefix):
    actions = [f"SORTTEST{prefix}{suffix}" for suffix in "ABC"]
    first, second = _pages(platform, AUDIT, "what", "asc", **audit_events)
    assert [row["action"] for row in first + second] == actions
    first, second = _pages(platform, AUDIT, "when", "asc", lambda row: _when(row["at"]), **audit_events)
    assert [row["action"] for row in first + second] == actions
    first, second = _pages(platform, AUDIT, "why", "desc", **audit_events)
    assert [row["reason"] for row in first + second] == ["Reason C", "Reason B", "Reason A"]
    _pages(platform, AUDIT, "when", "desc", lambda row: _when(row["at"]))
    _pages(platform, AUDIT, "who", "asc", tenant_id=audit_events["tenant_id"])
    _pages(platform, AUDIT, "tenant", "asc", **audit_events)


def test_audit_trail_unknown_key_keeps_newest_first(platform, audit_events, prefix):
    newest_first = _get(platform, AUDIT, **audit_events)["items"]
    assert [row["action"] for row in newest_first] == [f"SORTTEST{prefix}{suffix}" for suffix in "CBA"]
    assert _ids(platform, AUDIT, sort="no_such_column", order="asc", **audit_events) == [
        row["id"] for row in newest_first
    ]
