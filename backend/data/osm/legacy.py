"""Explicit compatibility adapter for snapshots with unrecoverable provenance."""

from pathlib import Path

from data.osm.contracts import (
    BUILDER_VERSION, BuildResult, Extent, Quality, SourceReference, Status, canonical_bytes, checksum,
)
from data.osm.observations import observation
from data.osm.validation import read_response

# Configuration for the bundled snapshot, not a parser city branch.
LEGACY_EXTENT = Extent(west=92.5, south=55.8, east=93.45, north=56.25)


def build_legacy(path: Path, *, extent: Extent = LEGACY_EXTENT,
                 dataset_id="legacy-poi", scope_id="krasnoyarsk") -> BuildResult:
    raw = path.read_bytes()
    payload = read_response(raw, require_header=False)
    if payload.get("remark") or payload.get("error"):
        raise ValueError("Legacy snapshot reports an error/remark")
    digest = checksum(raw)
    snapshot_id = f"legacy-{digest}"
    reference = SourceReference(part_id="legacy-merged-artifact", artifact_reference=path.name,
        artifact_checksum=digest, source_base_timestamp=None, fetched_at=None)
    grouped = {}
    for item in payload["elements"]:
        row = observation(item, dataset_id=dataset_id, scope_id=scope_id, snapshot_id=snapshot_id,
                          extent=extent, references=(reference,))
        key = row.identity
        if key in grouped and canonical_bytes(item) != grouped[key][0]:
            raise ValueError(f"Conflicting legacy OSM identity: {key}")
        grouped[key] = (canonical_bytes(item), row)
    rows = tuple(grouped[key][1] for key in sorted(grouped))
    quality = Quality(provenance_status=Status.PARTIAL,
        eligibility_status=Status.PARTIAL if any("invalid_or_missing_coordinate" in row.exclusions for row in rows) else Status.VALIDATED,
        quality_status=Status.PARTIAL, reasons=("legacy_original_part_query_base_timestamps_unrecoverable",
        "query_coverage_unknown", "source_completeness_unknown", "real_world_completeness_unknown",
        "freshness_policy_not_defined", "normalization_not_implemented"))
    canonical = {"builder_version": BUILDER_VERSION, "source_id": "osm", "dataset_id": dataset_id,
        "scope_id": scope_id, "snapshot_id": snapshot_id, "extent": extent.model_dump(),
        "legacy_snapshot_fetched_at": payload.get("snapshot_fetched_at"),
        "quality": quality.model_dump(mode="json"), "observations": [row.model_dump(mode="json") for row in rows]}
    return BuildResult(canonical=canonical, canonical_checksum=checksum(canonical_bytes(canonical)),
        observations=rows, quality=quality, report={"legacy": True, "input_checksum": digest,
        "observation_count": len(rows), "eligible_count": sum(row.eligible for row in rows),
        "quality": quality.model_dump(mode="json")})
