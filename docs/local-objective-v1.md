# MESTO Local — Objective Point Analytics V1

Version: `local-objective-v1`. Product label: **MESTO Local / Оценка места**.

An objective spatial characteristic of one WGS84 location relative to the frozen
Krasnoyarsk distributions. It is not personal Match, district ranking, housing
quality, affordability, market/growth, safety, service quality, commute or walking
accessibility. Stop means observed bus-stop proximity, not transport provision.

## Architecture and distance contracts

`app.analytics.local.service.LocalAnalyticsService` only orchestrates the five
existing `*AvailabilityService.points()` and `PointNormalizer.normalize()` paths:

| Key | Canonical observed destination |
| --- | --- |
| stop_availability | `highway=bus_stop` |
| school | `amenity=school` |
| kindergarten | `amenity=kindergarten` |
| healthcare | `amenity=clinic` or `amenity=hospital`; subtype retained |
| parks | `leisure=park`, independently frozen real geometry |

Distances retain `postgis-geography-wgs84-spheroid-v1`. Searches cross district
borders. Only real eligible observations bound to the active source snapshot are
destinations. Names are nullable. No synthetic, unbound, retired or historical
facts enter the active nearest searches. No network collection occurs.

Point components preserve their canonical representative-point contracts. Parks
uses actual Polygon/MultiPolygon geometry, including boundary/inside distance=0,
and genuine node coordinates. It never substitutes Overpass centers, bounding
boxes, centroids or convex hulls for park geometry.

## Normalization, provenance and missing policy

Reuse the five existing `*-krasnoyarsk-relative-v1` references, their packaged byte
SHA256 pins, typed version contracts and original midrank empirical CDF:

`utility(d) = 100 * (1 - (count(ref < d) + count(ref <= d)) / (2N))`.

No new reference or recalibration. Parks zero-distance ties receive their ordinary
CDF value, without a bonus. Utilities retain full precision.

Every evidence snapshot must match the accepted frozen reference identity and
the live active projection. The existing Objective projection fingerprint query
is reused strictly as a provenance guard, without consuming district scores.
The Parks normalizer independently checks geometry snapshot identity. All API
queries run in a single read-only PostgreSQL `REPEATABLE READ` transaction.

Local Objective is `fsum(0.20 * utility_i)` over exactly five components. Backend
does not round component or composite outputs; UI rounds only for display.
Any required missing/invalid evidence, snapshot, reference or version means
`UNAVAILABLE`, `score=null` and an explicit reason. No zero substitution,
remaining-weight renormalization, district or legacy fallback.

## Supported geography

Coverage is the union of the seven accepted real OSM district MultiPolygons from
the frozen reference contracts. Every polygon's WGS84 SRID, type, validity,
nonempty status, source/synthetic status and exact EWKB fingerprint is checked.
Use `ST_Covers`: inside and on boundary are supported; hole interiors and outside locations
are unsupported. Checking whether any accepted polygon covers a point implements
coverage of that union without generating a new neighborhood geometry.

Outside returns `UNAVAILABLE / unsupported_geography`. Coordinate ranges are
validated; nonfinite values, strings, booleans, null and extra fields are rejected
with HTTP 422. There is no clamping and no arbitrary bounding-box substitute.
An invalid/missing accepted polygon fails the coverage contract closed.

## Public API

`POST /api/analytics/local`, no profile or personal weights:

```json
{"latitude": 56.01, "longitude": 92.85}
```

Response includes `version`, `availability`, full-precision `score`, `location`,
the five `components`, fixed equal `weights`, `provenance`, `limitations` and
`unavailable_reason`. Each component exposes:

- `key`, `score`, `distance_m`, `available`, `unavailable_reason`;
- normalization/evidence/eligibility versions, reference ID/checksum, distance method;
- nearest OSM source identity, nullable name, category/subtype, raw distance and
  coordinate representation;
- `inside_geometry` for Parks, plus source/geometry provenance and limitations.

Unavailable components have null score and nearest evidence. Available siblings
can remain explained while the composite is unavailable. `/api/analytics/score`
and its district semantics are unchanged.

## UI

On `/district`, enable **Оценить место на карте** and click a coordinate. Ordinary
district-selection mode stays separate. A selected-place marker and Local panel
show score, a short explanation, the five utilities, distances and nearest names.
The coordinate form also provides a keyboard-accessible path independent of map
gestures and onboarding. Unnamed evidence displays **Объект без названия**.
Parks inside/boundary is explicitly explained. Versions/checksums stay out of the
ordinary UI. Request cancellation, stale-result suppression, timeout and retry
prevent a previous place's score from being displayed for a new selection.

