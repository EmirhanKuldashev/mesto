# Krasnoyarsk OpenStreetMap snapshot

These district boundaries and points of interest were retrieved on 2026-09-27
from OpenStreetMap through Nominatim and Overpass API. Both JSON files are
OpenStreetMap data, available under the Open Database License (ODbL):
https://www.openstreetmap.org/copyright

Attribution: ? OpenStreetMap contributors.

The snapshot contains seven administrative district boundaries and 1,988
named schools, kindergartens, clinics, hospitals, parks, and bus stops.
The importer retains source IDs and fetch timestamps and assigns a POI
to a district only when one boundary covers it. It does not contain
property prices, listings, travel times, or future development plans.

## Historical provenance limitation

The merged POI artifact preserves an aggregate `snapshot_fetched_at`, but not
the exact original part queries/extents or per-observation source base times.
Foundation V1 therefore marks it as partial provenance with unknown query and
temporal coherence. The aggregate fetch time is not assigned as an observation's
OSM source base timestamp. No fresh snapshot was collected for Foundation V1.
See [the shared foundation contract](../../../../docs/osm-data-foundation.md).
