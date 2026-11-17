"""scripts/enter_trial_ai_keys.sh: the owner's guided entry of the trial AI keys (RELEASE_0.11.05.md, step 3).

The real script runs in bash on a temporary settings file with fake values only: it writes each key once, keeps a
timestamped copy, never prints a value, and leaves the file alone when nothing changes or a key cannot be stored.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "enter_trial_ai_keys.sh"
BASH = shutil.which("bash")

pytestmark = [pytest.mark.unit, pytest.mark.skipif(BASH is None, reason="needs bash, as the server has")]

FAKE = ("fake-freellmapi-key-111", "fake-omniroute-key-222", "fake_groq_key_333")
FEATURES = "ask,summaries,case_analysis,drafting,evidence_extraction,code_suggestions"


def _run(settings: Path, answers: str) -> subprocess.CompletedProcess:
    # Bytes, so Windows does not turn the answers' newlines into CRLF as a terminal never would.
    result = subprocess.run(
        [BASH, SCRIPT.as_posix(), settings.as_posix()],
        input=answers.encode(),
        capture_output=True,
        timeout=60,
    )
    return subprocess.CompletedProcess(result.args, result.returncode, result.stdout.decode(), result.stderr.decode())


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "prod-settings"
    path.write_text(
        "MDARIX_RELEASE=v0.11.05\nMDARIX_AI_TRIAL_CHAIN=\nMDARIX_GENAI_GROQ_API_KEY=old\nMDARIX_GENAI_GROQ_API_KEY=old2\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_it_writes_every_setting_once_keeps_a_copy_and_never_prints_a_value(tmp_path):
    settings = _settings(tmp_path)
    result = _run(settings, "\n".join(FAKE) + "\n")
    assert result.returncode == 0, result.stderr
    lines = _lines(settings)
    assert lines[0] == "MDARIX_RELEASE=v0.11.05"
    assert "MDARIX_GENAI_FREELLMAPI_API_KEY=fake-freellmapi-key-111" in lines
    assert "MDARIX_GENAI_OMNIROUTE_API_KEY=fake-omniroute-key-222" in lines
    assert [line for line in lines if line.startswith("MDARIX_GENAI_GROQ_API_KEY=")] == [
        "MDARIX_GENAI_GROQ_API_KEY=fake_groq_key_333"
    ]
    assert "MDARIX_AI_TRIAL_CHAIN=freellmapi,omniroute,groq" in lines
    assert f"MDARIX_AI_FEATURES={FEATURES}" in lines
    assert "MDARIX_GENAI_OMNIROUTE_MODEL=mdarix-trial" in lines
    output = result.stdout + result.stderr
    for value in (*FAKE, "old2"):
        assert value not in output
    assert "MDARIX_GENAI_GROQ_API_KEY: set" in result.stdout
    backups = list(tmp_path.glob("prod-settings.pre-trial-ai-*"))
    assert len(backups) == 1 and "MDARIX_GENAI_GROQ_API_KEY=old2" in backups[0].read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".trial-ai-keys.*"))
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(settings).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(backups[0]).st_mode) == 0o600


def test_running_again_with_empty_answers_changes_nothing(tmp_path):
    settings = _settings(tmp_path)
    assert _run(settings, "\n".join(FAKE) + "\n").returncode == 0
    before = settings.read_bytes()
    result = _run(settings, "\n\n\n")
    assert result.returncode == 0, result.stderr
    assert settings.read_bytes() == before
    assert "set" not in result.stdout.replace("unchanged", "")
    assert len(list(tmp_path.glob("prod-settings.pre-trial-ai-*"))) == 1


def test_a_key_the_file_cannot_hold_is_refused_and_nothing_changes(tmp_path):
    settings = _settings(tmp_path)
    before = settings.read_bytes()
    result = _run(settings, "has a space\n\n\n")
    assert result.returncode != 0
    assert "STOP" in result.stderr and "has a space" not in result.stdout + result.stderr
    assert settings.read_bytes() == before
    assert not list(tmp_path.glob("prod-settings.pre-trial-ai-*"))


def test_a_missing_file_stops(tmp_path):
    result = _run(tmp_path / "missing", "\n\n\n")
    assert result.returncode != 0 and "not found" in result.stderr
