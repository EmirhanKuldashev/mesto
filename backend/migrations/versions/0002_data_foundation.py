"""Extend the Stage 1 tables with source-neutral data foundation fields.

Revision ID: 0002_data_foundation
Revises: 0001_initial
"""

from alembic import op
from sqlalchemy import inspect

from app import models  # noqa: F401
from app.db import Base

revision = "0002_data_foundation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

ADDED = {
    "districts": ["slug", "geometry", "centroid", "population", "area_km2", "density", "created_at", "updated_at"],
    "pois": ["geometry", "external_id", "subcategory", "district_id", "metadata"],
    "residential_complexes": ["developer", "building_class", "price_from", "price_per_sqm", "available_units", "layouts"],
    "property_offers": ["floor", "address", "location"],
    "rent_listings": ["address"],
    "mortgage_programs": ["provider", "requirements", "region", "official_url"],
    "future_objects": ["geometry", "district_id", "planned_year", "confidence", "source", "source_document", "source_date"],
    "data_sources": ["organization"],
    "source_versions": ["record_count"],
    "data_quality": ["entity_type", "entity_id", "freshness", "confidence", "forecast_share", "limitations"],
}


def upgrade():
    bind = op.get_bind()
    for table_name, names in ADDED.items():
        present = {column["name"] for column in inspect(bind).get_columns(table_name)}
        for name in names:
            if name not in present:
                column = Base.metadata.tables[table_name].c[name]
                op.add_column(table_name, column.copy())
    for table_name, name in (("districts", "geometry"), ("districts", "centroid"), ("pois", "geometry"),
                             ("future_objects", "geometry"), ("property_offers", "location")):
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{name}_gist ON {table_name} USING gist ({name})")


def downgrade():
    bind = op.get_bind()
    for table_name, names in reversed(list(ADDED.items())):
        present = {column["name"] for column in inspect(bind).get_columns(table_name)}
        for name in reversed(names):
            if name in present:
                op.drop_column(table_name, name)
