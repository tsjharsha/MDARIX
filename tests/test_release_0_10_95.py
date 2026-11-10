"""Hardening 0.10.95 (code-audit fixes 6-12) against the database."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_authority_reports_api import REPORTS, _ok, _start_rv06, trial  # noqa: F401 (trial is a fixture)
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD

pytestmark = pytest.mark.db


def test_a_cancellation_committed_before_the_lock_refuses_the_approval(trial, monkeypatch):  # noqa: F811 (audit 6)
    from backend.app import governance_router

    user, colleague = trial["user"], trial["colleague"]
    detail = _start_rv06(trial)
    assert detail["state"] == "DRAFT", detail["state"]
    _ok(user.put(f"{REPORTS}/{detail['id']}/fields/MFR_REPORT", json={"value": "1234567-2026-00001"}))
    snapshot = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))["pending_snapshot"]
    real = governance_router.verify_signing_credentials

    def cancelled_meanwhile(*args, **kwargs):
        real(*args, **kwargs)
        # Another request cancels the report after the approval read it, before the approval takes the lock.
        with SessionLocal() as other:
            bind_tenant(other, trial["tenant_id"])
            row = other.get(ReportObligation, uuid.UUID(detail["id"]))
            row.state = "CANCELLED"
            other.commit()

    monkeypatch.setattr(governance_router, "verify_signing_credentials", cancelled_meanwhile)
    refused = colleague.post(
        f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": COLLEAGUE_PASSWORD}
    )
    assert refused.status_code == 409, refused.text
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert db.get(ReportObligation, uuid.UUID(detail["id"])).state == "CANCELLED"
