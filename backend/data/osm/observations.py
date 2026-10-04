"""Shared name-independent raw eligibility; no component grouping/scoring."""

import math

from data.osm.contracts import Extent, Observation, SourceReference


def observation(element: dict, *, dataset_id: str, scope_id: str, snapshot_id: str,
                extent: Extent, references: tuple[SourceReference, ...]) -> Observation:
    if not isinstance(element, dict) or not isinstance(element.get("type"), str) or element.get("type") not in {"node", "way", "relation"}:
        raise ValueError("Invalid OSM type")
    identity = element.get("id")
    if type(identity) is not int or identity <= 0:
        raise ValueError("Invalid OSM identity")
    tags = element.get("tags", {})
    if not isinstance(tags, dict) or not all(isinstance(k, str) and
            (isinstance(v, str) or (k == "name" and v is None)) for k, v in tags.items()):
        raise ValueError("OSM tags must be a string mapping")
    category = tags.get("amenity") or tags.get("leisure") or tags.get("highway")
    supported = {"school", "kindergarten", "hospital", "clinic", "park", "bus_stop"}
    category = category if category in supported else None
    exclusions = []
    if category is None:
        exclusions.append("outside_category_scope")
    if element.get("is_synthetic") is not None and element["is_synthetic"] is not False:
        raise ValueError("Synthetic data is not an OSM source observation")
    node = element["type"] == "node"
    coordinate = element if node else element.get("center", {})
    if not isinstance(coordinate, dict):
        coordinate = {}
    lat, lon = coordinate.get("lat"), coordinate.get("lon")
    valid = all(type(v) in (int, float) and math.isfinite(v) for v in (lat, lon))
    valid = valid and -90 <= lat <= 90 and -180 <= lon <= 180
    representation = "node_coordinate" if node else "overpass_center"
    if not valid:
        exclusions.append("invalid_or_missing_coordinate")
        lat = lon = None
        representation = "missing"
    elif not extent.contains(lon, lat):
        exclusions.append("outside_extent")
    limitations = () if node else ("overpass_center_is_not_boundary_or_entrance",)
    name = tags.get("name")
    return Observation(osm_type=element["type"], osm_id=identity,
        name=name if name is not None and name.strip() else None, tags=dict(tags),
        dataset_id=dataset_id, scope_id=scope_id, snapshot_id=snapshot_id,
        source_references=references, coordinate_representation=representation,
        longitude=lon, latitude=lat, category=category, eligible=not exclusions,
        exclusions=tuple(exclusions), limitations=limitations)
