"""Each person's workspace persona, "Viewing as" (release 0.10.73, Release C, part C1).

The thirteenth migration of the trial line, chained from ``tr12sampleservice`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: one nullable column with no default; no existing row changes. The downgrade removes only what this
migration added.

- ``auth_users.view_persona``: the persona the person's workspace opens on (admin, quality, regulatory, handler,
  investigator, risk, decision, executive; access_control/personas.py WORKSPACE_PERSONAS). The trial owner chooses
  their own (POST /api/v1/me/persona) and it is kept for their next sign-in; an invited colleague's is set by the owner
  with the colleague's role (POST /api/v1/trial/team, POST /api/v1/trial/team/{user_id}/persona). Empty: the persona
  follows the role (the owner's is Admin). It is a view, never a permission: every route keeps its guard.

No existing store fits: ``persona_assignments`` holds the identity control plane's R1 personas (another catalog,
several per person), and the e-mail preferences are the person's mail choices. The column goes with the account, so
retention, the purge and personal-data erasure already take it. Legacy dedicated organization databases get the same
from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_view_persona``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr13viewpersona"
down_revision = "tr12sampleservice"
branch_labels = None
depends_on = None


def add_view_persona(system_scope: bool = True) -> None:
    """The column (also used for legacy organization databases; ``system_scope`` is not needed: the table keeps its
    isolation)."""
    op.add_column("auth_users", sa.Column("view_persona", sa.String(40), nullable=True))


def upgrade():
    add_view_persona()


def downgrade():
    op.drop_column("auth_users", "view_persona")
