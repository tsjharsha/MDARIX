"""Scheduled jobs and per-instance worker heartbeats.

``scheduler_runs``: when each scheduled job last ran, how it ended, and the small state it keeps between runs. The
scheduler (scripts/run_scheduler.py) runs each job when it is due; a Postgres advisory lock makes sure only one
scheduler instance runs a job at a time.

``worker_heartbeats`` is now keyed by service *and* instance, so two worker instances no longer overwrite each
other's heartbeat. Platform-level tables: no tenant data.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md16schedulerruns"
down_revision = "md15rlssystemtoken"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scheduler_runs",
        sa.Column("job", sa.String(80), primary_key=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True)),
        sa.Column("last_finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(20)),
        sa.Column("last_result", postgresql.JSONB()),
        sa.Column("last_error", sa.Text()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.scheduler_runs TO mdarix_runtime; END IF; END $$;"
    )
    op.execute(
        "DO $$ DECLARE name text; BEGIN "
        "SELECT conname INTO name FROM pg_constraint "
        "WHERE conrelid = 'public.worker_heartbeats'::regclass AND contype = 'p'; "
        "IF name IS NOT NULL THEN EXECUTE format('ALTER TABLE public.worker_heartbeats DROP CONSTRAINT %I', name); "
        "END IF; END $$;"
    )
    op.create_primary_key("pk_worker_heartbeats", "worker_heartbeats", ["service", "instance_id"])


def downgrade():
    # Keep the newest heartbeat per service, then restore the one-row-per-service key.
    op.execute(
        "DELETE FROM public.worker_heartbeats w USING public.worker_heartbeats newer "
        "WHERE w.service = newer.service AND w.updated_at < newer.updated_at"
    )
    op.execute(
        "DO $$ DECLARE name text; BEGIN "
        "SELECT conname INTO name FROM pg_constraint "
        "WHERE conrelid = 'public.worker_heartbeats'::regclass AND contype = 'p'; "
        "IF name IS NOT NULL THEN EXECUTE format('ALTER TABLE public.worker_heartbeats DROP CONSTRAINT %I', name); "
        "END IF; END $$;"
    )
    op.create_primary_key("pk_worker_heartbeats", "worker_heartbeats", ["service"])
    op.drop_table("scheduler_runs")
