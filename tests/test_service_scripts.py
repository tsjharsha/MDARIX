"""The long-running service scripts read the settings file before deciding what environment they run in.

An unset MDARIX_ENV means production, with every protection on. The API and the worker load ``.env`` through the
database module they import first; the scheduler script ran its configuration check before anything had loaded the
file, so a developer's scheduler refused to start with production errors while the worker beside it ran.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _position(source: str, pattern: str) -> int:
    match = re.search(pattern, source, re.MULTILINE)
    assert match, pattern
    return match.start()


def test_the_scheduler_script_loads_the_settings_file_before_the_configuration_check():
    source = (ROOT / "scripts" / "run_scheduler.py").read_text(encoding="utf-8")
    assert _position(source, r"^load_dotenv\(\)") < _position(source, r"\benforce\(\)")


def test_the_worker_script_reaches_the_settings_file_through_its_first_imports():
    source = (ROOT / "scripts" / "run_outbox_worker.py").read_text(encoding="utf-8")
    session = (ROOT / "backend" / "app" / "db" / "session.py").read_text(encoding="utf-8")
    assert "load_dotenv()" in session
    assert _position(source, r"^from outbox\.worker import") < _position(source, r"\benforce\(\)")
