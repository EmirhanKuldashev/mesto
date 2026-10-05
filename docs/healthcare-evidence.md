# Healthcare V1: observed clinic/hospital destination proximity

Healthcare V1 is proximity to the nearest observed active real OSM object with
exact `amenity=clinic` or `amenity=hospital`. These categories are united only
as eligible destinations for territorial proximity. **Clinic and hospital are
not equivalent services or institutions.** The nearest observation retains
`source_category` for explainability; there are no separate subtype weights or
averaged clinic/hospital scores.

This does not establish medical quality, doctor count, capacity/beds,
specialization, appointment availability, cost, public/private access, emergency
response time, walking/driving travel time, or population-weighted healthcare
provision. No automatic expansion to doctors, pharmacy, dentist or other medical
POIs is performed. A source name or `healthcare=*` tag does not override the
exact amenity contract.

## Quick source and taxonomy check

Baseline: `fresh-20261004T132116Z`.

| Category | Eligible | Named | Unnamed | Node | Way | Relation | Overpass center |
|---|---:|---:|---:|---:|---:|---:|---:|
| clinic | 127 | 115 | 12 | 106 | 21 | 0 | 21 |
| hospital | 89 | 75 | 14 | 32 | 54 | 3 | 57 |
| Total | 216 | 190 | 26 | 138 | 75 | 3 | 78 |

All 216 have valid WGS84 locations and exact matching amenity/category tags.
126 clinics also have `healthcare=clinic`; one has `healthcare=laboratory`.
87 hospitals have `healthcare=hospital`, two lack that secondary tag.
Dental polyclinics, specialized hospital departments and facilities are present.
These are observed eligible tags, not a guarantee of general-purpose services,
admission or equivalent care. The broad destination union is honest under the
accepted metric; no narrower clinical-access claim is made.

OSM identity overlap and exact coordinate duplicate pairs are zero. There are
32 observation pairs within 50 m and 74 within 100 m, including 27 cross-category
pairs. Examples include repeated clinic names, node/building representations,
hospital departments, and co-located clinic/hospital campuses. No semantic
institution or campus deduplication is performed. The metric is nearest
observation-point distance, not an independent facility count. Close observations
remain a documented limitation; no exhaustive sensitivity research was needed.

## Canonical evidence

Evidence: `healthcare-evidence-v1`.
Eligibility: `healthcare-osm-eligibility-v1`.

Require the managed active lifecycle snapshot, source `osm`, a non-synthetic
source and POI, eligible canonical membership, exact `clinic`/`hospital` category
agreement with source amenity, `osm-poi-eligibility-v1`, and valid nonempty WGS84
point location. Unnamed observations are retained. Legacy, retired, candidate,
historical, unmanaged and unrelated medical POIs cannot enter the component.

Point distance uses PostGIS WGS84 geography spheroid distance to the canonical
node or Overpass center. It is not distance to an entrance, hospital boundary,
street route or care service. District ownership does not limit nearest search.
Ties sort by distance, OSM type using `C` collation, then numeric OSM ID. One
point batch is one MVCC SQL statement; there is no production d2/d3 contract.

Required provenance, query completeness, eligibility and temporal quality must
be validated. UNKNOWN real-world completeness and freshness are explicit
limitations, not numerical penalties. Invalid or unavailable input produces
explicit unavailability with a null nearest object or normalized value; missing
evidence is never substituted with score zero.

## District sampling / raw explanation

`healthcare-district-territorial-grid250-v1` uses the validated generic grid SQL:
EPSG:32646, 250 m cells, centers `(250*i+125,250*j+125)`, transformed to WGS84.
`ST_Covers` on the original reviewed District polygon determines membership;
all samples have equal weight. This is territorial sampling, not population,
residential or medical-need weighting.

Reviewed geometry identity and expected counts are checked. Missing/invalid or
unreviewed geometry/city, count mismatch, mixed source snapshots/quality states,
or missing selected point evidence cannot produce a District score. The expected
seven-District sample total is 6065; the lower edge of this validated geometry
domain is 180 samples, not a population law.

Raw explanation accompanies the score: N, valid/missing counts, median nearest
distance, continuous p90, inclusive C500/C1000/C1500, and
`nearest_category_counts` for clinic/hospital. Coverage denominator contains
valid evidence only; partial data remain explicit and the District score is null.
Subtype breakdown sums to valid evidence count and does not affect score weights.

