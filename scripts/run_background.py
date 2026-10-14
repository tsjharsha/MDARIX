"""The one background service: the outbox worker and the scheduler in one container (docker-compose.prod.yml).

    python scripts/run_background.py

Starts ``scripts/run_outbox_worker.py`` and ``scripts/run_scheduler.py`` as two child processes, unchanged, so each
keeps its own loop, signal handling and heartbeat file. SIGTERM or SIGINT is passed on to both, and both get the stop
grace period to finish the event or job in hand before they are killed. If either child stops on its own, the other is
stopped too and this process exits with an error, so Docker restarts the container and the health check (both
heartbeats) and the scheduler's external heartbeat show the outage.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHILDREN = (
    ("outbox worker", SCRIPTS / "run_outbox_worker.py"),
    ("scheduler", SCRIPTS / "run_scheduler.py"),
)
# Within the container's stop_grace_period (60 s), leaving Docker a margin.
GRACE_SECONDS = 55.0
POLL_SECONDS = 1.0


def _log(message: str) -> None:
    print(f"mdarix-background: {message}", flush=True)


def stop_all(processes: dict, grace: float = GRACE_SECONDS, *, clock=time.monotonic, sleep=time.sleep) -> None:
    """SIGTERM to every running child, then wait up to ``grace`` seconds and kill what is still running."""
    for name, process in processes.items():
        if process.poll() is None:
            _log(f"stopping the {name}")
            process.terminate()
    deadline = clock() + grace
    while any(process.poll() is None for process in processes.values()) and clock() < deadline:
        sleep(0.2)
    for name, process in processes.items():
        if process.poll() is None:
            _log(f"the {name} did not stop within {grace:.0f} s; killing it")
            process.kill()
            process.wait()


def supervise(
    launch=None,
    *,
    stopping=None,
    grace: float = GRACE_SECONDS,
    poll: float = POLL_SECONDS,
    sleep=time.sleep,
    clock=time.monotonic,
) -> int:
    """Run both children until a stop is asked for (0) or one of them stops on its own (that child's code, at least
    1). ``launch(path)`` starts one child; ``stopping()`` says whether a stop was asked for."""
    launch = launch or (lambda path: subprocess.Popen([sys.executable, str(path)]))
    stopping = stopping or (lambda: False)
    processes = {name: launch(path) for name, path in CHILDREN}
    _log("started the outbox worker and the scheduler")
    while True:
        if stopping():
            stop_all(processes, grace, clock=clock, sleep=sleep)
            _log("stopped")
            return 0
        ended = [(name, process.poll()) for name, process in processes.items() if process.poll() is not None]
        if ended:
            name, code = ended[0]
            _log(f"the {name} stopped on its own (exit code {code}); stopping the other so the container restarts")
            stop_all(processes, grace, clock=clock, sleep=sleep)
            return code if code else 1
        sleep(poll)


def main() -> int:
    asked = {"stop": False}

    def stop(signum, _frame):
        _log(f"signal {signum} received")
        asked["stop"] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return supervise(stopping=lambda: asked["stop"])


if __name__ == "__main__":
    sys.exit(main())
