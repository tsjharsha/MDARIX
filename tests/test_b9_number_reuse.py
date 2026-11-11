"""B9 review item 3 (B9-21): a US report number is never reused across roles. An importer's F2 built on its FEI has
the manufacturer number's very format, so a typed F2 equal to an earlier manufacturer number (or a typed
manufacturer number equal to an earlier F2) is refused, and a generated one skips the other role's numbers."""

# ruff: noqa: F811 (``trial`` is the shared fixture, imported)
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_authority_reports_api import trial  # noqa: F401 (a fixture)
from tests.test_release_0_10_96 import _assign, _us_report

pytestmark = pytest.mark.db


def _importer_report(tenant_id, number: str | None = None):
    report_id = _us_report(tenant_id)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.get(ReportObligation, report_id)
        row.report_type, row.entries = "US_IMP_30_DAY", ({"F2": {"value": number}} if number else {})
        db.commit()
    return report_id


def _f2(tenant_id, report_id):
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return ((db.get(ReportObligation, report_id).entries or {}).get("F2") or {}).get("value")


def test_a_number_is_never_reused_across_the_manufacturer_and_importer_roles(trial, monkeypatch):
    monkeypatch.delenv("MDARIX_B9_US_IMPORTER", raising=False)
    tenant = trial["tenant_id"]
    year = date.today().year
    maker = f"1234567-{year}-70001"
    _assign(tenant, _us_report(tenant, maker))
    # A typed F2 equal to the manufacturer's number is refused.
    with pytest.raises(HTTPException) as refused:
        _assign(tenant, _importer_report(tenant, maker))
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "REPORT_NUMBER_IN_USE"
    # The importer's own first F2 (same FEI), then a generated one: 70001 is the manufacturer's, so 70002.
    first = _importer_report(tenant, f"1234567-{year}-00001")
    _assign(tenant, first)
    later = _importer_report(tenant)
    _assign(tenant, later)
    assert _f2(tenant, later) == f"1234567-{year}-70002"
    # And the other way round: a typed manufacturer number equal to an importer's F2 is refused.
    with pytest.raises(HTTPException) as refused:
        _assign(tenant, _us_report(tenant, f"1234567-{year}-70002"))
    assert refused.value.detail["code"] == "REPORT_NUMBER_IN_USE"
