# Stop Availability: canonical raw evidence V1

Meaning: **distance to the nearest observed eligible OSM `highway=bus_stop`
observation in the active dataset**. This is objective, user-independent raw
evidence. It does not measure transport accessibility, route usability, frequency,
travel time or walking distance. Current `objective-current-v1`, Transport,
Infrastructure, MESTO, Match and ranking are unchanged. No public API is added.

## Code Map and separation

| Path | Responsibility |
| --- | --- |
| `backend/app/analytics/stop_availability/models.py` | Immutable internal point, identity, coverage and summary contracts |
| `backend/app/analytics/stop_availability/service.py` | Canonical point/batch spatial primitive over active OSM bindings |
| `backend/app/analytics/stop_availability/aggregation.py` | Pure median, p90 and coverage aggregation |
| `backend/app/analytics/stop_availability/research.py` | Explicit RESEARCH_ONLY administrative grid500 consumer |
| `backend/tests/test_stop_availability.py` | Isolation, borders, ties, nulls, distribution and seven-district research regressions |

The component lives alongside the existing analytics code, reuses PostgreSQL /
PostGIS and OSM lifecycle tables, and is not called by the current scoring service.
OSM source payload remains in the foundation; component outputs copy only source
identity, compact quality state and the explanatory nearest stop identity/name.
There is no new storage schema, source collection, data mutation or migration.

## Versions and input

- Evidence: `stop-availability-evidence-v1`.
- Component eligibility: `osm-highway-bus-stop-v1`.
- Distance method: `postgis-geography-wgs84-spheroid-v1`.
- Research sampling: `admin-grid-500-v1` (separate from evidence methodology).
- Foundation eligibility and query version/hash are reported where available.
- No normalization version, 0–100 score, weights or MESTO contribution exists.

```python
from app.analytics.stop_availability.models import Coordinate
from app.analytics.stop_availability.service import StopAvailabilityService
from app.analytics.stop_availability.aggregation import summarize

service = StopAvailabilityService(session, scope_id="krasnoyarsk")
point = service.point(Coordinate(longitude=92.85, latitude=56.01))
points = service.points(sample_coordinates)
summary = summarize(points, sampling_version="caller-sampling-v1", radii_m=(500, 1000))
```

Input is WGS84 longitude followed by latitude. The source scope is explicit and
selects one OSM dataset, independently of district IDs. This primitive is reusable
for any coordinate, future local areas or residential complexes. It needs neither
District ORM nor a user profile. Samples have equal weight; repeated coordinates
are retained as supplied, so the caller owns sample selection and weighting.

## Eligibility and lifecycle

The query follows `osm_datasets.active_snapshot_id`, requires that snapshot's
`ACTIVE` status, and joins its `osm_active_pois` bindings to current `pois` and
the matching immutable observation identity. Requirements: real OSM
`source_id='osm'`, `is_synthetic=false`, eligible observation, original
`tags.highway='bus_stop'`, nonempty `POI.location` with SRID 4326. `geometry` and
name are not required. One `(osm_type, osm_id)` is one source observation.

Standalone platforms, stations, tram stops, rail and GTFS are not added.
Nearby/same-name/opposite-direction observations are not semantically grouped.
Retired/candidate history, unmanaged POIs, other sources/scopes and synthetic
POIs cannot enter the search. District ownership, including `district_id=NULL`,
does not constrain eligibility. A stop in district B may be nearest to a sample
inside district A. The dataset's collection extent still limits available evidence;
no observations are fetched beyond it by this component.

## Point output and unavailable states

Point evidence contains coordinate, evidence/eligibility/distance versions,
dataset key/source/scope, snapshot version/checksum, query identity and foundation
eligibility identity, source quality, eligible dataset stop count, availability,
nearest `(osm_type, osm_id)`, nullable name, distance in meters and limitations.
The count is a secondary source diagnostic, not a route count or primary metric.

`AVAILABLE` means an observed distance was computed. It does not assert complete
OSM or real-world coverage. Source quality is copied honestly, including UNKNOWN
freshness/source/real-world completeness. Unavailable evidence has `nearest_stop=null`
and an explicit reason: `invalid_coordinate`, `dataset_unavailable`, or
`no_eligible_observations`. Invalid ranges are retained as input; malformed,
boolean, missing and nonfinite ordinates become null to keep output JSON safe.
Invalid coordinates never reach a PostGIS geography operation.

Zero distance is valid only for a known stop at the exact coordinate. Missing
evidence never becomes zero distance, zero score, or a fabricated stop.

## Distance and deterministic query

