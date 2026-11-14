"""scripts/check_backup_age.sh (REQ-BAK-002): a production backup older than 26 hours raises an alert.

The script lists the off-site copies with the AWS CLI and alerts through the webhook with curl. Both are replaced by
shell functions, so the test runs the real script on any machine with bash and never reaches a bucket or a
webhook. Scenario rows PL-26 (negative: 27 hours old, alert) and PL-27 (2 hours old, no alert).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_backup_age.sh"
BASH = shutil.which("bash")

pytestmark = [pytest.mark.unit, pytest.mark.skipif(BASH is None, reason="needs bash, as the backup image has")]


def _run(tmp_path: Path, folders: list[str], **env) -> tuple[subprocess.CompletedProcess, str]:
    listing = "".join(f"                           PRE {name}/\n" for name in folders)
    (tmp_path / "listing.txt").write_text(listing, encoding="utf-8")
    calls = tmp_path / "webhook.txt"
    # Exported shell functions stand in for the AWS CLI and curl in the script's own bash.
    command = (
        f'aws() {{ cat "{(tmp_path / "listing.txt").as_posix()}"; }}; '
        f'curl() {{ printf "%s\\n" "$@" >> "{calls.as_posix()}"; }}; '
        f'export -f aws curl; bash "{SCRIPT.as_posix()}"'
    )
    environment = {key: value for key, value in os.environ.items() if key != "MDARIX_BACKUP_MAX_AGE_HOURS"}
    environment.update(
        MDARIX_BACKUP_S3_URI="s3://backups.example.invalid/prod",
        MDARIX_ALERT_WEBHOOK="https://alerts.example.invalid/hook",
        MDARIX_ENV="production",
        **env,
    )
    done = subprocess.run([BASH, "-c", command], capture_output=True, text=True, env=environment, timeout=60)
    return done, calls.read_text(encoding="utf-8") if calls.exists() else ""


def _folder(hours_ago: float) -> str:
    return f"{datetime.now(timezone.utc) - timedelta(hours=hours_ago):%Y%m%dT%H%M%SZ}"


@pytest.mark.requirement("PL-26")
def test_a_backup_27_hours_old_raises_the_alert(tmp_path):
    newest = _folder(27.2)
    done, webhook = _run(tmp_path, [_folder(51), newest])
    assert done.returncode == 1
    assert f"is {newest}, 27 hours old (limit 26)" in done.stderr
    assert "https://alerts.example.invalid/hook" in webhook
    assert "[MDARIX production] Backups are not arriving" in webhook


@pytest.mark.requirement("PL-26")
def test_no_backup_at_all_raises_the_alert(tmp_path):
    done, webhook = _run(tmp_path, [])
    assert done.returncode == 1 and "No backup found" in done.stderr
    assert "Backups are not arriving" in webhook


@pytest.mark.requirement("PL-27")
def test_a_backup_2_hours_old_raises_no_alert(tmp_path):
    newest = _folder(2.2)
    done, webhook = _run(tmp_path, [_folder(26.5), newest])
    assert done.returncode == 0, done.stderr
    assert f"Newest backup {newest}" in done.stdout and "is 2 hours old (limit 26)" in done.stdout
    assert webhook == ""
