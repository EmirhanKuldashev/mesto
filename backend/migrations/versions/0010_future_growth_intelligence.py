"""Persist current/future outlook and evidence for each analytics snapshot.

Revision ID: 0010_future_growth_intelligence
Revises: 0009_district_scores
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010_future_growth_intelligence"
down_revision = "0009_district_scores"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("district_scores", sa.Column("current_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("district_scores", sa.Column("future_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("district_scores", sa.Column("future_factors", JSONB(), nullable=False,
                                                server_default=sa.text("'[]'::jsonb")))
    op.create_check_constraint("ck_district_scores_current", "district_scores",
                               "current_score IS NULL OR (current_score >= 0 AND current_score <= 100)")
    op.create_check_constraint("ck_district_scores_future", "district_scores",
                               "future_score IS NULL OR (future_score >= 0 AND future_score <= 100)")


def downgrade():
    op.drop_constraint("ck_district_scores_future", "district_scores", type_="check")
    op.drop_constraint("ck_district_scores_current", "district_scores", type_="check")
    op.drop_column("district_scores", "future_factors")
    op.drop_column("district_scores", "future_score")
    op.drop_column("district_scores", "current_score")