Canonical method is `ST_Distance(input::geography, POI.location::geography, true)`:
straight-line geodesic meters on the WGS84 spheroid, with spheroid use explicit.
EPSG:4326 degree distance and projected grid distance are not substituted.
Search evaluates every eligible stop in the selected active scope; there is no
approximate KNN preselection or geographic radius cutoff.

One SQL statement handles a batch: materialized active metadata and eligible stop
geographies, JSONB input points and a LATERAL exact nearest search. Metadata,
active pointer and stop results share the statement's MVCC snapshot even if a
later transaction activates a new dataset. Ties at the exact DB distance use
`osm_type COLLATE "C", osm_id`, independently of POI row IDs or input row order.
No fuzzy tie tolerance is introduced.

With 1,360 stops / 1,523 research points the deliberate exhaustive search evaluates
about 2.07 million distances on the DB server. This uses existing identity/binding
indexes to select active evidence, not the geometry GiST index for degree KNN.
There is one DB round trip for the point batch; research adds one grid statement.
No per-point network round trip, new index or national-scale infrastructure.

## Aggregation

`summarize` accepts point evidence and an explicit caller sampling version. Mixing
snapshot identities or source quality states raises an error. Distances are sorted;
median and p90 use continuous linear interpolation at `(N-1)*q`, equivalent to
PostgreSQL `percentile_cont`, without intermediate display rounding.

For finite nonnegative configurable radii, sorted/deduplicated into a curve:

`C(R) = count(valid samples with nearest distance <= R) / valid_evidence_count`.

Default radii are 500 and 1000 meters. Coverage shares are in [0,1]; multiply by
100 only for percentage display. Every curve point reports integer numerator and
valid denominator. Missing samples are excluded from both, counted separately,
and broken down by reason. Mixed availability yields `PARTIAL`. Empty/all-missing
samples yield `UNAVAILABLE`, null median/p90/shares and zero valid denominator.
Changing input sample order does not change summary output.

## Administrative grid: RESEARCH_ONLY

`district_research(session, district_ids, scope_id=...)` is a separate consumer.
It uses the existing district `geometry`, falling back to `boundary` if absent.
Missing district/boundary raises an explicit error instead of inventing samples.
Grid centers are globally anchored in **EPSG:32646** at
`(500*i+250, 500*j+250)`, for integer i/j. Centers are transformed to EPSG:4326;
membership uses **ST_Covers on the original WGS84 district polygon**, including
covered boundary points. Sample ordering is deterministic by district/cell i/j.
Separate district memberships are retained when administrative polygons overlap.

This matches the accepted fresh research replay (original local `simulate.py`),
including its continuous percentile and spheroidal distance semantics. Runtime
and tests need only published fixtures, not that ignored helper or raw storage.

| District | N | Median m | P90 m | C500 % | C1000 % |
| --- | ---: | ---: | ---: | ---: | ---: |
| Central | 138 | 440.52 | 1305.23 | 52.90 | 78.99 |
| Kirovsky | 91 | 383.60 | 978.53 | 61.54 | 90.11 |
| Leninsky | 217 | 503.50 | 1255.96 | 49.77 | 81.11 |
| Oktyabrsky | 363 | 520.68 | 1611.77 | 48.21 | 77.13 |
| Sovetsky | 360 | 466.46 | 1498.15 | 52.78 | 78.06 |
| Sverdlovsky | 308 | 636.84 | 2571.37 | 42.53 | 64.29 |
| Zheleznodorozhny | 46 | 244.41 | 687.83 | 82.61 | 100.00 |
| Total | 1523 | | | | |

Regression checks exact sample sizes, integer covered counts, and the accepted
sampling SHA256 `4e5d80adf7de9d5a8bf74198531390daefee987d3f24c1a938aaf928c7082925`.
Unrounded median/p90 references allow only 1e-6 meter absolute floating-point
tolerance; no relative or broad methodology tolerance is used.

The grid includes industrial land, forests and non-residential areas. It is not
population-weighted/residential-weighted sampling or the final District MESTO
basis. Residential complexes are not a district population mask. Stops are
observations, not independent routes; service availability is unmeasured. Source
completeness and real-world completeness remain UNKNOWN.

## Verification and future work

On a disposable migrated PostGIS database with strict integration mode, run
`python -m pytest -q -rs tests/test_stop_availability.py` and the full suite.
Existing packaged-baseline tests independently pin all seven current MESTO /
Infrastructure / Transport regression scores; those formulas and consumers are
unchanged. No tests require OSM collection or an AI API.

This phase stops at raw evidence. Calibration/normalization research and future
Objective MESTO v2 can consume the versioned contracts only after separate review.
There are no good/bad judgments, score thresholds, weights, new frontend flows,
public endpoint, School/Healthcare/Parks components or route analytics here.
