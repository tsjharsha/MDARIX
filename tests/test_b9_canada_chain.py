"""B9 step 11 (B9-11..B9-14): Canada's chain. The Final is created when the Preliminary is recorded as submitted, due on
the date the Preliminary promised (A5); updates on demand, one open at a time; nothing after a Preliminary & Final; A4
(Health Canada's file number) and the previous report's date carried; a Final needs E2 and E3 before approval; a
re-signed conclusion supersedes an unsent Final's approval (audit fix 4) but never moves its date. Step 10: the
official form waits for the form file (409 FORM_FILE_NEEDED). The switch: off, no chain route and no Final made."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.report_fill import fill
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import WHY, _acknowledge, _save, _sign
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok, _purge, _reports

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.db, pytest.mark.requirement("B9-13", "B9-17", "B9-18", "B9-19", "B9-20", "B9-23", "B9-33")]

CA = dict(CA1="YES", CA2="YES", CA3="NO", CA4="YES", CA5="YES", CA6="NOT_APPLICABLE")
WHAT = "The returned device was examined: a cracked housing let fluid reach the board."


@pytest.fixture
def trial():
    """A fresh trial per test: each signs the flagship's Canada conclusion afresh."""
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def _answers() -> dict:
    return {
        key: {"answer": value, "rationale": WHY, "evidence": ["Complaint description"]} for key, value in CA.items()
    }


def _sign_canada(user, complaint: str):
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    saved = _save(user, complaint, "CA", _answers(), harm_level=detail["severity_level"])
    return _ok(_sign(user, complaint, "CA", saved, "REPORTABLE", password=PASSWORD))


