"""The trend check and the count rule on real records (0.10.63, quality plan stage 2, S2-S5, J26, J27): an event linked
from several records counts once, a complaint dated in the future is not counted, a version younger than the window is
expected only its own days, the result allows for every group checked at once, a lasting rise since a version change
stays visible, and a single-use product is not counted per unit ever released.

Each test runs in a fresh organization of its own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion
from backend.app.db.models.intake import RecordLink
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


@pytest.fixture
def tenant():
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        customer, row = build_customer_tenant(
            db=db,
            tenant_key=f"TRENDSTAT_{uuid.uuid4().hex[:8].upper()}",
            name="Trend statistics",
            status="ACTIVE",
            now=NOW,
        )
        db.add(customer)
        db.add(row)
        db.commit()
        tenant_id = row.id
    try:
        yield tenant_id
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:trend-statistics-cleanup")


def _product(tenant_id, *, name: str = "Signal Pump", released: tuple = (400,), lots: tuple = ()) -> dict:
    """A product with one version per entry of ``released`` (days ago, oldest first: Rev A, Rev B, ...) and, for the
    last version, lots ``(days ago, quantity)``."""
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"TS-P-{tag}",
            name=f"{name} {tag}",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(product)
        db.flush()
        versions = []
        for index, days in enumerate(released):
            version = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=product.id,
                version_identifier=f"Rev {'ABCD'[index]}",
                release_timestamp=NOW - timedelta(days=days),
                created_at=NOW,
                updated_at=NOW,
            )
            db.add(version)
            db.flush()
            versions.append(str(version.id))
        for index, (days, quantity) in enumerate(lots):
            db.add(
                LotBatch(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lot_identifier=f"TS-L-{tag}-{index}",
                    product_version_id=uuid.UUID(versions[-1]),
                    quantity=quantity,
                    effective_timestamp=NOW - timedelta(days=days),
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        db.commit()
        return {"product": str(product.id), "versions": versions, "name": product.name}


def _complaints(tenant_id, item: dict, days_ago, *, version: int = -1) -> list[str]:
    ids = []
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for days in days_ago:
            moment = NOW - timedelta(days=days)
            row = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=f"TS-C-{uuid.uuid4().hex[:10].upper()}",
                product_id=uuid.UUID(item["product"]),
                product_version_id=uuid.UUID(item["versions"][version]),
                event_timestamp=moment,
                complaint_timestamp=moment,
                description="Occlusion alarm during infusion",
                problem_code="OCCLUSION",
                status="open",
                created_at=min(moment, NOW),
                updated_at=min(moment, NOW),
            )
            db.add(row)
            ids.append(str(row.id))
        db.commit()
    return ids


def _link(tenant_id, left: str, right: str) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(
            RecordLink(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                left_kind="COMPLAINT",
                left_id=uuid.UUID(left),
                right_kind="COMPLAINT",
                right_id=uuid.UUID(right),
                state="LINKED",
                reason="The same event reported by the ward and by the distributor",
                decided_by="test",
                decided_at=NOW,
                created_at=NOW,
            )
        )
        db.commit()


def _board(tenant_id, **kwargs) -> dict:
    from backend.app.signals.insight import trend_board

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return trend_board(db, tenant_id, today=TODAY, **kwargs)


def _item(board: dict, item: dict, version: int = -1) -> dict:
    return next(
        row for row in board["items"] if row["key"].startswith(f"{item['product']}|{item['versions'][version]}|")
    )


def _would_raise(tenant_id) -> list[str]:
    from backend.app.signals.detection import detect

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return detect(db, tenant_id, apply=False)["created"]


def test_an_event_linked_from_several_records_counts_once(tenant):
    """S2: one complaint and one event reported three times are two events in the last 30 days, not four; an event whose
    earliest record is older counts there, once. Before 0.10.63: a significant rise (5 against 1.2) and a signal."""
    item = _product(tenant)
    _complaints(tenant, item, (40, 70, 100, 130, 160, 190))  # history: 6 in 180 days, 1.0 expected in 30
    _complaints(tenant, item, (8,))
    first, second, third = _complaints(tenant, item, (10, 5, 3))
    _link(tenant, first, second)
    _link(tenant, third, second)  # linked through the second record: one event
    older, later = _complaints(tenant, item, (45, 2))
    _link(tenant, later, older)  # the event happened 45 days ago
    found = _item(_board(tenant), item)
    assert (found["recent"], found["history"]) == (2, 7)
    assert found["result"] == "TOO_FEW" and found["linked_records"] == 3
    assert len(found["recent_complaints"]) == 5  # every record stays listed as evidence
    assert "an event linked from several records counts once" in _board(tenant)["note"]
    assert _would_raise(tenant) == []


def test_a_complaint_dated_in_the_future_is_not_counted(tenant):
    """S5: three complaints dated next week are in neither window and raise no signal yet."""
    item = _product(tenant)
    _complaints(tenant, item, (40, 70, 100, 130, 160, 190))
    _complaints(tenant, item, (4, -3, -5, -7))
    found = _item(_board(tenant), item)
    assert found["recent"] == 1 and found["result"] == "TOO_FEW"
    assert _would_raise(tenant) == []


def test_a_version_younger_than_the_window_is_expected_only_its_own_days(tenant):
    """S3: Rev B, released 10 days ago, against Rev A's 18 complaints in 180 days: 1.1 expected in its 11 days (3.0
    over 30 days before 0.10.63, "In line")."""
    item = _product(tenant, released=(400, 10))
    _complaints(tenant, item, [15 + 10 * n for n in range(18)], version=0)  # 18 in the 180 days before Rev B
    _complaints(tenant, item, (1, 3, 6, 9))
    found = _item(_board(tenant), item)
    assert found["baseline"] == "PREVIOUS_VERSION" and found["recent_days"] == 11
    assert found["expected"] == pytest.approx(1.1) and found["result"] == "ELEVATED"
    assert "in the 11 days since its release" in found["sentence"]


def test_the_result_allows_for_every_group_checked_and_reads_the_same_everywhere(tenant):
    """S4: four groups tested at once; the one at p 0.004 is "Higher than usual" (adjusted 0.015), not a significant
    rise, on the board, filtered by its product, for its signal and in Readiness."""
    from backend.app.readiness_home.service import trends_without_action_rows
    from backend.app.signals.insight import trend_for_signal

    items = [_product(tenant) for _ in range(4)]
    for index, item in enumerate(items):
        _complaints(tenant, item, (40, 70, 100, 130, 160, 190))
        _complaints(tenant, item, (2, 5, 9, 14, 20) if index == 0 else (3, 8, 13))
    board = _board(tenant)
    found = _item(board, items[0])
    assert found["p_value"] == pytest.approx(0.0037, abs=1e-4)
    assert found["p_adjusted"] == pytest.approx(0.0146, abs=5e-5) and found["groups_tested"] == 4
    assert found["result"] == "ELEVATED" and board["summary"]["groups_tested"] == 4
    assert "allowing for the 4 groups assessed" in found["sentence"]
    alone = _item(_board(tenant, product_id=uuid.UUID(items[0]["product"])), items[0])
    assert (alone["p_adjusted"], alone["result"]) == (found["p_adjusted"], found["result"])
    with SessionLocal() as db:
        bind_tenant(db, tenant)
        signal = SimpleNamespace(
            tenant_id=tenant,
            product_id=uuid.UUID(items[0]["product"]),
            product_version_id=uuid.UUID(items[0]["versions"][0]),
            problem_key="OCCLUSION",
        )
        for_signal = trend_for_signal(db, signal, today=TODAY)
        assert (for_signal["p_adjusted"], for_signal["result"]) == (found["p_adjusted"], found["result"])
        _, rising = trends_without_action_rows(db, tenant, TODAY)
        assert rising == []  # Readiness counts significant rises from the same adjusted results


def test_a_lasting_rise_since_the_change_stays_visible(tenant):
    """J26: Rev B (200 days old) has run at 6 complaints a month since its release; against its own history that is
    "In line", against Rev A (1 a month) a significant rise. The stronger comparison is shown, saying which."""
    item = _product(tenant, released=(400, 200))
    _complaints(tenant, item, (205 + 30 * n for n in range(6)), version=0)  # Rev A: 6 in its last 180 days
    _complaints(tenant, item, [30 + 5 * n for n in range(34)])  # Rev B's own history: 34 in 170 days
    _complaints(tenant, item, (1, 5, 10, 15, 20, 25))
    found = _item(_board(tenant), item)
    assert found["baseline"] == "PREVIOUS_VERSION" and found["result"] == "SIGNIFICANT"
    assert found["also_compared"] == "its own history"
    assert "the stronger comparison is shown" in found["sentence"]


def test_a_single_use_product_is_counted_by_calendar_days(tenant):
    """J27: an infusion set's units are used up. Counted per unit ever released, doubling the lots made the rise read
    "In line" (6 against 4.0); by calendar days it is "Higher than usual" (6 against 2.0), and the board says why."""
    item = _product(tenant, name="Infusion set, single-use", lots=((400, 1000), (31, 1000)))
    _complaints(tenant, item, [35 + 14 * n for n in range(12)])  # 12 in the 180 days of history
    _complaints(tenant, item, (2, 6, 11, 16, 21, 26))
    board = _board(tenant)
    found = _item(board, item)
    assert found["basis"] == "TIME" and found["expected"] == pytest.approx(2.0)
    assert found["result"] == "ELEVATED" and found["basis_note"].startswith("Single-use or consumable product")
    assert board["basis"] == {"units": 0, "time": 0, "single_use": 1}
    # The same lots on a reusable product are counted per unit in the field, as before.
    pump = _product(tenant, name="Infusion pump", lots=((400, 1000), (31, 1000)))
    _complaints(tenant, pump, [35 + 14 * n for n in range(12)])
    _complaints(tenant, pump, (2, 6, 11, 16, 21, 26))
    reusable = _item(_board(tenant), pump)
    assert reusable["basis"] == "UNITS" and reusable["expected"] == pytest.approx(3.96, abs=0.01)
