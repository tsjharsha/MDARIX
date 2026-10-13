"""The AI release record: the proof a deployment reads before AI may be switched on for a pilot.

Three files under ``evaluation/``, all committed with the code and shipped in the API image:

- ``GOLDEN_DATASET_QUALIFICATION.json``, the dataset lock (scripts/qualify_ai_golden_dataset.py --approve);
- ``GOLDEN_DATASET_HUMAN_SIGN_OFF.json``, a named person's sign-off of exactly that lock (its hashes), written by
  ``scripts/qualify_ai_golden_dataset.py --human-sign-off``; an agent or a tool never signs;
- ``AI_RELEASE_RECORD.json``, written by ``scripts/run_real_evaluation.py --gate --require-model --release-record``
  only when the full golden evaluation (all 15 scenarios) passed with the language model writing every analysis, on
  the signed-off lock. It names the provider and model that passed.

``backend/app/ai_release_gate.py`` reads them: in production, AI is switched on for an organization only when the
configured model is the one the record names and the record, sign-off and lock still match. Changing the dataset,
the model or the provider therefore needs a new sign-off or a new passing run.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "evaluation" / "GOLDEN_DATASET_QUALIFICATION.json"
SIGN_OFF = ROOT / "evaluation" / "GOLDEN_DATASET_HUMAN_SIGN_OFF.json"
RECORD = ROOT / "evaluation" / "AI_RELEASE_RECORD.json"
SIGN_OFF_VERSION = "MDARIX_AI_GOLDEN_HUMAN_SIGN_OFF_V1"
RECORD_VERSION = "MDARIX_AI_RELEASE_RECORD_V1"
REQUIRED_SCENARIOS = 15
LOCK_STATUS = "QUALIFIED_FOR_INTERNAL_MVP"
SIGN_OFF_STATEMENT = (
    "I reviewed the golden dataset's 15 scenarios, their evidence, expected findings, prohibited conclusions and "
    "ground truth, and I approve it as the release gate for MDARIX's AI."
)
# A sign-off is a person's: names that read as a tool, an agent or a placeholder are refused.
_NOT_A_PERSON = re.compile(
    r"(?i)\b(agent|bot|claude|gpt|openai|anthropic|llm|automation|automated|script|system|engineering|team|"
    r"pending|todo|tbd|unknown)\b"
)


def read(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def lock_hashes(lock: dict | None) -> dict | None:
    """The lock's hashes when it is a qualified lock, else None."""
    if not lock or lock.get("status") != LOCK_STATUS or not isinstance(lock.get("hashes"), dict):
        return None
    return lock["hashes"]


def person_problem(name: str, role: str) -> str | None:
    """Why ``name`` / ``role`` cannot sign, or None."""
    name, role = " ".join(str(name or "").split()), " ".join(str(role or "").split())
    if len(name) < 3 or " " not in name:
        return "Give the reviewer's full name (first and last name)."
    if _NOT_A_PERSON.search(name):
        return "A sign-off is a named person's, not a tool's, an agent's or a team's."
    if len(role) < 3:
        return "Give the reviewer's role (for example Head of Quality)."
    return None


def build_sign_off(lock: dict, *, name: str, role: str, now: datetime | None = None) -> dict:
    hashes = lock_hashes(lock)
    if hashes is None:
        raise ValueError("The dataset lock is missing or not qualified; run --approve after review first")
    problem = person_problem(name, role)
    if problem:
        raise ValueError(problem)
    return {
        "sign_off_version": SIGN_OFF_VERSION,
        "approved_by": " ".join(name.split()),
        "role": " ".join(role.split()),
        "approved_at": (now or datetime.now(timezone.utc)).isoformat(),
        "statement": SIGN_OFF_STATEMENT,
        "change_control": lock.get("change_control"),
        "lock_hashes": hashes,
    }


