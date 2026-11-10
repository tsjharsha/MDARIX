# ruff: noqa: F811 (the imported "org" fixture is a test argument)
"""PV-1 (0.10.95): a case never borrows a version. The workspace, the legacy decision and the legacy brief use the case's
one version only when the scope names exactly one and every included complaint carries it (F3, F3c)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_case_workflow import _open, _seed, org  # noqa: F401, F811 (org is a fixture)

pytestmark = pytest.mark.db


def _unknown_version_complaints(tenant_id, product_id: str, count: int = 2) -> list[str]:
    now = datetime.now(timezone.utc)
    ids = []
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for _ in range(count):
            row = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=f"PV-C-{uuid.uuid4().hex[:10].upper()}",
                product_id=uuid.UUID(product_id),
                product_version_id=None,
                event_timestamp=now,
                description="Alarm, version not known",
                severity="MALFUNCTION",
                status="open",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            ids.append(str(row.id))
        db.commit()
    return ids


def _workspace(client, case_id: str) -> dict:
    found = client.get(f"/api/v1/investigations/{case_id}/workspace", params={"include_retrieval": False})
    assert found.status_code == 200, found.text
    return found.json()


def test_a_case_of_unknown_versions_gets_no_version(org):
    from decision_center.schemas import DecisionCreateRequest
    from decision_center.service import DecisionCenterService

    investigator, user_id = org["investigator"]
    seed = _seed(org["tenant_id"])
    case = _open(investigator, seed, _unknown_version_complaints(org["tenant_id"], seed["product_id"]))
    view = _workspace(investigator, case["id"])
    assert view["product_context"]["selected_version"] is None
    assert any(item["code"] == "VERSION_UNKNOWN" for item in view["limitations"])
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        decision = DecisionCenterService().create_decision(
            db,
            org["tenant_id"],
            uuid.UUID(case["id"]),
            DecisionCreateRequest(
                selected_action="CONTINUE_INVESTIGATION", rationale="Version unknown", authorized_by_ref=user_id
            ),
        )
        assert decision.product_version_id is None
        db.rollback()


def test_a_case_of_several_versions_is_not_collapsed_to_the_commonest(org):
    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    case = _open(investigator, seed, seed["complaints"])  # two on Rev A, one on Rev B
    view = _workspace(investigator, case["id"])
    assert view["product_context"]["selected_version"] is None
    unknown = next(item for item in view["limitations"] if item["code"] == "VERSION_UNKNOWN")
    assert sorted(unknown["product_version_ids"]) == sorted([seed["version_a"], seed["version_b"]])


def test_a_one_version_case_keeps_its_version_and_the_legacy_brief_stores_it(org):
    from briefs.schemas import BriefCreateRequest
    from briefs.service import BriefService

    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    case = _open(investigator, seed, seed["complaints"][:2])  # both on Rev A
    view = _workspace(investigator, case["id"])
    assert view["product_context"]["selected_version"]["id"] == seed["version_a"]
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        brief = BriefService().generate(db, org["tenant_id"], uuid.UUID(case["id"]), BriefCreateRequest())
        assert brief["provenance"]["product_version_id"] == seed["version_a"]
        db.rollback()


def test_a_scope_lot_of_another_product_is_refused(org):  # F9
    from backend.app.db.models.foundation import LotBatch
    from tests.test_case_workflow import REASON, _code, _put_scope

    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    case = _open(investigator, seed, seed["complaints"][:2])
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        foreign = LotBatch(
            id=uuid.uuid4(),
            tenant_id=org["tenant_id"],
            lot_identifier=f"PV-L-{uuid.uuid4().hex[:8]}",
            product_version_id=uuid.UUID(seed["other_version"]),
            created_at=now,
            updated_at=now,
        )
        db.add(foreign)
        db.commit()
        foreign_id = str(foreign.id)
    refused = _put_scope(investigator, case["id"], lot_ids=[foreign_id], change_reason=REASON)
    assert refused.status_code == 422 and _code(refused) == "LOT_NOT_FOR_PRODUCT", refused.text
    kept = _put_scope(
        investigator,
        case["id"],
        lot_ids=[seed["lot_id"]],
        included_complaint_ids=seed["complaints"][:2],
        change_reason=REASON,
    )
    assert kept.status_code == 200, kept.text


def test_the_brief_scope_counts_the_complaints_of_unknown_version(org):  # F10
    from backend.app.case_workflow import scope
    from backend.app.db.models.foundation import Investigation
    from backend.app.decision_brief.compose import scope_section

    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    unknown = _unknown_version_complaints(org["tenant_id"], seed["product_id"])
    case = _open(investigator, seed, [*seed["complaints"][:2], *unknown])
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        row = db.get(Investigation, uuid.UUID(case["id"]))
        section = scope_section(db, row, scope.current_scope(db, row))
    assert section["included_count"] == 4 and section["unknown_version_count"] == 2
