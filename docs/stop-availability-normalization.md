# Stop Availability: frozen Krasnoyarsk-relative V1

Internal component, parallel to `objective-current-v1`. It measures **average
relative proximity of sampled administrative-territory points to observed
eligible OSM highway=bus_stop observations**, compared with a frozen Krasnoyarsk
territorial reference. It is not transport/service/route quality, walking time,
resident experience, worst-tail accessibility or a universal cross-city score.
No public API, frontend, migration or current MESTO integration is introduced.

## Separate versions and Code Map

| Version | Responsibility |
| --- | --- |
| `stop-availability-evidence-v1` | Canonical raw coordinate evidence |
| `osm-highway-bus-stop-v1` | Stop eligibility, including unnamed observations |
| `postgis-geography-wgs84-spheroid-v1` | Exact straight-line distance in meters |
| `district-territorial-grid250-v1` | Approved District territorial sampling |
| `stop-availability-krasnoyarsk-relative-v1` | Frozen relative normalization |
| `objective-current-v1` | Existing production MESTO scoring, unchanged |

| Path | Responsibility |
| --- | --- |
| `backend/app/analytics/stop_availability/service.py` | Existing raw evidence owner; one SQL statement per batch |
| `backend/app/analytics/stop_availability/aggregation.py` | Existing median/p90/configurable raw coverage |
| `backend/app/analytics/stop_availability/reference.py` | Immutable calibration contract, pinned bytes/digest verification; no regeneration |
| `backend/app/analytics/stop_availability/normalization.py` | Pure reusable point utility and normalized point contract; no DB/ORM dependency |
| `backend/app/analytics/stop_availability/sampling.py` | Fixed grid250, validated geometry/domain, deterministic membership |
| `backend/app/analytics/stop_availability/district.py` | Internal batch orchestration, strict gates, equal point mean paired with raw summary |
| `backend/data/fixtures/analytics/stop-availability-krasnoyarsk-relative-v1.json` | Minimal packaged reference distribution and reviewed identity/specification |
| `backend/tests/test_stop_availability_normalization.py` | Frozen-CDF properties, failure gates, real PostGIS seven-district and invariance regressions |

The original `research.py` / `admin-grid-500-v1` remains explicitly RESEARCH_ONLY,
with its original grid500 regression intact. No broad analytics refactor.

## Frozen reference

- Reference ID: `research-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-center-cdf-v1`.
- City/scope: Krasnoyarsk / `krasnoyarsk`.
- Snapshot: `fresh-20261004T132116Z`, 1360 eligible stops.
- Source canonical SHA256: `c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7`.
- Reference: **6065** fixed center-grid250 territorial distances, equal point weights.
- Values SHA256: `e4c08d4d7d63d83f56343db867f9285ccfc4ac0ccfa50cbf2eb703dfdca7d535`.
- Packaged whole-file SHA256: `8a0ac0adfde9d4f1f3f33d630bb8bcab0a64d81cd9d7e1a5580343c441452cb5`, pinned outside the artifact.
- Geometry fixture SHA256: `7ac78515978087c0ba0272eaa427731473ee63421019eb962aa7e449c18e37a2`.

The packaged contract includes original snapshot/query/eligibility identity,
all sorted reference values, geometry EWKB identities and per-district counts,
CDF method, limitations, and links by checksum to the accepted research artifact.
Reference values are copied exactly from accepted research, not regenerated from
the current DB. The ignored research folder is not a runtime/test dependency.
Setuptools package data and the existing Docker fixture copy include the artifact.
Checksum/contract failure is explicit unavailable; no silent refit or fallback.

## Exact empirical CDF and endpoints

For fixed sorted reference values `r[0..N-1]`, `N=6065`, distance `d >= 0`:

```text
L(d) = count(r < d)       = bisect_left(r, d)
U(d) = count(r <= d)      = bisect_right(r, d)
F_ref(d) = (L(d) + U(d)) / (2*N)
u(d) = 100 * (1 - F_ref(d))
District score = arithmetic mean of u(d_i) for ALL selected available points
```

This is the exact research **midrank empirical CDF**: an equal reference-distance
tie receives the midpoint of its tie-group CDF jump. No linear interpolation
between reference distances. Gaps have constant utility; equal distances have
equal values. Counts are nondecreasing with distance, so utility is deterministic,
non-increasing, bounded [0,100]. An equal nonnegative-weight mean preserves these
properties. Calculation uses full precision and `statistics.mean`, independent
of point order; display rounding only, normally two decimal places.

Point utility100 means distance below the smallest reference value; point utility0
means distance above the largest reference value. At the exact empirical minimum
utility is below100; at the exact maximum it is above0 because of midrank ties.
District100/0 would require every selected point to have the corresponding
endpoint utility. Best/worst current districts are not forced to100/0.
These endpoints do not mean perfect/no transport.

## Sampling and validated domain

