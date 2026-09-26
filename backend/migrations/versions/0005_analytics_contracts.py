"""Make ownership, preference answers and analysis snapshots explicit.

Revision ID: 0005_analytics_contracts
Revises: 0004_life_profile
"""

from alembic import op
from sqlalchemy import inspect, text

from app import models  # noqa: F401
from app.db import Base

revision = "0005_analytics_contracts"
down_revision = "0004_life_profile"
branch_labels = None
depends_on = None

PREFERENCE_NAMES = [
    "education_weight", "kindergarten_weight", "healthcare_weight", "transport_weight",
    "ecology_weight", "safety_weight", "parks_weight", "shopping_weight",
    "entertainment_weight", "housing_price_weight", "future_growth_weight",
    "quiet_active", "green_urban", "center_calm",
]
UNANSWERED = '{"value": null, "is_answered": false, "source": "default", "confidence": 0}'


def upgrade():
    bind = op.get_bind()
    additions = {
        "life_points": ["owner_type", "primary_user_id", "partner_profile_id"],
        "user_preferences": ["preference_values"],
        "analysis_requests": ["profile_snapshot", "partner_snapshot", "life_points_snapshot",
                              "preferences_snapshot", "data_version_snapshot"],
    }
    for table_name, names in additions.items():
        existing = {column["name"] for column in inspect(bind).get_columns(table_name)}
        for name in names:
            if name not in existing:
                column = Base.metadata.tables[table_name].c[name].copy()
                if table_name == "life_points" and name == "owner_type":
                    column.nullable = True
                op.add_column(table_name, column)

    op.execute("UPDATE life_points SET owner_type='primary_user', primary_user_id=user_profile_id WHERE owner_type IS NULL")
    op.execute("""UPDATE life_points AS lp SET owner_type='partner', primary_user_id=NULL,
               partner_profile_id=pp.id FROM partner_profiles AS pp
               WHERE lp.kind='partner_work' AND lp.user_profile_id=pp.user_profile_id
               AND lp.partner_profile_id IS NULL""")
    op.alter_column("life_points", "owner_type", nullable=False)
    checks = {check["name"] for check in inspect(bind).get_check_constraints("life_points")}
    if "ck_life_points_owner" not in checks:
        op.create_check_constraint("ck_life_points_owner", "life_points",
            "(owner_type = 'primary_user' AND primary_user_id IS NOT NULL AND partner_profile_id IS NULL) "
            "OR (owner_type = 'partner' AND primary_user_id IS NULL AND partner_profile_id IS NOT NULL)")
    indexes = {index["name"] for index in inspect(bind).get_indexes("life_points")}
    for name, column in (("ix_life_points_primary_user_id", "primary_user_id"),
                         ("ix_life_points_partner_profile_id", "partner_profile_id")):
        if name not in indexes:
            op.create_index(name, "life_points", [column])
    foreign_keys = {fk["name"] for fk in inspect(bind).get_foreign_keys("life_points")}
    for name, column, target in (("fk_life_points_primary_user_id", "primary_user_id", "user_profiles"),
                                 ("fk_life_points_partner_profile_id", "partner_profile_id", "partner_profiles")):
        if name not in foreign_keys and not any(fk["constrained_columns"] == [column] for fk in inspect(bind).get_foreign_keys("life_points")):
            op.create_foreign_key(name, "life_points", target, [column], ["id"])

    # The old 50 defaults carried no evidence of an answer. Historical values remain
    # in legacy columns, while the canonical contract records them as unanswered.
    empty_values = "jsonb_build_object(" + ", ".join(
        f"'{name}', '{UNANSWERED}'::jsonb" for name in PREFERENCE_NAMES) + ")"
    op.execute(text(f"UPDATE user_preferences SET preference_values={empty_values} WHERE preference_values IS NULL OR preference_values='{{}}'::jsonb"))
    partner_values = "jsonb_build_object(" + ", ".join(
        f"'{name}', CASE WHEN jsonb_typeof(preferences->'{name}')='number' "
        f"THEN jsonb_build_object('value', (preferences->>'{name}')::integer, 'is_answered', true, 'source', 'partner', 'confidence', 1) "
        f"WHEN jsonb_typeof(preferences->'{name}')='object' THEN preferences->'{name}' "
        f"ELSE '{UNANSWERED}'::jsonb END" for name in PREFERENCE_NAMES) + ")"
    op.execute(text(f"UPDATE partner_profiles SET preferences={partner_values}"))
    for name in PREFERENCE_NAMES:
        op.alter_column("user_preferences", name, nullable=True, server_default=None)

    # Pre-contract requests cannot be reconstructed; their empty snapshots are explicit.
    op.execute("UPDATE analysis_requests SET profile_snapshot='{}'::jsonb WHERE profile_snapshot IS NULL")
    op.execute("UPDATE analysis_requests SET partner_snapshot='{}'::jsonb WHERE partner_snapshot IS NULL")
    op.execute("UPDATE analysis_requests SET life_points_snapshot='[]'::jsonb WHERE life_points_snapshot IS NULL")
    op.execute("UPDATE analysis_requests SET preferences_snapshot='{}'::jsonb WHERE preferences_snapshot IS NULL")
    op.execute("UPDATE analysis_requests SET data_version_snapshot='{}'::jsonb WHERE data_version_snapshot IS NULL")


def downgrade():
    bind = op.get_bind()
    op.execute("""UPDATE partner_profiles AS p SET preferences=(
        SELECT COALESCE(jsonb_object_agg(key, value->'value'), '{}'::jsonb)
        FROM jsonb_each(p.preferences) WHERE value->>'is_answered'='true')""")
    for name in PREFERENCE_NAMES:
        op.execute(text(f"UPDATE user_preferences SET {name}=50 WHERE {name} IS NULL"))
        op.alter_column("user_preferences", name, nullable=False, server_default="50")
    op.drop_column("user_preferences", "preference_values")

    for name in ("data_version_snapshot", "preferences_snapshot", "life_points_snapshot",
                 "partner_snapshot", "profile_snapshot"):
        op.drop_column("analysis_requests", name)

    checks = {check["name"] for check in inspect(bind).get_check_constraints("life_points")}
    if "ck_life_points_owner" in checks:
        op.drop_constraint("ck_life_points_owner", "life_points", type_="check")
    for fk in inspect(bind).get_foreign_keys("life_points"):
        if fk["constrained_columns"] in (["primary_user_id"], ["partner_profile_id"]):
            op.drop_constraint(fk["name"], "life_points", type_="foreignkey")
    indexes = {index["name"] for index in inspect(bind).get_indexes("life_points")}
    for name in ("ix_life_points_primary_user_id", "ix_life_points_partner_profile_id"):
        if name in indexes:
            op.drop_index(name, table_name="life_points")
    for name in ("partner_profile_id", "primary_user_id", "owner_type"):
        op.drop_column("life_points", name)
