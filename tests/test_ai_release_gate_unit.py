"""The AI release gate without a database (evaluation/release_record.py, backend/app/ai_release_gate.py): a person's
sign-off bound to the dataset lock, the release record written only for a full, model-written pass, and the four bars
read against the model configured here."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app import ai_release_gate
from evaluation import release_record

HASHES = {"canonical_sha256": "a" * 64, "scenario_index_sha256": "b" * 64}
LOCK = {"status": release_record.LOCK_STATUS, "hashes": HASHES, "change_control": "MVP-AI-GOLDEN-002"}
NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)
MODEL = {"provider": "anthropic", "model": "claude-sonnet-5-5"}


def _report(**changes) -> dict:
    report = {
        "evaluation_version": "R1-REAL",
        "model": "anthropic:claude-sonnet-5-5",
        "passed": 15,
        "total": 15,
        "with_specific_expectations": 15,
        "passed_with_specific_expectations": 15,
        "model_written": 15,
        "generated_at": "2026-10-13T10:00:00+00:00",
        "results": [],
    }
    return {**report, **changes}


def _sign_off(**changes):
    return {**release_record.build_sign_off(LOCK, name="Dana Whitfield", role="Head of Quality", now=NOW), **changes}


@pytest.mark.parametrize(
    "name, role",
    [
        ("ai-governance agent (human review pending)", "Reviewer"),
        ("MDARIX Engineering", "Engineering"),
        ("Claude Code", "Assistant"),
        ("Dana", "Head of Quality"),
        ("Dana Whitfield", ""),
    ],
)
def test_only_a_named_person_can_sign_off(name, role):
    with pytest.raises(ValueError):
        release_record.build_sign_off(LOCK, name=name, role=role, now=NOW)


def test_a_sign_off_binds_to_the_exact_lock():
    sign_off = _sign_off()
    assert sign_off["lock_hashes"] == HASHES and sign_off["statement"] == release_record.SIGN_OFF_STATEMENT
    assert release_record.sign_off_problem(LOCK, sign_off) is None
    changed = {**LOCK, "hashes": {**HASHES, "canonical_sha256": "c" * 64}}
    assert "another version" in release_record.sign_off_problem(changed, sign_off)
    assert release_record.sign_off_problem(LOCK, None) == "No person has signed off the golden dataset lock yet."
    with pytest.raises(ValueError):
        release_record.build_sign_off(
            {"status": "DRAFT", "hashes": HASHES}, name="Dana Whitfield", role="Head of Quality"
        )


@pytest.mark.parametrize(
    "changes, problem",
    [
        ({"total": 3, "passed": 3, "model_written": 3}, "full golden suite"),
        ({"passed": 14}, "14/15 scenarios passed"),
        ({"passed_with_specific_expectations": 14}, "specific expectations"),
        ({"model_written": 12}, "language model must write every analysis"),
        ({"model": "MDARIX rules (no language model configured)"}, "provider and model"),
    ],
)
def test_the_release_record_needs_a_full_model_written_pass(changes, problem):
    problems = release_record.release_problems(_report(**changes), LOCK, _sign_off())
    assert any(problem in item for item in problems), problems
    with pytest.raises(ValueError):
        release_record.build_record(_report(**changes), LOCK, _sign_off())


def test_the_release_record_needs_the_signed_off_dataset():
    problems = release_record.release_problems(_report(), LOCK, None)
    assert problems == ["No person has signed off the golden dataset lock yet."]


def test_a_full_pass_on_the_signed_off_dataset_becomes_the_release_record():
    record = release_record.build_record(_report(), LOCK, _sign_off(), now=NOW)
    assert (record["provider"], record["model"]) == ("anthropic", "claude-sonnet-5-5")
    assert record["evaluation"]["passed"] == 15 and len(record["evaluation"]["report_sha256"]) == 64
    assert record["lock_hashes"] == HASHES and record["human_sign_off"]["approved_by"] == "Dana Whitfield"
    assert release_record.record_problem(record, LOCK, _sign_off()) is None
    changed = {**LOCK, "hashes": {**HASHES, "scenario_index_sha256": "d" * 64}}
    assert "changed since" in release_record.record_problem(record, changed, _sign_off())


def _bars(gate: dict) -> dict[str, str]:
    return {bar["code"]: bar["status"] for bar in gate["bars"]}


def test_today_only_the_automatic_trust_check_is_met():
    gate = ai_release_gate.status(models=[], files=(LOCK, None, None))
    assert gate["ready"] is False and (gate["met"], gate["total"]) == (1, 4)
    assert _bars(gate) == {
        "PROVIDER_CONTRACTED": "NOT_MET",
        "DATASET_SIGNED_OFF": "NOT_MET",
        "GOLDEN_EVALUATION_PASSED": "NOT_MET",
        "TRUST_CHECK_AUTOMATIC": "MET",
    }
    assert all(bar["action"] for bar in gate["bars"] if bar["status"] == "NOT_MET")
    assert gate["enforced"] is False  # tests run as MDARIX_ENV=test; production enforces


def test_every_bar_met_with_the_released_model():
    record = release_record.build_record(_report(), LOCK, _sign_off(), now=NOW)
    gate = ai_release_gate.status(models=[MODEL], files=(LOCK, _sign_off(), record))
    assert gate["ready"] is True and set(_bars(gate).values()) == {"MET"}
    passed = next(bar for bar in gate["bars"] if bar["code"] == "GOLDEN_EVALUATION_PASSED")
    assert passed["detail"].startswith("15 of 15 with anthropic claude-sonnet-5-5")


def test_another_model_than_the_released_one_is_not_released():
    record = release_record.build_record(_report(), LOCK, _sign_off(), now=NOW)
    gate = ai_release_gate.status(
        models=[{"provider": "groq", "model": "openai/gpt-oss-120b"}], files=(LOCK, _sign_off(), record)
    )
    assert gate["ready"] is False and _bars(gate)["GOLDEN_EVALUATION_PASSED"] == "NOT_MET"
    assert "not with the model configured here" in next(
        bar["detail"] for bar in gate["bars"] if bar["code"] == "GOLDEN_EVALUATION_PASSED"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--name", "Dana Whitfield", "--role", "Head of Quality"],  # no --confirm
        ["--name", "ai-governance agent", "--role", "Reviewer", "--confirm"],  # not a person
    ],
)
def test_the_sign_off_command_refuses_without_confirmation_or_a_person(arguments):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/qualify_ai_golden_dataset.py", "--human-sign-off", *arguments],
        cwd=release_record.ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert not release_record.SIGN_OFF.exists()


def test_the_committed_files_are_read_and_no_sign_off_is_claimed():
    """The repository holds the lock but no human sign-off and no release record yet: the gate says so."""
    lock, sign_off, record = release_record.load()
    assert release_record.lock_hashes(lock) is not None
    assert sign_off is None and record is None
    gate = ai_release_gate.status(models=[])
    assert _bars(gate)["DATASET_SIGNED_OFF"] == "NOT_MET"
