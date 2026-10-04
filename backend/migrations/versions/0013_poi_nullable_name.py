"""Allow unnamed POIs without inventing source names.

Downgrade restores NOT NULL only if no NULL names exist. PostgreSQL rejects
the downgrade otherwise; records are never deleted or backfilled.
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_poi_nullable_name"
down_revision = "0012_profile_commute"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("pois", "name", existing_type=sa.String(200), nullable=True)


def downgrade():
    op.alter_column("pois", "name", existing_type=sa.String(200), nullable=False)
