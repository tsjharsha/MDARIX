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


def test_a_signal_of_one_version_takes_only_that_version(org):  # F11
    from tests.test_case_workflow import _code

    lead, _ = org["lead"]
    seed = _seed(org["tenant_id"])
    rev_a_1, rev_a_2, rev_b = seed["complaints"]

    def raise_signal(version: str, complaints: list[str]):
        return lead.post(
            "/api/v1/triage/signals",
            json={
                "title": "Occlusion alarms rising",
                "product_id": seed["product_id"],
                "product_version_id": version,
                "complaint_ids": complaints,
                "priority": "HIGH",
                "reason": "Customer reported alarms during infusion",
            },
        )

    refused = raise_signal(seed["version_a"], [rev_a_1, rev_b])
    assert refused.status_code == 422 and _code(refused) == "COMPLAINT_NOT_FOR_VERSION", refused.text
    signal_a = raise_signal(seed["version_a"], [rev_a_1])
    signal_b = raise_signal(seed["version_b"], [rev_b])
    assert signal_a.status_code == 201 and signal_b.status_code == 201, (signal_a.text, signal_b.text)
    signal_a, signal_b = signal_a.json()["id"], signal_b.json()["id"]
    added = lead.post(
        f"/api/v1/triage/signals/{signal_a}/complaints",
        json={"complaint_ids": [rev_b], "reason": "Same alarm on the older release"},
    )
    assert added.status_code == 422 and _code(added) == "COMPLAINT_NOT_FOR_VERSION", added.text
    merged = lead.post(
        f"/api/v1/triage/signals/{signal_a}/merge",
        json={"source_signal_ids": [signal_b], "reason": "Same alarm on the older release"},
    )
    assert merged.status_code == 422 and _code(merged) == "VERSION_MISMATCH", merged.text
    added = lead.post(
        f"/api/v1/triage/signals/{signal_a}/complaints",
        json={"complaint_ids": [rev_a_2], "reason": "Same alarm on the same release"},
    )
    assert added.status_code == 200, added.text


def test_the_unknown_version_age_is_per_product(org):  # F12
    from datetime import timedelta

    from backend.app.signals.insight import _version_ages

    seed, other = _seed(org["tenant_id"]), _seed(org["tenant_id"])
    old = _unknown_version_complaints(org["tenant_id"], seed["product_id"], 1)
    _unknown_version_complaints(org["tenant_id"], other["product_id"], 1)
    today = datetime.now(timezone.utc).date()
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        db.query(Complaint).filter(Complaint.id == uuid.UUID(old[0])).update(
            {"event_timestamp": datetime.now(timezone.utc) - timedelta(days=400)}
        )
        db.commit()
        ages = _version_ages(
            db, org["tenant_id"], {None}, today, {uuid.UUID(seed["product_id"]), uuid.UUID(other["product_id"])}
        )
    assert ages[(None, uuid.UUID(seed["product_id"]))] == 400
    assert ages[(None, uuid.UUID(other["product_id"]))] == 0


def test_a_case_scoped_to_one_version_does_not_cover_another(org):  # F13
    from backend.app.complaint_disposition import triggers

    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        db.query(Complaint).filter(Complaint.id.in_([uuid.UUID(item) for item in seed["complaints"]])).update(
            {"problem_code": "E01"}, synchronize_session=False
        )
        db.commit()
    case = _open(investigator, seed, seed["complaints"][:2])  # scope: Rev A
    product = uuid.UUID(seed["product_id"])
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        covering = triggers.covering_cases(db, org["tenant_id"], product, "E01", uuid.UUID(seed["version_a"]))
        assert [str(row.id) for row in covering] == [case["id"]]
        assert triggers.covering_cases(db, org["tenant_id"], product, "E01", uuid.UUID(seed["version_b"])) == []
        assert triggers.covering_cases(db, org["tenant_id"], product, "E01", None) == []
        assert triggers.covering_cases(db, org["tenant_id"], product, "E01")  # any version: as before


def test_ai_requests_refuse_a_version_or_case_of_another_product(org):  # F14
    from tests.test_case_workflow import _code

    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    case = _open(investigator, seed, seed["complaints"][:2])
    ask = "/api/v1/stage3/interactions"
    body = {"prompt": "What changed?", "product_id": seed["product_id"]}
    refused = investigator.post(ask, json={**body, "product_version_id": seed["other_version"]})
    assert refused.status_code == 422 and _code(refused) == "PRODUCT_VERSION_SCOPE_MISMATCH", refused.text
    other_product = _seed(org["tenant_id"])["product_id"]
    refused = investigator.post(ask, json={**body, "product_id": other_product, "investigation_id": case["id"]})
    assert refused.status_code == 422 and _code(refused) == "PRODUCT_CASE_MISMATCH", refused.text
    draft = investigator.post(
        "/api/v1/regulatory/draft",
        json={"document_type": "CER", "investigation_id": case["id"], "product_version_id": seed["other_version"]},
    )
    assert draft.status_code == 422 and _code(draft) == "PRODUCT_VERSION_SCOPE_MISMATCH", draft.text


def test_the_version_story_lists_whole_product_cases_as_overview_does(org):  # W1 follow-up (report section 5)
    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    product_case = _open(investigator, seed, _unknown_version_complaints(org["tenant_id"], seed["product_id"]))
    rev_a_case = _open(investigator, seed, seed["complaints"][:2])
    story = investigator.get(f"/api/v1/products/{seed['product_id']}/versions/{seed['version_b']}/story")
    assert story.status_code == 200, story.text
    story = story.json()
    listed = {row["investigation_identifier"]: row["applies_to"] for row in story["investigations"]}
    assert listed == {product_case["investigation_identifier"]: "PRODUCT"}
    assert rev_a_case["investigation_identifier"] not in listed and story["counts"]["investigations"] == 1
    story_a = investigator.get(f"/api/v1/products/{seed['product_id']}/versions/{seed['version_a']}/story").json()
    assert {row["investigation_identifier"]: row["applies_to"] for row in story_a["investigations"]} == {
        product_case["investigation_identifier"]: "PRODUCT",
        rev_a_case["investigation_identifier"]: "VERSION",
    }
