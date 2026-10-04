# Shared OSM Data Foundation V1

This layer provides source evidence and quality contracts for school, kindergarten,
clinic, hospital, park and `highway=bus_stop`. It implements no score, calibration,
district sampling, semantic stop grouping or new transport taxonomy. No external
OSM collection was performed in this phase; the bundled snapshot is unchanged.

## Source snapshot and query

`backend/data/osm/query.json` is the tracked Overpass definition. The query renderer
takes a WGS84 extent (west/south/east/north) and optional timezone-aware
`requested_as_of`. Selector/value ordering is canonical. SHA-256 covers the query
version, source and exact rendered query; changing the extent, timeout or requested
date changes the hash. Shared parser/build logic contains no city branch.

Collection is an explicit Python API, `data.osm.collection.collect`. Supply
dataset/scope/snapshot IDs, total extent, named part extents, and a new output
directory. Production transport performs one bounded POST per part, without
retries. Tests inject mocked responses. The collector records each response,
including failed responses, in exclusive-created files. It writes the exact query
and `manifest.json`; an existing collection directory is never overwritten.
The CLI is offline-only, and application bootstrap never invokes collection.

## Manifest and immutable artifacts

`Manifest`/`Part` in `contracts.py` define dataset, scope, snapshot, source, tracked
query definition/version/hash, extent, optional requested date, builder version,
category scope, known limitations and optional build time. Each part records ID,
extent, exact query/hash/request artifact, response artifact/checksum, HTTP and
collection status, element count, remark/error, source base time and actual fetch
time. Missing optional provenance remains missing and blocks validation.

Raw bytes are immutable inputs. Checksums identify bytes, not freshness,
completeness or correctness. Validation checks JSON/top-level shape, Overpass
header/base time, elements array, exact request/hash/extent, count, artifact
checksum and errors/remarks. References cannot escape the artifact root.
Original ignored raw parts are not automatically added to Git.

## Offline build

From `backend/`:

```sh
python -m data.osm /path/to/manifest.json \
  --artifact-root /path/to/artifacts --output-dir /path/to/new-build
```

The output directory must be new. Outputs are `canonical.json` and
`build-report.json`. Exit code 0 means the evidence build passed structural,
provenance, query-coverage and temporal gates; 2 means blocked. No request is made.
Invalid manifest schema fails before a build is produced.

Part order and object-key order do not determine winners. Observations are sorted
by `(osm_type, osm_id)` and source references by part ID. Canonical JSON uses fixed
serialization and SHA-256, excludes `built_at`, and uses no wall-clock time.
Changing raw artifact bytes can change the checksum even if the source facts
appear equivalent: provenance is part of canonical content.

## Identity, conflicts and coordinates

An OSM identity is `(node|way|relation, positive OSM ID)`, never name, coordinate or
DB integer ID. Canonical-equivalent repeated payloads deduplicate and retain all
part references. Different payloads for one identity block the build. The report
contains both/all source references and payload checksums; there is no last-wins
resolution. Conflicting identities produce no accepted observation.

Nodes use `node_coordinate`; ways/relations use `overpass_center`. Centers are not
boundaries, entrances or complete geometries. Consumers use the WGS84 point in
`POI.location` (SRID 4326); `geometry` is not backfilled. Name-independent eligibility
retains the six categories and the existing category precedence. Missing/blank
names become null, never invented labels. Full source tags are preserved for all
components. Same-name/nearby observations are not grouped. Synthetic input is
rejected. Eligibility records a version, category, exclusions and limitations.

POI catalogue bbox filtering now uses `location`. `ST_Intersects` includes points
on the envelope boundary; other catalogues retain their prior geometry selection.

## Timestamps and quality

Actual fetch, source base, requested date and build time are separate. Different
part base times yield `MIXED` and block validation; no tolerance is invented.
Missing bases are unknown, not replaced with fetch/build time. A requested date
not verified by the reported source bases blocks the build conservatively.

Quality exposes independent freshness, query completeness, source completeness,
real-world completeness, provenance, eligibility, temporal, overall and normalized
score statuses. Rectangle-union coverage proves coverage of the declared query
extent only. `VALIDATED` overall means a coherent checked evidence build, not
that OSM captures every real-world object or that every object is fresh.
Freshness/source/real-world completeness remain `UNKNOWN` without reviewed
policies. Unknown is not assigned a numeric penalty. `normalized_score_status`
is always `BLOCKED`, with reasons; normalization is not implemented.

## Legacy bootstrap and persistence

