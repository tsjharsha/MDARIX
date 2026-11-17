"""DB-1 on a legacy dedicated database (owner decision 6): scripts/add_workflow_tables_to_legacy_planes.py runs
tr21, tr22 + tr23, tr24 and tr24a, leaves the schema exactly as the migrations do, and only lists without --apply.

The schema test runs Alembic against a fresh database of its own (the ``migration_database`` fixture in conftest.py).
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from tests.test_db1_migration_roundtrip import _alembic as _run
from tests.test_db1_migration_roundtrip import _fingerprint, _ok

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


def test_the_legacy_steps_give_the_same_schema_as_the_db1_migrations(migration_database):
    engine, env = migration_database

    def _alembic(*args: str) -> None:
        _ok(_run(env, *args))

    script = _script()
    url = engine.url.render_as_string(hide_password=False)
    _alembic("downgrade", "tr24aproductreferences")
    try:
        after_migrations = _fingerprint(engine)
        _alembic("downgrade", "tr19casesescalation")
        _legacy, todo, problems = script.state(url)
        assert problems == []
        db1 = [step for step in todo if step.name in DB1_STEPS]  # a later branch's steps follow; not run here
        assert [step.name for step in todo][: len(DB1_STEPS)] == DB1_STEPS == [step.name for step in db1]
        script.apply(url, db1)
        assert not {step.name for step in script.state(url)[1]} & set(DB1_STEPS)  # a second run has nothing to do
        assert _fingerprint(engine) == after_migrations
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
