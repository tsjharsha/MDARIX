"""B8 follow-up (owner, 11 Nov, "tick-box"): patient and reporter details held in frozen report snapshots and their
official files (India/Canada PDF, EU/GB MIR XML, eMDR) stay out of a full export unless "Include patient and reporter
details from submitted reports" is ticked (data.export, the export's reason, audited EXPORT_PERSONAL_DATA_INCLUDED with
box ids and counts only). The hand-back of a suspended or terminated organization always holds everything; a masked
export never does. Left out means each value and each frozen file carrying them reads "Personal data held: yes"."""

from __future__ import annotations

import base64
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

import pytest

from backend.app import tenant_export
from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot
from backend.app.db.models.foundation import AuditEvent, Complaint, Product
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.tenant_export import run_export
from tests.test_business_permissions import _client_with_role
from tests.test_tenant_data import _set_status, make_organization, use_local_storage
from tests.conftest import authenticated_client

pytestmark = pytest.mark.db

PLANTED = "Zyxexportplanted"
PDF_B64 = base64.b64encode(f"%PDF-1.4 reporter {PLANTED}".encode()).decode()
WHY = "The notified body asked for the full report as sent"
OWN = "/api/v1/admin/exports"


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    """A paying organization (not a trial) with one frozen GB report snapshot holding typed patient and reporter
    details in its sections, its MIR XML and an official PDF."""
    org = make_organization(platform)
    tenant_id, now = org["tenant_id"], datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test:b8-export-personal")
        product = db.query(Product).filter(Product.tenant_id == tenant_id).one()
        complaint = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=f"EXP-{uuid.uuid4().hex[:6]}",
            product_id=product.id,
            description="Synthetic complaint for the export test",
            created_at=now,
            updated_at=now,
        )
        db.add(complaint)
        db.flush()
        obligation = ReportObligation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_id=complaint.id,
            market="GB",
            form_code="GB_MIR",
            form_version="7.3.1",
            created_by="test",
            created_at=now,
            updated_at=now,
        )
        db.add(obligation)
        db.flush()
        fields = {
            "sections": [
                {
                    "fields": [
                        {"id": "3_3B", "personal": True, "value": "64 years"},
                        {"id": "3_4D", "personal": True, "value": f"Alex {PLANTED}"},
                        {"id": "3_4B", "personal": True, "value": None},
                        {"id": "1_1A", "value": "Kept: not personal"},
                    ]
                }
            ],
            "mir_xml": f"<mir><reporter>{PLANTED}</reporter></mir>",
            "official_pdf": PDF_B64,
        }
        db.add(
            ReportSnapshot(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                obligation_id=obligation.id,
                version=1,
                form_version="7.3.1",
                fields=fields,
                content_fingerprint="0" * 64,
                requested_by="test",
                requested_at=now,
            )
        )
        db.commit()
    return org


def _archive(client, url: str) -> zipfile.ZipFile:
    download = client.get(url)
    assert download.status_code == 200, download.text
    return zipfile.ZipFile(io.BytesIO(download.content))


def _holds_personal(archive: zipfile.ZipFile) -> bool:
    return any(
        PLANTED.encode() in archive.read(name) or PDF_B64.encode() in archive.read(name) for name in archive.namelist()
    )


def _snapshot(archive: zipfile.ZipFile) -> dict:
    [row] = [json.loads(line) for line in archive.read("data/public.report_snapshots.jsonl").splitlines()]
    return row["fields"]


def _audits(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test:b8-export-personal")
        return db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action).all()


def _own_export(admin, tenant_id, body: dict) -> zipfile.ZipFile:
    queued = admin.post(OWN, json=body)
    assert queued.status_code == 202, queued.text
    assert run_export(queued.json()["id"])["status"] == "READY"
    return _archive(admin, f"{OWN}/{queued.json()['id']}/download")


def test_an_unmasked_export_leaves_out_snapshot_personal_data_by_default(organization):
    tenant_id = organization["tenant_id"]
    admin = _client_with_role("Customer Admin", tenant_id)
    archive = _own_export(admin, tenant_id, {"reason": WHY, "unmask_contacts": True})
    assert not _holds_personal(archive)
    fields = _snapshot(archive)
    assert fields["mir_xml"] == fields["official_pdf"] == tenant_export.PERSONAL_HELD
    boxes = {item["id"]: item["value"] for item in fields["sections"][0]["fields"]}
    assert boxes == {
        "3_3B": tenant_export.PERSONAL_HELD,
        "3_4D": tenant_export.PERSONAL_HELD,
        "3_4B": None,
        "1_1A": "Kept: not personal",
    }
    manifest = json.loads(archive.read("manifest.json"))["personal_data"]
    assert manifest["included"] is False and "left out" in manifest["note"]
    assert manifest["fields"] == {"3_3B": 1, "3_4D": 1} and manifest["files"] == {"mir_xml": 1, "official_pdf": 1}
    assert _audits(tenant_id, tenant_export.PERSONAL_EVENT) == []
    [requested] = _audits(tenant_id, "TENANT_EXPORT_REQUESTED")
    assert requested.details == {"contacts": "UNMASKED", "personal": "LEFT_OUT", "exit": False}


