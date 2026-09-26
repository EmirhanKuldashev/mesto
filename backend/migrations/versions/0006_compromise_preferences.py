"""Remove implicit answers from the three compromise sliders.

Revision ID: 0006_compromise_preferences
Revises: 0005_analytics_contracts
"""

from alembic import op
from sqlalchemy import text

revision = "0006_compromise_preferences"
down_revision = "0005_analytics_contracts"
branch_labels = None
depends_on = None

NAMES = ("price_vs_time", "today_vs_future", "car_dependency")
UNANSWERED = '{"value": null, "is_answered": false, "source": "default", "confidence": 0}'


def upgrade():
    for name in NAMES:
        op.alter_column("user_profiles", name, nullable=True, server_default=None)
        op.execute(text(
            f"UPDATE user_preferences SET preference_values=jsonb_set(preference_values, '{{{name}}}', "
            f"'{UNANSWERED}'::jsonb, true) WHERE NOT preference_values ? '{name}'"
        ))
        op.execute(text(
            f"UPDATE user_profiles AS profile SET {name}=NULL FROM user_preferences AS pref "
            f"WHERE pref.user_profile_id=profile.id AND "
            f"COALESCE((pref.preference_values->'{name}'->>'is_answered')::boolean, false)=false"
        ))
        op.execute(text(
            f"UPDATE partner_profiles SET preferences=jsonb_set(preferences, '{{{name}}}', "
            f"'{UNANSWERED}'::jsonb, true) WHERE NOT preferences ? '{name}'"
        ))


def downgrade():
    for name in NAMES:
        op.execute(text(f"UPDATE user_profiles SET {name}=50 WHERE {name} IS NULL"))
        op.alter_column("user_profiles", name, nullable=False, server_default="50")
        op.execute(text(f"UPDATE user_preferences SET preference_values=preference_values - '{name}'"))
        op.execute(text(f"UPDATE partner_profiles SET preferences=preferences - '{name}'"))
