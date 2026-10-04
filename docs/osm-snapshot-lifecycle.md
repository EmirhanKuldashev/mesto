# OSM snapshot lifecycle foundation

## Code Map

| Path | Responsibility |
| --- | --- |
| `backend/app/osm/models.py` | Dataset, immutable snapshot/history, current POI bindings |
| `backend/app/models.py` | Register internal ORM models; existing POI schema unchanged |
| `backend/migrations/versions/0014_osm_snapshot_lifecycle.py` | Schema, legacy adoption, database guards, guarded downgrade |
| `backend/data/osm/lifecycle.py` | Candidate persistence, explicit review, atomic projection/activation, bootstrap adoption |
| `backend/data/loaders/osm_poi_loader.py` | Offline legacy bootstrap and managed candidate entry point |
| `backend/data/osm/builder.py` | Unchanged canonical build and evidence quality contracts |
| `backend/tests/test_osm_lifecycle.py` | Disposable PostGIS history/activation/isolation/rollback regressions |
| `backend/tests/test_osm_foundation.py` | Existing foundation/bbox/scoring regression; explicit lifecycle steps |

## Identity and immutable history

`OsmDataset` identity is `(source_id, scope_id)`, not a city branch or source-version
ordering. `dataset_key` records the initial builder label; `legacy-poi`, `osm-poi`
and other builder labels can describe versions of the same source/scope. Exact
builder identity remains in each immutable canonical JSON. Another scope is a
different dataset. Only the real `osm` source is managed; synthetic/other sources
are outside this lifecycle.

`OsmSnapshot` has unique `(dataset_id, version)`, canonical/manifest checksum,
query identity, independent quality, report and timestamps. `OsmSnapshotObservation`
has unique `(snapshot_id, osm_type, osm_id)`: the same OSM identity in A and B can
retain different names, tags and coordinates. It keeps the canonical observation,
point and historical consumer projection. District assignment is derived, outside
source identity. Point representation/eligibility/provenance are unchanged.

Snapshot identity/payload and sealed memberships are protected by database
triggers. Sealing occurs after history insertion. History cannot be updated/deleted
or appended after sealing. Snapshot status and its first explicit review are the
only mutable lifecycle fields; a saved review cannot be overwritten. No version
upsert destroys earlier observations.

## Explicit pointer and compatibility projection

`dataset.active_snapshot_id` is the sole active choice. Composite FK proves that
it references the same dataset. A partial unique index permits only one ACTIVE
snapshot per dataset; deferred constraint triggers check pointer/status and
projection consistency at transaction completion.

`pois` remains the current consumer materialization, with its original public
schema. `osm_active_pois` binds managed POI rows to their dataset, active snapshot
and exact history identity. Candidate/history tables are not product POI rows.
Existing analytics, POI catalogue/map, complex ranking/Match and AI context continue
to read `pois`; no public API or frontend changes are needed. Future spatial
consumers must read `pois` or explicitly join history through the active pointer.

When A→B activates, overlapping current POI IDs are reused and updated to B. Rows
missing in B are removed ONLY from the current projection, while immutable A
history and its full consumer payload remain replayable. Synthetic rows and other
sources/scopes cannot be removed or reassigned. An identity colliding with another
active scope or unadopted OSM row is rejected: overlapping-scope merging requires
separate review, rather than silently overwriting or double-counting evidence.

## Internal functions and quality gate

- `persist_candidate(session, build, manifest=...)` writes immutable history only;
  repeat same version/checksum is idempotent, different content is rejected.
- `load_dataset` delegates to candidate persistence and returns snapshot ID/counts.
  It no longer performs immediate active POI upserts. Invalid builds are rejected
  by this loader; the internal persistence function may retain REJECTED history.
- `review_for_activation(..., reviewer, reason)` explicitly reviews a CANDIDATE.
- `activate_snapshot(session, snapshot_id)` switches a reviewed VALIDATED version.

