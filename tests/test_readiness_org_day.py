"""Readiness is as of the organization's day (0.10.64; owner to approve): an Indian organization reads 2 Nov from 00:00
IST. 0.10.63 used the UTC date, 1 Nov until 05:30 IST, the same day stage 2 moved the due times to."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.oversight.rules import zone_info
from tests.test_one_deadline_api import _india_trial

pytestmark = pytest.mark.db


def test_readiness_is_as_of_the_organizations_day():
    from backend.app.readiness_home.service import organization_today
    from backend.app.trial.retention import purge_trial

    user, tenant_id = _india_trial()
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            evening = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)  # 01:30 on 2 Nov in India
            assert organization_today(db, tenant_id, evening) == date(2026, 11, 2)
            today = organization_today(db, tenant_id)
        assert today == datetime.now(zone_info("Asia/Kolkata")).date()
        assert user.get("/api/v1/readiness").json()["as_of"] == today.isoformat()
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:sample-story-days-cleanup")
