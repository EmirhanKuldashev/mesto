"""Store Cian ЖК identity and provenance in existing residential_complexes.

Revision ID: 0008_cian_complexes
Revises: 0007_cian_offer_loader
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_cian_complexes"
down_revision = "0007_cian_offer_loader"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("residential_complexes")}
    for name, column_type in (("external_id", sa.String(120)), ("url", sa.Text()), ("address", sa.String(250))):
        if name not in columns:
            op.add_column("residential_complexes", sa.Column(name, column_type, nullable=True))
    constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("residential_complexes")}
    if "uq_residential_complex_source_external" not in constraints:
        op.create_unique_constraint(
            "uq_residential_complex_source_external", "residential_complexes", ["source_id", "external_id"]
        )


def downgrade():
    bind = op.get_bind()
    constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("residential_complexes")}
    if "uq_residential_complex_source_external" in constraints:
        op.drop_constraint("uq_residential_complex_source_external", "residential_complexes", type_="unique")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("residential_complexes")}
    for name in ("address", "url", "external_id"):
        if name in columns:
            op.drop_column("residential_complexes", name)