def _values(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


def _fill_and_approve(user, report: str) -> dict:
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    fields = _values(detail)
    for field in detail["mandatory"]["missing"]:
        if fields[field]["options"]:
            _ok(user.put(f"{REPORTS}/{report}/fields/{field}", json={"value": fields[field]["options"][0]}))
        else:
            fill(user, REPORTS, report, [field])
    asked = _ok(user.post(f"{REPORTS}/{report}/snapshots"))
    return _ok(
        user.post(
            f"{REPORTS}/{report}/snapshots/{asked['pending_snapshot']['id']}/approve", json={"password": PASSWORD}
        )
    )


def _submit(user, report: str, reference: str = ""):
    return _ok(
        user.post(
            f"{REPORTS}/{report}/submissions",
            json={
                "route": "HC_EMAIL",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "content_note": "Sent to Health Canada by e-mail with the form attached.",
                "no_differences": True,
                "authority_reference": reference,
            },
        )
    )


def _frozen(tenant_id, snapshot: str) -> dict:
    """The values frozen in a snapshot at Send for approval."""
    from backend.app.authority_reports.fda_3500a import values
    from backend.app.db.models.authority_reports import ReportSnapshot

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return values(db.get(ReportSnapshot, uuid.UUID(snapshot)).fields["sections"])


def _children(tenant_id, report: str) -> list[ReportObligation]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return db.query(ReportObligation).filter_by(parent_id=uuid.UUID(report)).order_by("created_at").all()


def test_the_final_follows_the_preliminary_and_the_chain_carries_its_numbers(trial, monkeypatch):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    _sign_canada(user, complaint)
    (item,) = [row for row in _reports(user, complaint) if row["market"] == "CA"]
    report = item["id"]
    # The first report is a Preliminary or a Preliminary & Final: updates and the final follow it.
    for later in ("Update", "Final"):
        refused = user.put(f"{REPORTS}/{report}/fields/A5", json={"value": later})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "STARTS_THE_CHAIN"
    fields = _values(_ok(user.get(f"{REPORTS}/{report}")))
    assert not fields["A6"]["editable"]  # the day sent for approval (B9 spec 3.3)
    _ok(user.put(f"{REPORTS}/{report}/fields/A5_FINAL_DATE", json={"value": "2027-02-01"}))
    approved = _fill_and_approve(user, report)
    assert _frozen(trial["tenant_id"], approved["approved_snapshot"]["id"])["A6"]  # filled at Send for approval
    # Step 10: the official form waits for the owner's form file; off, it is not offered at all.
    snapshot = approved["approved_snapshot"]["id"]
    official = user.get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": snapshot, "form": "official"})
    assert official.status_code == 409 and official.json()["detail"]["code"] == "FORM_FILE_NEEDED"
    monkeypatch.setenv("MDARIX_B9_CANADA", "off")
    off = user.get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": snapshot, "form": "official"})
    assert off.status_code == 404
    monkeypatch.delenv("MDARIX_B9_CANADA")
    assert _children(tenant_id, report) == []  # nothing before the Preliminary is submitted

    sent = _submit(user, report, reference="HC-2026-00123 (sample)")
    (final,) = _children(tenant_id, report)
    assert final.kind == "RESPONSE" and str(final.due_on) == "2027-02-01" and final.entries["A5"]["value"] == "Final"
    assert [row["type"] for row in sent["canada_chain"]["items"]] == ["Final"]
    view = _ok(user.get(f"{REPORTS}/{final.id}"))
    assert view["canada_chain"]["type"] == "Final" and view["canada_chain"]["due_on"] == "2027-02-01"
    fields = _values(view)
    assert fields["A4"]["value"] == "HC-2026-00123 (sample)"  # carried from the acknowledgement
    assert fields["A5_PREVIOUS"]["value"] and fields["A3"]["value"] == _values(approved)["A3"]["value"]
    typed = user.put(f"{REPORTS}/{final.id}/fields/A5", json={"value": "Update"})
    assert typed.status_code == 422 and typed.json()["detail"]["code"] == "FOLLOWS_CHAIN"
    # A Final goes for approval only with its root cause (E2) and corrective actions (E3).
    missing = _ok(user.get(f"{REPORTS}/{final.id}"))["mandatory"]["missing"]
    assert "E2" in missing
    fill(user, REPORTS, str(final.id), [field for field in missing if field not in ("E2", "E3")])
    blocked = user.post(f"{REPORTS}/{final.id}/snapshots")
    assert blocked.status_code == 422 and "E2" in blocked.json()["detail"]["missing"]

    # Updates on demand, one open at a time; the Final is never made twice.
    update = _ok(user.post(f"{REPORTS}/{report}/canada-chain", json={"type": "Update", "what_is_new": WHAT}))
    assert update["canada_chain"]["type"] == "Update" and _values(update)["A5"]["value"] == "Update"
    again = user.post(f"{REPORTS}/{report}/canada-chain", json={"type": "Update", "what_is_new": WHAT})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "CHAIN_OPEN"
    from backend.app.authority_reports import router

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        ctx = SimpleNamespace(user_id=uuid.uuid4(), correlation_id=None)
        initial = db.get(ReportObligation, uuid.UUID(report))
        # Sent again after a correction that promises a new date: no second Final; the unsent one takes the new date.
        initial.entries = {**initial.entries, "A5_FINAL_DATE": {"value": "2027-04-01"}}
        assert router.canada_final_on_submission(db, ctx, initial, datetime.now(timezone.utc)) is None
        db.commit()
    (final,) = [row for row in _children(tenant_id, report) if row.entries["A5"]["value"] == "Final"]
    assert str(final.due_on) == "2027-04-01"
    # The Final is owed (s.61): never cancelled, since nothing would make it again.
    owed = user.post(f"{REPORTS}/{final.id}/cancel", json={"reason": "Started by mistake, not needed."})
    assert owed.status_code == 409 and owed.json()["detail"]["code"] == "FINAL_IS_OWED"
    monkeypatch.setenv("MDARIX_B9_CANADA", "off")
    assert (
        user.post(f"{REPORTS}/{report}/canada-chain", json={"type": "Update", "what_is_new": WHAT}).status_code == 404
    )


def test_a_re_sign_supersedes_an_unsent_final_but_keeps_its_date(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    _sign_canada(user, complaint)
    report = next(row["id"] for row in _reports(user, complaint) if row["market"] == "CA")
    _ok(user.put(f"{REPORTS}/{report}/fields/A5_FINAL_DATE", json={"value": "2027-03-01"}))
    _fill_and_approve(user, report)
    _submit(user, report)
    (final,) = _children(tenant_id, report)
    _ok(user.put(f"{REPORTS}/{final.id}/fields/E2", json={"value": "A cracked housing (sample)."}))
    _ok(user.put(f"{REPORTS}/{final.id}/fields/E3", json={"value": "Housing redesigned (sample)."}))
    approved = _fill_and_approve(user, str(final.id))
    assert approved["stage"] == "APPROVED"
    _sign_canada(user, complaint)  # signed again (a new version, with its change reason)
    after = _ok(user.get(f"{REPORTS}/{final.id}"))
    assert after["state"] == "DRAFT" and after["canada_chain"]["due_on"] == "2027-03-01"
    assert not [row for row in after["snapshots"] if row["state"] == "APPROVED"]


def test_a_preliminary_and_final_ends_the_chain(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    _sign_canada(user, complaint)
    report = next(row["id"] for row in _reports(user, complaint) if row["market"] == "CA")
    _ok(user.put(f"{REPORTS}/{report}/fields/A5", json={"value": "Preliminary & Final"}))
    _ok(user.put(f"{REPORTS}/{report}/fields/E2", json={"value": "A cracked housing (sample)."}))
    _ok(user.put(f"{REPORTS}/{report}/fields/E3", json={"value": "Housing redesigned (sample)."}))
    _fill_and_approve(user, report)
    sent = _submit(user, report)
    assert _children(tenant_id, report) == [] and sent["canada_chain"]["ended"] is True
    refused = user.post(f"{REPORTS}/{report}/canada-chain", json={"type": "Update", "what_is_new": WHAT})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "CHAIN_ENDED"


def test_off_the_worksheet_stays_and_no_final_is_made(trial, monkeypatch):
    user, tenant_id = trial["user"], trial["tenant_id"]
    monkeypatch.setenv("MDARIX_B9_CANADA", "off")
    complaint = _flagship(user)
    _acknowledge(user, "CA")
    _sign_canada(user, complaint)
    report = next(row["id"] for row in _reports(user, complaint) if row["market"] == "CA")
    _ok(user.put(f"{REPORTS}/{report}/fields/A6", json={"value": "2026-11-11"}))  # typed again, as before B9
    _ok(user.put(f"{REPORTS}/{report}/fields/A5_FINAL_DATE", json={"value": "2027-02-01"}))
    _fill_and_approve(user, report)
    sent = _submit(user, report)
    assert _children(tenant_id, report) == [] and _values(sent)["A6"]["value"] == "2026-11-11"


@pytest.mark.unit
def test_the_final_gate_names_what_is_missing():
    from fastapi import HTTPException

    from backend.app.authority_reports import router

    section = {"fields": [{"id": "E2", "label": "E2", "value": None}, {"id": "E3", "label": "E3", "value": "CAPA"}]}
    with pytest.raises(HTTPException) as refused:
        router._canada_final_gate([section])
    assert refused.value.detail["code"] == "FINAL_NEEDS_E2_E3" and refused.value.detail["missing"] == ["E2"]
