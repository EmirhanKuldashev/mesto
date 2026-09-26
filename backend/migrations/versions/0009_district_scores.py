"""Store versioned, profile-specific district scores.

Revision ID: 0009_district_scores
Revises: 0008_cian_complexes
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_district_scores"
down_revision = "0008_cian_complexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "district_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("total_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("lifestyle_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("infrastructure_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("transport_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("future_growth_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("market_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("calculation_version", sa.String(40), nullable=False, server_default="baseline-v1"),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("total_score IS NULL OR (total_score >= 0 AND total_score <= 100)", name="ck_district_scores_total"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_district_scores_confidence"),
    )
    op.create_index("ix_district_scores_profile_id", "district_scores", ["profile_id"])
    op.create_index("ix_district_scores_district_id", "district_scores", ["district_id"])


def downgrade():
    op.drop_index("ix_district_scores_district_id", table_name="district_scores")
    op.drop_index("ix_district_scores_profile_id", table_name="district_scores")
    op.drop_table("district_scores")
