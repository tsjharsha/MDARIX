"""B7 step 7 (G15): files on a Case: clean, infected, wrong type, quota, another organization."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.intake import CaseAttachment
from backend.app.db.models.oversight import OversightSettings
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_free_trial import _approved_trial_client
from tests.test_intake_triage_api import INTAKE, _ok

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def trials():
    from backend.app.trial.retention import purge_trial

    made = [_approved_trial_client() for _ in range(2)]
    try:
        yield [{"user": user, "tenant_id": uuid.UUID(approval["tenant_id"])} for user, approval, _ in made]
    finally:
        with SessionLocal() as db:
            for _, approval, _ in made:
                purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:case-attachments-cleanup")


@pytest.fixture(autouse=True)
def storage(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    for name in ("MDARIX_CLAMD_HOST", "MDARIX_MALWARE_SCANNER_COMMAND"):
        monkeypatch.delenv(name, raising=False)  # the built-in check: an executable or a script is refused


def _case(user) -> dict:
    return _ok(user.post(INTAKE, json={"kind": "CONTACT", "reporter_words": "Display flickered; photo to follow"}))


def _upload(user, case: dict, name: str, content: bytes, content_type: str = "text/plain"):
    return user.post(f"{INTAKE}/{case['id']}/attachments", files={"file": (name, content, content_type)})


def test_a_clean_file_is_stored_listed_opened_and_audited(trials):
    user, tenant_id = trials[0]["user"], trials[0]["tenant_id"]
    case = _case(user)
    added = _ok(_upload(user, case, "service log.txt", b"Error 42 at 09:40"))
    assert added["file_name"] == "service log.txt" and added["size"] == 17 and added["source"] == "UPLOAD"
    listed = _ok(user.get(f"{INTAKE}/{case['id']}/attachments"))["items"]
    assert [item["id"] for item in listed] == [added["id"]]
    opened = user.get(f"{INTAKE}/{case['id']}/attachments/{added['id']}")
    assert opened.status_code == 200 and opened.content == b"Error 42 at 09:40"
    with SessionLocal() as db:
        bind_system(db, "test:case-attachments")
        actions = {
            row.action
            for row in db.query(AuditEvent).filter(
                AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(added["id"])
            )
        }
        assert actions == {"CASE_ATTACHMENT_ADDED", "CASE_ATTACHMENT_OPENED"}


def test_an_infected_or_wrong_file_is_never_stored(trials):
    user = trials[0]["user"]
    case = _case(user)
    infected = _upload(user, case, "run.txt", b"#!/bin/sh\nrm -rf /")
    assert infected.status_code == 422 and infected.json()["detail"]["code"] == "MALWARE_SCAN_REJECTED"
    wrong = _upload(user, case, "macro.docm", b"PK", "application/vnd.ms-word.document.macroEnabled.12")
    assert wrong.status_code == 415
    lying = _upload(user, case, "photo.png", b"not a png", "image/png")
    assert lying.status_code == 415 and lying.json()["detail"]["code"] == "ATTACHMENT_CONTENT_MISMATCH"
    with SessionLocal() as db:
        bind_system(db, "test:case-attachments")
        stored = db.query(CaseAttachment).filter(CaseAttachment.intake_event_id == uuid.UUID(case["id"])).count()
        assert stored == 0


def test_the_organizations_quota_is_its_setting(trials):  # B7-D16
    user, tenant_id = trials[0]["user"], trials[0]["tenant_id"]
    case = _case(user)
    refused = user.put("/api/v1/oversight/settings/alerts-and-files", json={"attachment_quota_mb": 5})
    assert refused.status_code == 422 and "100 MB" in refused.text  # a trial keeps 100 MB
    with SessionLocal() as db:
        bind_system(db, "test:case-attachments")
        row = db.query(OversightSettings).filter(OversightSettings.tenant_id == tenant_id).first()
        if row is None:
            row = OversightSettings(id=uuid.uuid4(), tenant_id=tenant_id)
            db.add(row)
        row.attachment_quota_mb = 1  # a pilot's setting, set here directly
        db.commit()
    try:
        full = _upload(user, case, "big.txt", b"x" * (1024 * 1024 + 1))
        assert full.status_code == 413 and full.json()["detail"]["code"] == "TENANT_ATTACHMENT_QUOTA_EXCEEDED"
    finally:
        with SessionLocal() as db:
            bind_system(db, "test:case-attachments")
            db.query(OversightSettings).filter(OversightSettings.tenant_id == tenant_id).update(
                {"attachment_quota_mb": 100}
            )
            db.commit()


def test_another_organization_never_sees_the_files(trials):
    owner, other = trials[0]["user"], trials[1]["user"]
    case = _case(owner)
    added = _ok(_upload(owner, case, "note.txt", b"Reporter sent a photo"))
    assert other.get(f"{INTAKE}/{case['id']}/attachments").status_code == 404
    assert other.get(f"{INTAKE}/{case['id']}/attachments/{added['id']}").status_code == 404
    assert _upload(other, case, "x.txt", b"hello").status_code == 404
