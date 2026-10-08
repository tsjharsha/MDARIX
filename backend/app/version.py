"""The application version: one source, the repository's VERSION file (release.yml refuses a tag that differs)."""

from __future__ import annotations

import os
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:  # an image built without the file still starts and reports 0.0.0
        return "0.0.0"


APP_VERSION = _read_version()


def release() -> str:
    """The deployed release: MDARIX_RELEASE when the deployment sets it, otherwise v<VERSION>."""
    return (os.getenv("MDARIX_RELEASE") or "").strip()[:80] or f"v{APP_VERSION}"
