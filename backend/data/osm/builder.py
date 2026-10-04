"""Deterministic offline merge and explicit dataset quality gates."""

from collections import Counter
from pathlib import Path

from data.osm.contracts import (
    BUILDER_VERSION, BuildResult, Manifest, Quality, SourceReference, Status,
    canonical_bytes, checksum,
)
from data.osm.observations import observation
from data.osm.query import load_definition, query_hash, render_query
from data.osm.validation import artifact_path, validate_part


def extent_covered(extent, parts) -> bool:
    """Exact rectangle-union coverage, without a tolerance or sampling policy."""
    if any(not (extent.west <= p.extent.west < p.extent.east <= extent.east and
                extent.south <= p.extent.south < p.extent.north <= extent.north) for p in parts):
        return False
    xs = sorted({extent.west, extent.east, *(v for p in parts for v in (p.extent.west, p.extent.east))})
    ys = sorted({extent.south, extent.north, *(v for p in parts for v in (p.extent.south, p.extent.north))})
    return all(any(p.extent.west <= x1 and x2 <= p.extent.east and
                   p.extent.south <= y1 and y2 <= p.extent.north for p in parts)
               for x1, x2 in zip(xs, xs[1:]) for y1, y2 in zip(ys, ys[1:]))


def build(manifest: Manifest, artifact_root: Path) -> BuildResult:
    """Never fetch, change raw inputs, resolve conflicts or invent provenance."""
    manifest = Manifest.model_validate(manifest)
    reasons = []
    errors = []
    grouped = {}
    expected_definition = load_definition()
    if query_hash(manifest.query_definition, manifest.extent, manifest.requested_as_of) != query_hash(
            expected_definition, manifest.extent, manifest.requested_as_of):
        reasons.append("unrecognized_tracked_query_definition")
    if manifest.query_hash != query_hash(manifest.query_definition, manifest.extent, manifest.requested_as_of):
        reasons.append("dataset_query_hash_mismatch")
    coverage = extent_covered(manifest.extent, manifest.parts)
    if not coverage:
        reasons.append("unknown_or_invalid_query_extent_coverage")
    missing_provenance = False
    bases = set()
    for part in sorted(manifest.parts, key=lambda p: p.part_id):
        if not all((part.fetched_at, part.source_base_timestamp, part.request_reference,
                    part.query_text, part.query_hash, part.artifact_reference, part.artifact_checksum)):
            missing_provenance = True
        if part.source_base_timestamp is not None:
            bases.add(part.source_base_timestamp)
        try:
            if part.query_text != render_query(manifest.query_definition, part.extent, manifest.requested_as_of):
                raise ValueError("Part query text/extent mismatch")
            if part.query_hash != query_hash(manifest.query_definition, part.extent, manifest.requested_as_of):
                raise ValueError("Part query hash mismatch")
            if not part.request_reference:
                raise ValueError("Missing exact request reference")
            request_path = artifact_path(artifact_root, part.request_reference)
            if request_path.read_text(encoding="utf-8") != part.query_text:
                raise ValueError("Exact request artifact mismatch")
            payload, _ = validate_part(part, artifact_root)
            if part.fetched_at is not None and part.fetched_at < part.source_base_timestamp:
                raise ValueError("Fetch timestamp predates the reported source base")
            reference = SourceReference(part_id=part.part_id, artifact_reference=part.artifact_reference,
                artifact_checksum=part.artifact_checksum, source_base_timestamp=part.source_base_timestamp,
                fetched_at=part.fetched_at)
            for element in payload["elements"]:
                if not isinstance(element, dict):
                    raise ValueError("Element is not an OSM object")
                identity = (element.get("type"), element.get("id"))
                if not isinstance(identity[0], str) or identity[0] not in {"node", "way", "relation"} or type(identity[1]) is not int or identity[1] <= 0:
                    raise ValueError("Invalid OSM identity")
                grouped.setdefault(identity, []).append((canonical_bytes(element), element, reference))
        except (ValueError, OSError) as exc:
            errors.append({"part_id": part.part_id, "artifact_reference": part.artifact_reference, "error": str(exc)})
    conflicts = []
    observations = []
    duplicate_count = 0
    for identity, occurrences in sorted(grouped.items()):
        variants = {raw for raw, _, _ in occurrences}
        refs = sorted({canonical_bytes(ref.model_dump(mode="json")): ref for _, _, ref in occurrences}.values(),
                      key=lambda ref: (ref.part_id, ref.artifact_reference or ""))
        if len(variants) > 1:
            conflicts.append({"osm_type": identity[0], "osm_id": identity[1],
                "source_references": [ref.model_dump(mode="json") for ref in refs],
                "payload_checksums": sorted(checksum(raw) for raw in variants)})
            continue
        duplicate_count += len(occurrences) - 1
        try:
            observations.append(observation(occurrences[0][1], dataset_id=manifest.dataset_id,
                scope_id=manifest.scope_id, snapshot_id=manifest.snapshot_id, extent=manifest.extent,
                references=tuple(refs)))
        except ValueError as exc:
            errors.append({"osm_type": identity[0], "osm_id": identity[1], "error": str(exc)})
    if errors:
        reasons.append("failed_or_invalid_parts_or_observations")
    if conflicts:
        reasons.append("conflicting_observations")
    if missing_provenance:
        reasons.append("missing_per_part_provenance")
    temporal = Status.MIXED if len(bases) > 1 else Status.UNKNOWN if missing_provenance or not bases else Status.VALIDATED
    if temporal != Status.VALIDATED:
        reasons.append("mixed_temporal_snapshot" if temporal == Status.MIXED else "unknown_temporal_coherence")
    if manifest.requested_as_of is not None and bases and any(base != manifest.requested_as_of for base in bases):
        reasons.append("requested_as_of_not_verified_by_source_base")
    eligibility_partial = any("invalid_or_missing_coordinate" in row.exclusions for row in observations)
    if eligibility_partial:
        reasons.append("invalid_or_missing_coordinates")
    if manifest.known_limitations:
        reasons.append("declared_collection_limitations")
    quality = Quality(query_completeness_status=Status.VALIDATED if coverage and not errors and
            not any("query" in reason for reason in reasons) else Status.PARTIAL,
        provenance_status=Status.BLOCKED if errors else Status.PARTIAL if missing_provenance else Status.VALIDATED,
        eligibility_status=Status.PARTIAL if eligibility_partial or errors else Status.VALIDATED,
        temporal_status=temporal, quality_status=Status.BLOCKED if reasons else Status.VALIDATED,
        reasons=tuple(sorted(set(reasons + ["freshness_policy_not_defined", "source_completeness_unknown",
            "real_world_completeness_unknown", "normalization_not_implemented"])) ))
    canonical = {"builder_version": BUILDER_VERSION, "source_id": manifest.source_id,
        "dataset_id": manifest.dataset_id, "scope_id": manifest.scope_id, "snapshot_id": manifest.snapshot_id,
        "query_version": manifest.query_version, "query_hash": manifest.query_hash,
        "extent": manifest.extent.model_dump(), "requested_as_of":
            manifest.requested_as_of.isoformat() if manifest.requested_as_of else None,
        "category_scope": sorted(manifest.category_scope), "quality": quality.model_dump(mode="json"),
        "parts": [part.model_dump(mode="json") for part in sorted(manifest.parts, key=lambda p: p.part_id)],
        "observations": [row.model_dump(mode="json") for row in observations]}
    report = {"built_at": manifest.built_at.isoformat() if manifest.built_at else None,
        "builder_version": BUILDER_VERSION, "quality": quality.model_dump(mode="json"),
        "part_errors": errors, "conflicts": conflicts, "duplicate_count": duplicate_count,
        "observation_count": len(observations), "eligible_count": sum(row.eligible for row in observations),
        "exclusions": dict(sorted(Counter(reason for row in observations for reason in row.exclusions).items()))}
    return BuildResult(canonical=canonical, canonical_checksum=checksum(canonical_bytes(canonical)),
        observations=tuple(observations), quality=quality, report=report)
