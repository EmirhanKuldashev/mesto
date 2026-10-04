"""OSM immutable history and atomic active projection; never collect fresh data."""
import hashlib
import json
import re

from alembic import op
import sqlalchemy as sa

revision = "0014_osm_snapshot_lifecycle"
down_revision = "0013_poi_nullable_name"
branch_labels = None
depends_on = None

LEGACY_QUALITY = {
    "freshness_status": "UNKNOWN", "query_completeness_status": "UNKNOWN",
    "source_completeness_status": "UNKNOWN", "real_world_completeness_status": "UNKNOWN",
    "provenance_status": "PARTIAL", "eligibility_status": "UNKNOWN",
    "temporal_status": "UNKNOWN", "quality_status": "PARTIAL", "normalized_score_status": "BLOCKED",
    "reasons": ["legacy_original_provenance_unrecoverable", "adopted_persisted_payload_without_revalidation"],
}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def upgrade():
    # 0001 uses LIVE Base.metadata.create_all. Clean installs can already have
    # these tables; upgrades of existing installations do not. Do not edit 0001.
    from app.osm.models import OsmDataset, OsmSnapshot, OsmSnapshotObservation, OsmActivePoi
    bind = op.get_bind()
    for model in (OsmDataset, OsmSnapshot, OsmSnapshotObservation, OsmActivePoi):
        model.__table__.create(bind, checkfirst=True)
    if "fk_osm_active_same_dataset" not in {f["name"] for f in sa.inspect(bind).get_foreign_keys("osm_datasets")}:
        op.create_foreign_key("fk_osm_active_same_dataset", "osm_datasets", "osm_snapshots",
            ["id", "active_snapshot_id"], ["dataset_id", "id"], deferrable=True, initially="DEFERRED")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_osm_one_active ON osm_snapshots(dataset_id) WHERE status = 'ACTIVE'")
    _adopt_existing(bind)
    _guards()


