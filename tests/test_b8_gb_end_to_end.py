"""B8 run 5: one GB report through the API, end to end, on the organization's own data (not the sample's EU report):
a complaint in Great Britain, its GB conclusion signed reportable, the GB MIR report it makes, Send for approval,
approval, and `mir.xml` serving the frozen GB file, valid against MHRA's schema. And one Northern Ireland report on
the "MHRA MORE (EU form)" route: the EU file, recorded as uploaded in MORE."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from backend.app.authority_reports import forms, mir_xml
from backend.app.db.models.authority_reports import ReportSnapshot
from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.report_fill import fill
from tests.test_b8_mir_freeze import PARTIES, PARTS
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import WHY, _acknowledge, _save, _sign
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok, _purge, _reports

pytestmark = pytest.mark.db

SERIOUS = dict(X1="YES", X2="NO", X3A="YES", X3B="NO", X3C="NO", X3D="NO", X3E="NO", X3F="NO", X4="NO", X5="YES")
SERIOUS["X6"] = "NO"  # a serious incident, no public health threat, no death: the 15-day report


@pytest.fixture
def trial():
    """A fresh trial per test: each signs the flagship's conclusion for one market afresh."""
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def _in(tenant_id, complaint: str, country: str) -> None:
    """Where the incident happened, as the organization's complaint record holds it."""
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.get(Complaint, uuid.UUID(complaint)).country = country
        db.commit()


def _parties(user, market: str, representative: str, country: str) -> None:
    """The manufacturer (in the US) and its representative, with every part, in Settings › Products."""
    for role, name, where in (
        ("MANUFACTURER", "Orbit Medical Devices (Sample)", "US"),
        (representative, "Representative (Sample)", country),
    ):
        _ok(
            user.put(
                PARTIES, json={"market": market, "role": role, "organisation": name, **PARTS, "country_code": where}
            )
        )


def _report(user, complaint: str, market: str) -> str:
    """The market's conclusion signed reportable (the 15-day report): the report it makes."""
    prefix = "EU" if market == "EU_NI" else market
    _acknowledge(user, market)
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    answers = {
        key.replace("X", prefix): {"answer": value, "rationale": WHY, "evidence": ["Complaint description"]}
        for key, value in SERIOUS.items()
    }
    saved = _save(user, complaint, market, answers, harm_level=detail["severity_level"])
    _ok(_sign(user, complaint, market, saved, "REPORTABLE", password=PASSWORD))
    (item,) = [row for row in _reports(user, complaint) if row["market"] == market]
    return item["id"]


def _complete(user, report: str) -> dict:
    """Every mandatory field filled as a person does: a list's first choice, else a value that fits the field."""
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    fields = {item["id"]: item for section in detail["sections"] for item in section["fields"]}
    for field in detail["mandatory"]["missing"]:
        if field == "1_2E":
            _ok(user.put(f"{REPORTS}/{report}/fields/1_2E", json={"value": forms.MIR_INITIAL}))
        elif field == "2_4":
            _ok(user.put(f"{REPORTS}/{report}/fields/2_4", json={"value": "MDR class IIb"}))
        elif fields[field]["options"]:
            _ok(user.put(f"{REPORTS}/{report}/fields/{field}", json={"value": fields[field]["options"][0]}))
        else:
            fill(user, REPORTS, report, [field])
    return _ok(user.get(f"{REPORTS}/{report}"))


def _approve(user, report: str) -> dict:
    asked = _ok(user.post(f"{REPORTS}/{report}/snapshots"))
    snapshot = asked["pending_snapshot"]["id"]
    _ok(user.post(f"{REPORTS}/{report}/snapshots/{snapshot}/approve", json={"password": PASSWORD}))
    return snapshot


def _frozen(tenant_id, snapshot: str) -> dict:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return dict(db.get(ReportSnapshot, uuid.UUID(snapshot)).fields)


def _record(user, report: str, route: str):
    return user.post(
        f"{REPORTS}/{report}/submissions",
        json={
            "route": route,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "content_note": "Uploaded in MORE (sample).",
            "no_differences": True,
        },
    )


def test_b8_a_gb_complaint_gives_a_frozen_xsd_valid_gb_mir_file(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _in(tenant_id, complaint, "Great Britain")
    _parties(user, "GB", "UK_RESPONSIBLE_PERSON", "GB")
    report = _report(user, complaint, "GB")
    detail = _complete(user, report)
    assert detail["form"]["code"] == forms.GB_MIR.code
    assert [route["code"] for route in detail["routes"]] == ["MHRA_MORE"]  # MHRA takes no other route
    snapshot = _approve(user, report)
    frozen = _frozen(tenant_id, snapshot)
    served = user.get(f"{REPORTS}/{report}/mir.xml", params={"snapshot": snapshot})
    assert served.status_code == 200, served.text
    # The download is the file the approval froze and signed, valid against MHRA's GB Initial schema.
    assert served.content == frozen["mir_xml"].encode("utf-8")
    assert hashlib.sha256(served.content).hexdigest() == frozen["mir_sha256"]
    assert frozen["mir_type"] == forms.MIR_INITIAL
    assert mir_xml.validate(served.content, forms.MIR_INITIAL, form=forms.GB_MIR.code) == []
    assert b"ncaEudamedNum" not in served.content and b"mfrAwarenessReportDate" not in served.content  # EU-only
    assert frozen["mir_parties"]["UK_RESPONSIBLE_PERSON"]["country_code"] == "GB"
    assert _record(user, report, "MHRA_MORE").status_code == 200


def test_b8_a_northern_ireland_complaint_goes_to_more_with_the_eu_file(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _in(tenant_id, complaint, "Northern Ireland")
    _parties(user, "EU", "AUTHORISED_REPRESENTATIVE", "FR")
    report = _report(user, complaint, "EU_NI")
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    assert [route["code"] for route in detail["routes"]] == ["MHRA_MORE_EU"]
    _ok(user.put(f"{REPORTS}/{report}/fields/1_1A", json={"value": "MHRA (Northern Ireland)"}))  # asked (B8-D4)
    _complete(user, report)
    snapshot = _approve(user, report)
    served = user.get(f"{REPORTS}/{report}/mir.xml", params={"snapshot": snapshot})
    assert served.status_code == 200, served.text
    assert mir_xml.validate(served.content, forms.MIR_INITIAL) == []  # the EU file, for upload in MORE
    assert served.content == _frozen(tenant_id, snapshot)["mir_xml"].encode("utf-8")
    assert _record(user, report, "EU_NCA").json()["detail"]["code"] == "ROUTE_NOT_A_RECIPIENT"
    assert _record(user, report, "MHRA_MORE_EU").status_code == 200
