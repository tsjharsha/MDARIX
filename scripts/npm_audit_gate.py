"""Run the frontend npm audit and fail on any high or critical advisory that is not a reviewed, unexpired exception.

npm audit has no ignore list, so CI calls this instead of `npm audit --audit-level=high`. Exceptions live in
.npm-audit-exceptions.toml (id, package, reason, reviewed_by, expires). An expired entry fails the run on its own.

    python scripts/npm_audit_gate.py              # every dependency
    python scripts/npm_audit_gate.py --omit=dev   # extra arguments go to npm audit
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCEPTIONS_FILE = ROOT / ".npm-audit-exceptions.toml"
BLOCKING = {"high", "critical"}


def load_exceptions(path: Path = EXCEPTIONS_FILE) -> list[dict]:
    return tomllib.loads(path.read_text(encoding="utf-8")).get("exception", [])


def problems(report: dict, exceptions: list[dict], today: datetime.date) -> list[str]:
    """Return what fails the audit: unlisted high/critical advisories and expired exceptions."""
    if "error" in report or "vulnerabilities" not in report:
        return [f"npm audit did not produce a report: {report.get('error', report)}"]
    found = []
    for exc in exceptions:
        if exc["expires"] < today:
            found.append(f"exception {exc['id']} ({exc['package']}) expired on {exc['expires']}: review it again")
    allowed = {(exc["id"], exc["package"]) for exc in exceptions if exc["expires"] >= today}
    seen = set()
    for vuln in report["vulnerabilities"].values():
        # String entries in "via" point at another package's advisory, which is checked under that package.
        for via in vuln.get("via", []):
            if not isinstance(via, dict) or via.get("severity") not in BLOCKING:
                continue
            advisory = (via.get("url", "").rsplit("/", 1)[-1] or str(via.get("source")), via.get("name"))
            if advisory in allowed or advisory in seen:
                continue
            seen.add(advisory)
            found.append(
                f"{via['severity']} {advisory[0]} in {advisory[1]}: {via.get('title', '')} {via.get('url', '')}"
            )
    return found


def main(argv: list[str]) -> int:
    npm = shutil.which("npm") or "npm"
    result = subprocess.run(
        [npm, "--prefix", str(ROOT / "frontend"), "audit", "--json", *argv], capture_output=True, text=True
    )
    report = json.loads(result.stdout or "{}")
    found = problems(report, load_exceptions(), datetime.date.today())
    for line in found:
        print(f"FAIL {line}")
    if found:
        return 1
    print(f"{' '.join(['npm audit', *argv])}: no high or critical advisory outside {EXCEPTIONS_FILE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