def _adopt_existing(bind):
    rows = bind.execute(sa.text("""SELECT to_jsonb(p) - 'location' - 'geometry' AS payload,
        ST_AsEWKT(p.location) AS location_wkt, ST_AsEWKT(p.geometry) AS geometry_wkt,
        v.checksum AS source_checksum
        FROM pois p LEFT JOIN LATERAL (SELECT checksum FROM source_versions
            WHERE source_id=p.source_id AND source_version=p.source_version
            ORDER BY id LIMIT 1) v ON true
        WHERE p.source_id='osm' AND NOT p.is_synthetic ORDER BY p.id"""
    )).mappings().all()
    if rows and bind.scalar(sa.text("SELECT is_synthetic FROM data_sources WHERE source_id='osm'")) is not False:
        raise ValueError("Legacy OSM adoption requires a real DataSource")
    groups = {}
    for item in rows:
        payload = dict(item["payload"])
        match = re.fullmatch(r"(node|way|relation):([1-9][0-9]*)", payload.get("external_id") or "")
        if not match:
            raise ValueError("Unidentifiable legacy OSM row: adoption requires review")
        foundation = (payload.get("metadata") or {}).get("osm_foundation", {})
        version = payload["source_version"]
        # Published legacy naming is <scope>-<artifact checksum prefix>. This is
        # bookkeeping evidence only; it does not recover original query/time.
        digest = item["source_checksum"]
        scope = foundation.get("scope_id")
        if not scope:
            suffix = "-" + digest[:20] if digest else None
            scope = version[:-len(suffix)] if suffix and version.endswith(suffix) else "legacy-source-version:" + version
        dataset_key = foundation.get("dataset_id") or "legacy-poi"
        key = (scope, dataset_key, version)
        payload.update(location_wkt=item["location_wkt"], geometry_wkt=item["geometry_wkt"])
        groups.setdefault(key, []).append((payload, match.group(1), int(match.group(2))))
    scopes = set()
    for (scope, dataset_key, version), records in groups.items():
        if scope in scopes:
            raise ValueError("Multiple legacy versions in one scope: explicit adoption review required")
        scopes.add(scope)
        if len({(kind, id_) for _, kind, id_ in records}) != len(records):
            raise ValueError("Duplicate legacy OSM identities: explicit adoption review required")
        dataset_id = bind.scalar(sa.text("""INSERT INTO osm_datasets(source_id,dataset_key,scope_id)
            VALUES ('osm',:key,:scope) RETURNING id"""), {"key":dataset_key,"scope":scope})
        canonical = {"legacy_adoption":True,"source_version":version,"persisted_payloads":[p for p,_,_ in records]}
        canonical_text = _json(canonical)
        snapshot_id = bind.scalar(sa.text("""INSERT INTO osm_snapshots
            (dataset_id,version,status,is_legacy,sealed,canonical_checksum,canonical_json,build_report,quality)
            VALUES (:dataset,:version,'ACTIVE',true,true,:checksum,CAST(:canonical AS jsonb),'{}',CAST(:quality AS jsonb)) RETURNING id"""),
            {"dataset":dataset_id,"version":"legacy-source-version:"+version,
             "checksum":hashlib.sha256(canonical_text.encode()).hexdigest(),"canonical":canonical_text,"quality":_json(LEGACY_QUALITY)})
        for payload, kind, osm_id in records:
            bind.execute(sa.text("""INSERT INTO osm_snapshot_observations
                (snapshot_id,osm_type,osm_id,eligible,observation,projection,location)
                VALUES (:snapshot,:kind,:osm_id,true,CAST(:observation AS jsonb),CAST(:projection AS jsonb),ST_GeomFromEWKT(:location))"""),
                {"snapshot":snapshot_id,"kind":kind,"osm_id":osm_id,
                 "observation":_json({"osm_type":kind,"osm_id":osm_id,"legacy_persisted_payload":True}),
                 "projection":_json(payload),"location":payload["location_wkt"]})
            bind.execute(sa.text("""INSERT INTO osm_active_pois(poi_id,dataset_id,snapshot_id,osm_type,osm_id)
                VALUES (:poi,:dataset,:snapshot,:kind,:osm_id)"""),
                {"poi":payload["id"],"dataset":dataset_id,"snapshot":snapshot_id,"kind":kind,"osm_id":osm_id})
        bind.execute(sa.text("UPDATE osm_datasets SET active_snapshot_id=:snapshot WHERE id=:dataset"), {"snapshot":snapshot_id,"dataset":dataset_id})


