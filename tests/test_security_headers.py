"""The API sets the security headers Caddy adds in production (infrastructure/docker/Caddyfile) on its own responses."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)

EXPECTED = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def test_every_response_carries_the_browser_protections():
    response = client.get("/health/live")
    assert response.status_code == 200
    for name, value in EXPECTED.items():
        assert response.headers[name] == value, name
    policy = response.headers["Permissions-Policy"]
    assert all(
        feature in policy for feature in ("camera=()", "microphone=()", "geolocation=()", "payment=()", "usb=()")
    )
    csp = response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp and "form-action 'self'" in csp
    # Only API answers are kept out of caches by default; this is not one.
    assert response.headers.get("Cache-Control") != "no-store"


def test_api_answers_are_never_cached_unless_the_route_says_otherwise():
    refused = client.get("/api/v1/session/context")  # no session: refused, and still not cacheable
    assert refused.status_code == 401
    assert refused.headers["Cache-Control"] == "no-store"
    assert refused.headers["X-Frame-Options"] == "DENY"
    # The public company details choose their own short public caching.
    public = client.get("/api/v1/public/site-info")
    assert public.status_code == 200
    assert public.headers["Cache-Control"] == "public, max-age=300"


def test_the_caddyfile_and_the_api_name_the_same_protections():
    from pathlib import Path

    caddyfile = (Path(__file__).resolve().parents[1] / "infrastructure" / "docker" / "Caddyfile").read_text(
        encoding="utf-8"
    )
    for name, value in EXPECTED.items():
        assert f'{name} "{value}"' in caddyfile, name
    assert 'Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()"' in caddyfile
