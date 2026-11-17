"""tr33inconclusive: down to tr33validationruns and up again leaves the same schema; only the head's status check names
INCONCLUSIVE. Runs Alembic against a fresh database of its own (the ``migration_database`` fixture in conftest.py)."""

from sqlalchemy import text

from tests.test_db1_migration_roundtrip import _alembic, _fingerprint

BEFORE = "tr33validationruns"
CHECK = (
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_capa_effectiveness_checks_status_known'"
)


def _check(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text(CHECK)).scalar()


def test_inconclusive_migration_goes_down_and_up_again(migration_database):
    engine, env = migration_database
    at_head = _fingerprint(engine)
    assert "INCONCLUSIVE" in _check(engine)
    try:
        down = _alembic(env, "downgrade", BEFORE)
        assert down.returncode == 0, down.stderr[-2000:]
        assert "INCONCLUSIVE" not in _check(engine) and "NOT_EFFECTIVE" in _check(engine)
    finally:
        up = _alembic(env, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    assert _fingerprint(engine) == at_head and "INCONCLUSIVE" in _check(engine)
