"""Add consent-aware life profiles without changing Stage 1 integer foreign keys.

Revision ID: 0004_life_profile
Revises: 0003_spatial_aliases
"""

from alembic import op
from sqlalchemy import inspect

from app import models  # noqa: F401
from app.db import Base

revision = "0004_life_profile"
down_revision = "0003_spatial_aliases"
branch_labels = None
depends_on = None

ADDED = {
    "user_profiles": [
        "public_id", "household_type", "adults_count", "children_count", "children", "housing_goal",
        "purchase_budget", "initial_payment", "comfortable_monthly_payment", "rent_budget",
        "planning_horizon", "car_availability", "transport_preferences", "future_changes",
        "home_values", "good_home_text", "price_vs_time", "today_vs_future", "car_dependency",
        "data_processing_consent", "consent_at",
    ],
    "partner_profiles": ["work_location", "transport_preferences", "preferences", "life_goals"],
    "life_points": ["importance"],
    "user_preferences": [
        "education_weight", "kindergarten_weight", "healthcare_weight", "transport_weight",
        "ecology_weight", "safety_weight", "parks_weight", "shopping_weight",
        "entertainment_weight", "housing_price_weight", "future_growth_weight",
        "quiet_active", "green_urban", "center_calm",
    ],
}


def upgrade():
    bind = op.get_bind()
    for table_name, names in ADDED.items():
        present = {column["name"] for column in inspect(bind).get_columns(table_name)}
        for name in names:
            if name not in present:
                op.add_column(table_name, Base.metadata.tables[table_name].c[name].copy())
    op.alter_column("user_profiles", "name", nullable=True)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_profiles_public_id ON user_profiles (public_id)")
    Base.metadata.tables["analysis_requests"].create(bind=bind, checkfirst=True)


def downgrade():
    Base.metadata.tables["analysis_requests"].drop(bind=op.get_bind(), checkfirst=True)
    op.drop_index("ix_user_profiles_public_id", table_name="user_profiles", if_exists=True)
    op.alter_column("user_profiles", "name", nullable=False)
    for table_name, names in reversed(list(ADDED.items())):
        for name in reversed(names):
            op.drop_column(table_name, name, if_exists=True)
