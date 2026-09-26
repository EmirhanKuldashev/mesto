"""Validation of administrative OSM geometry before database import."""

import pytest

from data.loaders.osm_district_loader import as_multipolygon, validate_record


def test_polygon_is_normalized_without_changing_the_rings():
    ring = [[92.8, 56.0], [92.9, 56.0], [92.9, 56.1], [92.8, 56.0]]
    assert as_multipolygon({"type": "Polygon", "coordinates": [ring]}) == {
        "type": "MultiPolygon", "coordinates": [[ring]],
    }


def test_only_known_administrative_districts_are_accepted():
    geometry = {"type": "MultiPolygon", "coordinates": [[[[92.8, 56], [92.9, 56], [92.8, 56]]]]}
    valid = {"name": "Центральный", "slug": "centralny", "osm_id": 5854094, "geometry": geometry}
    validate_record(valid)
    for changed in ({"slug": "unknown"}, {"name": "Фантазийный"}, {"osm_id": None},
                    {"geometry": {"type": "Point", "coordinates": [92.8, 56]}}):
        with pytest.raises(ValueError):
            validate_record({**valid, **changed})
