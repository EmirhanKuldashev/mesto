# Parks V1: geometry-aware observed proximity

Internal parallel component only. No integration into `objective-current-v1`,
current MESTO, frontend, public API or ranking.

## Accepted semantics

Territorial proximity to the nearest observed real active OSM `leisure=park`
geometry. A genuine node park is a point. A way is its original closed polygon;
a multipolygon relation is reconstructed from complete outer/inner member rings.
Unnamed destinations and destinations across District borders remain eligible.
No semantic deduplication, representative center, bbox or convex hull fallback.

Spheroid/geodesic minimum distance is computed with
`ST_Distance(point::geography, park::geography, true)` in meters. Inside or on an
area boundary gives zero; outside gives the minimum distance to that geometry.
Holes remain outside. `ST_Covers(geography, geography)` records area containment.
See [PostGIS ST_Distance](https://postgis.net/docs/ST_Distance.html) and
[ST_Covers](https://postgis.net/docs/ST_Covers.html).

## Geometry recovery and temporal contract

The accepted baseline `fresh-20261004T132116Z` has source time
`2026-10-04T13:19:51Z`, 283 parks: 3 nodes, 266 ways, 14 relations;
59 named / 224 unnamed. Its raw response has centers but no park boundaries.

Historical recovery was attempted at the exact source time. Main Overpass
returned HTTP 504, two alternative endpoints timed out. These attempts do not
prove historical geometry is permanently unavailable.

The accepted geometry is a **separate dataset** `osm-park-geometry`, snapshot
`parks-geometry-20261005T134520Z`, source time `2026-10-05T13:45:20Z`.
It was retrieved from `https://overpass-api.de/api/interpreter` by selecting the
283 exact baseline identities and requesting `out meta geom`.
Historical/current options are documented in
[Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL).

This is explicitly **not** geometry recovered at the baseline timestamp.
Boundary changes between the two times cannot be inferred from the old centers.
Evidence and normalization preserve both identities/timestamps. No claim of
historical boundary equivalence is made.

Identity match: 283 recovered, 0 missing, 0 tag changes, 0 unexpected returned
identities. The dataset is scoped to the baseline identity set; new parks outside
that set are not eligible. Separate full-extent census attempts received HTTP 504;
we do not assert there were no new parks across the city.

`way:31959413` retains both `leisure=park` and `landuse=cemetery`, name
"Николаевское кладбище". No manual taxonomy correction/exclusion is made.

## Frozen source and minimal storage

Packaged folder:
`backend/data/fixtures/osm/snapshots/parks-geometry-20261005T134520Z/`

- `raw.json.gz`: exact immutable response, deterministic gzip wrapper.
- `query.txt`: exact request; also embedded in the manifest.
- `canonical.json.gz`: deterministic source shapes, identity/tags/object version/time.
- `manifest.json`: dataset/source/baseline identity, query/version/checksums,
  temporal policy and identity comparison.

Raw response SHA256: `7c6d6ed63e117374e8133980f48c34b9215caf550e4f734a8ccc7a036d36714a`.
Canonical geometry SHA256: `85049095487da93bbfcad03507c8255d86133c9d9e5fd4ef1549316a49d29bc5`.

Storage separates nullable `area_geometry` (Polygon/MultiPolygon for ways/relations)
from `point_location` (genuine nodes only). Existing `POI.location`, `POI.geometry`
and OSM snapshot POINT columns are untouched. No migration or lifecycle mutation
is needed; sealed accepted snapshots remain sealed.

Runtime reads checksum-pinned packaged artifacts and passes shapes to one
materialized SQL batch. It never fetches, rebuilds or requires ignored research
files. Active real baseline membership is joined by OSM type/id and exact baseline
version/checksum. A different active snapshot fails closed until separately
reviewed geometry is available; old geometry is never silently applied to it.

## Reconstruction and validation

Source vertices only. Ring assembly joins exact endpoints, permits reversed member
directions, normalizes start/orientation deterministically and preserves holes.
Missing members, unsupported roles, ambiguous endpoint graphs, orphan holes,
unclosed/degenerate rings and invalid coordinates are rejected.
No topology repair (`ST_MakeValid`), simplification or synthetic replacement.

All 283 recovered objects reconstructed reproducibly: 3 Point, 266 Polygon,
14 MultiPolygon; 0 invalid, 0 empty, 0 missing. The 14 real relations have outer
members only; split-ring and inner-hole behavior is separately tested with fixtures.
`ST_IsValid` runs on all shapes in real PostGIS and again in the runtime batch.

## Sampling and frozen normalization

Versions: `parks-evidence-v1`, `parks-osm-eligibility-v1`,
`parks-district-territorial-grid250-v1`, `parks-krasnoyarsk-relative-v1`;
geometry contract `parks-geometry-v1`.

Validated territorial grid250: EPSG:32646, centers `(250*i+125,250*j+125)`,
original District polygon `ST_Covers`, equal weights. N=6065.
Reference: `parks-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-geometry-cdf-v1`.
Reference file SHA256: `db3ba8ccedb1ff83c5c34fdca3346c48dd02c75260e6c448d155a39271a15fec`.
Distribution SHA256: `1ce2594e12ee487bd7f0fd62f4c76237487ccc915fbc6c00023addef9a4b78a8`.

```text
L(d) = count(ref < d)
U(d) = count(ref <= d)
F(d) = (L(d) + U(d)) / (2N)
u(d) = 100 * (1 - F(d))
District score = mean(u(d_i))
```

171 zero distances form an ordinary tie group; no zero-distance bonus, subtype
weight, interpolation, dynamic refit or seven-District min/max. The city-wide mean
of reference point utilities is 50. Corrupt/version-mismatched reference or
geometry, unavailable/partial evidence, unsupported geometry/sampling domain
produce null/unavailable with a reason, never a fabricated zero score.

Raw explanation retains N/valid/missing, median/p90, C500/C1000/C1500.
`share_inside_park_geometry` is the share of valid samples with distance zero,
including boundaries and an exact genuine-node coincidence if one occurs.
It is not the share of the city land area or population located inside parks.

| District | Score | N | Median m | p90 m | C500 | C1000 | C1500 | Share inside |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| osm-centralny | 54.58 | 553 | 741.95 | 2393.12 | 35.99% | 63.47% | 74.68% | 1.08% |
| osm-kirovsky | 68.75 | 376 | 468.84 | 1053.56 | 54.26% | 86.44% | 99.73% | 4.26% |
| osm-leninsky | 56.99 | 843 | 687.28 | 1751.37 | 35.11% | 69.16% | 84.82% | 0.95% |
| osm-oktyabrsky | 48.23 | 1461 | 1014.84 | 2399.27 | 27.93% | 49.42% | 66.60% | 1.03% |
| osm-sovetsky | 47.72 | 1437 | 936.10 | 4876.93 | 36.05% | 51.57% | 59.78% | 8.21% |
| osm-sverdlovsky | 38.83 | 1215 | 1489.45 | 3727.95 | 20.74% | 36.63% | 50.12% | 0.49% |
| osm-zheleznodorozhny | 71.97 | 180 | 377.65 | 987.54 | 65.56% | 91.11% | 100.00% | 1.11% |

Two complete canonical batches reproduced identical point coordinates, nearest
identities, source contracts and distances. Initial point batch runtime:
38.375s on disposable local PostGIS; all Districts
use two queries (one grid + one evidence), without N+1. This is not an SLA.

## Honest limitations

The metric does not measure quality, landscaping, safety, entrance access,
walking routes, green area per resident, vegetation quality or population-weighted
provision. OSM completeness/freshness UNKNOWN remain limitations without penalties.
The separate recovery time and fixed baseline identity set are explicit limitations.

Current Stop/School/Kindergarten/Healthcare and objective-current-v1 remain
unchanged. Next integration stage is OBJECTIVE MESTO V2, not part of this task.