## Frozen Krasnoyarsk-relative normalization

Version: `healthcare-krasnoyarsk-relative-v1`.

```text
L(d) = count(reference < d)
U(d) = count(reference <= d)
F(d) = (L(d) + U(d)) / (2N)
u(d) = 100 * (1 - F(d))
District score = mean(u(d_i))
```

Exact empirical midrank CDF, without interpolation, refit, District min/max,
p90 weights or manual coefficients. Equal distances receive equal values,
regardless of subtype. The score is average relative territorial proximity
against a frozen Krasnoyarsk Healthcare reference, not quality or provision out
of 100. All selected evidence must be available before averaging.

The packaged artifact contains only the deterministic sorted Healthcare
distance distribution, versions, reference/source/geometry identities,
checksums and limitations. School/Kindergarten/Stop reference values are not used.
Whole-file checksum and typed contract identity are validated; mismatch fails
closed. Runtime does not collect, regenerate or depend on ignored research files.
Scoped `.gitattributes` preserves exact artifact bytes on Windows checkout.

A future city cannot silently use this reference/sampler. A future validated
Krasnoyarsk snapshot can use the unchanged frozen calibration while retaining its
own evidence provenance, without refitting the reference.

## Architecture / code map

`backend/app/analytics/healthcare/`:

- `models.py`: evidence/subtype/raw contracts; generic coordinate, snapshot,
  coverage and foundation quality primitives are reused without changing them.
- `service.py`: nearest-only real active clinic/hospital batch search.
- `aggregation.py`: median/p90/coverage and explanatory nearest subtype counts.
- `reference.py`: frozen integrity and identity checks.
- `normalization.py`: pure point CDF, without ORM or POI queries.
- `sampling.py`: reviewed generic grid SQL with Healthcare-specific metadata.
- `district.py`: two-query orchestration and equal mean with raw explanation.

This standalone component is not integrated into `objective-current-v1`, MESTO,
Match, Growth, Market, Affordability or ranking. Existing School, Kindergarten
and Stop implementations remain unchanged. No frontend/public API/migration
change is required. Focused regressions are in `test_healthcare.py` and
`test_healthcare_normalization.py`.

## Accepted calibration / District regressions

Reference ID: `healthcare-krasnoyarsk-fresh-20261004T132116Z-territorial-grid250-center-cdf-v1`. N=6065. Artifact size: 84019 bytes.

Artifact SHA256: `145349df460a5fa17455cffa534b1263033b7f65454bfd6bee3aa97d4cc9e0b6`.

Distribution SHA256: `3870ae1180816781fa5de14d25d22cb4afd9df7757c081ffa7233becd815e75d`.

Canonical identities, coordinates, nearest subtypes and distances reproduced exactly in two complete batches.

Two-query District observation: 3.917378 seconds locally; not an SLA.

Display values are rounded; tests preserve full precision. Median/p90 are meters; C columns are percentages.

| District slug | Score | N | Median | p90 | C500 | C1000 | C1500 | Nearest clinic/hospital |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| osm-centralny | 61.87 | 553 | 848.05 | 2018.40 | 26.58 | 59.13 | 75.23 | 431/122 |
| osm-kirovsky | 62.14 | 376 | 819.38 | 2321.18 | 30.32 | 58.78 | 77.13 | 261/115 |
| osm-leninsky | 60.66 | 843 | 880.59 | 2084.67 | 23.96 | 57.30 | 76.28 | 650/193 |
| osm-oktyabrsky | 45.70 | 1461 | 1472.46 | 3604.61 | 14.99 | 36.14 | 50.79 | 1075/386 |
| osm-sovetsky | 44.41 | 1437 | 1324.59 | 6348.96 | 19.49 | 39.60 | 54.77 | 1026/411 |
| osm-sverdlovsky | 40.34 | 1215 | 1814.57 | 4077.70 | 11.28 | 27.00 | 41.56 | 1029/186 |
| osm-zheleznodorozhny | 82.99 | 180 | 398.20 | 786.65 | 63.33 | 97.22 | 100.00 | 115/65 |
