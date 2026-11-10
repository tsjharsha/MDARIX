"""0.10.93 (B2) step 5: what the Case screens need from the API. Log a case keeps a product or lot that is not in the
organization's master data as typed, flagged (spec 4.2), with its ID-1 entry and the S-1 category."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.session import SessionLocal
from tests.test_case_addenda_api import _log
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-screens-cleanup")


def test_a_typed_product_and_an_unknown_lot_are_kept_as_typed_and_flagged(trial):  # spec 4.2, ID-1
    event = _log(
        trial["user"],
        product_text="OrbitCare infusion pump (older model)",
        lot="LOT-NOT-LOADED-7",
        identifiers={"lot": {"source": "LABEL_OR_PHOTO", "status": "CONFIRMED"}, "serial": {"not_sure": True}},
        issue_category="hardware",
    )
    assert (event["product_name"], event["lot"]) == ("OrbitCare infusion pump (older model)", "LOT-NOT-LOADED-7")
    assert sorted(event["not_in_master"]) == ["lot", "product"]
    assert event["identifiers"]["lot"] == {"not_sure": False, "status": "CONFIRMED", "source": "LABEL_OR_PHOTO"}
    assert event["identifiers"]["serial"]["not_sure"] is True
    assert event["issue_category"] == "HARDWARE"
    missing = {item["code"] for item in event["missing"]}
    assert {"IDENTIFIER_NOT_SURE:serial", "IDENTIFIER_UNCONFIRMED:product"} <= missing
    assert "IDENTIFIER_UNCONFIRMED:lot" not in missing
