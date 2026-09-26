"""Extend existing property offers for source-aware, timestamped upserts.

Revision ID: 0007_cian_offer_loader
Revises: 0006_compromise_preferences
"""

from alembic import op
from sqlalchemy import inspect, text

from app import models  # noqa: F401
from app.db import Base

revision = "0007_cian_offer_loader"
down_revision = "0006_compromise_preferences"
branch_labels = None
depends_on = None

ADDED = ("source", "url", "title", "city", "created_at", "updated_at")
UNIQUE_NAME = "uq_property_offers_source_external"


def upgrade():
    bind = op.get_bind()
    present = {column["name"] for column in inspect(bind).get_columns("property_offers")}
    for name in ADDED:
        if name not in present:
            column = Base.metadata.tables["property_offers"].c[name].copy()
            if name == "source":
                column.nullable = True
            op.add_column("property_offers", column)

    op.execute("UPDATE property_offers SET source=source_id WHERE source IS NULL")
    op.alter_column("property_offers", "source", nullable=False)

    constraints = {constraint["name"] for constraint in inspect(bind).get_unique_constraints("property_offers")}
    if UNIQUE_NAME not in constraints:
        duplicate = bind.execute(text("""SELECT source_id, external_id FROM property_offers
            WHERE external_id IS NOT NULL GROUP BY source_id, external_id
            HAVING count(*) > 1 LIMIT 1""")).first()
        if duplicate:
            raise RuntimeError(f"Duplicate property offer identity must be resolved before migration: {duplicate}")
        op.create_unique_constraint(UNIQUE_NAME, "property_offers", ["source_id", "external_id"])


def downgrade():
    bind = op.get_bind()
    constraints = {constraint["name"] for constraint in inspect(bind).get_unique_constraints("property_offers")}
    if UNIQUE_NAME in constraints:
        op.drop_constraint(UNIQUE_NAME, "property_offers", type_="unique")
    present = {column["name"] for column in inspect(bind).get_columns("property_offers")}
    for name in reversed(ADDED):
        if name in present:
            op.drop_column("property_offers", name)
