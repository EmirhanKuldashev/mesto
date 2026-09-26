"""Add bounded, provenance-aware district signals.

Revision ID: 0011_external_signals
Revises: 0010_future_growth_intelligence
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_external_signals"
down_revision = "0010_future_growth_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("district_id", sa.Integer(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("impact_direction", sa.String(10), nullable=False),
        sa.Column("impact_value", sa.Numeric(5, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("event_date", sa.Date()),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source_type IN ('news', 'tender', 'construction', 'government_plan', 'other')",
                           name="ck_external_signals_source_type"),
        sa.CheckConstraint("category IN ('education', 'transport', 'healthcare', 'environment', 'commercial', 'housing')",
                           name="ck_external_signals_category"),
        sa.CheckConstraint("impact_direction IN ('positive', 'negative', 'neutral')",
                           name="ck_external_signals_direction"),
        sa.CheckConstraint("impact_value >= -100 AND impact_value <= 100",
                           name="ck_external_signals_impact_range"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_external_signals_confidence"),
        sa.CheckConstraint("(impact_direction = 'positive' AND impact_value > 0) OR "
                           "(impact_direction = 'negative' AND impact_value < 0) OR "
                           "(impact_direction = 'neutral' AND impact_value = 0)",
                           name="ck_external_signals_direction_value"),
    )
    op.create_index("ix_external_signals_district_id", "external_signals", ["district_id"])


def downgrade():
    op.drop_index("ix_external_signals_district_id", table_name="external_signals")
    op.drop_table("external_signals")
