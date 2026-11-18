"""The production image has no pytest: the API must import without it (0.11.05 release failure, 18 Nov 2026)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_api_starts_without_pytest_installed():
    code = "import sys; sys.modules['pytest'] = None; import backend.app.main"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]


def test_ci_and_release_run_the_built_api_image_before_scanning_or_publishing_it():
    """The pytest-free check above runs on a developer's packages; the image job runs the built image itself."""
    for name in ("ci.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        step = text.index("The production API image starts")
        assert text.index("docker build -f Dockerfile.api") < step < text.index("aquasec/trivy:0.57.0 image"), name
        for entry in ("import backend.app.main", "run_background", "import backend.app.mail_in.receiver"):
            assert entry in text[step : text.index("aquasec/trivy", step)], (name, entry)
