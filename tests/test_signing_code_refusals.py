"""A signature's wrong, blank or reused authenticator code is refused with a code about the signature, never with
MFA_REQUIRED: that code means "this sign-in still owes its second factor" and sends the browser to /mfa, losing what
the person typed into the signing form (0.10.62, J1)."""

import inspect
import sys
import types
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app import governance_router
from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.models.stage2 import LoginThrottle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.enterprise_audit import make_audit_event
from backend.app.main import app
from tests.route_inventory import api_routes
from tests.test_mfa_mvp import PASSWORD, _enroll, _make_user, _next_code, _sign_in

# Every route whose signature or controlled approval goes through verify_signing_credentials. A new signing route
# must be added here, and so to the browser's signing forms that show the refusal in place. B2's Case and triage
# routes (0.10.93) are tested route by route in test_triage_signing_refusals.py; /confirm carries no credential.
SIGNING_ROUTES = {
    ("POST", "/api/v1/capas/{capa_id}/effectiveness/result"),
    ("POST", "/api/v1/complaints/{complaint_id}/disposition/sign"),
    ("POST", "/api/v1/complaints/{complaint_id}/market-assessments/{market}/sign"),
    ("POST", "/api/v1/complaints/{complaint_id}/market-assessments/OTHER-{country}/sign"),  # B9b
    ("POST", "/api/v1/complaints/{complaint_id}/resolve-and-close"),
    ("POST", "/api/v1/decision-guides/{market}/versions/{version}/approve"),
    ("POST", "/api/v1/documents/{version_id}/sign"),
    ("POST", "/api/v1/governance/decisions/{decision_id}/sign"),
    ("POST", "/api/v1/intake/{event_id}/check/review"),
    ("POST", "/api/v1/intake/{event_id}/check/sign"),
    ("POST", "/api/v1/intake/{event_id}/void"),
    ("POST", "/api/v1/investigations/{investigation_id}/decision/sign"),
    ("POST", "/api/v1/investigations/{investigation_id}/lot-impact/sign"),
    ("POST", "/api/v1/oversight/events/{complaint_id}/ready"),
    ("POST", "/api/v1/regulatory/documents/{document_id}/status"),
    ("POST", "/api/v1/reports/{obligation_id}/attached-submission"),  # B9b: the recorder signs (B9b-N4)
    ("POST", "/api/v1/reports/{obligation_id}/snapshots/{snapshot_id}/approve"),
    ("POST", "/api/v1/triage/downgrades/{task_id}"),
    ("POST", "/api/v1/triage/{kind}/{record_id}/confirm"),
    ("POST", "/api/v1/triage/{kind}/{record_id}/confirm-qms"),
    ("POST", "/api/v1/triage/{kind}/{record_id}/exclude-threat"),
    ("POST", "/api/v1/triage/{kind}/{record_id}/record"),
}


def _reaches(function, target: str, seen: set) -> bool:
    """Whether a function (or a module-level helper it calls, at any depth, imported from another app module too: B7's
    resolve-and-close signs through the disposition router's ``sign``) names ``target``."""
    if function in seen or not isinstance(function, types.FunctionType):
        return False
    seen.add(function)
    module = sys.modules.get(function.__module__)
    codes = [function.__code__]
    while codes:
        code = codes.pop()
        if target in code.co_names or target in code.co_varnames:
            return True
        codes.extend(const for const in code.co_consts if isinstance(const, types.CodeType))
        for name in code.co_names:
            helper = getattr(module, name, None)
            if isinstance(helper, types.FunctionType) and helper.__module__.startswith("backend.app."):
                if _reaches(helper, target, seen):
                    return True
    return False


def _signing_routes():
    for path, route in api_routes(app):
        if _reaches(inspect.unwrap(route.endpoint), "verify_signing_credentials", set()):
            for method in route.methods:
                yield method, path, route


def test_every_signing_route_is_known():
    assert {(method, path) for method, path, _ in _signing_routes()} == SIGNING_ROUTES


