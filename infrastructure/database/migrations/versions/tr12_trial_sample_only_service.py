"""A sample-only trial, and a complaint's linked service work (release 0.10.71, Release A, tasks A2 and A5).

The twelfth migration of the trial line, chained from ``tr11navigation`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: one column with a default, and nullable columns with no default; no existing row changes. The downgrade
removes only what this migration added.

- ``tenants.sample_only``: an evaluation on the sample only (an event or judge trial). A platform administrator sets it
  in Tenant 360 (PATCH /api/v1/platform-admin/tenants/{id}, with a reason, audited as TENANT_UPDATED); while it is on,
  every import route answers 403 SAMPLE_ONLY_TRIAL and the screens offer "Discuss a pilot" instead of an upload.
- ``complaints.service_reference``, ``service_owner``, ``service_status`` (OPEN, IN_PROGRESS, COMPLETE) and
  ``service_status_at``: the service work linked to a complaint (the customer's service ticket, free text), its owner
  and status with the date. It never closes or advances the complaint (backend/app/oversight/service_work.py).

No existing store fits: the tenant's plan assignment changes when a trial becomes a pilot, the trial request's profile
is not edited in Tenant 360, and no complaint column holds service work (the disposition's service record is part of a
signed service-level decision). The complaint columns go with the complaint, so retention, sample removal and the
purge already take them. Legacy dedicated organization databases get the same from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_sample_only_and_service``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr12sampleservice"
down_revision = "tr11navigation"
branch_labels = None
depends_on = None

SERVICE_COLUMNS = (
    ("service_reference", lambda: sa.String(120)),
    ("service_owner", lambda: sa.String(255)),
    ("service_status", lambda: sa.String(20)),
    ("service_status_at", lambda: sa.DateTime(timezone=True)),
)


def add_sample_only_and_service(system_scope: bool = True) -> None:
    """The columns and their check (also used for legacy organization databases; ``system_scope`` is not needed:
    each table keeps its isolation)."""
    op.add_column("tenants", sa.Column("sample_only", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    for column, kind in SERVICE_COLUMNS:
        op.add_column("complaints", sa.Column(column, kind(), nullable=True))
    op.create_check_constraint(
        op.f("ck_complaints_complaint_service_status_known"),
        "complaints",
        "service_status IS NULL OR service_status IN ('OPEN','IN_PROGRESS','COMPLETE')",
    )


def upgrade():
    add_sample_only_and_service()


def downgrade():
    op.drop_constraint(op.f("ck_complaints_complaint_service_status_known"), "complaints", type_="check")
    for column, _ in reversed(SERVICE_COLUMNS):
        op.drop_column("complaints", column)
    op.drop_column("tenants", "sample_only")
