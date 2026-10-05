# School — canonical component evidence V1

## Meaning and scope

`school-evidence-v1` describes **observed school proximity** to an eligible active
OSM observation point. It is objective, user-independent and district-independent.
It does not describe school quality, seats/capacity, enrollment, grades, catchment,
admission eligibility, walking routes, entrances or travel time. Raw evidence remains
separate from the standalone normalized School V1 described below. The accepted
V1 policy deliberately retains all eligible observed amenity=school objects.
No weights, arbitrary meter thresholds or MESTO contribution are introduced.
Current `objective-current-v1` and Stop Availability V1 remain unchanged.

## Eligibility and taxonomy

`school-osm-eligibility-v1` preserves the published canonical `school` category:
`amenity=school`, canonical category `school`, eligible observation with
`osm-poi-eligibility-v1`, active lifecycle binding, `source_id=osm`,
`is_synthetic=false` and usable WGS84 POI `location`.
Projection category must agree. Name is nullable, never an eligibility condition.
Kindergarten, college, university, training, music_school and language_school
**amenity values** are not admitted. `building=school` alone is not sufficient.

Foundation category construction is `amenity or leisure or highway`, followed by
the six-category allowlist. All 205 published school observations actually have
`amenity=school`; the component explicitly tests that criterion. Query selectors
are in `backend/data/osm/query.json`; canonical policy is
`backend/data/osm/observations.py`. No source or canonical policy is changed.

**This is not an audited ordinary/general-education school inventory.** Name/tag
diagnostics identify two music schools (`way:689541328`, `way:946011167`), three
schools of arts (`node:1263652634`, `way:114439520`, `way:689542089`), and a college
name with `building=college` (`way:58788670`) within `amenity=school`.
`way:136858035` has `building=kindergarten` but `amenity=school` and no name.
One boarding school is operated by a university; seven names mention boarding.
These are explicit taxonomy ambiguities, not grounds for an invented name filter.
They stay in the accepted observed-tag set. An ordinary-school-only component would
require taxonomy review; this V1 explicitly normalizes observed amenity=school
proximity instead. UNKNOWN rows must not be silently removed.

## Point contract and source quality

`SchoolAvailabilityService(session, scope_id=...).point(Coordinate(...))` returns
`PointSchoolAvailabilityEvidence`. `points(...)` evaluates an ordered batch.
The coordinate has no district/profile dependency. Evidence includes versions,
snapshot identity/checksum/query policy, source quality, eligible observation
count and nearest `osm_type`, `osm_id`, nullable name, representation and meters.
It does not copy full tags/payload into point results.

Available evidence requires the known foundation policy/query metadata and
VALIDATED quality, provenance, query completeness, eligibility and temporal
statuses. UNKNOWN freshness/source completeness/real-world completeness remain
visible limitations; they are neither zero evidence nor penalties. Foundation
`normalized_score_status=BLOCKED` is retained on the foundation/raw contract. It is
not the readiness status of the separately approved normalized School component.

Unavailable reasons are `invalid_coordinate`, `dataset_unavailable`,
`no_eligible_observations` and `version_quality_failure`. Nearest observation and
distance are null on failure. Legitimate coordinate coincidence can yield zero
meters. Empty batches return empty results without SQL.

## Representation and distance

Node coordinates are `node_coordinate`; ways/relations use `overpass_center`.
Canonical POI `location` is the distance target. `geometry` is not required;
all 205 fresh schools currently have NULL geometry and usable locations.
School center distance is not school entrance or boundary distance. Original
polygons, entrance nodes and campus membership are not reconstructed here.

Distance method: `postgis-geography-wgs84-spheroid-v1`:
`ST_Distance(input::geography, poi.location::geography, true)`.
No degree-distance, approximate KNN shortlist or walking-network calculation.
Exact distance ties sort by `osm_type COLLATE "C"`, then numeric `osm_id`.

Search covers all eligible observations of the chosen active scope. District
ownership does not restrict search: adjacent-district and `district_id=NULL`
observations may be nearest. Dataset extent still limits available observations.

## Lifecycle and performance

One MVCC statement reads `osm_datasets.active_snapshot_id`, ACTIVE snapshot,
`osm_active_pois` and matching `osm_snapshot_observations`. Synthetic, other-source,
unmanaged POIs, candidate/retired history and other scopes cannot enter results.
The eligible set is materialized once per batch; exact spheroid distances are
evaluated in SQL. Primary batches retain one nearest observation; the separate
`diagnostics(...)` contract returns at most three, marked `DIAGNOSTIC_ONLY`.

