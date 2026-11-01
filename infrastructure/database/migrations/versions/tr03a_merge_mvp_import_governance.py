"""Join mvp-1.0's md49-md52 (signing grants, import quarantine, row lineage, regulatory reference: 0.10.56) with the
trial line's tr02 (0.10.53, complaint dispositions) into one head.

No schema change: both branches start at md48legalacceptance and touch different tables. Not ``tr03``: that id is
kept for proactive PMS sources. On mvp-1.0, which already joins them in md54mergetrialtr02, the forward merge needs
one more empty merge revision (md55).
"""

revision = "tr03amergemvpimports"
down_revision = ("tr02complaintdispositions", "md52regulatoryreference")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
