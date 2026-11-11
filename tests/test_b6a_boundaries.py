"""B6a Part B (spec 4.5): every security limit tested on both sides, the value just inside and the value just over.

Each test carries its scenario id (scenario-register.md B6-18..B6-27) as a ``requirement`` marker, so a validation
run can list which test proves which row: ``pytest -m db tests/test_b6a_boundaries.py -v``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from auth import cookies, totp
from auth.durable import new_session
from auth.service import MIN_LENGTH, password_problem
from backend.app import auth_router, client_errors, mfa, rate_limit, request_body
from backend.app.db.models.stage2 import AuthSession, LoginThrottle
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.test_auth_hardening import PASSWORD, _client_for, _user

pytestmark = pytest.mark.db
requirement = pytest.mark.requirement


@pytest.fixture
def behind_proxy(monkeypatch):
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "1")


def _address() -> str:
    return f"198.51.100.{secrets.randbelow(250) + 1}"


def _signin(client: TestClient, user, password: str, address: str):
    return client.post(
        "/api/v1/auth/signin",
        json={"email": user.username, "password": password},
        headers={"X-Forwarded-For": address},
    )


# ------------------------------------------------------------------------------------------- sign-in lockout


@requirement("B6-18")
def test_four_wrong_passwords_still_sign_in_and_five_lock(behind_proxy):
    assert auth_router.LOCK_AFTER_FAILURES == 5
    inside, over = _user(), _user()
    client, address = TestClient(app), _address()
    for _ in range(4):
        assert _signin(client, inside, "wrong password!", address).status_code == 401
    assert _signin(client, inside, PASSWORD, address).status_code == 200
    for _ in range(5):
        assert _signin(client, over, "wrong password!", address).status_code == 401
    locked = _signin(client, over, PASSWORD, address)
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "ACCOUNT_TEMPORARILY_LOCKED"


@requirement("B6-19")
def test_the_lock_lasts_fifteen_minutes_and_no_longer(behind_proxy):
    assert auth_router.LOCK_MINUTES == 15
    user, client, address = _user(), TestClient(app), _address()
    for _ in range(5):
        _signin(client, user, "wrong password!", address)
    key = auth_router._throttle_key(user.username.strip().lower(), address)
    with SessionLocal() as db:
        row = db.query(LoginThrottle).filter(LoginThrottle.identifier == key).one()
        assert row.locked_until - row.last_failure_at == timedelta(minutes=15)

    def lock_ends_in(seconds: int) -> None:
        with SessionLocal() as db:
            row = db.query(LoginThrottle).filter(LoginThrottle.identifier == key).one()
            row.locked_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            db.commit()

    lock_ends_in(5)  # 14:55 into the lock: still locked
    assert _signin(client, user, PASSWORD, address).status_code == 429
    lock_ends_in(-1)  # 15:01: open again
    assert _signin(client, user, PASSWORD, address).status_code == 200


# ------------------------------------------------------------------------------------------- MFA and signing


def _enrolled(clock: dict):
    user = _user()
    client, _ = _client_for(user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    enrolled = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert enrolled.status_code == 200, enrolled.text
    clock["step"] += 1
    return user, secret


def _wrong(secret: str) -> str:
    right = totp.current_code(secret)
    return next(code for code in ("000000", "111111") if code != right)


@requirement("B6-20")
def test_four_wrong_codes_then_the_right_one_signs_in_and_five_lock(monkeypatch):
    assert mfa.MAX_FAILURES == 5 and mfa.LOCK_MINUTES == 15
    clock = {"step": int(time.time() // 30)}
    monkeypatch.setattr(totp, "_step", lambda at=None: clock["step"])
    for wrong, expected in ((4, 200), (5, 429)):
        user, secret = _enrolled(clock)
        client = TestClient(app)
        assert client.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD}).json()[
            "mfa_required"
        ]
        for _ in range(wrong):
            assert client.post("/api/v1/auth/mfa/verify", json={"code": _wrong(secret)}).status_code in (403, 429)
        answer = client.post("/api/v1/auth/mfa/verify", json={"code": totp.current_code(secret)})
        assert answer.status_code == expected, (wrong, answer.text)
        if expected == 429:
            assert answer.json()["detail"]["code"] == "MFA_TEMPORARILY_LOCKED"


@requirement("B6-21")
def test_four_failed_signatures_still_allow_signing_and_five_lock_it():
    # The "sign" throttle every signature's re-authentication counts on (governance_router.reauthenticate).
    inside, over = _user(), _user()

    def fail(db, user) -> bool:
        locked = mfa.record_failure(db, user, "sign")
        db.commit()  # each refusal is committed on its own, as the signing routes do
        return locked

    with SessionLocal() as db:
        assert [fail(db, inside) for _ in range(4)] == [False] * 4
        mfa.ensure_not_locked(db, inside, "sign")
        assert [fail(db, over) for _ in range(5)] == [False] * 4 + [True]
        with pytest.raises(HTTPException) as refused:
            mfa.ensure_not_locked(db, over, "sign")
        assert refused.value.status_code == 429
        assert refused.value.detail["code"] == "SIGNATURE_TEMPORARILY_LOCKED"


# ------------------------------------------------------------------------------------------- sessions


def _expiry(client: TestClient) -> tuple[datetime, datetime]:
    with SessionLocal() as db:
        row = (
            db.query(AuthSession)
            .filter(AuthSession.session_hash == hashlib.sha256(client.token.encode()).hexdigest())
            .one()
        )
        return row.created_at, row.expires_at


def _session(*, signed_in_ago: timedelta, idle_for: timedelta, expires_in: timedelta) -> TestClient:
    user = _user()
    with SessionLocal() as db:
        token = new_session(db, user.id, user.tenant_id)
        row = db.query(AuthSession).filter(AuthSession.session_hash == hashlib.sha256(token.encode()).hexdigest()).one()
        now = datetime.now(timezone.utc)
        row.created_at, row.last_seen_at, row.expires_at = now - signed_in_ago, now - idle_for, now + expires_in
        db.commit()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    client.token = token
    return client


@requirement("B6-22")
def test_29_idle_minutes_keep_the_session_and_31_end_it(monkeypatch):
    monkeypatch.delenv("MDARIX_SESSION_IDLE_MINUTES", raising=False)
    hour = timedelta(hours=1)
    alive = _session(signed_in_ago=hour, idle_for=timedelta(minutes=29), expires_in=hour)
    assert alive.get("/api/v1/me/context").status_code == 200
    idle = _session(signed_in_ago=hour, idle_for=timedelta(minutes=31), expires_in=hour)
    ended = idle.get("/api/v1/me/context")
    assert ended.status_code == 401 and ended.json()["detail"]["code"] == "SESSION_IDLE_TIMEOUT"


@requirement("B6-23")
def test_a_session_lives_11_59_and_ends_at_twelve_hours():
    assert cookies.SESSION_SECONDS == 12 * 3600
    alive = _session(
        signed_in_ago=timedelta(hours=11, minutes=59), idle_for=timedelta(0), expires_in=timedelta(minutes=1)
    )
    assert alive.get("/api/v1/me/context").status_code == 200
    # The renewal on that request never carried it past twelve hours after sign-in.
    created, expires = _expiry(alive)
    assert expires <= created + timedelta(hours=12)
    ended = _session(
        signed_in_ago=timedelta(hours=12, minutes=1), idle_for=timedelta(0), expires_in=timedelta(minutes=-1)
    )
    assert ended.get("/api/v1/me/context").status_code == 401


# ------------------------------------------------------------------------------------------- rate limits


@requirement("B6-24")
@pytest.mark.parametrize("scope", sorted(rate_limit.LIMITS))
def test_each_rate_limit_allows_its_limit_and_refuses_one_more_with_retry_after(monkeypatch, scope):
    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", secrets.token_hex(16))
    frozen = int(time.time())
    monkeypatch.setattr(rate_limit, "time", SimpleNamespace(time=lambda: frozen))  # one window throughout
    rule, key = rate_limit.LIMITS[scope], f"boundary-{uuid.uuid4().hex}"
    for _ in range(rule.limit):
        rate_limit.enforce(scope, key)
    with pytest.raises(HTTPException) as refused:
        rate_limit.enforce(scope, key)
    assert refused.value.status_code == 429
    retry = int(refused.value.headers["Retry-After"])
    assert 0 < retry <= rule.window_seconds


# ------------------------------------------------------------------------------------------- request sizes


def _request(body: bytes, *, declared: bool) -> SimpleNamespace:
    async def stream():
        for start in range(0, len(body), 65536):
            yield body[start : start + 65536]

    headers = {"content-length": str(len(body))} if declared else {}
    return SimpleNamespace(headers=headers, stream=stream)


@requirement("B6-25")
@pytest.mark.parametrize("limit", [request_body.WEBHOOK_LIMIT_BYTES, 2 * 1024 * 1024])
@pytest.mark.parametrize("declared", [True, False])
def test_a_body_at_the_limit_is_read_and_one_byte_over_is_refused(limit, declared):
    # read_limited guards the webhooks (1 MB) and every import file (2 MB in a free trial, trial/imports.py).
    assert len(asyncio.run(request_body.read_limited(_request(b"x" * limit, declared=declared), limit))) == limit
    with pytest.raises(HTTPException) as refused:
        asyncio.run(request_body.read_limited(_request(b"x" * (limit + 1), declared=declared), limit))
    assert refused.value.status_code == 413


@requirement("B6-25")
def test_a_browser_error_report_of_64_kb_is_accepted_and_one_byte_more_refused():
    assert client_errors.MAX_BODY_BYTES == 64 * 1024
    tag = uuid.uuid4().hex
    body = json.dumps({"path": "/app", "message": f"TypeError: boundary [{tag}]"}).encode()
    at_limit = body + b" " * (client_errors.MAX_BODY_BYTES - len(body))  # JSON allows trailing white space
    headers = {"Content-Type": "application/json"}
    client = TestClient(app)
    assert client.post("/api/v1/client-errors", content=at_limit, headers=headers).status_code == 202
    over = client.post("/api/v1/client-errors", content=at_limit + b" ", headers=headers)
    assert over.status_code == 413 and over.json()["detail"]["code"] == "REPORT_TOO_LARGE"


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    try:
        yield user
    finally:
        with SessionLocal() as db:
            purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:b6a-boundaries-cleanup")


@requirement("B6-25")
def test_a_case_attachment_of_10_mb_is_stored_and_one_byte_more_refused(trial, monkeypatch, tmp_path):
    from backend.app import stage3_workflow_router
    from tests.test_intake_triage_api import INTAKE, _ok

    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path))
    for name in ("MDARIX_CLAMD_HOST", "MDARIX_MALWARE_SCANNER_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    limit = stage3_workflow_router.MAX_ATTACHMENT_BYTES
    assert limit == 10 * 1024 * 1024
    case = _ok(trial.post(INTAKE, json={"kind": "CONTACT", "reporter_words": "Boundary test: log file to follow"}))

    def upload(size: int):
        return trial.post(f"{INTAKE}/{case['id']}/attachments", files={"file": ("log.txt", b"a" * size, "text/plain")})

    stored = upload(limit)
    assert stored.status_code == 200, stored.text[:300]
    assert stored.json()["size"] == limit
    refused = upload(limit + 1)
    assert refused.status_code == 413 and refused.json()["detail"]["code"] == "ATTACHMENT_TOO_LARGE"


@requirement("B6-25")
def test_a_submission_file_of_2_mb_is_kept_and_one_byte_more_refused(monkeypatch):
    import base64

    from backend.app.authority_reports import router as reports_router
    from backend.app.authority_reports import rules as report_rules

    monkeypatch.setattr(reports_router.ObjectStorageService, "scan", lambda self, data, content_type: True)
    limit = report_rules.FILE_MAX
    assert limit == 2 * 1024 * 1024

    def payload(size: int):
        return reports_router.FileIn(name="ack.pdf", data=base64.b64encode(b"a" * size).decode())

    assert reports_router._file(payload(limit))["size"] == limit
    with pytest.raises(HTTPException) as refused:
        reports_router._file(payload(limit + 1))
    assert refused.value.status_code == 422 and refused.value.detail["code"] == "FILE_TOO_LARGE"


def test_the_e_mail_limits_are_25_mb_and_30_an_hour():  # constants only; both sides are in tests/test_mail_in.py
    from backend.app.mail_in import receiver

    assert receiver.MAX_MESSAGE_BYTES == 25 * 1024 * 1024 and receiver.PER_IP_PER_HOUR == 30
    # shortcut: the receiver's own size and per-address checks are proven at small limits in tests/test_mail_in.py
    # (monkeypatched); a real 25 MB SMTP session is left to the release checks' manual list.


# ------------------------------------------------------------------------------------------- rows and passwords


@requirement("B6-26")
@pytest.mark.parametrize(("entity", "limit"), [("cases", 5_000), ("complaints", 50_000)])
def test_a_file_at_the_row_limit_is_checked_and_one_row_more_is_refused(monkeypatch, entity, limit):
    from backend.app.intake import case_import
    from backend.app.trial import imports

    assert (case_import.MAX_ROWS if entity == "cases" else imports.MAX_ROWS_PER_FILE) == limit

    class Checked(Exception):
        pass

    class Counted(Exception):
        pass

    def checked(*_args, **_kwargs):
        raise Checked

    def counted(*_args, **_kwargs):
        raise Counted

    # Stop at the first step after the size rule: the rows' values are checked (inside) or never are (over).
    monkeypatch.setattr(imports, "_check_values", checked)
    monkeypatch.setattr(imports, "uploaded_rows", counted)
    rows = [(line, {}) for line in range(2, limit + 2)]
    with pytest.raises(Checked):
        imports._check_rows(None, None, entity, rows, imports._Report(), imports.TRIAL_POLICY)
    report = imports._Report()
    with pytest.raises(Counted):
        imports._check_rows(None, None, entity, [*rows, (limit + 2, {})], report, imports.TRIAL_POLICY)
    assert report.file_problems == 1
    assert f"one file can have up to {limit:,}" in report.issues[0]["message"]


@requirement("B6-27")
def test_a_password_of_12_characters_is_accepted_and_11_refused():
    assert MIN_LENGTH == 12
    assert password_problem("Kq7#mVx2pL9w") is None
    assert password_problem("Kq7#mVx2pL9") == "PASSWORD_TOO_SHORT"
