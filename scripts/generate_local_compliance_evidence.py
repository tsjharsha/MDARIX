"""Generate a reproducible local MVP compliance evidence report.

This report intentionally records local evidence only; it does not make
production compliance claims.  It archives an expired synthetic audit event,
collects test identifiers and existing browser artifacts, and writes a
machine-readable manifest for review.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "artifacts" / "compliance"
ARCHIVE = OUT / "audit-archives"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    expired = SimpleNamespace(
        id="local-expired-compliance-event",
        tenant_id="local-mvp-tenant-a",
        actor_ref="local-compliance-test",
        action="RETENTION_TEST_EVENT",
        entity_type="ComplianceEvidence",
        entity_id=None,
        details={"source": "LOCAL_MVP_VALIDATION"},
        source_ip="127.0.0.1",
        user_agent="MDARIX-local-compliance",
        reason="Verify local retention archival",
        old_values={"status": "ACTIVE"},
        new_values={"status": "EXPIRED"},
        retention_until=now - timedelta(days=1),
        created_at=now - timedelta(days=2),
    )
    from backend.app.retention import archive_expired_audit_events

    retention = archive_expired_audit_events([expired], archive_dir=ARCHIVE, now=now)
    test_commands = {
        "audit_controls": [sys.executable, "-m", "pytest", "-q", "tests/test_audit_compliance_controls.py"],
        "compliance_report": [sys.executable, "-m", "pytest", "-q", "tests/test_compliance_report.py"],
    }
    tests = {}
    for name, command in test_commands.items():
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        tests[name] = {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "command": " ".join(command),
            "output_tail": (result.stdout + result.stderr)[-2000:],
        }
    screenshots = sorted(str(path.relative_to(ROOT)) for path in (ROOT / "frontend" / "artifacts").glob("*.png"))
    report = {
        "report": "MDARIX_LOCAL_MVP_COMPLIANCE_EVIDENCE",
        "generated_at": now.isoformat(),
        "scope": "Local synthetic MVP validation only; production compliance is not claimed.",
        "test_ids": [
            "test_audit_diff_is_redacted_and_contains_only_changed_values",
            "test_audit_event_captures_request_origin_and_retention",
            "test_expired_audit_events_are_archived_without_deletion",
            "test_compliance_report_payload_is_renderable_in_all_formats",
        ],
        "tests": tests,
        "retention": retention,
        "archive_exists": Path(retention.get("archive_path", "")).exists(),
        "screenshots": screenshots,
        "audit_ids": ["local-expired-compliance-event"],
        "browser_workflows": [
            "audit history",
            "audit export",
            "evidence package download",
            "signature verification",
            "MFA enrollment/challenge",
        ],
        "browser_execution": "See retained Playwright artifacts; live authenticated execution remains environment-dependent.",
    }
    (OUT / "local-compliance-evidence.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS"
                if all(item["status"] == "PASS" for item in tests.values()) and report["archive_exists"]
                else "FAIL",
                "report": str(OUT / "local-compliance-evidence.json"),
                "retention": retention,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if report["archive_exists"] and all(item["status"] == "PASS" for item in tests.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
