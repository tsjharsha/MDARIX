# ruff: noqa: F811  (the organization fixture is imported from the market assessment tests)
"""B6a G10, B6-38 (never cut): a re-upload that changes a fact behind a signed market conclusion needs one reason for
the run; a QMS sync records "QMS sync <run>" by itself; signed conclusions are flagged, never rewritten."""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.db.models.foundation import AuditEvent, Complaint, Product
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.trial import imports
from tests.test_b4_effective_dating import _row
from tests.test_b6a_change_reason import TODAY, _signed
from tests.test_market_assessment_api import _market, _url, org  # noqa: F401
from tests.test_reporting_capa_api import _complaint

pytestmark = pytest.mark.db
UPLOAD = "/api/v1/data/import/complaints"


def _keys(tenant_id, complaint_id: str) -> tuple[str, str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaint = db.get(Complaint, uuid.UUID(complaint_id))
        return complaint.complaint_identifier, db.get(Product, complaint.product_id).product_identifier


def _file(rows: list[tuple[str, str, str]]) -> str:
    # Received as stored (5 days ago): only the awareness date differs.
    received = (TODAY - timedelta(days=5)).isoformat()
    lines = ["complaint_id,product_id,description,received_date,awareness_date,country"]
    lines += [f"{key},{product},Pump alarm during therapy,{received},{aware},US" for key, product, aware in rows]
    return "\n".join(lines) + "\n"


def _events(action: str, entity_id: str | None = None, tenant_id=None) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: re-upload reason")
        query = db.query(AuditEvent).filter(AuditEvent.action == action)
        if tenant_id:
            query = query.filter(AuditEvent.tenant_id == tenant_id)
        if entity_id:
            query = query.filter(AuditEvent.entity_id == uuid.UUID(entity_id))
        return query.order_by(AuditEvent.created_at).all()


def test_a_reupload_behind_a_signed_conclusion_needs_one_reason_for_the_run(org, monkeypatch):  # B6-38
    regulatory, uploader = org["regulatory"], org["approver"]  # an Approver may import (records.write)
    first, before_first = _signed(org)
    second, before_second = _signed(org)
    unsigned = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    earlier = (TODAY - timedelta(days=6)).isoformat()
    rows = [(*_keys(org["tenant_id"], key), earlier) for key in (first, second)]
    body = _file(rows)

    # The check lists the complaints whose signed conclusion used a changed fact, and asks for a reason.
    check = uploader.post(f"{UPLOAD}/check", content=body)
    assert check.status_code == 200, check.text
    assert check.json()["ready"], check.text
    listed = check.json()["signed_decisions_changed"]
    assert {item["complaint_id"] for item in listed} == {rows[0][0], rows[1][0]}
    assert all(item["fields"] == ["awareness date"] for item in listed)
    assert check.json()["change_reason_required"] is True

    # No reason (or only spaces): refused with the clear code; nothing written.
    for query in ("", "?change_reason=%20%20"):
        refused = uploader.post(f"{UPLOAD}{query}", content=body)
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "CHANGE_REASON_REQUIRED"
    assert _market(regulatory.get(_url(first)).json(), "US")["current"]["facts_changed"] == []

    # One reason covers the whole run: on the run's audit event and on one event per complaint behind a signature.
    done = uploader.post(f"{UPLOAD}?change_reason=QMS%20export%20corrected%20awareness", content=body)
    assert done.status_code == 200, done.text
    assert done.json()["change_reason"] == "QMS export corrected awareness"
    run = _events("TRIAL_DATA_IMPORTED", tenant_id=org["tenant_id"])[-1]
    assert run.reason == "QMS export corrected awareness"
    for key in (first, second):
        (event,) = _events(imports.SIGNED_FACTS_REIMPORTED, key)
        assert event.reason == "QMS export corrected awareness" and event.entity_type == "Complaint"
        assert list(event.new_values) == ["awareness date"] and event.new_values["awareness date"].startswith(earlier)
        # Flagged on read; the signed conclusion itself is never rewritten.
        assert _market(regulatory.get(_url(key)).json(), "US")["current"]["facts_changed"] == ["awareness"]
    for key, before in ((first, before_first), (second, before_second)):
        after = _row(org["tenant_id"], key)
        assert (after.id, after.content_fingerprint, after.date_calc, after.due_on, after.signed_at) == (
            before.id,
            before.content_fingerprint,
            before.date_calc,
            before.due_on,
            before.signed_at,
        )

    # A complaint without a signed conclusion: no reason asked.
    key, product = _keys(org["tenant_id"], unsigned)
    plain = _file([(key, product, earlier)])
    assert uploader.post(f"{UPLOAD}/check", content=plain).json()["change_reason_required"] is False
    assert uploader.post(UPLOAD, content=plain).status_code == 200
    # The same file again changes nothing: no reason asked.
    assert uploader.post(f"{UPLOAD}/check", content=body).json()["signed_decisions_changed"] == []
    # Switched off: today's behaviour (no reason asked), the change still audited per complaint.
    monkeypatch.setenv("MDARIX_B6_CHANGE_REASON", "off")
    later = (TODAY - timedelta(days=7)).isoformat()
    off = uploader.post(UPLOAD, content=_file([(rows[0][0], rows[0][1], later)]))
    assert off.status_code == 200, off.text
    assert [event.reason for event in _events(imports.SIGNED_FACTS_REIMPORTED, first)] == [
        "QMS export corrected awareness",
        None,
    ]


def test_a_qms_sync_records_its_own_reason_and_a_corrected_row_is_refused_without_one(org, monkeypatch):  # B6-38
    complaint, _ = _signed(org)
    key, product = _keys(org["tenant_id"], complaint)
    record = {
        "complaint_id": key,
        "product_id": product,
        "description": "Pump alarm during therapy",
        "country": "DE",
    }
    with SessionLocal() as data:
        bind_tenant(data, org["tenant_id"])
        # A set-aside row re-imported by hand (the same checked path, no reason field): refused, nothing written.
        with pytest.raises(HTTPException) as refused:
            imports.import_records(data, org["tenant_id"], "complaints", [record], imports.TRIAL_POLICY)
        assert refused.value.detail["code"] == "CHANGE_REASON_REQUIRED"
        data.rollback()
        # A QMS sync is never refused: it lists what it changed for its run's reason.
        synced = imports.import_records(
            data, org["tenant_id"], "complaints", [record], imports.ImportPolicy(source="CONNECTOR:test-qms")
        )
        assert [item["fields"] for item in synced["signed_decisions_changed"]] == [["country"]]
        data.rollback()

    # The sync run records "QMS sync <run>" on one event per complaint behind a signature (G1 flag 2 reads it).
    from backend.app.access import connector_mapping, connector_sync

    monkeypatch.setattr(connector_mapping, "released_mapping", lambda *args: object())
    monkeypatch.setattr(
        connector_mapping,
        "import_connector_records",
        lambda *args: {"status": "IMPORTED", "rows": 1, "signed_decisions_changed": synced["signed_decisions_changed"]},
    )
    connector = SimpleNamespace(
        id=uuid.uuid4(), code="test-qms", connector_type="REST", configuration={"mapping_code": "M"}, version=1
    )
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        outcome = connector_sync.sync_connector(db, org["tenant_id"], connector, "QMS", "system:test", records=[record])
        run_id = outcome["run"].id
    (event,) = _events(imports.SIGNED_FACTS_REIMPORTED, complaint)
    assert event.reason == f"QMS sync {run_id}"
    assert list(event.new_values) == ["country"]
