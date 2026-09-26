"""Expose explicit geometry fields while preserving Stage 1 location columns.

Revision ID: 0003_spatial_aliases
Revises: 0002_data_foundation
"""

from alembic import op
from sqlalchemy import inspect

from app.db import Base
from app import models  # noqa: F401

revision = "0003_spatial_aliases"
down_revision = "0002_data_foundation"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("pois", "future_objects"):
        if "geometry" not in {column["name"] for column in inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, Base.metadata.tables[table].c.geometry.copy())
        op.execute(f"UPDATE {table} SET geometry = location WHERE geometry IS NULL")
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_geometry_gist ON {table} USING gist (geometry)")


def downgrade():
    # The Stage 1 location fields remain the source of spatial data.
    for table in ("pois", "future_objects"):
        op.drop_index(f"idx_{table}_geometry_gist", table_name=table, if_exists=True)
        op.drop_column(table, "geometry", if_exists=True)
