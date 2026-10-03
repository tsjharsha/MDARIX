"""Check a running API started with MDARIX_ENV=production behaves as production must (CI job "Production mode").

    python scripts/production_smoke.py --base http://127.0.0.1:8000 --origin https://app.example.test \\
        --email admin@example.test --token <activation token>

Checks: health; API documentation is off; security headers (HSTS, CSP, frame denial); a sign-in from another site is
refused (CSRF); an invited platform administrator activates, signs in, gets a __Host- session cookie that is Secure,
HttpOnly and SameSite, and must set up MFA before anything else; a weak or breached password is refused. Exits 1
listing every failed check.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

PASSWORD = "Production smoke 2026: correct horse battery"


def call(base: str, method: str, path: str, *, origin: str | None = None, body: dict | None = None, cookie=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if origin:
        request.add_header("Origin", origin)
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if not ok and detail else ""))
        if not ok:
            failures.append(name)

    status, _, body = call(args.base, "GET", "/health/live")
    check("liveness answers", status == 200, status)
    status, _, body = call(args.base, "GET", "/health/ready")
    check("readiness answers without a server error", status in (200, 503), status)
    for path in ("/docs", "/openapi.json", "/redoc"):
        status, _, _ = call(args.base, "GET", path)
        check(f"{path} is not served", status == 404, status)

    status, headers, _ = call(args.base, "GET", "/health/live")
    check("HSTS is sent", "max-age=" in (headers.get("Strict-Transport-Security") or ""))
    check("CSP is sent", "frame-ancestors 'none'" in (headers.get("Content-Security-Policy") or ""))
    check("framing is denied", headers.get("X-Frame-Options") == "DENY")

    status, _, body = call(
        args.base,
        "POST",
        "/api/v1/auth/signin",
        origin="https://evil.example",
        body={"email": args.email, "password": "x" * 12},
    )
    check("sign-in from another site is refused", status == 403 and b"CSRF_ORIGIN_DENIED" in body, status)

    status, _, body = call(
        args.base,
        "POST",
        "/api/v1/auth/activate-account",
        origin=args.origin,
        body={"token": args.token, "password": "password1234"},
    )
    check("a weak or breached password is refused", status == 422, status)
    status, _, body = call(
        args.base,
        "POST",
        "/api/v1/auth/activate-account",
        origin=args.origin,
        body={"token": args.token, "password": PASSWORD},
    )
    check("the invited administrator activates the account", status == 200, body[:200])

    status, headers, body = call(
        args.base, "POST", "/api/v1/auth/signin", origin=args.origin, body={"email": args.email, "password": PASSWORD}
    )
    check("the administrator signs in", status == 200, body[:200])
    payload = json.loads(body or b"{}") if status == 200 else {}
    check("MFA setup is required before anything else", payload.get("mfa_enrollment_required") is True, payload)
    cookie = headers.get("Set-Cookie") or ""
    check("the session cookie is __Host- prefixed", cookie.startswith("__Host-mdarix_session="), cookie[:60])
    lowered = cookie.lower()
    check(
        "the session cookie is Secure, HttpOnly and SameSite",
        "secure" in lowered and "httponly" in lowered and "samesite" in lowered,
        cookie,
    )
    session = cookie.split(";", 1)[0]
    status, _, body = call(args.base, "GET", "/api/v1/session/context", cookie=session)
    check("the pending session cannot open the workspace", status == 403 and b"MFA_ENROLLMENT_REQUIRED" in body, status)

    print(f"\n{len(failures)} check(s) failed." if failures else "\nAll production checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
