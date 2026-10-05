"""Snapshot-bound park areas, separate from the existing representative POINTs.

Offline reconstruction only. No collection, topology repair or runtime rebuild.
"""
import gzip
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

GEOMETRY_VERSION = "parks-geometry-v1"
GEOMETRY_SNAPSHOT = "parks-geometry-20261005T134520Z"
BASELINE_VERSION = "fresh-20261004T132116Z"
BASELINE_SHA256 = "c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7"
ROOT = Path(__file__).resolve().parents[1] / "fixtures/osm/snapshots" / GEOMETRY_SNAPSHOT
GEOMETRY_SHA256 = "85049095487da93bbfcad03507c8255d86133c9d9e5fd4ef1549316a49d29bc5"
MANIFEST_SHA256 = "899b7fba673614e2fb3330c3e4f812799632179e843666fef8c56f454d79f29a"
RAW_SHA256 = "7c6d6ed63e117374e8133980f48c34b9215caf550e4f734a8ccc7a036d36714a"


class GeometryError(ValueError):
    pass


def coordinates(points):
    result = tuple((p["lon"], p["lat"]) for p in points)
    if any(type(x) not in (int, float) or not math.isfinite(x) for p in result for x in p):
        raise GeometryError("Nonfinite coordinate")
    if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in result):
        raise GeometryError("Coordinate outside WGS84")
    return result


def canonical_ring(points):
    if len(points) < 4 or points[0] != points[-1] or len(set(points[:-1])) < 3:
        raise GeometryError("Unclosed or degenerate ring")
    # Exact source vertices only; normalize orientation/start, never simplify/repair.
    ring = tuple(points[:-1])
    candidates = []
    for oriented in (ring, tuple(reversed(ring))):
        minimum = min(oriented)
        for i, p in enumerate(oriented):
            if p == minimum:
                candidate = oriented[i:] + oriented[:i]
                candidates.append(candidate + (candidate[0],))
    return min(candidates)


def assemble_rings(members):
    closed, segments = [], []
    if len({m["ref"] for m in members}) != len(members):
        raise GeometryError("Duplicate way member")
    for member in sorted(members, key=lambda m: m["ref"]):
        if member["type"] != "way" or not member.get("geometry"):
            raise GeometryError("Missing way member geometry")
        part = coordinates(member["geometry"])
        if len(part) < 2:
            raise GeometryError("Short member")
        if part[0] == part[-1]:
            closed.append(canonical_ring(part))
        else:
            segments.append(part)
    ends = Counter(p for part in segments for p in (part[0], part[-1]))
    if any(n != 2 for n in ends.values()):
        raise GeometryError("Ambiguous or incomplete endpoint graph")
    while segments:
        chain = list(segments.pop(0))
        while chain[0] != chain[-1]:
            matches = [(i, p) for i, p in enumerate(segments) if chain[-1] in (p[0], p[-1])]
            if len(matches) != 1:
                raise GeometryError("Ambiguous ring continuation")
            i, p = matches[0]
            segments.pop(i)
            chain.extend(p[1:] if p[0] == chain[-1] else tuple(reversed(p))[1:])
        closed.append(canonical_ring(tuple(chain)))
    return tuple(sorted(closed))


def inside_ring(point, ring):
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def reconstruct(element):
    """Reject incomplete/ambiguous topology; PostGIS validates the final shape."""
    kind = element["type"]
    if kind == "node":
        return {"type": "Point", "coordinates": coordinates((element,))[0]}
    if kind == "way":
        ring = canonical_ring(coordinates(element["geometry"]))
        if len(element["nodes"]) != len(element["geometry"]) or element["nodes"][0] != element["nodes"][-1]:
            raise GeometryError("Way node/geometry mismatch")
        return {"type": "Polygon", "coordinates": (ring,)}
    if kind != "relation" or element["tags"].get("type") != "multipolygon":
        raise GeometryError("Unsupported area type")
    members = element["members"]
    if any(m["role"] not in ("outer", "inner") for m in members):
        raise GeometryError("Unsupported member role")
    outers = assemble_rings([m for m in members if m["role"] == "outer"])
    inners = assemble_rings([m for m in members if m["role"] == "inner"])
    if not outers:
        raise GeometryError("Missing outer ring")
    polygons = [[outer] for outer in outers]
    for inner in inners:
        owners = [i for i, outer in enumerate(outers) if inside_ring(inner[0], outer)]
        if len(owners) != 1:
            raise GeometryError("Hole requires exactly one outer")
        polygons[owners[0]].append(inner)
    return {"type": "MultiPolygon", "coordinates": polygons}


@dataclass(frozen=True)
class LoadedGeometry:
    manifest: dict
    features: tuple[dict, ...]
    checksum: str


def read_geometry(root=ROOT):
    """Exact frozen byte pins; no dependency on ignored research files."""
    try:
        manifest_bytes = (Path(root) / "manifest.json").read_bytes()
        raw = gzip.decompress((Path(root) / "canonical.json.gz").read_bytes())
        if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256 or hashlib.sha256(raw).hexdigest() != GEOMETRY_SHA256:
            raise GeometryError("geometry_checksum_mismatch")
        manifest, data = json.loads(manifest_bytes), json.loads(raw)
        features = data["features"]
        identities = {(f["osm_type"], f["osm_id"]) for f in features}
        if (manifest["geometry_version"] != GEOMETRY_VERSION or manifest["snapshot_id"] != GEOMETRY_SNAPSHOT
                or manifest["baseline_version"] != BASELINE_VERSION or manifest["baseline_checksum"] != BASELINE_SHA256
                or manifest["raw_sha256"] != RAW_SHA256 or manifest["canonical_sha256"] != GEOMETRY_SHA256
                or len(features) != 283 or len(identities) != 283
                or any(f["tags"].get("leisure") != "park" for f in features)):
            raise GeometryError("geometry_contract_mismatch")
        return LoadedGeometry(manifest, tuple(features), GEOMETRY_SHA256)
    except (OSError, EOFError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, GeometryError):
            raise
        raise GeometryError("geometry_unavailable") from exc
