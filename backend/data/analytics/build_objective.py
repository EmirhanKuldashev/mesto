"""Explicit offline build: python -m data.analytics.build_objective --output PATH.

Requires a migrated database with the accepted canonical baseline. Never called
by an endpoint; outputs canonical service results, never hand-entered scores.
"""
import argparse
import json
import time
from pathlib import Path

from sqlalchemy import event, select

from app import models
from app.db import create_session_factory
from app.analytics.objective.components import contracts
from app.analytics.objective.provider import PARITY_QUERY
from app.analytics.school.models import source_ready
from app.analytics.stop_availability.models import SnapshotIdentity
from data.osm.contracts import Quality


def build(session):
    districts = list(session.scalars(select(models.District).where(
        models.District.source_id == "osm", models.District.is_synthetic.is_(False))))
    ids = [d.id for d in districts]
    rows = list(session.execute(PARITY_QUERY, {"district_ids": ids}).mappings())
    assert len(rows) == 7 and all(r["version"] for r in rows)
    row = rows[0]
    snapshot = SnapshotIdentity(dataset_key=row["dataset_key"], scope_id=row["scope_id"],
        snapshot_version=row["version"], canonical_checksum=row["canonical_checksum"],
        query_version=row["query_version"], query_hash=row["query_hash"],
        foundation_eligibility_version=row["foundation_policy"])
    assert source_ready(snapshot, Quality.model_validate(row["quality"]))
    artifact = {"version": "objective-canonical-district-snapshot-v1",
        "snapshot": snapshot.model_dump(mode="json"), "projection_fingerprint": row["fingerprint"],
        "districts": {r["slug"]: {"geometry_ewkb_md5": r["geometry_checksum"], "components": {}} for r in rows}}
    slugs = {d.id: d.slug for d in districts}
    timings = {}
    for name, _, service, _, _ in contracts():
        started = time.perf_counter()
        outputs = service(session, scope_id="krasnoyarsk").districts(ids)
        timings[name] = time.perf_counter() - started
        assert len(outputs) == 7 and all(o.availability == "AVAILABLE" for o in outputs)
        for output in outputs:
            artifact["districts"][slugs[output.district_id]]["components"][name] = output.model_dump(
                mode="json", exclude={"district_id"})
    # Detect concurrent source/geometry changes rather than publishing a mixed baseline.
    assert rows == list(session.execute(PARITY_QUERY, {"district_ids": ids}).mappings())
    return artifact, timings


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    factory, engine = create_session_factory()
    count = []
    event.listen(engine, "before_cursor_execute", lambda *a: count.append(1))
    try:
        with factory() as session:
            artifact, timings = build(session)
        args.output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"component_seconds": timings, "queries": len(count)}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
