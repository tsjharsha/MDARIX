"""Background jobs get 5 minutes per statement; requests keep the runtime role's 60 s (DB-1, owner decision 4)."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from backend.app.db import job_timeouts
from backend.app.db.session import engine as app_engine
from backend.app.db.tls import connect_args

ROOT = Path(__file__).resolve().parents[1]


def _fresh_engine():
    return create_engine(app_engine.url, connect_args=connect_args(request_path=True))


def _settings(engine) -> tuple[str, str]:
    with engine.connect() as connection:
        return (
            connection.execute(text("SHOW statement_timeout")).scalar(),
            connection.execute(text("SHOW idle_in_transaction_session_timeout")).scalar(),
        )


def test_a_background_connection_gets_five_minutes_and_a_longer_socket_wait():
    jobs, requests = _fresh_engine(), _fresh_engine()
    seen: dict = {}

    def capture(_dialect, _record, _cargs, cparams):
        seen.update(cparams)

    try:
        assert job_timeouts.use_background_timeouts(jobs) == "300s"
        event.listen(jobs, "do_connect", capture)  # after the job listener: sees what the driver is given
        assert _settings(jobs) == ("5min", "5min")
        assert seen["timeout"] == 330
        # Another engine of a process that never asked (the API) keeps the role's own setting.
        assert "5min" not in _settings(requests)
    finally:
        job_timeouts.stop_background_timeouts(jobs)
        jobs.dispose()
        requests.dispose()


def test_the_job_timeout_is_configurable_and_checked(monkeypatch):
    monkeypatch.setenv("MDARIX_DB_JOB_STATEMENT_TIMEOUT", "10min")
    assert job_timeouts.job_statement_timeout() == "10min"
    monkeypatch.setenv("MDARIX_DB_JOB_STATEMENT_TIMEOUT", "300s; DROP TABLE x")
    try:
        job_timeouts.job_statement_timeout()
    except ValueError:
        pass
    else:
        raise AssertionError("an unsafe value was accepted")


def test_the_scheduler_asks_for_the_background_timeouts_before_it_connects():
    spec = importlib.util.spec_from_file_location("run_scheduler_for_timeouts", ROOT / "scripts" / "run_scheduler.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    try:
        assert script.main(["--list"]) == 0
        assert Engine in job_timeouts._installed["targets"]
    finally:
        job_timeouts.stop_background_timeouts(Engine)