def test_no_signing_module_answers_mfa_required_itself():
    modules = {sys.modules[inspect.unwrap(route.endpoint).__module__] for *_, route in _signing_routes()}
    assert len(modules) >= 10
    for module in modules:
        assert '"MFA_REQUIRED"' not in inspect.getsource(module), module.__name__


@pytest.fixture
def signer():
    email = _make_user(role="APPROVER")
    client, _ = _sign_in(email)
    secret, _ = _enroll(client)
    with SessionLocal() as db:
        bind_system(db, "test: signer")
        user = db.query(AuthUser).filter(AuthUser.username == email).one()
        ctx = SimpleNamespace(user_id=str(user.id), tenant_id=user.tenant_id)
    yield ctx, secret
    with SessionLocal() as db:
        db.query(LoginThrottle).filter(LoginThrottle.identifier == f"sign:{ctx.user_id}").delete()
        db.commit()


def _verify(ctx, *, password=PASSWORD, code=None):
    refusals = []
    with SessionLocal() as db:
        bind_system(db, "test: verify signing")
        try:
            governance_router.verify_signing_credentials(
                db, ctx, password=password, mfa_code=code, record_refusal=refusals.append
            )
            db.commit()  # as the signing route does with its signature
        except HTTPException as refused:
            return refused.status_code, refused.detail, refusals
    return 200, None, refusals


@pytest.mark.db
def test_a_wrong_blank_or_reused_code_is_a_signature_refusal(monkeypatch, signer):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    ctx, secret = signer
    status, detail, refusals = _verify(ctx, code="000000")
    assert status == 403 and detail["code"] == "SIGNATURE_CODE_INVALID"
    assert detail["message"] == "That code didn't match. Enter the current code from your authenticator app."
    assert refusals == ["SIGNATURE_MFA_FAILED"]
    status, detail, _ = _verify(ctx, code=None)
    assert status == 403 and detail["code"] == "SIGNATURE_CODE_INVALID"
    assert detail["message"] == "Enter the current code from your authenticator app."
    code = _next_code(secret)
    assert _verify(ctx, code=code)[0] == 200
    status, detail, _ = _verify(ctx, code=code)  # each code works once
    assert status == 403 and detail["code"] == "SIGNATURE_CODE_INVALID"


@pytest.mark.db
@pytest.mark.parametrize("password, code", [("not-the-password", None), (PASSWORD, "000000")])
def test_a_refusal_never_commits_what_the_route_staged(monkeypatch, signer, password, code):
    """The helper rolls back the caller's session before the refusal audit is committed (hardening 0.10.95)."""
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    ctx, _ = signer
    marker = f"staged-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        bind_system(db, "test: staged change")
        user = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(ctx.user_id)).one()
        before = user.display_name
        user.display_name = marker  # what a route changed before it checked the signature

        def refused(action):
            db.add(
                make_audit_event(
                    tenant_id=ctx.tenant_id,
                    actor_ref=ctx.user_id,
                    action=action,
                    entity_type="Test",
                    details={"m": marker},
                )
            )

        with pytest.raises(HTTPException) as caught:
            governance_router.verify_signing_credentials(
                db, ctx, password=password, mfa_code=code, record_refusal=refused
            )
    assert caught.value.status_code == 403
    with SessionLocal() as db:
        bind_system(db, "test: read back")
        assert db.query(AuthUser).filter(AuthUser.id == uuid.UUID(ctx.user_id)).one().display_name == before
        audits = (
            db.query(AuditEvent).filter(AuditEvent.actor_ref == ctx.user_id, AuditEvent.entity_type == "Test").all()
        )
        assert [row.details["m"] for row in audits] == [marker]
        throttle = db.query(LoginThrottle).filter(LoginThrottle.identifier == f"sign:{ctx.user_id}").one()
        assert throttle.failure_count == 1  # the failed attempt still counts


@pytest.mark.db
def test_repeated_wrong_codes_lock_signing_with_a_signature_code(monkeypatch, signer):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    ctx, _ = signer
    statuses = [_verify(ctx, code=f"{n:06d}") for n in range(6)]
    assert [item[0] for item in statuses] == [403] * 5 + [429]
    assert statuses[5][1]["code"] == "SIGNATURE_TEMPORARILY_LOCKED"
