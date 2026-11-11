"""B8 step 18 (B8-31): each B8 switch off, on, off. Off: the MIR XML answers 404, no file is frozen, no draft is made on
submission, the chain card and the MIR checks are gone (today's worksheet), and a draft is still sent and approved."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from backend.app import feature_set
from backend.app.authority_reports import forms
from backend.app.authority_reports import router as reports
from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.rule_register import register
from tests.test_authority_reports_api import REPORTS, _ok, trial  # noqa: F401
from tests.test_b8_mir_chain import _initial, _record
from tests.test_b8_mir_freeze import _approve_pending, _fill, _send, _xml, eu_parties, report  # noqa: F401


@pytest.mark.unit
def test_b8_switches_default_on_and_each_answers_for_its_own_form(monkeypatch):
    for name in feature_set.B8_SWITCHES:
        monkeypatch.delenv(name, raising=False)
    eu, gb = SimpleNamespace(form_code=forms.EU_MIR.code), SimpleNamespace(form_code=forms.GB_MIR.code)
    assert reports.mir_on(eu) and reports.mir_on(gb)
    for state in ("off", "on", "off"):
        monkeypatch.setenv("MDARIX_B8_GB_MIR", state)
        assert reports.mir_on(gb) is (state == "on") and reports.mir_on(eu)
        assert register.offered(register.get("gb-mir-rule-book-1")) is (state == "on")
    assert not reports.mir_on(SimpleNamespace(form_code=forms.FDA_3500A.code))


def _children(trial, report_id: str) -> int:  # noqa: F811
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        return db.query(ReportObligation).filter_by(parent_id=uuid.UUID(report_id)).count()


@pytest.mark.db
def test_b8_the_eu_switch_off_on_off(trial, eu_parties, report, monkeypatch):  # noqa: F811
    user = trial["user"]
    for state in ("off", "on", "off"):
        monkeypatch.setenv("MDARIX_B8_EU_MIR", state)
        on = state == "on"
        _initial(trial)
        _fill(trial, report, **{"1_2E": forms.MIR_INITIAL, "2_4": "MDR class IIb"})
        detail = _ok(user.get(f"{REPORTS}/{report}"))
        assert (detail["mir"] is not None, detail["mir_chain"] is not None) == (on, on), state
        _ok(_send(trial, report))  # a draft is sent for approval either way
        frozen = _approve_pending(trial, report)
        assert ("mir_xml" in frozen.fields) is on, state
        assert _xml(trial, report, frozen.id).status_code == (200 if on else 404), state
        _ok(_record(user, report))
        assert _children(trial, report) == (1 if on else 0), state  # the next Follow-up only while on (D14)
    _initial(trial)
