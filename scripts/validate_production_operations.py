"""Fail-closed production operations gate: what can be observed from outside a deployment, and what cannot.

For every address in MDARIX_OPERATIONAL_URLS (comma-separated; default MDARIX_APP_URL) it checks the two public
health endpoints the front door serves: ``/health/live`` (the API process answers) and ``/health/status`` (``ok`` or
``degraded`` with 200; ``down`` with 503 when the database or schema is not fit for traffic). Readiness detail
(``/health/ready``) is internal and is not checked here. It then reports whether operational alerts and the
scheduler's dead-man's switch are configured in this environment, never treating configuration as proof of delivery:
``python scripts/send_test_alert.py`` proves alerts arrive.

    python scripts/validate_production_operations.py
    MDARIX_OPERATIONAL_URLS=https://app.mdarix.example python scripts/validate_production_operations.py

Exit status 1 when any target is not live or not serving.
"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check_url(base: str, path: str) -> tuple[int | None, str]:
    """(HTTP status or None when unreachable, the first 500 characters of the body or the error type)."""
    url = base.rstrip("/") + path
    try:
        with urlopen(Request(url, headers={"User-Agent": "MDARIX-operations-gate/1"}), timeout=10) as response:
            return response.status, response.read().decode("utf-8", errors="replace")[:500]
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:500]
    except (URLError, TimeoutError, OSError) as exc:
        return None, type(exc).__name__


def status_word(body: str) -> str | None:
    try:
        return json.loads(body).get("status")
    except (ValueError, AttributeError):
        return None


def main() -> int:
    targets = os.getenv("MDARIX_OPERATIONAL_URLS", "").strip() or os.getenv("MDARIX_APP_URL", "http://127.0.0.1:8007")
    urls = [item.strip().rstrip("/") for item in targets.split(",") if item.strip()]
    print("MDARIX PRODUCTION OPERATIONS GATE")
    print(f"TARGETS = {len(urls)}")

    healthy = []
    for index, base in enumerate(urls, 1):
        live_status, live_detail = check_url(base, "/health/live")
        status_code, status_body = check_url(base, "/health/status")
        word = status_word(status_body)
        live = live_status == 200
        serving = status_code == 200 and word in {"ok", "degraded"}
        healthy.append(live and serving)
        print(
            f"HEALTH instance_{index} live={'PASS' if live else 'FAIL'} "
            f"status={'PASS' if serving else 'FAIL'} ({word or status_code or status_body})"
        )
        if not live:
            print(f"  live_detail={live_status or live_detail}")
        if word == "degraded":
            print("  degraded: serving, but a component needs attention (read /health/ready on the server)")

    webhook = bool(os.getenv("MDARIX_ALERT_WEBHOOK", "").strip())
    email = bool(os.getenv("MDARIX_ALERT_EMAIL", "").strip())
    if webhook or email:
        channels = ", ".join(name for name, on in (("webhook", webhook), ("email", email)) if on)
        print(f"ALERT_DESTINATION = CONFIGURED ({channels}); prove delivery with scripts/send_test_alert.py")
    else:
        print("ALERT_DESTINATION = MISSING (set MDARIX_ALERT_WEBHOOK and/or MDARIX_ALERT_EMAIL)")
    heartbeat = os.getenv("MDARIX_SCHEDULER_HEARTBEAT_URL", "").strip()
    print(
        "SCHEDULER_HEARTBEAT = CONFIGURED (an outside monitor notices a stopped scheduler)"
        if heartbeat
        else "SCHEDULER_HEARTBEAT = PENDING (MDARIX_SCHEDULER_HEARTBEAT_URL is not set)"
    )
    print("UPTIME_MONITOR = PENDING (confirm an external monitor polls /health/status; see DEPLOYMENT.md)")
    return 0 if urls and all(healthy) else 1


if __name__ == "__main__":
    raise SystemExit(main())