def sign_off_problem(lock: dict | None, sign_off: dict | None) -> str | None:
    """Why the lock is not signed off by a person, or None."""
    hashes = lock_hashes(lock)
    if hashes is None:
        return "The golden dataset lock is missing or not qualified."
    if not sign_off:
        return "No person has signed off the golden dataset lock yet."
    if sign_off.get("sign_off_version") != SIGN_OFF_VERSION or sign_off.get("lock_hashes") != hashes:
        return "The sign-off is for another version of the golden dataset; it must be signed off again."
    problem = person_problem(sign_off.get("approved_by"), sign_off.get("role"))
    if problem:
        return f"The sign-off is not valid: {problem}"
    return None


def report_digest(report: dict) -> str:
    return hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()


def model_of(report: dict) -> tuple[str | None, str | None]:
    """(provider, model) from an evaluation report's ``model`` ("provider:model"), or (None, None) for the rules."""
    value = str(report.get("model") or "")
    provider, _, model = value.partition(":")
    if not provider or not model or value.startswith("MDARIX rules"):
        return None, None
    return provider, model


def release_problems(report: dict, lock: dict | None, sign_off: dict | None) -> list[str]:
    """Why an evaluation report cannot become the release record (empty when it can)."""
    problems = []
    total = int(report.get("total") or 0)
    if total < REQUIRED_SCENARIOS:
        problems.append(f"the full golden suite must run ({total} of {REQUIRED_SCENARIOS} scenarios ran)")
    if int(report.get("passed") or 0) < total:
        problems.append(f"{report.get('passed')}/{total} scenarios passed; all are required")
    if int(report.get("passed_with_specific_expectations") or 0) < int(report.get("with_specific_expectations") or 0):
        problems.append("every scenario with specific expectations must pass")
    if int(report.get("model_written") or 0) < total:
        problems.append("the language model must write every analysis")
    if model_of(report) == (None, None):
        problems.append("the report does not name the provider and model")
    sign_off_issue = sign_off_problem(lock, sign_off)
    if sign_off_issue:
        problems.append(sign_off_issue)
    return problems


def build_record(report: dict, lock: dict, sign_off: dict, now: datetime | None = None) -> dict:
    problems = release_problems(report, lock, sign_off)
    if problems:
        raise ValueError("; ".join(problems))
    provider, model = model_of(report)
    return {
        "record_version": RECORD_VERSION,
        "released_at": (now or datetime.now(timezone.utc)).isoformat(),
        "provider": provider,
        "model": model,
        "evaluation": {
            key: report.get(key)
            for key in (
                "evaluation_version",
                "passed",
                "total",
                "with_specific_expectations",
                "passed_with_specific_expectations",
                "model_written",
                "generated_at",
            )
        }
        | {"report_sha256": report_digest(report)},
        "lock_hashes": lock_hashes(lock),
        "human_sign_off": {key: sign_off.get(key) for key in ("approved_by", "role", "approved_at")},
    }


def record_problem(record: dict | None, lock: dict | None, sign_off: dict | None) -> str | None:
    """Why the release record does not stand for the current dataset and sign-off, or None."""
    if not record:
        return "No golden evaluation has passed with a language model yet."
    if record.get("record_version") != RECORD_VERSION:
        return "The release record is not in a version this server reads."
    hashes = lock_hashes(lock)
    if hashes is None or record.get("lock_hashes") != hashes:
        return "The golden dataset changed since the evaluation passed; run it again."
    if sign_off_problem(lock, sign_off) is not None:
        return "The evaluation passed on a dataset that is not signed off by a person."
    evaluation = record.get("evaluation") or {}
    total = int(evaluation.get("total") or 0)
    if total < REQUIRED_SCENARIOS or int(evaluation.get("passed") or 0) < total:
        return "The release record does not show every scenario passing."
    return None


def load() -> tuple[dict | None, dict | None, dict | None]:
    """(lock, sign-off, record) as committed."""
    return read(LOCK), read(SIGN_OFF), read(RECORD)


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
