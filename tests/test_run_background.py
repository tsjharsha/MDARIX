"""The one background service's supervisor (scripts/run_background.py): both children start, a requested stop stops
both cleanly, and a child that stops on its own takes the container down so Docker restarts it."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("run_background", ROOT / "scripts" / "run_background.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supervisor = _load()


class FakeProcess:
    """A child that exits with ``code`` once ``polls_left`` polls have passed, or on terminate unless ``stubborn``."""

    def __init__(self, path, *, code=None, polls_left=None, stubborn=False):
        self.path = path
        self.code = None
        self._exit_code = code
        self._polls_left = polls_left
        self.stubborn = stubborn
        self.terminated = False
        self.killed = False

    def poll(self):
        if self.code is None and self._polls_left is not None:
            if self._polls_left <= 0:
                self.code = self._exit_code
            else:
                self._polls_left -= 1
        return self.code

    def terminate(self):
        self.terminated = True
        if not self.stubborn:
            self.code = -15

    def kill(self):
        self.killed = True
        self.code = -9

    def wait(self):
        return self.code


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _run(children, *, stop_after=None, grace=5.0):
    """Supervise fake children (by script name); ``stop_after`` loop sleeps before a stop is asked for."""
    clock = FakeClock()
    started = {}

    def launch(path):
        started[path.name] = children[path.name](path)
        return started[path.name]

    def stopping():
        return stop_after is not None and clock.now >= stop_after

    code = supervisor.supervise(launch, stopping=stopping, grace=grace, poll=1.0, sleep=clock.sleep, clock=clock)
    return code, started


def test_both_children_start_and_a_requested_stop_stops_both_cleanly():
    code, started = _run(
        {"run_outbox_worker.py": FakeProcess, "run_scheduler.py": FakeProcess},
        stop_after=3.0,
    )
    assert code == 0
    assert sorted(started) == ["run_outbox_worker.py", "run_scheduler.py"]
    assert all(process.terminated and not process.killed for process in started.values())


def test_a_child_that_exits_cleanly_on_its_own_still_restarts_the_container():
    code, started = _run(
        {
            "run_outbox_worker.py": lambda path: FakeProcess(path, code=0, polls_left=2),
            "run_scheduler.py": FakeProcess,
        }
    )
    assert code == 1
    assert started["run_scheduler.py"].terminated
    assert not started["run_outbox_worker.py"].terminated


def test_a_child_that_fails_passes_its_exit_code_on_and_stops_the_other():
    code, started = _run(
        {
            "run_outbox_worker.py": FakeProcess,
            "run_scheduler.py": lambda path: FakeProcess(path, code=3, polls_left=1),
        }
    )
    assert code == 3
    assert started["run_outbox_worker.py"].terminated
    assert not started["run_outbox_worker.py"].killed


def test_a_child_that_ignores_the_stop_is_killed_after_the_grace_period():
    clock = FakeClock()
    stubborn = FakeProcess(Path("run_scheduler.py"), stubborn=True)
    polite = FakeProcess(Path("run_outbox_worker.py"))
    supervisor.stop_all({"scheduler": stubborn, "outbox worker": polite}, 5.0, clock=clock, sleep=clock.sleep)
    assert polite.terminated and not polite.killed
    assert stubborn.terminated and stubborn.killed
    assert 5.0 <= clock.now < 5.5


def test_stop_all_leaves_children_that_have_already_stopped_alone():
    clock = FakeClock()
    done = FakeProcess(Path("run_outbox_worker.py"))
    done.code = 0
    supervisor.stop_all({"outbox worker": done}, 5.0, clock=clock, sleep=clock.sleep)
    assert not done.terminated and not done.killed
    assert clock.now == 0.0


def test_the_supervisor_runs_the_two_existing_scripts():
    assert [path.name for _, path in supervisor.CHILDREN] == ["run_outbox_worker.py", "run_scheduler.py"]
    assert all(path.is_file() for _, path in supervisor.CHILDREN)