Measured local research: **2 SQL statements, 6065 points, 4.057630 seconds** for
grid plus d1/d2/d3 evaluation and Python aggregation on PostgreSQL 16/PostGIS 3.4.
Named-only and duplicate counterfactuals add two diagnostic SQL statements outside
that measured component call. This is a runtime observation, not a latency SLA.

## Aggregation and research grid

`summarize(points, sampling_version=..., radii_m=...)` returns raw School summary:
versions, snapshot/quality, sample/valid/missing counts, missing reasons, median,
p90 and coverage curve. Different snapshots or quality states are rejected.
Samples have equal weight, including deliberate repeats. Quantiles use the shared
linear `(N-1)*q` interpolation equivalent to PostgreSQL `percentile_cont`.

`C(R) = count(valid nearest distance <= R) / valid_evidence_count`.
Missing evidence is excluded from the denominator and counted explicitly. Empty
or fully unavailable samples have null median/p90/coverage. Coverage is monotonic;
the radius boundary is inclusive. R=500/1000/1500 are diagnostics, not policy
thresholds or score parameters.

School `district_research` reuses the existing accepted grid250 generator strictly
as **RESEARCH_USE_FOR_SCHOOL**, version `school-research-territorial-grid250-v1`.
It uses Stop reference metadata only for polygon/grid identity checks, never its
distances/CDF. This historical research consumer stays research-only. The new
School District V1 sampler separately adopts the reviewed grid pattern as
`school-district-territorial-grid250-v1`, with its own School reference metadata. UTM46N fixed centers `250*x+125`, `250*y+125`, original WGS84
polygon `ST_Covers`, reviewed seven real OSM polygons; grid outside that domain
fails explicitly. Administrative territory includes forest, industry and vacant
land: this is not resident/child/population-weighted accessibility.

## Published baseline audit

Baseline: `fresh-20261004T132116Z`, canonical checksum
`c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7`.

205 eligible observations: 160 named, 45 unnamed; 3 nodes, 182 ways, 20 relations.
Representations: 3 node coordinates, 202 centers. Identity duplicates: 0; missing
locations: 0; geometry present: 0. Complete retained tags are available in
`POI.metadata.osm_foundation.tags` and immutable snapshot observation JSON.
All 205 have amenity=school; education=school appears on 170. Capacity/enrollment/
catchment data are not established. Names and heterogeneous optional tags do not
reliably distinguish ordinary from specialized schools.

Assignment: Central 14, Kirov 22, Lenin 27, Oktyabr 26, Sovet 47, Sverdlov 26,
Zheleznodorozhny 15, unassigned 28. Assignment is descriptive only.

## Duplication and k-nearest diagnostics

No exact coordinate duplicate pairs. Geodesic single-link connected components
at <=50m: 5 clusters (10 identities). At <=100m: 10 clusters (21 identities),
11 close pairs. Five 100m clusters mix relation/way representations. Same
trimmed/lowercase name: 8 pairs. Near coordinates or equal names do not prove
one physical school; no semantic deduplication is performed.

An explicitly diagnostic counterfactual retaining lexical-first identity per
100m cluster removes 11 observations. It changes d1 at 67/6065 points; maximum
increase 81.552100m. This is sensitivity, **not an approved dedup rule**. Effects
are not confined to counts: center representations can alter nearest distance.
Counts and d2/d3 are especially vulnerable and cannot represent seats or schools.

Top3 contains two identities in the same possible 100m campus cluster at 283/6065
points. Median d2-d1 gaps range 158.63–276.04m; d3-d1 337.52–632.03m across
districts. Additional distances may describe observed spatial alternatives, but
independent school choice/redundancy is unvalidated without semantic grouping.

## Seven-district raw regression

Calculated first, then recorded with full float precision and integer coverage
counts in `backend/data/fixtures/analytics/school-grid250-raw-research-v1.json`.
These are raw regression values, not desired outcomes or calibration anchors.
Below, meters/percentages are rounded only for display.

| District | N | Median m | p90 m | C500 % | C1000 % | C1500 % |
|---|---:|---:|---:|---:|---:|---:|
| Central | 553 | 782.12 | 1722.83 | 26.40 | 65.28 | 83.73 |
| Kirov | 376 | 684.48 | 2141.09 | 39.63 | 63.56 | 77.66 |
| Lenin | 843 | 895.95 | 1827.17 | 25.27 | 55.52 | 81.49 |
| Oktyabr | 1461 | 1598.04 | 4755.04 | 14.65 | 32.92 | 47.36 |
| Sovet | 1437 | 1417.05 | 6392.56 | 23.94 | 40.57 | 52.54 |
| Sverdlov | 1215 | 1774.74 | 4371.60 | 16.13 | 33.91 | 44.61 |
| Zheleznodorozhny | 180 | 440.25 | 962.44 | 56.11 | 91.11 | 100.00 |

