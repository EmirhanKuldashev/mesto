"""Persist the commute answer for personalized district summaries."""
from alembic import op
import sqlalchemy as sa

revision = '0012_profile_commute'
down_revision = '0011_external_signals'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('user_profiles')}
    if 'commute_minutes' not in columns:
        op.add_column('user_profiles', sa.Column('commute_minutes', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('user_profiles', 'commute_minutes')
