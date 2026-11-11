"""B9b step 1 (tr31): a country outside the five markets on the assessment and the report.

Two countries on one complaint are allowed; the same country twice (the same version, or a second initial report) is
refused; a five-market row keeps an empty country and an OTHER row needs one.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import DBAPIError

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_reporting_capa_api import _complaint, _organization, _product

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def complaint():
    from backend.app.trial.retention import purge_trial

    tenant_id = _organization("OCS")
    try:
        yield tenant_id, uuid.UUID(_complaint(tenant_id, _product(tenant_id)))
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b9b-schema-cleanup")


def _assessment(tenant_id, complaint_id, market: str, country: str | None, version: int = 1):
    now = datetime.now(timezone.utc)
    return ComplaintMarketAssessment(
        tenant_id=tenant_id,
        complaint_id=complaint_id,
        market=market,
        country=country,
        version=version,
        question_set="OTHER-starter-1",
        scale_version="scale-starter-1",
        answers={},
        suggested_conclusion="PENDING_INFORMATION",
        created_by="test",
        created_at=now,
        updated_at=now,
    )


def _report(tenant_id, complaint_id, market: str, country: str | None):
    now = datetime.now(timezone.utc)
    return ReportObligation(
        tenant_id=tenant_id,
        complaint_id=complaint_id,
        market=market,
        country=country,
        kind="INITIAL",
        form_code="ATTACHED",
        form_version="attached-1",
        created_by="test",
        created_at=now,
        updated_at=now,
    )


def _refused(tenant_id, row) -> bool:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add(row)
        try:
            db.commit()
        except DBAPIError:  # a unique key: IntegrityError; a check (pg8000): ProgrammingError
            db.rollback()
            return True
        return False


def test_two_countries_side_by_side_and_the_same_country_twice_refused(complaint):
    tenant_id, complaint_id = complaint
    assert not _refused(tenant_id, _assessment(tenant_id, complaint_id, "OTHER", "AU"))
    assert not _refused(tenant_id, _assessment(tenant_id, complaint_id, "OTHER", "CH"))
    assert _refused(tenant_id, _assessment(tenant_id, complaint_id, "OTHER", "AU"))
    assert not _refused(tenant_id, _assessment(tenant_id, complaint_id, "OTHER", "AU", version=2))
    assert not _refused(tenant_id, _report(tenant_id, complaint_id, "OTHER", "AU"))
    assert not _refused(tenant_id, _report(tenant_id, complaint_id, "OTHER", "CH"))
    assert _refused(tenant_id, _report(tenant_id, complaint_id, "OTHER", "AU"))
    # The five markets keep their own one-initial-report key.
    assert not _refused(tenant_id, _report(tenant_id, complaint_id, "US", None))
    assert _refused(tenant_id, _report(tenant_id, complaint_id, "US", None))


def test_a_country_only_with_other_and_always_with_it(complaint):
    tenant_id, complaint_id = complaint
    assert _refused(tenant_id, _assessment(tenant_id, complaint_id, "OTHER", None))
    assert _refused(tenant_id, _assessment(tenant_id, complaint_id, "OTHER", "au"))
    assert _refused(tenant_id, _assessment(tenant_id, complaint_id, "US", "AU"))
    assert _refused(tenant_id, _report(tenant_id, complaint_id, "OTHER", None))
    assert _refused(tenant_id, _report(tenant_id, complaint_id, "EU_NI", "FR"))
    assert _refused(tenant_id, _assessment(tenant_id, complaint_id, "XX", None))
