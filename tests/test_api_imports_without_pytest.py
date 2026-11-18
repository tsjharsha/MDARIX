"""The production image has no pytest: the API must import without it (0.11.05 release failure, 18 Nov 2026)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_api_starts_without_pytest_installed():
    code = "import sys; sys.modules['pytest'] = None; import backend.app.main"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