### Named-only sensitivity (diagnostic, never eligibility)

Nearest identity changes at 1091/6065 points (17.99%).

| District | Median increase m | p90 increase m | C500 change pp | C1000 change pp |
|---|---:|---:|---:|---:|
| Central | 370.77 | 561.73 | -11.21 | -23.51 |
| Kirov | 134.44 | 0.00 | -4.79 | -5.05 |
| Lenin | 107.81 | 295.45 | -1.90 | -5.93 |
| Oktyabr | 5.82 | 0.00 | -1.03 | -0.89 |
| Sovet | 41.36 | 170.41 | -2.09 | -2.02 |
| Sverdlov | 287.42 | 90.43 | -3.79 | -6.91 |
| Zheleznodorozhny | 107.94 | 109.80 | -11.67 | -5.56 |

RC comparison is not used: isolated baseline/test fixtures have zero real RC
locations. Production RC data was not imported. Legacy spatial comparison is not
used; historical input lacks the fresh validated query/provenance contract. Fresh
remains the sole primary baseline. No collection, activation or baseline switch.

## Data quality verdict and future questions

- Taxonomy: READY for the exact observed `amenity=school` contract; ordinary-school
  semantics BLOCKED pending explicit taxonomy review of specialized/ambiguous rows.
- Nearest-distance evidence: READY for canonical observation points. Real-world
  completeness is UNKNOWN, not independently validated. 202 center targets may
  distort entrance/boundary proximity; magnitude cannot be established from current
  location-only data. There is no evidence for entrance accessibility guarantees.
- Normalized observed-school-proximity V1: approved under the explicit proxy
  semantics and territorial grid250 policy below. It makes no ordinary-school-only,
  capacity, admission or quality claim. Ordinary-only taxonomy remains review-required.

Questions: ordinary vs specialized schools; center/entrance semantics; semantic
campus grouping; appropriate residential/territorial sampling and completeness;
whether d2/d3 can describe independent choices. These remain questions for future
product methodology; they are limitations of the deliberately accepted V1 proxy.

## Code Map and verification

- `backend/app/analytics/school/models.py`: immutable raw and diagnostic contracts.
- `service.py`: active scope point/batch nearest search, explicit unavailable states.
- `aggregation.py`: raw quantiles and valid-only coverage.
- `research.py`: separate grid250 research consumer; no School production sampler.
- `backend/tests/test_school.py`: offline real PostGIS point/lifecycle/border/
  taxonomy/representation/aggregation tests and seven-district regression.
- `backend/data/fixtures/analytics/school-grid250-raw-research-v1.json`: minimal
  calculated raw regression artifact; existing package-data includes analytics JSON.

Reused lower-level primitives: Coordinate, SnapshotIdentity, EvidenceModel,
CoveragePoint and distance version; shared continuous-quantile helper. These live
in the existing Stop module; School never calls StopAvailabilityService. No broad
refactor or changes to published Stop files. Research-only grid reuse is explicit.
Full per-point results, audits, counterfactuals and scripts stay in ignored
`backend/data/raw/research/school-evidence-v1-20261005/`.
No migration, public endpoint, frontend, ranking or current scoring changes.


## Standalone normalized School V1 — accepted proxy semantics

Meaning: average relative territorial proximity to observed active real OSM
amenity=school observations, compared with a frozen Krasnoyarsk territorial School
reference. It does not mean school quality out of 100 or percent school provision.
Music/art/college-looking objects remain eligible when their published canonical
source contract is amenity=school. Name remains nullable; no semantic deduplication.

Versions:

- Evidence: `school-evidence-v1`; eligibility: `school-osm-eligibility-v1`.
- Sampling: `school-district-territorial-grid250-v1`.
- Normalization: `school-krasnoyarsk-relative-v1`.
- Distance: `postgis-geography-wgs84-spheroid-v1`.

District sampling uses EPSG:32646 centers `(250*i+125,250*j+125)` and
`ST_Covers(original WGS84 polygon, point)`. The SQL grid primitive is reused without
changing Stop Availability. School checks its own packaged geometry identities,
real OSM geometry validity and exact reviewed sample counts: 553/376/843/1461/
1437/1215/180 (6065 total). The smallest reviewed District has 180 samples; this is
an existing domain boundary, not a population law. Missing/changed/synthetic or
unreviewed polygons fail closed. Boundary fallback is accepted only if it matches
that exact reviewed polygon identity. Forest/industrial/vacant territory contributes
with equal point weight. No population, residential or child weighting is claimed.

