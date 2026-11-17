"""An effectiveness check result may be INCONCLUSIVE (W1d, D04, owner decision 17 Nov 2026).

The thirty-fourth migration of the trial line, on ``tr33validationruns`` (re-parented from ``tr32aiready`` when the
W1d line joined release 0.11.05, so the line keeps one head). Expand-only: the check constraint on
``capa_effectiveness_checks.status`` gains ``INCONCLUSIVE`` beside ``EFFECTIVE`` and ``NOT_EFFECTIVE``. Nothing is
dropped, renamed or rewritten. The downgrade refuses while a check is signed INCONCLUSIVE (a signed result is never
changed silently).
"""

from alembic import op
from sqlalchemy import text

revision = "tr33inconclusive"
down_revision = "tr33validationruns"
branch_labels = None
depends_on = None

TABLE = "capa_effectiveness_checks"
NAME = "ck_capa_effectiveness_checks_status_known"


def _status_check(statuses: tuple[str, ...]) -> None:
    op.drop_constraint(op.f(NAME), TABLE, type_="check")
    op.create_check_constraint(op.f(NAME), TABLE, "status IN (" + ", ".join(f"'{s}'" for s in statuses) + ")")


def upgrade() -> None:
    _status_check(("PLANNED", "EFFECTIVE", "NOT_EFFECTIVE", "INCONCLUSIVE"))


def downgrade() -> None:
    signed = op.get_bind().execute(text(f"SELECT count(*) FROM {TABLE} WHERE status = 'INCONCLUSIVE'")).scalar()
    if signed:
        raise RuntimeError(f"{signed} effectiveness checks are signed INCONCLUSIVE; refusing to drop that result")
    _status_check(("PLANNED", "EFFECTIVE", "NOT_EFFECTIVE"))
