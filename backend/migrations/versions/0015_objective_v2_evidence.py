"""Preserve new objective component provenance without rewriting score history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_objective_v2_evidence"
down_revision = "0014_osm_snapshot_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    # 0001 uses live metadata, so fresh databases can already contain the column.
    if "objective_evidence" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("district_scores")}:
        op.add_column("district_scores", sa.Column("objective_evidence", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("district_scores", "objective_evidence")