### Frozen School reference

Reference ID:
`school-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-center-cdf-v1`.
City/scope: Krasnoyarsk / krasnoyarsk. Snapshot: `fresh-20261004T132116Z`.
N=6065. The complete coordinate/OSM identity/nearest distance evidence reproduced
point-for-point against the published raw research outputs; DB surrogate District
IDs are excluded from that comparison because they vary across disposable DBs.

Values SHA256:
`6f5c6dcb4dcc457fee86dfc628f433a013d50fb58526786b0990712ef6a00037`.
Packaged artifact SHA256:
`b39783e4e579a0c7b800ac838cd93a7777835ddf04181d8b57d0e35b2fd662dc`.
Artifact: `backend/data/fixtures/analytics/school-krasnoyarsk-relative-v1.json`,
83,738 bytes, sorted School distance distribution plus minimum version/snapshot/
geometry metadata and limitations. The existing analytics package-data includes it.
Stop reference values are not used. Runtime does not require ignored research files.
Checksum failure/unavailable artifact returns null with an explicit reason; runtime
never regenerates reference. Source refresh does not refit or replace calibration.

### Exact formula

```text
N = 6065
L(d) = count(reference < d)
U(d) = count(reference <= d)
F_ref(d) = (L(d) + U(d)) / (2N)
u(d) = 100 * (1 - F_ref(d))
District score = arithmetic mean(u(d_i))
```

Midrank empirical CDF, without interpolation or rounding in calculation. Equal
matches are deterministic; lower distance cannot reduce utility. No p90 weighting,
seven-district min/max, dynamic refit, arbitrary distance thresholds or legacy
Infrastructure fit. The full equally weighted reference reproduces mean utility 50.

### Pipeline, raw explanations and null policy

`PointNormalizer` consumes existing canonical School evidence; it never queries POIs.
`DistrictSchoolAvailabilityService` uses one grid statement and one School batch
statement for all reviewed Districts, then pure normalization and arithmetic mean.
Every selected point must be available, version/quality valid and coordinate-paired;
partial evidence does not produce a score. UNKNOWN completeness/freshness remains
visible and does not penalize values. Output retains N, median, p90, C500, C1000,
C1500, source snapshot/quality and limitations. Radius coverage is raw explanation,
not a normalization threshold. Missing/invalid reference, source, geometry, sampling,
evidence or versions yield score=null with explicit reason, never fake score 0.

### Multi-city and refresh behavior

This is **Krasnoyarsk-relative V1**. Point normalization requires Krasnoyarsk OSM
scope; District geometry domain is the reviewed seven polygons. Other city/scope
inputs fail with explicit unavailable state. A future city needs separate reviewed
reference/version/domain; it cannot silently enter this reference. A future active
Krasnoyarsk snapshot can be evaluated against the unchanged frozen School reference
when its canonical evidence/quality contract remains valid. No bootstrap recalibration.

### Deterministic District results

| District | Score | N | Median m | p90 m | C500 % | C1000 % | C1500 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| Central | 63.05 | 553 | 782.12 | 1722.83 | 26.40 | 65.28 | 83.73 |
| Kirov | 65.12 | 376 | 684.48 | 2141.09 | 39.63 | 63.56 | 77.66 |
| Lenin | 60.56 | 843 | 895.95 | 1827.17 | 25.27 | 55.52 | 81.49 |
| Oktyabr | 42.59 | 1461 | 1598.04 | 4755.04 | 14.65 | 32.92 | 47.36 |
| Sovet | 44.78 | 1437 | 1417.05 | 6392.56 | 23.94 | 40.57 | 52.54 |
| Sverdlov | 42.89 | 1215 | 1774.74 | 4371.60 | 16.13 | 33.91 | 44.61 |
| Zheleznodorozhny | 78.70 | 180 | 440.25 | 962.44 | 56.11 | 91.11 | 100.00 |

All raw regressions are preserved; displayed rounding is not used in calculation.
Current MESTO scoring, Stop Availability, APIs, frontend and migrations are unchanged.

### Additional Code Map

- `backend/app/analytics/school/reference.py`: pinned School-only runtime calibration.
- `normalization.py`: pure point CDF and version/source/scope/quality gates.
- `sampling.py`: separately versioned School District grid250 and geometry checks.
- `district.py`: normalized District value paired with raw School explanations.
- `backend/tests/test_school_normalization.py`: calibration, null, scope, exact
  seven-district regression, batch query count and current MESTO invariance tests.
