"""Load Master Data seed v1 (controlled load of platform reference data).

The seed content lives in infrastructure/database/seeds/master_data_v1.py and is
frozen; later reference-data changes ship as new seed versions and migrations.
"""

from alembic import op

from infrastructure.database.seeds import master_data_v1

revision = "md02masterseed"
down_revision = "md01masterdata"
branch_labels = None
depends_on = None


def upgrade():
    master_data_v1.load(op.get_bind())


def downgrade():
    # Seed rows are protected by the Master Data delete guard; reference data is
    # removed together with the schema by downgrading md01.
    pass
