"""The deploy's readiness gate (scripts/deploy_gate.py, 0.10.88 DEV-13): the release is ready for traffic only when
it is the release named, its database answers at this build's schema, and every required component is ok."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "deploy_gate", Path(__file__).resolve().parents[1] / "scripts" / "deploy_gate.py"
)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

READY = {
    "status": "degraded",
    "checks": [
        {"name": "database", "ok": True, "schema": "tr16codelists"},
        {"name": "worker", "ok": False, "error": "STOPPED"},
        {"name": "scheduler", "ok": True},
    ],
}


def test_a_ready_database_on_the_named_release_passes_even_while_other_parts_are_degraded():
    assert gate.problems(READY, "0.10.88", "v0.10.88", set()) == []


@pytest.mark.parametrize(
    "report, version, release, required, reason",
    [
        (READY, "0.10.87", "v0.10.88", set(), "this code is v0.10.87, not v0.10.88"),
        (
            {"checks": [{"name": "database", "ok": False, "error": "RuntimeError"}]},
            "0.10.88",
            "",
            set(),
            "database: RuntimeError",
        ),
        (READY, "0.10.88", "", {"worker"}, "worker: STOPPED"),
        (READY, "0.10.88", "", {"outbox"}, "outbox: not reported"),
    ],
)
def test_the_gate_names_what_is_not_ready(report, version, release, required, reason):
    assert reason in gate.problems(report, version, release, required)


def test_the_gate_exits_nonzero_with_the_reasons_when_time_is_up(monkeypatch, capsys):
    from backend.app import readiness

    monkeypatch.setattr(readiness, "readiness_report", lambda: {"checks": [{"name": "database", "ok": False}]})
    monkeypatch.setattr("sys.argv", ["deploy_gate.py", "--timeout", "0"])
    assert gate.main() == 1
    assert "DEPLOY_GATE=FAIL database: not reported" in capsys.readouterr().out