def test_ticked_with_a_reason_includes_them_and_audits_ids_and_counts_only(organization):
    tenant_id = organization["tenant_id"]
    admin = _client_with_role("Customer Admin", tenant_id)
    archive = _own_export(admin, tenant_id, {"reason": WHY, "unmask_contacts": True, "include_personal": True})
    fields = _snapshot(archive)
    assert PLANTED in fields["mir_xml"] and fields["official_pdf"] == PDF_B64
    assert json.loads(archive.read("manifest.json"))["personal_data"]["included"] is True
    [event] = _audits(tenant_id, tenant_export.PERSONAL_EVENT)
    assert event.reason == WHY and event.actor_ref != "system:worker"
    assert event.details == {
        "exit": False,
        "snapshots": 1,
        "fields": {"3_3B": 1, "3_4D": 1},
        "files": {"mir_xml": 1, "official_pdf": 1},
    }
    every = _audits(tenant_id, tenant_export.PERSONAL_EVENT) + _audits(tenant_id, "TENANT_EXPORT_CREATED")
    assert all(PLANTED not in str((row.details, row.reason)) and "64 years" not in str(row.details) for row in every)


def test_the_option_is_refused_without_a_reason_unmasking_or_the_export_right(organization, monkeypatch):
    tenant_id = organization["tenant_id"]
    admin = _client_with_role("Customer Admin", tenant_id)
    ticked = {"unmask_contacts": True, "include_personal": True}
    assert admin.post(OWN, json=ticked).status_code == 422
    assert admin.post(OWN, json={**ticked, "reason": "too short"}).status_code == 422
    alone = admin.post(OWN, json={"reason": WHY, "include_personal": True})
    assert alone.status_code == 422 and alone.json()["detail"]["code"] == "PERSONAL_DATA_NEEDS_UNMASKED"
    from backend.app.access import permissions

    monkeypatch.setattr(permissions, "permissions_for_roles", lambda roles: frozenset())
    denied = admin.post(OWN, json={**ticked, "reason": WHY})
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "PERMISSION_DENIED"
    assert admin.get(OWN).json()["exports"] == []
    investigator = _client_with_role("Investigator", tenant_id)
    assert investigator.post(OWN, json={**ticked, "reason": WHY}).status_code in (401, 403)


def test_the_exit_hand_back_always_holds_everything(platform, organization):
    tenant_id = organization["tenant_id"]
    _set_status(tenant_id, "SUSPENDED")
    base = f"/api/v1/platform-admin/tenants/{tenant_id}/exports"
    queued = platform.post(base, json={"reason": "Hand the data back at account closing"})
    assert queued.status_code == 202, queued.text
    result = run_export(queued.json()["id"])
    assert result["summary"]["contacts"] == "UNMASKED" and result["summary"]["personal"] == "INCLUDED"
    assert result["summary"]["exit"] is True
    fields = _snapshot(_archive(platform, f"{base}/{queued.json()['id']}/download"))
    assert PLANTED in fields["mir_xml"] and fields["official_pdf"] == PDF_B64
    [event] = _audits(tenant_id, tenant_export.PERSONAL_EVENT)
    assert event.details["exit"] is True and event.details["snapshots"] == 1


def test_a_masked_export_never_holds_them(platform, organization):
    tenant_id = organization["tenant_id"]
    base = f"/api/v1/platform-admin/tenants/{tenant_id}/exports"
    # Staff exports of an active organization stay masked; the option is not theirs to tick.
    queued = platform.post(base, json={"reason": WHY, "unmask_contacts": True, "include_personal": True})
    assert queued.status_code == 202, queued.text
    result = run_export(queued.json()["id"])
    assert result["summary"]["contacts"] == "MASKED" and result["summary"]["personal"] == "LEFT_OUT"
    assert not _holds_personal(_archive(platform, f"{base}/{queued.json()['id']}/download"))
    assert _audits(tenant_id, tenant_export.PERSONAL_EVENT) == []
    # The customer's own default (masked) export: the same.
    admin = _client_with_role("Customer Admin", tenant_id)
    assert not _holds_personal(_own_export(admin, tenant_id, {"reason": WHY}))
