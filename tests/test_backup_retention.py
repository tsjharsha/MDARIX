"""Backup retention, 30 daily + 12 monthly (owner decision, 5 Nov 2026; 0.10.88): infrastructure/docker/backup/
retention.sh decides which local backup folders backup.sh removes."""

import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infrastructure" / "docker" / "backup" / "retention.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash, as the backup image has")


def _expired(folder: Path, today: date, keep_days: int = 30, keep_months: int = 12) -> set[str]:
    command = f'source "{SCRIPT.as_posix()}" && expired_backups "{folder.as_posix()}" {today:%Y%m%d} {keep_days} {keep_months}'
    out = subprocess.run([BASH, "-c", command], capture_output=True, text=True, check=True).stdout
    return {Path(line).name for line in out.split()}


def test_thirty_days_and_the_newest_of_each_of_twelve_months_are_kept(tmp_path):
    today = date(2026, 11, 5)
    names = []
    # A daily backup at 03:00 for 15 months, and a pre-upgrade backup on 3 Nov (two that day).
    for back in range(460):
        day = today - timedelta(days=back)
        names.append(f"{day:%Y%m%d}T030000Z")
    names.append("20261103T151005Z")
    for name in names:
        (tmp_path / name).mkdir()
    (tmp_path / "lost+found").mkdir()
    expired = _expired(tmp_path, today)
    kept = set(names) - expired

    daily = {name for name in kept if datetime.strptime(name[:8], "%Y%m%d").date() > today - timedelta(days=30)}
    assert len(daily) == 31  # 30 days of daily backups, and the second backup of 3 Nov (taken before an upgrade)
    assert "20261103T151005Z" in kept and "20261103T030000Z" in kept
    monthly = kept - daily
    # The newest backup of each of the twelve months before those 30 days: October 2026 (its days before the window)
    # back to November 2025.
    expected, year, month = [], 2026, 10
    for _ in range(12):
        expected.append(f"{year}{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    assert sorted(name[:6] for name in monthly) == sorted(expected)
    for name in monthly:
        month = name[:6]
        assert name == max(n for n in names if n.startswith(month) and n not in daily)
    assert "lost+found" not in expired  # only backup folders are ever removed


def test_the_newest_backup_is_never_removed_even_when_backups_stopped(tmp_path):
    for name in ("20260101T030000Z", "20260102T030000Z"):
        (tmp_path / name).mkdir()
    # Backups stopped ten months ago: the newest stays, whatever the age.
    assert "20260102T030000Z" not in _expired(tmp_path, date(2026, 11, 5), keep_days=30, keep_months=0)


def test_an_empty_folder_is_fine_under_the_backup_scripts_strict_mode(tmp_path):
    command = f'set -euo pipefail; source "{SCRIPT.as_posix()}"; expired_backups "{tmp_path.as_posix()}" 20261105 30 12'
    done = subprocess.run([BASH, "-c", command], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == ""