Grid CRS EPSG:32646, spacing250m, global origin(0,0), phase(.5,.5), centers
`(250*i+125,250*j+125)` for integer i/j. Transform centers to WGS84 before
`ST_Covers(original district polygon, point)`. Boundary points, including hole
boundaries, are included; hole interiors excluded. Samples are ordered by
district/cell i/j, equally weighted and unique within each district.

Use valid, nonempty SRID4326 MultiPolygon `geometry`, with `boundary` fallback
only when geometry is absent and its identity matches the accepted geometry.
No silent geometry repair. The seven reviewed Krasnoyarsk geometries are the only
approved V1 domain; changed/unknown geometry, synthetic source or another scope
fails closed. Geometry fingerprints and expected sample counts prevent a changed
boundary or sampling recipe silently retaining this version.

The minimum180 is the lower edge of the validated District domain, **not a
universal statistical rule or proof of sample independence**. Coordinates reuse
the point normalizer without this minimum. Small LocalArea sampling and new-city
geometries require separate validation; they must not inherit District rules.

Nearest-stop lookup is owned solely by StopAvailabilityService, across the active
eligible dataset, not restricted by District boundary/POI ownership. Names do not
gate eligibility. One grid SQL query plus one canonical evidence batch serve all
seven districts (6065 points), with no per-point DB round trip. Normalization and
aggregation run in memory. This does not establish an interactive latency SLA.

## Quality and unavailable behavior

The component requires the pinned reference, expected evidence/eligibility/distance
and sampling versions, accepted geometry/domain and minimum180, an active source,
and **ALL** selected canonical evidence AVAILABLE. Query completeness, provenance,
eligibility, temporal coherence and core quality must be VALIDATED. Mixed source
identities/quality states and duplicated/unpaired coordinates cannot score.

Failure returns `score=null` / `normalized_value=null`, explicit UNAVAILABLE and
reason: reference unavailable/checksum/contract mismatch, version mismatch,
sampling unavailable/domain unvalidated/contract mismatch, insufficient samples,
dataset unavailable, point evidence missing, quality unavailable or inconsistent
evidence. Missing observations never become score0. Raw partial summaries retain
missing counts/reasons when possible, but never receive a normalized partial score.

Freshness, source completeness and real-world completeness UNKNOWN remain visible;
they are not numerical penalties. Raw foundation `normalized_score_status=BLOCKED`
and its generic `normalization_not_implemented` reason are unchanged: that status
is not the readiness status of this separately reviewed component. The normalized
point's limitations do not repeat that stale generic claim; original raw quality
is retained in the paired raw summary.

## Explanatory evidence and accepted regression

Median, p90, C500, C1000, sample/valid/missing counts, raw snapshot/quality and
limitations remain paired with the normalized District result. **p90 is not a
separate weighted penalty.** The reviewed score is mean relative proximity;
poor-tail behavior is mandatory explanation, not a hidden composite weight.
No absolute good/bad distance standards are claimed.

| District | N | Score (display) | Median m | P90 m | C500% | C1000% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Central | 553 | 52.61 | 461.55 | 1283.98 | 54.25 | 80.11 |
| Kirovsky | 376 | 58.01 | 375.51 | 978.53 | 58.78 | 90.69 |
| Leninsky | 843 | 51.53 | 484.86 | 1248.47 | 51.48 | 81.61 |
| Oktyabrsky | 1461 | 47.62 | 536.79 | 1545.99 | 47.36 | 77.62 |
| Sovetsky | 1437 | 52.21 | 454.68 | 1478.47 | 53.51 | 78.91 |
| Sverdlovsky | 1215 | 42.47 | 653.55 | 2575.19 | 42.06 | 63.62 |
| Zheleznodorozhny | 180 | 70.57 | 259.03 | 628.33 | 83.89 | 98.33 |

Full-precision score regressions are accepted outputs, never calibration inputs.
Order: Zheleznodorozhny > Kirovsky > Central > Sovetsky > Leninsky > Oktyabrsky >
Sverdlovsky. Close ordering does not establish a meaningful quality difference.

## Refresh and future cities

Active OSM evidence may change; this reference/version stays frozen. Evaluate new
raw evidence against the same distribution, never rebuild during bootstrap.
City2 may explicitly use a Krasnoyarsk-relative point result; it does not join or
refit this cohort. New city-specific or frozen multicity calibration requires a
new reviewed normalization version. Spatially dependent territorial samples are
not independent resident/population observations. No residential weighting layer
is claimed. The source extent still limits observed nearest lookup.

## Verification

Use a disposable migrated PostgreSQL/PostGIS DB with MESTO_REQUIRE_TEST_DATABASE=1.
Run targeted raw and normalized Stop Availability tests, then the full backend,
frontend lint/typecheck/build and isolated E2E cycle. New tests exercise checksum
and version failure, ties/endpoints/bounds/monotonicity, no normalizer DB query,
geometry/domain/missing/minimum gates, deterministic sampling, raw explanatory
metrics, exact full-precision seven-district scores and unchanged current MESTO.
