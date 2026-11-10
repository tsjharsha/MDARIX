"""B5 step 10: a field-action follow-up records its reference, kind, effective date and the lots and versions it
covers when it is completed; a product change names its new version. Fields of another type, another product's
versions or lots are refused; with the closed loop off, nothing of it is recorded; an older completion still works."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import LotBatch, ProductVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_decision_followups import NOTE, _client, _decide, _open, _organization, _purge, _seed

pytestmark = pytest.mark.db


def _version_and_lot(tenant_id, product_id: str) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        made = []
        for name in ("Rev A", "Rev B"):
            row = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=uuid.UUID(product_id),
                version_identifier=name,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            made.append(row)
        db.flush()
        lot = LotBatch(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            lot_identifier=f"FF-L-{uuid.uuid4().hex[:6]}",
            product_version_id=made[0].id,
            created_at=now,
            updated_at=now,
        )
        db.add(lot)
        db.commit()
        return str(made[0].id), str(made[1].id), str(lot.id)


@pytest.fixture(scope="module")
def org():
    tenant_id = _organization("B5FIELDS")
    other_id = _organization("B5FIELDS_OTHER")
    try:
        investigator, user_id = _client(tenant_id, "INVESTIGATOR", "Investigator")
        seed = _seed(tenant_id)
        case = _open(investigator, seed)
        rev_a, rev_b, lot = _version_and_lot(tenant_id, seed["product_id"])
        _, _, other_lot = _version_and_lot(other_id, _seed(other_id)["product_id"])
        made = _decide(
            tenant_id,
            case["id"],
            follow_ups=[
                {"action_type": "FIELD_ACTION_REVIEW_REQUIRED", "assignee": user_id},
                {"action_type": "PRODUCT_CHANGE_REQUIRED", "assignee": user_id},
                {"action_type": "RISK_REASSESSMENT_REQUIRED", "assignee": user_id},
                {"action_type": "FIELD_ACTION_REVIEW_REQUIRED", "assignee": user_id},
            ],
        )
        yield {
            "tenant_id": tenant_id,
            "client": investigator,
            "follow_ups": made["follow_ups"],
            "rev_a": rev_a,
            "rev_b": rev_b,
            "lot": lot,
            "other_lot": other_lot,
        }
    finally:
        _purge(tenant_id)
        _purge(other_id)


def _row(org, follow_up_id: str) -> DecisionFollowUp:
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        return db.query(DecisionFollowUp).filter(DecisionFollowUp.id == uuid.UUID(follow_up_id)).one()


def test_a_field_action_records_reference_kind_date_and_what_it_covers(org):
    field, *_ = org["follow_ups"]
    wrong_lot = org["client"].post(
        f"/api/v1/follow-ups/{field}/complete", json={"note": NOTE, "lot_ids": [org["other_lot"]]}
    )
    assert wrong_lot.status_code == 422 and wrong_lot.json()["detail"]["code"] == "LOT_NOT_OF_PRODUCT"
    bad_kind = org["client"].post(f"/api/v1/follow-ups/{field}/complete", json={"note": NOTE, "action_kind": "RECALL"})
    assert bad_kind.status_code == 422
    done = org["client"].post(
        f"/api/v1/follow-ups/{field}/complete",
        json={
            "note": NOTE,
            "action_reference": "FSCA-2026-014",
            "action_kind": "ADVISORY_NOTICE",
            "action_effective_on": "2026-11-01",
            "lot_ids": [org["lot"]],
            "version_ids": [org["rev_a"]],
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["action_record"] == {
        "reference": "FSCA-2026-014",
        "kind": "ADVISORY_NOTICE",
        "effective_on": "2026-11-01",
        "scope": {"lot_ids": [org["lot"]], "version_ids": [org["rev_a"]]},
    }
    row = _row(org, field)
    assert row.status == "DONE" and row.action_effective_on.isoformat() == "2026-11-01"


def test_a_product_change_names_its_new_version_and_other_types_refuse_field_fields(org):
    _, change, risk, _ = org["follow_ups"]
    not_field = org["client"].post(
        f"/api/v1/follow-ups/{change}/complete", json={"note": NOTE, "action_effective_on": "2026-11-01"}
    )
    assert not_field.status_code == 422 and not_field.json()["detail"]["code"] == "NOT_A_FIELD_ACTION"
    not_change = org["client"].post(
        f"/api/v1/follow-ups/{risk}/complete", json={"note": NOTE, "new_version_id": org["rev_b"]}
    )
    assert not_change.status_code == 422 and not_change.json()["detail"]["code"] == "NOT_A_PRODUCT_CHANGE"
    done = org["client"].post(
        f"/api/v1/follow-ups/{change}/complete",
        json={"note": NOTE, "action_reference": "ECO-77", "new_version_id": org["rev_b"]},
    )
    assert done.status_code == 200, done.text
    assert _row(org, change).action_scope == {"new_version_id": org["rev_b"]}
    plain = org["client"].post(f"/api/v1/follow-ups/{risk}/complete", json={"note": NOTE})
    assert plain.status_code == 200 and plain.json()["action_record"]["scope"] == {}


def test_with_the_closed_loop_off_the_fields_are_refused(org, monkeypatch):
    monkeypatch.setenv("MDARIX_CLOSED_LOOP", "off")
    last = org["follow_ups"][3]
    refused = org["client"].post(
        f"/api/v1/follow-ups/{last}/complete", json={"note": NOTE, "action_reference": "FSCA-1"}
    )
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "CLOSED_LOOP_OFF"
    assert _row(org, last).status != "DONE"
