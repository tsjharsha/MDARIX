"""DB-1 on a legacy dedicated database (owner decision 6): scripts/add_workflow_tables_to_legacy_planes.py runs
tr21, tr22 + tr23, tr24 and tr24a, leaves the schema exactly as the migrations do, and only lists without --apply.

The schema test runs Alembic against the test database (``POSTGRES_DB``), so it must not run beside another test run
on the same database.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from backend.app.db.session import engine
from tests.test_db1_migration_roundtrip import _fingerprint

ROOT = Path(__file__).resolve().parents[1]
DB1_STEPS = ["tr21", "tr22+tr23", "tr24", "tr24a"]


def _script():
    spec = importlib.util.spec_from_file_location(
        "add_workflow_tables_to_legacy_planes", ROOT / "scripts" / "add_workflow_tables_to_legacy_planes.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def _alembic(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=ROOT, env=dict(os.environ), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_the_legacy_steps_give_the_same_schema_as_the_db1_migrations():
    script = _script()
    url = engine.url.render_as_string(hide_password=False)
    _alembic("downgrade", "tr24aproductreferences")
    try:
        after_migrations = _fingerprint()
        _alembic("downgrade", "tr19casesescalation")
        _legacy, todo, problems = script.state(url)
        assert problems == []
        assert [step.name for step in todo] == DB1_STEPS
        script.apply(url, todo)
        assert script.state(url)[1] == []  # a second run has nothing to do
        assert _fingerprint() == after_migrations
        _alembic("stamp", "tr24aproductreferences")
    finally:
        _alembic("upgrade", "head")


def test_without_apply_the_script_only_lists(monkeypatch, capsys):
    script = _script()
    plane = SimpleNamespace(database_ref="legacy_plane", tenant_id="t-1", connection_secret_ref="LEGACY_PLANE_URL")

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return [plane]

    steps = [step for step in script.STEPS if step.name in DB1_STEPS]
    monkeypatch.setattr(script, "SessionLocal", lambda: SimpleNamespace(query=lambda _m: Query(), close=lambda: None))
    monkeypatch.setattr(script, "bind_system", lambda *_a: None)
    monkeypatch.setattr(script, "_secret_url", lambda _ref: "postgresql+pg8000://legacy")
    monkeypatch.setattr(script, "state", lambda _url: (True, steps, []))
    monkeypatch.setattr(script, "apply", lambda *_a: (_ for _ in ()).throw(AssertionError("changed without --apply")))
    monkeypatch.setattr(sys, "argv", ["add_workflow_tables_to_legacy_planes.py"])
    assert script.main() == 0
    assert "PENDING   legacy_plane (tenant t-1): tr21, tr22+tr23, tr24, tr24a (dry run)" in capsys.readouterr().out
