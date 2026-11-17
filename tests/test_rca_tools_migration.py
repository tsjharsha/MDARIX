"""RCA tools migration (trrcatools): down to tr31othercountries and up again leaves the same schema, and the downgrade
refuses while a decision carries a root-cause category (no silent loss).

Runs Alembic against a fresh database of its own (the ``migration_database`` fixture in conftest.py).
"""

import uuid

from sqlalchemy import text

from tests.test_db1_migration_roundtrip import _alembic, _fingerprint

BEFORE_RCA = "tr31othercountries"


def _columns(engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name IN ('hypotheses', 'failure_chains', 'decisions', 'brief_review_actions', 'risks')"
            )
        )
        return {row[0] for row in rows}


def test_rca_migration_goes_down_and_up_again_to_the_same_schema(migration_database):
    engine, env = migration_database
    at_head, columns = _fingerprint(engine), _columns(engine)
    try:
        down = _alembic(env, "downgrade", BEFORE_RCA)
        assert down.returncode == 0, down.stderr[-2000:]
        before, columns_before = _fingerprint(engine), _columns(engine)
    finally:
        up = _alembic(env, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    assert _fingerprint(engine) == at_head and _columns(engine) == columns
    added = columns - columns_before
    assert {
        "hypotheses.cause_category",
        "hypotheses.failure_mode_id",
        "failure_chains.method",
        "decisions.root_cause_category",
        "decisions.root_cause_hypothesis_ids",
        "brief_review_actions.section_key",
        "risks.estimated_probability",
        "risks.match_codes",
    } <= added
    names = " ".join(item for _, item in before)
    assert "fk_hypotheses_failure_mode_id_tenant" not in names
    after = " ".join(item for _, item in at_head)
    # DB-1: the reference includes the organization and is indexed from tenant_id.
    assert "fk_hypotheses_failure_mode_id_tenant FOREIGN KEY (tenant_id, failure_mode_id)" in after
    assert "ix_hypotheses_tenant_failure_mode" in after


def test_rca_downgrade_refuses_while_a_decision_carries_a_root_cause_category(migration_database):
    engine, env = migration_database
    decision_id, tenant_id, investigation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        # The fresh database has no organization to hang a decision on; only the guard's count matters here, so this
        # one session skips the reference checks (the database is dropped after the run).
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(
            text(
                "INSERT INTO decisions (id, tenant_id, investigation_id, business_id, decision_identifier, decision_type, "
                "disposition, rationale, authorized_by_ref, root_cause_category, decision_timestamp, created_at, updated_at) "
                "VALUES (:id, :tenant, :inv, :bid, "
                ":ident, 'TEST', 'TEST', 'Migration guard test', 'test', 'MATERIAL', now(), now(), now())"
            ),
            {
                "id": decision_id,
                "tenant": tenant_id,
                "inv": investigation_id,
                "ident": f"RCA-GUARD-{decision_id}",
                "bid": f"DGUARD{decision_id.hex[:8]}",
            },
        )
    try:
        refused = _alembic(env, "downgrade", BEFORE_RCA)
        assert refused.returncode != 0
        assert "would be lost by downgrading trrcatools" in refused.stderr
        assert "decisions.root_cause_category" in _columns(engine)
    finally:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(text("DELETE FROM decisions WHERE id = :id"), {"id": decision_id})
        assert _alembic(env, "upgrade", "head").returncode == 0