Lifecycle: CANDIDATE→VALIDATED after explicit review; VALIDATED→ACTIVE;
ACTIVE→RETIRED. Failed/partial/mixed/conflicting or RESEARCH_ONLY builds are
REJECTED or refused. Retired versions cannot automatically reactivate. No public
admin endpoint is introduced.

Required evidence gates remain VALIDATED: query, provenance, eligibility,
temporal coherence and overall build. Part errors/conflicts, missing manifest
identity or membership, and empty eligible snapshots block activation. Empty
replacement needs its own reviewed policy. `normalized_score_status=BLOCKED`
remains unchanged: current consumers still use their existing proxy formulas.

Freshness/source/real-world completeness UNKNOWN are never upgraded. Activation
requires a named review and justification accepting those specific UNKNOWN proxy
limitations (`osm-proxy-reviewed-unknown-v1`), recorded with the actual review time.
This is a reviewed override gate, not an invented age threshold. Without review,
activation remains blocked. Other non-VALIDATED/non-UNKNOWN values are refused.

Prefer passing the original `Manifest` when persisting a collection. Its identity
is checked against canonical inputs. `manifest_checksum` hashes canonical manifest
serialization, not raw JSON whitespace. If only BuildResult is supplied, the
tracked query/input manifest is reconstructed and honestly labelled
`reconstructed_builder_input` in the build report; unknown original build-time or
declared metadata is not claimed recovered. Canonical parts still retain exact
raw/query artifact references/checksums/timestamps. Legacy adoption has no
original manifest checksum/query/base/fetch claim.

## Atomicity and concurrency

All functions use caller-owned transactions. Activation locks the dataset row
with SELECT FOR UPDATE, refreshes its snapshot, checks quality/collisions, retires
the prior active snapshot, materializes B and switches the pointer within one
savepoint. Readers in other transactions never see a half-switch. Exceptions
roll back every projection/status/pointer change, including when the caller
catches an exception and continues. Caller commit makes the switch durable;
outer rollback restores the old state. Dataset locking serializes concurrent
activations; a candidate/review can be retried only under its valid status.

## Legacy adoption and offline startup

Migration 0014 adopts existing real OSM rows without modifying their PK, payload,
counts, geometry, district assignment or scores. Provenance remains PARTIAL;
query/time/freshness/source/real-world completeness UNKNOWN. Metadata-only
registration does not validate the source evidence. Original lost timestamps and
manifest are left null. Synthetic OSM-labelled rows are excluded.

Scope comes from recorded foundation metadata, or the published
`<scope>-<checksum-prefix>` legacy source-version bookkeeping when proven by its
SourceVersion checksum. Unrecoverable naming gets an explicit
`legacy-source-version:<version>` scope; no city is guessed. Missing/invalid OSM
identity, duplicates, conflicting versions in one scope or a synthetic DataSource
block migration for explicit review.

On an empty DB, migration creates schema; the existing offline fixture bootstrap
creates legacy POIs once and adopts them as active within the same transaction.
Repeating the same legacy bootstrap does not mutate managed payload/history.
Changed partial fixtures cannot replace an adopted legacy version. Once a reviewed
nonlegacy snapshot is active, startup is a no-op for that scope: it does not
resurrect old legacy observations. No network is required.

Old migration 0001 uses current ORM metadata.create_all. The new migration uses
checkfirst and verifies/adds its cyclic FK so both clean and existing DB upgrades
work without editing historical migrations. This pre-existing historical coupling
is not redesigned here.

## Downgrade and phase boundary

0014→0013 can drop lifecycle metadata only while it represents adopted legacy
alone; current source POI payload remains untouched. If any nonlegacy snapshot or
multiple historical versions exist, downgrade fails before destructive operations.
An explicit preservation/export plan is required; versions are never silently
collapsed into one POI row.

`fresh-20261004T132116Z` remains an ignored research artifact, NOT imported or
activated in this phase. Lifecycle must be reviewed and published before its
separate controlled activation task. No scoring calibration, taxonomy expansion,
frontend work or production deployment is part of this foundation.
