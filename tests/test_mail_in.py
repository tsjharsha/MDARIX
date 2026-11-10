"""B7b step 8: the mail-in receiver in local SMTP sessions (EM-01, 10, 14, 16, 18).

The receiver runs in-process on 127.0.0.1 through aiosmtpd's test controller. No real mailbox, no real send: a guard
refuses any SMTP connection to a host other than this machine.
"""

from __future__ import annotations

import smtplib
import socket
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.intake import InboundMessage
from backend.app.db.models.oversight import OversightSettings
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.models.stage3 import InboundProviderMapping
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.mail_in import PROVIDER, addresses, receiver
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db
LOCAL = "127.0.0.1"


@pytest.fixture(autouse=True)
def only_this_machine(monkeypatch, tmp_path):
    real_connect = smtplib.SMTP.connect

    def guarded(self, host="localhost", port=0, source_address=None):
        assert host in (LOCAL, "localhost"), f"a test tried to reach a real mail host: {host}"
        return real_connect(self, host, port, source_address)

    monkeypatch.setattr(smtplib.SMTP, "connect", guarded)
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MDARIX_INTAKE_DOMAIN", "intake.example.test")
    for name in ("MDARIX_MAIL_IN_CERT", "MDARIX_MAIL_IN_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def orgs():
    from backend.app.trial.retention import purge_trial

    made = [_approved_trial_client() for _ in range(2)]
    tenants = [uuid.UUID(approval["tenant_id"]) for _, approval, _ in made]
    now = datetime.now(timezone.utc)
    with SessionLocal() as control:
        bind_system(control, "test:mail-in")
        for tenant_id in tenants:
            addresses.switch(control, tenant_id, True, now)
        control.commit()
    try:
        yield tenants
    finally:
        with SessionLocal() as db:
            bind_system(db, "test:mail-in-cleanup")
            db.query(InboundProviderMapping).filter(InboundProviderMapping.tenant_id.in_(tenants)).delete()
            db.commit()
            for tenant_id in tenants:
                purge_trial(db, tenant_id, "test:mail-in-cleanup")


@pytest.fixture
def smtp():
    with socket.socket() as probe:
        probe.bind((LOCAL, 0))
        port = probe.getsockname()[1]
    server = receiver.controller(LOCAL, port)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _address(tenant_id) -> str:
    with SessionLocal() as control:
        bind_system(control, "test:mail-in")
        return addresses.view(control, tenant_id, datetime.now(timezone.utc))["address"]


def _message(to: str, message_id: str | None = None, body: str = "The pump alarm sounded twice.") -> bytes:
    message_id = message_id or f"<{uuid.uuid4().hex}@hospital.example>"
    return (
        f"From: Nurse <nurse@hospital.example>\r\nTo: {to}\r\nSubject: Pump alarm\r\n"
        f"Message-ID: {message_id}\r\n\r\n{body}\r\n"
    ).encode()


def _send(server, to: str, content: bytes | None = None, sender: str = "nurse@hospital.example"):
    with smtplib.SMTP(LOCAL, server.port, timeout=10) as client:
        return client.sendmail(sender, [to], content or _message(to))


def _stored(tenant_id) -> list[InboundMessage]:
    with SessionLocal() as db:
        bind_system(db, "test:mail-in")
        return db.query(InboundMessage).filter(InboundMessage.tenant_id == tenant_id).all()


def test_em01_an_unknown_address_or_another_domain_is_refused_and_nothing_is_stored(orgs, smtp):
    before = len(_stored(orgs[0]))
    for to in ("cases-nosuchtoken@intake.example.test", "someone@elsewhere.example"):
        with pytest.raises(smtplib.SMTPRecipientsRefused) as refused:
            _send(smtp, to)
        assert refused.value.recipients[to][0] == 550
    assert len(_stored(orgs[0])) == before


def test_a_message_is_kept_once_with_the_server_time_and_a_processing_job(orgs, smtp):
    to = _address(orgs[0])
    content = _message(to, "<once-only@hospital.example>")
    started = datetime.now(timezone.utc)
    _send(smtp, to, content)
    _send(smtp, to, content)  # EM-05: the same Message-ID twice is stored once
    rows = [row for row in _stored(orgs[0]) if row.message_id == "<once-only@hospital.example>"]
    assert len(rows) == 1
    row = rows[0]
    assert row.state == "NEW" and row.raw_size == len(content) and row.received_at >= started
    from object_storage.service import ObjectStorageService

    assert ObjectStorageService().get(str(orgs[0]), row.raw_object_key) == content
    with SessionLocal() as control:
        bind_system(control, "test:mail-in")
        jobs = control.query(OutboxEvent).filter(
            OutboxEvent.event_name == receiver.PROCESS_EVENT, OutboxEvent.aggregate_id == row.id
        )
        assert jobs.count() == 1


def test_em18_a_token_never_writes_into_another_organisation(orgs, smtp):
    before = {row.id for row in _stored(orgs[1])}
    _send(smtp, _address(orgs[0]), _message(_address(orgs[0]), "<for-the-first-org@hospital.example>"))
    assert {row.id for row in _stored(orgs[1])} == before
    assert any(row.message_id == "<for-the-first-org@hospital.example>" for row in _stored(orgs[0]))


def test_em10_over_a_limit_the_sender_is_told_to_retry_451(orgs, smtp, monkeypatch):
    to = _address(orgs[1])
    with SessionLocal() as db:
        bind_system(db, "test:mail-in")
        settings = db.query(OversightSettings).filter(OversightSettings.tenant_id == orgs[1]).first()
        if settings is None:
            settings = OversightSettings(tenant_id=orgs[1])
            db.add(settings)
        settings.mail_daily_limit = len(_stored(orgs[1])) + 1
        db.commit()
    _send(smtp, to)
    for _ in range(2):
        with pytest.raises(smtplib.SMTPRecipientsRefused) as refused:
            _send(smtp, to)
        assert refused.value.recipients[to][0] == 451
    # The Customer Admin is told once a day, through the notifications outbox, however often senders are refused.
    from backend.app.notifications import MAIL_INTAKE_LIMIT_REACHED

    with SessionLocal() as control:
        bind_system(control, "test:mail-in")
        notices = (
            control.query(OutboxEvent)
            .filter(OutboxEvent.tenant_id == orgs[1], OutboxEvent.event_name == MAIL_INTAKE_LIMIT_REACHED)
            .all()
        )
    assert len(notices) == 1
    assert notices[0].payload["day"] == datetime.now(timezone.utc).date().isoformat()
    assert "@" not in str(notices[0].payload)
    # Per sending IP: 30 an hour.
    monkeypatch.setattr(receiver, "PER_IP_PER_HOUR", 0)
    with pytest.raises(smtplib.SMTPRecipientsRefused) as refused:
        _send(smtp, _address(orgs[0]))
    assert refused.value.recipients[_address(orgs[0])][0] == 451


def test_an_allowlist_refuses_other_senders_and_a_large_message_is_refused(orgs, monkeypatch):
    to = _address(orgs[0])
    with SessionLocal() as db:
        bind_system(db, "test:mail-in")
        settings = db.query(OversightSettings).filter(OversightSettings.tenant_id == orgs[0]).first()
        if settings is None:
            settings = OversightSettings(tenant_id=orgs[0])
            db.add(settings)
        settings.mail_allowed_domains = ["hospital.example"]
        db.commit()
    monkeypatch.setattr(receiver, "MAX_MESSAGE_BYTES", 2000)
    with socket.socket() as probe:
        probe.bind((LOCAL, 0))
        port = probe.getsockname()[1]
    server = receiver.controller(LOCAL, port)
    server.start()
    try:
        with pytest.raises(smtplib.SMTPRecipientsRefused) as refused:
            _send(server, to, sender="someone@spam.example")
        assert refused.value.recipients[to][0] == 550
        with pytest.raises(smtplib.SMTPException) as too_big:
            _send(server, to, _message(to, body="x" * 5000))
        assert "552" in str(too_big.value) or getattr(too_big.value, "smtp_code", None) == 552
    finally:
        server.stop()
        with SessionLocal() as db:
            bind_system(db, "test:mail-in")
            db.query(OversightSettings).filter(OversightSettings.tenant_id == orgs[0]).update(
                {"mail_allowed_domains": []}
            )
            db.commit()


def test_em14_after_rotation_the_old_address_works_for_30_days_then_is_refused(orgs, smtp):
    old = _address(orgs[1])
    with SessionLocal() as control:
        bind_system(control, "test:mail-in")
        addresses.rotate(control, orgs[1], datetime.now(timezone.utc))
        control.commit()
        with SessionLocal() as db:
            bind_system(db, "test:mail-in")
            db.query(OversightSettings).filter(OversightSettings.tenant_id == orgs[1]).update(
                {"mail_daily_limit": 5000}
            )
            db.commit()
    new = _address(orgs[1])
    assert new != old
    _send(smtp, old)
    _send(smtp, new)
    with SessionLocal() as control:
        bind_system(control, "test:mail-in")
        control.query(InboundProviderMapping).filter(
            InboundProviderMapping.provider == PROVIDER,
            InboundProviderMapping.provider_account_id == old.split("@")[0],
        ).update({"updated_at": datetime.now(timezone.utc) - timedelta(days=31)})
        control.commit()
    with pytest.raises(smtplib.SMTPRecipientsRefused):
        _send(smtp, old)


def test_em16_switched_off_nothing_listens(monkeypatch):
    monkeypatch.delenv("MDARIX_EMAIL_INTAKE", raising=False)
    started = []
    monkeypatch.setattr(receiver, "controller", lambda *args: started.append(args))
    assert receiver.main() == 0 and started == []
