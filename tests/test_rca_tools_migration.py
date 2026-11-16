"""RCA tools migration (trrcatools): down to tr31othercountries and up again leaves the same schema, and the downgrade
refuses while a decision carries a root-cause category (no silent loss).

Runs Alembic against the test database (``POSTGRES_DB``), so it must not run beside another test run on that database.
"""

import os
import subprocess
import sys
import uuid

from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.db.tenant_scope import bind_connection_system
from tests.test_db1_migration_roundtrip import FINGERPRINT, ROOT

BEFORE_RCA = "tr31othercountries"


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=ROOT, env=dict(os.environ), capture_output=True, text=True
    )


def _fingerprint() -> set[tuple[str, str]]:
    with engine.connect() as connection:
        return {tuple(row) for row in connection.execute(text(FINGERPRINT))}


def _columns() -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name || '.' || column_name FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name IN ('hypotheses', 'failure_chains', 'decisions', 'brief_review_actions', 'risks')"
            )
        )
        return {row[0] for row in rows}


def test_rca_migration_goes_down_and_up_again_to_the_same_schema():
    at_head, columns = _fingerprint(), _columns()
    try:
        down = _alembic("downgrade", BEFORE_RCA)
        assert down.returncode == 0, down.stderr[-2000:]
        before, columns_before = _fingerprint(), _columns()
    finally:
        up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    assert _fingerprint() == at_head and _columns() == columns
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


def test_rca_downgrade_refuses_while_a_decision_carries_a_root_cause_category():
    decision_id = uuid.uuid4()
    with engine.begin() as connection:
        bind_connection_system(connection)
        tenant_id, investigation_id = connection.execute(
            text("SELECT tenant_id, id FROM investigations ORDER BY created_at LIMIT 1")
        ).one()
        connection.execute(
            text(
                "INSERT INTO decisions (id, tenant_id, investigation_id, decision_identifier, decision_type, "
                "disposition, rationale, authorized_by_ref, root_cause_category, decision_timestamp, created_at, updated_at) "
                "VALUES (:id, :tenant, :inv, "
                ":ident, 'TEST', 'TEST', 'Migration guard test', 'test', 'MATERIAL', now(), now(), now())"
            ),
            {"id": decision_id, "tenant": tenant_id, "inv": investigation_id, "ident": f"RCA-GUARD-{decision_id}"},
        )
    try:
        refused = _alembic("downgrade", BEFORE_RCA)
        assert refused.returncode != 0
        assert "would be lost by downgrading trrcatools" in refused.stderr
        assert "decisions.root_cause_category" in _columns()
    finally:
        with engine.begin() as connection:
            bind_connection_system(connection)
            connection.execute(text("DELETE FROM decisions WHERE id = :id"), {"id": decision_id})
        assert _alembic("upgrade", "head").returncode == 0
