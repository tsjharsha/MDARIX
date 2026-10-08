"""scripts/production_smoke.py judges a production server correctly: a 503 from readiness or the public status fails
the run, and behind the front door readiness detail must be hidden. The HTTP calls are replaced by canned answers."""

from __future__ import annotations

import importlib.util
import json
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("production_smoke", ROOT / "scripts" / "production_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

SECURITY = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}
COOKIE = "__Host-mdarix_session=abc; Path=/; Secure; HttpOnly; SameSite=Strict"


def _headers(values: dict) -> Message:
    message = Message()
    for name, value in values.items():
        message[name] = value
    return message


def fake_server(overrides: dict | None = None):
    """A production API that passes every check, unless ``overrides`` replaces the answer for a path."""
    answers = {
        "/health/live": (200, SECURITY, b'{"status":"alive"}'),
        "/health/ready": (200, {}, b'{"status":"ready"}'),
        "/health/status": (200, {"Cache-Control": "no-store"}, b'{"status":"ok"}'),
        "/docs": (404, {}, b""),
        "/openapi.json": (404, {}, b""),
        "/redoc": (404, {}, b""),
        "/api/v1/auth/session": (401, {"Cache-Control": "no-store"}, b"{}"),
        "/api/v1/session/context": (403, {}, b'{"detail":{"code":"MFA_ENROLLMENT_REQUIRED"}}'),
        **(overrides or {}),
    }

    def call(base, method, path, *, origin=None, body=None, cookie=None):
        if path == "/api/v1/auth/signin" and origin == "https://evil.example":
            return 403, _headers({}), b'{"detail":{"code":"CSRF_ORIGIN_DENIED"}}'
        if path == "/api/v1/auth/activate-account":
            weak = body["password"] == "password1234"
            return (422, _headers({}), b"{}") if weak else (200, _headers({}), b"{}")
        if path == "/api/v1/auth/signin":
            return 200, _headers({"Set-Cookie": COOKIE}), json.dumps({"mfa_enrollment_required": True}).encode()
        status, headers, payload = answers[path]
        return status, _headers(headers), payload

    return call


def run(monkeypatch, overrides=None, *extra) -> int:
    monkeypatch.setattr(smoke, "call", fake_server(overrides))
    argv = ["--base", "https://x", "--origin", "https://x", "--email", "a@x.test", "--token", "t", *extra]
    return smoke.main(argv)


def test_a_healthy_production_api_passes(monkeypatch, capsys):
    assert run(monkeypatch) == 0
    assert "All production checks passed." in capsys.readouterr().out


def test_a_degraded_server_still_passes(monkeypatch):
    assert run(monkeypatch, {"/health/status": (200, {"Cache-Control": "no-store"}, b'{"status":"degraded"}')}) == 0


@pytest.mark.parametrize(
    "path,answer",
    [
        ("/health/ready", (503, {}, b'{"status":"not_ready"}')),
        ("/health/status", (503, {"Cache-Control": "no-store"}, b'{"status":"down"}')),
    ],
)
def test_a_503_fails_the_run(monkeypatch, capsys, path, answer):
    assert run(monkeypatch, {path: answer}) == 1
    assert "FAIL" in capsys.readouterr().out


def test_behind_the_front_door_readiness_must_be_hidden(monkeypatch, capsys):
    hidden = {"/health/ready": (404, {}, b"")}
    assert run(monkeypatch, hidden, "--front-door") == 0
    assert run(monkeypatch, {}, "--front-door") == 1
    assert "FAIL  readiness detail is not public" in capsys.readouterr().out


def test_behind_the_front_door_api_answers_must_not_be_cacheable(monkeypatch, capsys):
    cacheable = {"/health/ready": (404, {}, b""), "/api/v1/auth/session": (401, {}, b"{}")}
    assert run(monkeypatch, cacheable, "--front-door") == 1
    assert "FAIL  API responses are not cacheable" in capsys.readouterr().out


def test_the_web_apps_page_at_docs_is_not_mistaken_for_api_documentation(monkeypatch):
    page = (200, {}, b"<!doctype html><div id=root></div>")
    assert run(monkeypatch, {"/docs": page, "/redoc": page, "/openapi.json": page}) == 0
    swagger = (200, {}, b"<html><script src=swagger-ui-bundle.js></script></html>")
    assert run(monkeypatch, {"/docs": swagger}) == 1
    schema = (200, {}, b'{"openapi": "3.1.0", "paths": {}}')
    assert run(monkeypatch, {"/openapi.json": schema}) == 1
