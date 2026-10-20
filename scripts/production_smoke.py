"""Check a running API started with MDARIX_ENV=production behaves as production must (CI jobs "Production mode" and
"Production stack").

    python scripts/production_smoke.py --base http://127.0.0.1:8000 --origin https://app.mdarix-ci.test \\
        --email admin@mdarix-ci.test --token <activation token>
    python scripts/production_smoke.py --front-door --base https://localhost --origin https://localhost ...

Checks: health (a readiness or status answer of 503 fails: the server is up but not fit for traffic); API documentation
is off; security headers (HSTS, CSP, frame denial); a sign-in from another site is refused (CSRF); an invited platform
administrator activates, signs in, gets a __Host- session cookie that is Secure, HttpOnly and SameSite=Strict, and must set up
MFA before anything else; a weak or breached password is refused. With ``--front-door`` the base is Caddy
(docker-compose.prod.yml): readiness detail must then be hidden (404) and API responses must not be cacheable. Exits 1
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


def api_docs_served(status: int, body: bytes) -> bool:
    """True when the response is interactive API documentation or the OpenAPI schema. Behind Caddy, /docs is a page
    of the web app (200 with the app's index.html), which is fine; the API's own documentation is not."""
    lowered = (body or b"")[:20000].lower()
    return status == 200 and (b"swagger-ui" in lowered or b'"openapi"' in lowered or b"redoc.standalone" in lowered)


# Website pages behind the front door: each has its own pre-rendered file, with its canonical address and its text
# in the page (frontend/scripts/prerender.mjs, infrastructure/docker/Caddyfile; WEB-05). The canonical names the
# production site whatever the host the check runs against.
WEBSITE_PAGES = ("/", "/platform", "/trust/regulations", "/videos")
SITE_URL = "https://mdarix.in"


def website_page(body: bytes, path: str) -> bool:
    """The pre-rendered page for ``path``: its own canonical address and the page's markup inside the root."""
    canonical = f'<link rel="canonical" href="{SITE_URL}{path}"'.encode()
    return canonical in (body or b"") and b'<div id="root"><' in (body or b"")


def application_shell(body: bytes) -> bool:
    """The plain application shell: an empty root and no canonical address (it is served for every other path)."""
    return b'<div id="root"></div>' in (body or b"") and b'rel="canonical"' not in (body or b"")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument(
        "--front-door", action="store_true", help="the base is the Caddy front door, not the API container"
    )
    args = parser.parse_args(argv)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if not ok and detail else ""))
        if not ok:
            failures.append(name)

    status, _, body = call(args.base, "GET", "/health/live")
    check("liveness answers", status == 200, status)
    status, _, body = call(args.base, "GET", "/health/ready")
    if args.front_door:
        check("readiness detail is not public", status == 404, status)
    else:
        check("readiness: the database answers and the schema is current", status == 200, body[:300])
    status, headers, body = call(args.base, "GET", "/health/status")
    word = (json.loads(body or b"{}") if status in (200, 503) else {}).get("status")
    check("the public status is ok or degraded", status == 200 and word in ("ok", "degraded"), f"{status} {word}")
    check("the public status is never cached", "no-store" in (headers.get("Cache-Control") or ""))
    for path in ("/docs", "/openapi.json", "/redoc"):
        status, _, body = call(args.base, "GET", path)
        check(f"{path} is not served", status == 404 or not api_docs_served(status, body), status)

    status, headers, _ = call(args.base, "GET", "/health/live")
    check("HSTS is sent", "max-age=" in (headers.get("Strict-Transport-Security") or ""))
    check("CSP is sent", "frame-ancestors 'none'" in (headers.get("Content-Security-Policy") or ""))
    check("framing is denied", headers.get("X-Frame-Options") == "DENY")
    if args.front_door:
        status, headers, _ = call(args.base, "GET", "/api/v1/auth/session")
        check("API responses are not cacheable", "no-store" in (headers.get("Cache-Control") or ""), status)
        for path in WEBSITE_PAGES:
            status, _, body = call(args.base, "GET", path)
            check(f"{path} serves its own pre-rendered page", status == 200 and website_page(body, path), status)
        for path in ("/app", "/signin"):
            status, _, body = call(args.base, "GET", path)
            check(f"{path} gets the plain application shell", status == 200 and application_shell(body), status)

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
        "the session cookie is Secure, HttpOnly and SameSite=Strict",
        "secure" in lowered and "httponly" in lowered and "samesite=strict" in lowered,
        cookie,
    )
    session = cookie.split(";", 1)[0]
    status, _, body = call(args.base, "GET", "/api/v1/session/context", cookie=session)
    check("the pending session cannot open the workspace", status == 403 and b"MFA_ENROLLMENT_REQUIRED" in body, status)

    print(f"\n{len(failures)} check(s) failed." if failures else "\nAll production checks passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
