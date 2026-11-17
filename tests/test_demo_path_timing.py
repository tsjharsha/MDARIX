"""scripts/demo_path_timing.py: the p95 it reports, the SLO verdict, and that it refuses a non-test database or host."""

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("demo_path_timing", ROOT / "scripts" / "demo_path_timing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p95_is_the_nearest_rank():
    script = _script()
    assert script.p95([float(n) for n in range(1, 21)]) == 19.0
    assert script.p95([7.0]) == 7.0


def test_a_server_error_or_a_slow_read_fails_the_table():
    script = _script()
    walk = script.Walk("http://127.0.0.1:1", rounds=1)
    walk.samples[("s", "GET", "/fast")] = [10.0]
    walk.statuses[("s", "GET", "/fast")] = {200}
    assert walk.table()[1] is True
    walk.samples[("s", "POST", "/write")] = [900.0]
    walk.statuses[("s", "POST", "/write")] = {500}
    table, ok = walk.table()
    assert ok is False and "| 5xx |" in table
    walk.statuses[("s", "POST", "/write")] = {200}
    walk.samples[("s", "GET", "/slow")] = [600.0]
    walk.statuses[("s", "GET", "/slow")] = {200}
    table, ok = walk.table()
    assert ok is False and "| OVER |" in table


@pytest.mark.parametrize("database", ["mdarix_r1", "mdarix_r1_test", "mdarix_demo", "mdarix_whif_x;drop"])
def test_it_refuses_a_shared_or_non_demo_database(monkeypatch, database):
    script = _script()
    monkeypatch.setenv("POSTGRES_DB", database)
    monkeypatch.setattr(sys, "argv", ["demo_path_timing.py"])
    with pytest.raises(SystemExit) as refused:
        script.main()
    assert "Refusing" in str(refused.value)


@pytest.mark.parametrize("database", ["mdarix_whif_demo", "mdarix_demo_test"])
def test_it_accepts_a_whif_demo_or_a_test_database(database):
    assert _script().checked_database(database) == database


def test_the_walk_signs_with_the_next_code_and_seed_relative_dates():
    from auth import totp

    script = _script()
    secret = totp.new_secret()
    step = totp.matching_step(secret, script.next_code(secret), last_used_step=totp._step())
    assert step == totp._step() + 1 or step == totp._step()  # accepted after the current code was used
    assert script.day(0) == script.iso()[:10]
