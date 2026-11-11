# ruff: noqa: F811  (the organization fixture is imported from the market assessment tests)
"""B9 step 3 (B9-16, B9-17, B9-26, B9-30): the organization's role per market. Default Manufacturer; set only by an
approver with a reason, audited REPORTING_ROLE_SET; a customer administrator alone is refused; a draft re-picks its
floor at the next save (signing one saved under another floor answers 409 FLOOR_CHANGED); signed rows keep theirs; the
user facility role is offered only while its switch is on."""

from __future__ import annotations

import pytest

from backend.app.access.permissions import CUSTOMER_ADMIN
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_b4_effective_dating import _row
from tests.test_market_assessment_api import (
    US_SERIOUS,
    _acknowledge,
    _answers,
    _client,
    _save,
    _sign,
    org,  # noqa: F401
)
from tests.test_reporting_capa_api import _complaint

pytestmark = pytest.mark.db

ROLES = "/api/v1/complaints/reportability-roles"
SETTINGS = "/api/v1/complaints/reportability-settings"
WHY = "We import this device into the US from its maker."


def _set(client, market: str, role: str, reason: str = WHY):
    return client.put(ROLES, json={"market": market, "role": role, "reason": reason})


def test_the_role_is_set_by_an_approver_with_a_reason_audited_and_picks_the_floor(org, monkeypatch):
    approver, regulatory = org["approver"], org["regulatory"]
    monkeypatch.delenv("MDARIX_B9_US_USER_FACILITY", raising=False)
    settings = approver.get(SETTINGS).json()
    assert settings["reporting_roles"] == {} and settings["roles_offered"]["US"] == ["MANUFACTURER", "IMPORTER"]

    # A customer administrator alone, a viewer and a missing reason are refused; the user facility is not offered.
    admin = _client(org["tenant_id"], CUSTOMER_ADMIN, "Ada Admin")
    assert _set(admin, "US", "IMPORTER").status_code == 403
    assert _set(org["viewer"], "US", "IMPORTER").status_code == 403
    assert _set(approver, "US", "IMPORTER", reason="short").status_code == 422
    refused = _set(approver, "US", "USER_FACILITY")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "ROLE_NOT_OFFERED"
    assert _set(approver, "GB", "IMPORTER").json()["detail"]["code"] == "ROLE_NOT_OFFERED"

    # A draft saved as a manufacturer; then the role is set: signing asks for the answers again, under the new floor.
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True)
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    assert _row(org["tenant_id"], complaint).floor_code == "US-floor-1"
    done = _set(approver, "US", "IMPORTER")
    assert done.status_code == 200, done.text
    assert done.json()["reporting_roles"] == {"US": "IMPORTER"}
    refused = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "FLOOR_CHANGED"
    item = _save(regulatory, complaint, "US", _answers(**US_SERIOUS), harm_level="SERIOUS")
    signed = _sign(regulatory, complaint, "US", item, "REPORTABLE")
    assert signed.status_code == 200, signed.text
    row = _row(org["tenant_id"], complaint)
    assert row.floor_code == "US-IMP-floor-1" and row.report_type == "US_IMP_30_DAY"
    assert {rule["id"]: rule.get("recipients") for rule in row.rules_applied["rules"]}["F-IMP-1"] == [
        "FDA",
        "MANUFACTURER",
    ]

    # Back to Manufacturer: the signed row keeps its floor; nothing to change answers 422.
    assert _set(approver, "US", "MANUFACTURER").status_code == 200
    assert _set(approver, "US", "MANUFACTURER").json()["detail"]["code"] == "NOTHING_TO_CHANGE"
    assert _row(org["tenant_id"], complaint).floor_code == "US-IMP-floor-1"
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        audits = db.query(AuditEvent).filter_by(tenant_id=org["tenant_id"], action="REPORTING_ROLE_SET").all()
    assert sorted((a.old_values["role"], a.new_values["role"]) for a in audits) == [
        ("IMPORTER", "MANUFACTURER"),
        ("MANUFACTURER", "IMPORTER"),
    ]
    assert all(a.reason == WHY for a in audits)


def test_user_facility_only_while_its_switch_is_on_and_an_off_switch_reads_manufacturer(org, monkeypatch):
    approver = org["approver"]
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")
    assert _set(approver, "US", "USER_FACILITY").status_code == 200
    assert approver.get(SETTINGS).json()["reporting_roles"] == {"US": "USER_FACILITY"}
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "off")
    assert approver.get(SETTINGS).json()["reporting_roles"] == {}  # stored, read as Manufacturer while off
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")
    assert _set(approver, "US", "MANUFACTURER").status_code == 200


def test_another_organization_never_sees_the_role(org):
    assert _set(org["approver"], "IN", "IMPORTER").status_code == 200
    assert org["other"].get(SETTINGS).json()["reporting_roles"] == {}
    assert _set(org["approver"], "IN", "MANUFACTURER").status_code == 200


def test_a_user_facility_sees_its_10_work_day_clock_in_triage_and_on_the_watch(org, monkeypatch):
    """Review 6: triage's provisional clock and the watch's pending clock count by the role floor (803.30), not the
    manufacturer's 30 days or 5 work days; back to Manufacturer, today's clocks."""
    approver, regulatory = org["approver"], org["regulatory"]
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")
    _acknowledge(regulatory)
    complaint = _complaint(org["tenant_id"], org["product"], country="US", malfunction=True, aware_days_ago=1)
    pending = dict(US1="NO", US2A="UNKNOWN", US2B="UNKNOWN", US2C="UNKNOWN", US3="YES")

    def clocks() -> tuple[dict, dict]:
        ref = next(item for item in _watch(regulatory) if item["id"] == complaint)
        triage = {item["ref"]: item for item in regulatory.get(TRIAGE, params={"show": "all"}).json()["items"]}
        us = next(d for d in triage[ref["complaint_identifier"]]["deadlines"] if d["market"] == "US")
        return us, next(m for m in ref["markets"] if m["market"] == "US")["clock"]

    maker_triage, _ = clocks()
    assert (maker_triage["days"], maker_triage["day_basis"]) == (5, "WORK")  # the earliest until triage answers
    assert _set(approver, "US", "USER_FACILITY").status_code == 200
    _save(regulatory, complaint, "US", _answers(**pending), harm_level="SERIOUS")
    triage, watch = clocks()
    assert (triage["days"], triage["day_basis"]) == (10, "WORK") and "803.30" in triage["basis"]
    assert watch["days"] == 10 and watch["day_basis"] == "WORK"
    assert _set(approver, "US", "MANUFACTURER").status_code == 200
    again, _ = clocks()
    assert again == maker_triage


TRIAGE = "/api/v1/triage"


def _watch(client) -> list[dict]:
    response = client.get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 100})
    assert response.status_code == 200, response.text
    return response.json()["items"]
