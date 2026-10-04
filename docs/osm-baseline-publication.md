# Current packaged OSM baseline

CURRENT OSM BASELINE: `fresh-20261004T132116Z`, source/scope `osm / krasnoyarsk`.
There are 2,387 eligible real observations, including 394 without names. The
previous explicit legacy fixture has 1,988 observations and remains unchanged.

## Code Map

| Path | Responsibility |
| --- | --- |
| `backend/data/fixtures/osm/current-baseline.json` | Explicit version, checksums, counts, accepted review and previous baseline |
| `backend/data/fixtures/osm/snapshots/fresh-20261004T132116Z/` | Exact canonical bytes compressed in gzip, original manifest and build report |
| `backend/data/osm/baseline.py` | Offline integrity checks and existing lifecycle persistence/review/activation |
| `backend/app/etl/bootstrap_data.py` | Normal startup: districts, current OSM baseline, existing Cian fixtures |
| `backend/app/etl/bootstrap_osm.py` | OSM-only startup using the same declaration |
| `backend/data/loaders/osm_poi_loader.py` | CLI selects packaged baseline; explicit `load_pois` keeps legacy compatibility |
| `backend/pyproject.toml` | Include packaged fixture/config bytes in Python distributions |
| `backend/tests/test_osm_baseline.py` | Clean/upgraded bootstrap, integrity, offline, counts, scoring and bbox regressions |
| `backend/tests/conftest.py` | Default CI database uses fresh; historical regressions get a separate disposable legacy database |

## Distribution and identity

The tracked bundle ships the accepted canonical bytes, not a new collection or
regenerated dataset. Gzip has an empty filename and mtime=0; decompression returns
the original 1,935,597 bytes. Raw Overpass response, research reports, activation
backup and local reports remain ignored. No release download or hidden raw store
is required by startup. Docker copies `data/fixtures`; Python package data includes
the versioned bundle. Never select by filename order or newest timestamp.

Canonical SHA256:
`c1ad85a1d071749c84e31541d104cdaee25d94881ac908ea0838433cbba306e7`

Gzip SHA256:
`7d606150ae6d487cd3671db9a170b2eb788e21c2b31d94bc8364b9b00f6eee13`

Original manifest SHA256:
`2330b5fe0f5d807dba58493be8edc2f3dc92213d9607491ae55b5be6b963981a`

Original raw response SHA256 (reference only; raw not distributed):
`cf98ce519e9d3fbe5d0735230cbe7e8a02ed881ee0dfa0901b19365ead8375c4`

Query version `osm-poi-query-v1`, hash:
`5dd8b0b1555d83e35b3694375fbb595ef62074ff1545065f1779d5e8e6df0c09`

The loader verifies gzip, decompressed canonical, manifest and report checksums,
consistent identities and exact memberships/category/name counts before any DB
change. The existing lifecycle validates manifest/build consistency and activation
quality. Packaged approval records the previously accepted reviewer/justification;
each new DB records its actual lifecycle review time. This never invents a new
collection, source-base or fetch timestamp. Original manifest/raw references
describe historical evidence and need not resolve to files on a deployment.

## Clean and existing databases

Run from `backend/` with `DATABASE_URL` set:

```sh
python -m alembic upgrade head
python -m app.etl.bootstrap_data
```

Current migration head is `0014_osm_snapshot_lifecycle`. Clean history policy is
**B: fresh initial snapshot**. A clean DB creates one reviewed fresh ACTIVE
snapshot and 2,387 current OSM POIs; it does not invent or duplicate legacy history.
Legacy fixture `poi.json` remains available for explicit historical tests/imports.

Existing legacy-active databases retain their immutable legacy history when the
packaged fresh snapshot is explicitly selected by bootstrap. Existing databases
with fresh ACTIVE and legacy RETIRED preserve both histories, the active pointer,
stored review and all current POI payloads on repeated startup. No second fresh
snapshot is created. Another nonlegacy active version requires explicit review:
startup refuses to downgrade it to the packaged version. Rejected/retired versions
are not silently reactivated. Activation and retirement still use the existing
transactional lifecycle, not direct POI upserts or a new public API.

## Data versus scoring

| Category | Active observations | Unnamed |
| --- | ---: | ---: |
| school | 205 | 45 |
| kindergarten | 323 | 61 |
| clinic | 127 | 12 |
| hospital | 89 | 14 |
| park | 283 | 224 |
| bus_stop | 1360 | 38 |
| Total | 2387 | 394 |

Query execution, provenance, eligibility and temporal coherence are VALIDATED.
Freshness, OSM source completeness and real-world completeness remain **UNKNOWN**;
normalized score remains **BLOCKED**. OSM centers are representative points, not
entrances or polygons. Multiple/no district covers remain unassigned.

Data version is `fresh-20261004T132116Z`; scoring version is
`objective-current-v1`. No scoring, calibration, Match, Growth, Market,
Affordability or AI semantics changed. These regression values describe the
accepted evidence input and do not endorse the old methodology:

| District | MESTO | Infrastructure | Transport |
| --- | ---: | ---: | ---: |
| Central | 80.45 | 100.00 | 56.01 |
| Kirovsky | 87.67 | 100.00 | 72.25 |
| Leninsky | 80.36 | 100.00 | 55.82 |
| Oktyabrsky | 63.84 | 83.86 | 38.81 |
| Sovetsky | 82.53 | 100.00 | 60.70 |
| Sverdlovsky | 65.64 | 82.11 | 45.06 |
| Zheleznodorozhny | 100.00 | 100.00 | 100.00 |

Rebuild application images after changing source/baseline:
`docker compose up --build`. Reusing an old image can leave runtime scoring and
migration support behind the published code even when the DB is current.
