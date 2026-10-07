"""Explicit offline extraction; never called by an API or automatic bootstrap.

Requires osmium==4.3.1. Takes an already downloaded, checksum-verified Geofabrik
PBF. Retains complete highway/ferry ways, restrictions and referenced node tags.
"""
import argparse
import json
from pathlib import Path

from data.osm.contracts import canonical_bytes, checksum

EXTRACTION_BOUNDS = (92.2, 55.7, 93.4, 56.55)  # west, south, east, north
COVERAGE_BOUNDS = (92.4, 55.8, 93.2, 56.35)  # endpoints; buffer reduces edge effects


def extract(source: Path, output: Path, expected_sha256: str):
    import osmium  # offline preparation dependency, not a backend dependency

    if output.exists():
        raise ValueError("Refusing to overwrite an existing routing snapshot")
    if checksum(source.read_bytes()) != expected_sha256:
        raise ValueError("Downloaded source checksum mismatch")
    west, south, east, north = EXTRACTION_BOUNDS
    nodes = set()
    for node in osmium.FileProcessor(source, osmium.osm.NODE):
        if west <= node.location.lon <= east and south <= node.location.lat <= north:
            nodes.add(node.id)
    ways = set()
    restrictions = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    # No regional location cache: stream source nodes once, then reference IDs.
    with osmium.BackReferenceWriter(output, source, remove_tags=False, relation_depth=2) as writer:
        for obj in osmium.FileProcessor(source, osmium.osm.WAY | osmium.osm.RELATION):
            if obj.is_way():
                if ("highway" in obj.tags or obj.tags.get("route") == "ferry") and any(n.ref in nodes for n in obj.nodes):
                    ways.add(obj.id)
                    writer.add_way(obj)
            elif obj.tags.get("type") == "restriction" and any(m.type == "w" and m.ref in ways for m in obj.members):
                writer.add_relation(obj)
                restrictions += 1
    if not ways or not restrictions:
        raise ValueError("Incomplete road/restriction extraction")
    return {"selected_ways": len(ways), "selected_restrictions": restrictions,
        "extraction_bounds": EXTRACTION_BOUNDS, "endpoint_bounds": COVERAGE_BOUNDS,
        "pbf_sha256": checksum(output.read_bytes()), "bytes": output.stat().st_size,
        "extractor": "pyosmium-4.3.1-complete-ways-backreferences-v1"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    report = extract(args.source, args.output, args.source_sha256)
    report_path = args.output.with_suffix(".extraction.json")
    report_path.write_bytes(canonical_bytes(report))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