## Parity verification

`tests/test_local.py` executes real PostgreSQL/PostGIS parity for all 6065 existing
validated grid250 centers, their original district membership, all 35 component
means and all seven Objective results. Expected values come from the checked
canonical artifact/provider, not a newly hardcoded Local baseline. Full-precision
absolute tolerance is `1e-12`; final presentation reproduces:

| District | Stop | School | Kindergarten | Healthcare | Parks | Objective |
| --- | --- | --- | --- | --- | --- | --- |
| Central | 52.60761581 | 63.04532424 | 63.99784433 | 61.86706997 | 54.58308052 | 59.22 |
| Kirovsky | 58.00933153 | 65.11616179 | 64.16954623 | 62.14090263 | 68.75173212 | 63.64 |
| Leninsky | 51.53246903 | 60.56257879 | 58.58506942 | 60.65863192 | 56.98921040 | 57.67 |
| Oktyabrsky | 47.62154573 | 42.58901260 | 43.78005669 | 45.70201440 | 48.23091503 | 45.58 |
| Sovetsky | 52.20711487 | 44.77990983 | 44.63536118 | 44.41080478 | 47.71623923 | 46.75 |
| Sverdlovsky | 42.47347155 | 42.88935028 | 42.96294261 | 40.33744856 | 38.83478367 | 41.50 |
| Zheleznodorozhny | 70.57021160 | 78.70092516 | 78.00320601 | 82.99074837 | 71.97297792 | 76.45 |

These are documented verification results, not implementation inputs.

## Runtime and descriptive differentiation

One available point uses **7 SQL statements**: coverage, shared active projection
guard and five existing canonical nearest searches. No grid construction, runtime
reference generation, district calibration or SQL N+1. The internal batch exists
for offline parity only; the public endpoint accepts exactly one location.

Local measurements on disposable PostGIS, including service/reference loading:
five point calculations took 0.5271 / 0.2615 / 0.2404 / 0.2277 / 0.2167 seconds;
median 0.2404s. These are developer-machine measurements, not a production SLA.
Parks reuses its existing deterministic geometry loader without a new cache layer.

Across the validated 6065 centers, Local Objective min/max/median are
0.4171 / 96.7733 / 50.9398; mean=50, SD=25.7248. Within Central, Local scores span
21.06–94.71; within Kirovsky 20.93–95.27; within Zheleznodorozhny 48.12–95.34.
Median within-point component spread is 28.2605, maximum 94.3116. This demonstrates
local contrasts without claiming residential/population representativeness.

## Residential complex audit

The clean application/E2E bootstrap imports **108 real Cian complexes**, all 108
with valid WGS84 coordinates inside supported coverage; zero synthetic complexes
and zero missing coordinates in that catalogue. Backend pytest's separate seeded
demo catalogue contains 12 synthetic complexes; it is not the real housing source.

Cian coordinates were extracted from the complex detail page's map-preview URL
associated with `newbuildingId`. This is a portal map anchor, not a verified
building footprint, entrance or construction-object coordinate contract. No RC
integration is added and no schema/data redesign occurs. The stateless coordinate
service can later accept verified ЕИСЖС Project/Building/ConstructionObject points.

## Reproduce

From `backend/`, with `DATABASE_URL` / `MESTO_TEST_DATABASE_URL` set to disposable
PostGIS and the standard test dependencies installed:

```sh
python -m alembic upgrade head
python -m pytest tests/test_local.py -q -rs
python -m pytest -q -rs
python -m data.analytics.check_local --output data/raw/local-v1/verification.json
```

The verification CLI is an offline developer command. It uses a read-only
repeatable-read transaction and writes only the optional local report file, never
DB records. It must not be run on an API request. In the frontend run lint,
`npx --no-install tsc --noEmit`, and build. The existing disposable Compose/E2E
workflow discovers `e2e/mesto-local.spec.ts` alongside the existing regression flows.

Objective MESTO V2, legacy Match/ranking, Market, Affordability and Growth remain
unchanged. AI synthesis, Mobility, Housing Foundation, ЕИСЖС integration and
Match V2 are out of scope. Next separate phase: Housing Foundation / ЕИСЖС discovery.
