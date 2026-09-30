"""Read-only local validation report for the repeatable demo/test stack."""

from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def tcp(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def http(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return {"reachable": True, "status": response.status}
    except Exception as exc:  # report only; never expose credentials
        return {"reachable": False, "error": type(exc).__name__}


def main() -> int:
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ports": {
            str(port): tcp(port)
            for port in [5177, 8007, 5433, 9000, 8025, 8101, 8102, 8103, 8104, 8105, 8106, 8107, 8108]
        },
        "http": {
            "frontend": http(os.getenv("PLAYWRIGHT_BASE_URL", "http://127.0.0.1:5177")),
            "backend_live": http(os.getenv("MDARIX_BACKEND_URL", "http://127.0.0.1:8007") + "/health/live"),
            "mailpit": http("http://127.0.0.1:8025/api/v1/messages"),
        },
        "database": "configured externally; validate with migrations and RLS tests",
        "production_gates": ["TLS", "runtime role", "backup/restore/PITR", "monitoring", "multi-instance"],
    }
    output = Path(os.getenv("MDARIX_EVIDENCE_DIR", "artifacts"))
    output.mkdir(parents=True, exist_ok=True)
    path = output / "local-stack-validation.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
