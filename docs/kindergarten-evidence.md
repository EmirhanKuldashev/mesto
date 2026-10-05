# Kindergarten V1: observed OSM proximity

Kindergarten V1 means proximity to observed active real OSM objects whose exact
tag is `amenity=kindergarten`. It is a standalone atomic component, without
integration into current `objective-current-v1`, ranking or user flows.

This is **not** kindergarten quality, availability of places, public/private
eligibility, fees, age-group suitability, walking-route accessibility or
population-weighted provision. The source does not establish those facts.

## Canonical evidence and eligibility

`kindergarten-evidence-v1` / `kindergarten-osm-eligibility-v1` requires the active
managed real OSM lifecycle snapshot, `source=osm`, `synthetic=false`, eligible
canonical membership, matching Kindergarten category, exact `amenity=kindergarten`,
`osm-poi-eligibility-v1`, and valid WGS84 observation location. Legacy, retired,
candidate, historical and unmanaged POIs cannot enter this component. The source
itself must be real. Unnamed observations remain eligible. Childcare, school,
social facilities and mixed amenity strings are not automatically included.

Distance is PostGIS geography WGS84 spheroid distance to the canonical node
coordinate or Overpass center, not an entrance, building boundary or pedestrian
route. Nearest observations may belong to another District or have no District.
Ties use distance, OSM type with `C` collation, then numeric OSM ID. Point batches
use one MVCC SQL statement. There is no d2/d3 in the production contract.

Required source provenance, eligibility, query completeness and temporal quality
must be validated. Unknown real-world completeness and freshness remain explicit
limitations, without numerical penalties. Missing or invalid input has explicit
unavailability and null evidence/value, never a substituted zero.

## Quick data and taxonomy check

Accepted snapshot: `fresh-20261004T132116Z`.

323 eligible observations: 262 named / 61 unnamed; node / way / relation:
9 / 301 / 13. All 323 have valid locations; 314 use Overpass centers. All have
exact `amenity=kindergarten`; 256 also have `education=kindergarten`.

Names include a primary school-kindergarten, a secondary school with preschool
department, and a specialized children's home. Names do not override the observed
tag contract and do not prove ordinary institutional access. These ambiguities
do not contradict observed `amenity=kindergarten` proximity; no narrower claim
is made and no name-based exclusion was introduced.

No exact coordinate duplicate pairs were found. There are 5 pairs within 50 m
and 13 within 100 m, including differently named neighbours and repeated names
which may describe buildings or campuses. No semantic institution deduplication
is performed. The component measures observation-point proximity, not an
independent institution count or capacity. No exhaustive taxonomy/sensitivity
study was needed for that accepted V1 meaning.

## District sampling

`kindergarten-district-territorial-grid250-v1` uses EPSG:32646, 250 m cells and
centers `(250*i+125, 250*j+125)`, transformed to WGS84. Membership uses
`ST_Covers` on the original reviewed District polygon; equal weights per point.
This is territorial sampling, **not** population, residential or child weighted.

Reviewed geometry identity and expected counts are checked. Null/invalid geometry,
unreviewed geometry/city, count mismatch or unavailable evidence cannot produce
a District score. All selected evidence must be available from one consistent
snapshot/quality contract; partial results keep raw missing counts but do not score.

Raw explanation accompanies the score: sample count, valid/missing counts,
median nearest distance, continuous p90, and inclusive C500/C1000/C1500 coverage.
Coverage denominator contains valid evidence only; partial evidence is explicit.

## Frozen Krasnoyarsk-relative normalization

Version: `kindergarten-krasnoyarsk-relative-v1`.

```text
L(d) = count(reference < d)
U(d) = count(reference <= d)
F(d) = (L(d) + U(d)) / (2N)
u(d) = 100 * (1 - F(d))
District score = arithmetic mean(u(d_i))
```

Exact empirical midrank CDF: no interpolation, p90 weight, hand coefficient,
seven-District min/max or dynamic refit. Equal distances receive the same value.
The score is average relative territorial proximity against the frozen
Krasnoyarsk Kindergarten reference, not percent provision or quality out of 100.

The runtime fixture contains only the deterministic sorted 6065 Kindergarten
distances, versions, source/geometry identities, checksums and limitations.
School/Stop distance distributions are never reused. Exact file checksum and
typed version/source/distribution identity must match; failures close the
calculation. Runtime never collects or regenerates reference data and does not
depend on ignored research files. A scoped `.gitattributes` rule preserves exact
fixture bytes on Windows checkout.

A future city cannot silently use this reference or sampler. A future validated
Krasnoyarsk snapshot may use the unchanged frozen reference, while retaining its
own evidence provenance; this does not refit or refresh the calibration artifact.

## Architecture / code map

`backend/app/analytics/kindergarten/`:

- `models.py`: component evidence and raw contracts; generic immutable coordinate,
  snapshot and coverage primitives and the foundation quality gate are reused.
- `service.py`: nearest-only active real OSM batch search.
- `aggregation.py`: raw median/p90/coverage using the existing percentile primitive.
- `reference.py`: frozen integrity and identity checks.
- `normalization.py`: pure point normalization, without ORM or POI queries.
- `sampling.py`: approved generic grid SQL with Kindergarten-specific metadata.
- `district.py`: two-query orchestration and equal mean, with raw explanations.

School and Stop implementations, current scoring, frontend, public API and
migrations remain unchanged. Focused PostGIS and normalization regressions are in
`backend/tests/test_kindergarten.py` and `test_kindergarten_normalization.py`.

## Accepted calibration / seven District regressions

Reference ID: `kindergarten-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-center-cdf-v1`. N=6065. Artifact size: 83507 bytes.

Artifact SHA256: `af8a70d0b048613ef83636d4938ddb9f4efc06e9351974683460b92c14845495`.

Distribution SHA256: `85a75707e7e47b5fd0331210086263e10a9ab5be2acf0a20f466f096145f1c70`.

Canonical identities, coordinates and distances reproduced exactly in two complete batches.

Two-query District observation: 4.992439 seconds locally; not an SLA.

Displayed values are rounded; tests preserve full precision. Median/p90 are meters; C columns are percentages.

| District slug | Score | N | Median | p90 | C500 | C1000 | C1500 |
|---|---:|---:|---:|---:|---:|---:|---:|
| osm-centralny | 64.00 | 553 | 694.64 | 1560.94 | 32.01 | 70.52 | 88.25 |
| osm-kirovsky | 64.17 | 376 | 629.77 | 2126.52 | 43.62 | 66.76 | 79.52 |
| osm-leninsky | 58.59 | 843 | 874.00 | 1893.14 | 27.40 | 58.24 | 81.61 |
| osm-oktyabrsky | 43.78 | 1461 | 1396.67 | 4393.31 | 18.41 | 38.12 | 52.09 |
| osm-sovetsky | 44.64 | 1437 | 1362.45 | 6226.50 | 28.04 | 42.17 | 53.03 |
| osm-sverdlovsky | 42.96 | 1215 | 1543.12 | 4343.69 | 18.19 | 36.46 | 49.14 |
| osm-zheleznodorozhny | 78.00 | 180 | 393.72 | 868.02 | 62.22 | 95.56 | 100.00 |
