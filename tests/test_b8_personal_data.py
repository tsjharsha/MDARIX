"""B8 run 6 (tr30, B9-D9 / B8-D9): personal data at the report step, end to end on a GB report.

Off (the default): the boxes say "enter in the authority's route" and Send for approval refuses typed details. On (a
Customer Admin with a reason, audited): details typed at Send for approval are written only into that report's frozen
snapshot and its MIR file; never into the report's entries, the audit trail, search or a masked export. Switching it
off later never changes the frozen snapshot."""

from __future__ import annotations

import uuid

import pytest

from backend.app import tenant_export
from backend.app.authority_reports import forms, mir_xml
from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_b8_gb_end_to_end import _complete, _frozen, _in, _parties, _report, trial  # noqa: F401
from tests.test_free_trial import PASSWORD, _activate_and_sign_in, _activation_token
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok

pytestmark = pytest.mark.db

SETTING = "/api/v1/complaints/reportability-personal-data"
WHY = "Our procedure lets us record the reporter's details in the report"
PLANTED = "Zyxplanted"
TYPED = {
    "3_3B": "64 years",
    "3_3C": "Female",
    "3_3D": "71 kg",
    "3_4B": f"{PLANTED} Ward (fictional)",
    "3_4D": f"Alex {PLANTED}, alex.zyx@example.invalid, +44 20 7946 0000",
}


def _rows(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


def test_b8_personal_data_off_on_off_keeps_values_only_in_the_frozen_snapshot(trial):  # noqa: F811 (the fixture)
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _flagship(user)
    _in(tenant_id, complaint, "Great Britain")
    _parties(user, "GB", "UK_RESPONSIBLE_PERSON", "GB")
    report = _report(user, complaint, "GB")
    detail = _complete(user, report)

    # GB rows only the EU help text makes mandatory: a warning when empty, never a block (owner: follow MHRA).
    rows = _rows(detail)
    assert "consultant" in rows["2_4"]["warning"] and "2_4" not in detail["mandatory"]["missing"]
    assert rows["3_4H"]["missing_class"] == "MUST_HAVE" and rows["3_4H"]["warning"] is None

    # Off (default): blank, entered in the authority's route; Send refuses typed details; a PUT is refused as before.
    assert _ok(user.get("/api/v1/complaints/reportability-settings"))["report_personal_data"] is False
    assert detail["personal_data"] is False and _rows(detail)["3_3B"]["status"] != "AT_SEND"  # sample: its class
    refused = user.post(f"{REPORTS}/{report}/snapshots", json={"personal": TYPED})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "PERSONAL_DATA_OFF"
    assert PLANTED not in refused.text
    put = user.put(f"{REPORTS}/{report}/fields/3_4B", json={"value": TYPED["3_4B"]})
    assert put.json()["detail"]["code"] == "PERSONAL_FIELD"

    # On: a reason of at least 10 characters; the trial owner stands in for the Customer Admin; audited.
    assert user.put(SETTING, json={"on": True, "reason": "short"}).status_code == 422
    assert _ok(user.put(SETTING, json={"on": True, "reason": WHY}))["report_personal_data"] is True
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    assert detail["personal_data"] is True and _rows(detail)["3_3B"]["status"] == "AT_SEND"
    wrong = user.post(f"{REPORTS}/{report}/snapshots", json={"personal": {"3_3C": "F"}})
    assert wrong.json()["detail"]["code"] == "PERSONAL_VALUE_INVALID"
    words = user.post(f"{REPORTS}/{report}/snapshots", json={"personal": {"3_3B": "about sixty"}})
    assert words.json()["detail"]["code"] == "PERSONAL_VALUE_INVALID" and "sixty" not in words.text
    stranger = user.post(f"{REPORTS}/{report}/snapshots", json={"personal": {"3_1A": "x"}})
    assert stranger.json()["detail"]["code"] == "PERSONAL_FIELD_UNKNOWN"

    asked = _ok(user.post(f"{REPORTS}/{report}/snapshots", json={"personal": TYPED}))
    snapshot = asked["pending_snapshot"]["id"]
    frozen = _frozen(tenant_id, snapshot)
    held = _rows({"sections": frozen["sections"]})
    assert held["3_4B"]["value"] == TYPED["3_4B"] and held["3_4B"]["status"] == "ENTERED"
    assert held["3_3C"]["value"] == "Female"
    gb_file = forms.switched_on("MDARIX_B8_GB_MIR")  # off: no GB MIR file, the snapshot alone holds them
    assert not gb_file or (
        PLANTED in frozen["mir_xml"]
        and mir_xml.validate(frozen["mir_xml"].encode(), frozen["mir_type"], "GB_MIR") == []
    )

    # Never stored elsewhere: the report's entries, the audit trail, search, a masked export.
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        obligation = db.get(ReportObligation, uuid.UUID(report))
        assert PLANTED not in str(obligation.entries)
        audits = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id).all()
        assert all(PLANTED not in str((row.details, row.old_values, row.new_values, row.reason)) for row in audits)
        sent = [row for row in audits if row.action == "REPORT_SNAPSHOT_REQUESTED"][-1]
        assert sent.details["personal_fields"] == sorted(TYPED)
        assert [row.reason for row in audits if row.action == "REPORT_PERSONAL_DATA_SET"] == [WHY]
    assert PLANTED not in user.get("/api/v1/data-plane/search", params={"q": PLANTED}).text
    masked = tenant_export.masked_row("report_snapshots", {"fields": frozen})
    assert PLANTED not in str(masked)

    # Off again: the frozen snapshot is unchanged, and its approval serves the same file.
    assert _ok(user.put(SETTING, json={"on": False, "reason": WHY}))["report_personal_data"] is False
    assert _frozen(tenant_id, snapshot) == frozen
    _ok(user.post(f"{REPORTS}/{report}/snapshots/{snapshot}/approve", json={"password": PASSWORD}))
    if gb_file:
        served = user.get(f"{REPORTS}/{report}/mir.xml", params={"snapshot": snapshot})
        assert served.status_code == 200 and served.content == frozen["mir_xml"].encode("utf-8")
    assert user.put(SETTING, json={"on": False, "reason": WHY}).json()["detail"]["code"] == "NOTHING_TO_CHANGE"


def test_b8_only_the_customer_admin_or_trial_owner_changes_the_setting(trial):  # noqa: F811 (the fixture)
    user = trial["user"]
    email = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = _ok(user.post("/api/v1/trial/team", json={"email": email, "display_name": "Casey Review"}))
    colleague = _activate_and_sign_in(email, _activation_token(invited, email))
    refused = colleague.put(SETTING, json={"on": True, "reason": WHY})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "CUSTOMER_ADMIN_REQUIRED"
    assert _ok(user.get("/api/v1/complaints/reportability-settings"))["report_personal_data"] is False