def _guards():
    op.execute("""CREATE FUNCTION osm_dataset_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (to_jsonb(OLD)-'active_snapshot_id') IS DISTINCT FROM (to_jsonb(NEW)-'active_snapshot_id') THEN
          RAISE EXCEPTION 'OSM dataset source/scope identity is immutable';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute("CREATE TRIGGER osm_dataset_guard BEFORE UPDATE ON osm_datasets FOR EACH ROW EXECUTE FUNCTION osm_dataset_guard()")
    op.execute("""CREATE FUNCTION osm_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP <> 'INSERT' OR (SELECT sealed FROM osm_snapshots WHERE id=NEW.snapshot_id) THEN
          RAISE EXCEPTION 'OSM snapshot observations are immutable after sealing';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute("CREATE TRIGGER osm_history_guard BEFORE INSERT OR UPDATE OR DELETE ON osm_snapshot_observations FOR EACH ROW EXECUTE FUNCTION osm_history_guard()")
    op.execute("""CREATE FUNCTION osm_snapshot_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'OSM snapshot history cannot be deleted'; END IF;
        IF (to_jsonb(OLD)-'status'-'activation_review'-'sealed') IS DISTINCT FROM
           (to_jsonb(NEW)-'status'-'activation_review'-'sealed') OR (OLD.sealed AND NOT NEW.sealed) THEN
          RAISE EXCEPTION 'OSM snapshot identity and payload are immutable';
        END IF;
        IF OLD.status <> NEW.status AND NOT (
           (OLD.status='CANDIDATE' AND NEW.status IN ('VALIDATED','REJECTED')) OR
           (OLD.status='VALIDATED' AND NEW.status IN ('ACTIVE','REJECTED')) OR
           (OLD.status='ACTIVE' AND NEW.status='RETIRED')) THEN
          RAISE EXCEPTION 'Invalid OSM lifecycle transition';
        END IF;
        IF OLD.activation_review IS NOT NULL AND OLD.activation_review IS DISTINCT FROM NEW.activation_review THEN
          RAISE EXCEPTION 'OSM activation review is immutable';
        END IF;
        IF NEW.status IN ('VALIDATED','ACTIVE') AND NOT NEW.is_legacy AND (
           NOT NEW.sealed OR NEW.activation_review IS NULL OR
           NEW.quality->>'quality_status' IS DISTINCT FROM 'VALIDATED' OR
           NEW.quality->>'provenance_status' IS DISTINCT FROM 'VALIDATED' OR
           NEW.quality->>'query_completeness_status' IS DISTINCT FROM 'VALIDATED' OR
           NEW.quality->>'eligibility_status' IS DISTINCT FROM 'VALIDATED' OR
           NEW.quality->>'temporal_status' IS DISTINCT FROM 'VALIDATED') THEN
          RAISE EXCEPTION 'OSM activation quality/review gate failed';
        END IF;
        RETURN NEW;
      END $$""")
    op.execute("CREATE TRIGGER osm_snapshot_guard BEFORE UPDATE OR DELETE ON osm_snapshots FOR EACH ROW EXECUTE FUNCTION osm_snapshot_guard()")
    op.execute("""CREATE FUNCTION osm_active_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE ds integer; pointer integer; n integer;
      BEGIN
        IF TG_TABLE_NAME='osm_datasets' THEN ds:=NEW.id;
        ELSE ds:=COALESCE(NEW.dataset_id,OLD.dataset_id); END IF;
        SELECT active_snapshot_id INTO pointer FROM osm_datasets WHERE id=ds;
        SELECT count(*) INTO n FROM osm_snapshots WHERE dataset_id=ds AND status='ACTIVE';
        IF (pointer IS NULL AND n<>0) OR (pointer IS NOT NULL AND
           (n<>1 OR NOT EXISTS (SELECT 1 FROM osm_snapshots WHERE id=pointer AND dataset_id=ds AND status='ACTIVE' AND sealed))) THEN
          RAISE EXCEPTION 'OSM explicit active pointer/status mismatch';
        END IF;
        IF EXISTS (SELECT 1 FROM osm_active_pois WHERE dataset_id=ds AND snapshot_id IS DISTINCT FROM pointer) THEN
          RAISE EXCEPTION 'OSM projection must reference the explicit active snapshot';
        END IF;
        RETURN NULL;
      END $$""")
    for table in ("osm_datasets","osm_snapshots","osm_active_pois"):
        op.execute(f"CREATE CONSTRAINT TRIGGER osm_active_guard AFTER INSERT OR UPDATE OR DELETE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION osm_active_guard()")


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("""SELECT EXISTS(SELECT 1 FROM osm_snapshots WHERE NOT is_legacy)
        OR EXISTS(SELECT 1 FROM osm_snapshots GROUP BY dataset_id HAVING count(*)>1)""")):
        raise ValueError("Lossy OSM lifecycle downgrade blocked: export/preserve snapshot history first")
    for table in ("osm_datasets","osm_snapshots","osm_active_pois"):
        op.execute(f"DROP TRIGGER osm_active_guard ON {table}")
    op.execute("DROP TRIGGER osm_snapshot_guard ON osm_snapshots")
    op.execute("DROP TRIGGER osm_history_guard ON osm_snapshot_observations")
    op.execute("DROP TRIGGER osm_dataset_guard ON osm_datasets")
    for function in ("osm_active_guard","osm_snapshot_guard","osm_history_guard","osm_dataset_guard"):
        op.execute(f"DROP FUNCTION {function}()")
    op.drop_constraint("fk_osm_active_same_dataset", "osm_datasets", type_="foreignkey")
    for table in ("osm_active_pois","osm_snapshot_observations","osm_snapshots","osm_datasets"):
        op.drop_table(table)
