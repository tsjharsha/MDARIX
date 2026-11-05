"""The deploy's readiness gate: is the new release ready for traffic? (0.10.88, DEV-13)

Run inside the new API container right after ``docker compose up``, before the upgrade is declared good:

    docker compose exec -T api python scripts/deploy_gate.py --release v0.10.88 --timeout 180
    ... --require worker,scheduler,outbox      # also wait for these components to report well

It asks the same readiness report as /health/ready (backend/app/readiness.py) every few seconds until the gate passes
or the time is up. It passes when the code is the release named, the database answers as the runtime role with its
schema at this build's migration head, and every component named in ``--require`` is ok. /health/live only says the
process answers; this says the release can serve. Exit 0 when it passes; 1 with the reasons when it does not (the
upgrade script then rolls back, as it does today when /health/live does not answer).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def problems(report: dict, version: str, release: str, required: set[str]) -> list[str]:
    """Why the release is not ready (empty when it is)."""
    found = []
    if release and version.lstrip("v") != release.lstrip("v"):
        found.append(f"this code is v{version.lstrip('v')}, not {release}")
    checks = {item["name"]: item for item in report.get("checks", [])}
    database = checks.get("database", {})
    if not database.get("ok"):
        found.append(f"database: {database.get('error', 'not reported')}")
    for name in sorted(required):
        check = checks.get(name)
        if check is None:
            found.append(f"{name}: not reported")
        elif not check.get("ok"):
            found.append(f"{name}: {check.get('error', 'failing')}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", default="", help="the release this container must be, e.g. v0.10.88")
    parser.add_argument("--timeout", type=int, default=180, help="seconds to keep asking (default 180)")
    parser.add_argument("--require", default="", help="components that must be ok too, e.g. worker,scheduler")
    args = parser.parse_args()
    from backend.app import readiness
    from backend.app.version import APP_VERSION

    required = {name.strip() for name in args.require.split(",") if name.strip()}
    deadline = time.monotonic() + args.timeout
    while True:
        readiness._cached = None
        report = readiness.readiness_report()
        found = problems(report, APP_VERSION, args.release, required)
        summary = {item["name"]: item.get("error", "ok") for item in report.get("checks", [])}
        print(json.dumps({"release": f"v{APP_VERSION}", "status": report.get("status"), "checks": summary}))
        if not found:
            print("DEPLOY_GATE=PASS")
            return 0
        if time.monotonic() >= deadline:
            print("DEPLOY_GATE=FAIL " + "; ".join(found))
            return 1
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
