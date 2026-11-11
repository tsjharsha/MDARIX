"""Clock check for the release IQ, after a server, network or NTP change, and in the restore drill (B6a G19).

    python scripts/clock_check.py                       # print the check, save artifacts/clock-check-<UTC time>.json
    python scripts/clock_check.py --ntp time.example.org  # also ask this time server (else MDARIX_NTP_SERVER)

Prints the application's time, the database clock's offset (corrected for the round trip), the time server's offset
and, on a host with chrony, ``chronyc tracking``. The limit is 1 s (B6a-D7). Exit status 0 when the check is ok, 1 when
an offset is above the limit or a source could not be measured. Nothing is changed and no record is re-timed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _chrony() -> str | None:
    """``chronyc tracking`` on this host, or None where chrony is not installed (a developer laptop)."""
    path = shutil.which("chronyc")
    if not path:
        return None
    try:
        return subprocess.run([path, "tracking"], capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return f"chronyc failed: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--ntp", default="", help="time server to ask (default: MDARIX_NTP_SERVER)")
    parser.add_argument("--out", default=str(ROOT / "artifacts"), help="folder for the JSON record")
    args = parser.parse_args(argv)
    if args.ntp:
        os.environ["MDARIX_NTP_SERVER"] = args.ntp
    from backend.app import clock_check
    from backend.app.db.session import runtime_engine

    with runtime_engine.connect() as connection:
        result = clock_check.check(connection)
    record = {
        "check": "MDARIX clock check (B6a G19)",
        "app_time_utc": datetime.now(timezone.utc).isoformat(),
        **result,
        "chronyc_tracking": _chrony(),
    }
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"clock-check-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))
    print(f"Saved {target}")
    return 0 if result["state"] == clock_check.OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