The 1,988-record historical fixture has an aggregate `snapshot_fetched_at` and no
recoverable original part/query/base-time mapping. `build_legacy` references the
merged artifact honestly, marks provenance `PARTIAL`, query/temporal completeness
`UNKNOWN`, and leaves original fetch/base fields null. The aggregate time is
recorded separately. The required DB `fetched_at` preserves aggregate/import-time
bookkeeping, with explicit semantics in metadata. It is not original per-part
provenance. Current source-version naming/checksum and fixture counts remain
compatible. Legacy repeat ingestion is an explicit compatibility path, not a
validated fresh dataset replacement.
Reloading legacy evidence may update an existing identity only at its existing
checksum-derived source version; a different partial artifact cannot replace it.

`load_dataset` accepts only validated coherent builder results for caller-owned
transactional **candidate persistence**, with content/checksum consistency checks. Metadata keeps
dataset/scope/snapshot, query, extent, tags, coordinate representation, policy,
quality and per-part references. Version-level fetch time is latest fetch
bookkeeping, not a substitute for per-part provenance. Cross-scope overwrites,
synthetic identity overwrites, ambiguous persisted identities and implicit
adoption of unlabelled legacy rows are rejected. Other sources are unaffected.
This original immediate-upsert path is superseded by the internal
[snapshot lifecycle](osm-snapshot-lifecycle.md): `load_dataset` now persists a
candidate/history only. Explicit reviewed activation updates the current `pois`
projection atomically; historical observations are never deleted. Empty snapshot
activation stays blocked. Legacy bootstrap adopts once and preserves the active
dataset on later restarts.

## Historical proposal for safe retirement (Phase 4B-3A)

The proposal below is the historical Phase 4B-3A design record. Phase 4B-3B.2
implements revision `0014_osm_snapshot_lifecycle`; the actual schema, compatibility
projection, reviewed UNKNOWN-quality gate, migration/downgrade and Code Map are
documented in [OSM snapshot lifecycle](osm-snapshot-lifecycle.md). The fresh
candidate has NOT been activated; publication/review precedes first activation.

In Phase 4B-3A, retirement/atomic active-dataset replacement was blocked for schema
review. JSON metadata can store provenance, but cannot enforce snapshot lifecycle,
unique scope/identity membership or an active pointer. Current scoring queries
read every district POI; a metadata-only `retired` flag would leave stale evidence
active unless consumer semantics were changed. `source_version` alone provides
neither an active pointer nor constraints and conflicts across overlapping scopes.

Minimum proposal recorded in Phase 4B-3A (the implemented design is linked above):

- `osm_datasets`: ID, source ID, scope ID, category scope, extent/version, nullable
  active snapshot FK; unique `(source_id, scope_id)`.
- `osm_snapshots`: ID, dataset FK, snapshot version, status, query/artifact/canonical
  hashes, full manifest/quality JSONB, built/validated/activated timestamps;
  unique `(dataset_id, snapshot_version)` and indexed dataset/status.
- `osm_observations`: snapshot FK, OSM type/ID, tags/provenance/eligibility,
  coordinate representation and point; unique `(snapshot_id, osm_type, osm_id)`,
  checked types/positive IDs, spatial and snapshot indexes. This separates source
  identity from per-dataset/snapshot membership, including overlapping scopes.
- Reviewed active-evidence view/query for catalogue/analytics consumers, with a
  locked dataset row and atomic pointer switch only after a validated full build.
  Synthetic and other-source POIs remain outside this lifecycle.

Affected code: ingestion, bootstrap, POI catalogue and analytics evidence reads.
Existing legacy observations need a reviewed adoption/backfill mapping, never
fabricated provenance. Downgrade must refuse to discard snapshot history or active
membership without an explicit preservation/export plan.

Acceptance tests for that future migration: failed/partial/mixed/conflicting builds
cannot switch active data; a full replacement excludes missing old observations
only in its scope; another city/source/synthetic data survives; empty replacement
policy is explicit; transaction failure rolls back pointer and observations;
concurrent activations serialize; overlapping scopes preserve separate membership.

## Verification boundary

Foundation tests use temporary raw files and mocked collection. PostGIS tests
cover bbox with null/misleading geometry, unnamed candidate/activation, fail-closed persistence,
scope/synthetic guards, transaction rollback, legacy counts and the pinned
seven-district scoring outputs. Lifecycle tests additionally cover history,
retirement, quality gates, concurrent activation, legacy adoption and guarded
downgrade. No real fresh candidate activation is performed by these tests.
Residential complexes play no role in query/build/quality/eligibility.
