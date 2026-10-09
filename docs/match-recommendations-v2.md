# Match recommendations V2 — experimental explicit personal utilities

Baseline: bde56dd591dfcb347172a4a7047f47b9c2229e07. This change adds a separate
`POST /api/recommendations/v2`; legacy recommendations and Foundation V1 are unchanged.
There are no schema migrations. New settings stay in the browser's onboarding
draft and are sent in the request, not to the legacy persisted profile schema.

## Contract and mathematics

`RequestV2` contains `profile`, optional `candidate_ids` (unique, 1–150), OR
`point`. No selector means the observed real CIAN catalogue; more than 150
records is rejected instead of silently truncated. Point requests never attach
a catalogue price. A requested missing/synthetic ID returns 404.

Profile version is `personal-match-v2`; response version is
`match-recommendations-v2`. Priorities are strict integer 0–3 or null. Null is
unanswered; zero explicitly excludes. The domain weights are explicit nonnegative
fractions summing to 1. The frontend normalizes the user's chosen relative
domain priorities, without a default combination. All-zero is NOT calculated.
The complete used profile is echoed; Decimal money is serialized as strings.

* Infrastructure reuses Foundation's full-precision weighted canonical Local
  utilities. No Objective/Local bonus is added to personal Match.
* Time utility is 100 for t<=g, 100*(b-t)/(b-g) for g<t<b, and 0 for t>=b.
  g and b are supplied by the user; b>g. A separate optional hard maximum is
  checked with <=. Zero soft utility is not a mandatory failure.
* Trip aggregation uses importance * visits/week only after explicit consent
  to that weighting. Missing preferences, time anchors or positive-weight
  route facts block Mobility's numeric utility. Explicitly excluded trips do
  not affect utility; their separately requested hard limit is still checked.
* Budget maximum is mandatory for a verified observed purchase candidate.
  The source's own starting price is compared using Decimal. Comfortable price
  is optional and must be below the maximum. Financial utility has the same
  piecewise function with comfortable and maximum prices as its anchors.
  Maximum-only budget is a constraint, not a fabricated financial utility.
* Overall = alphaI*I + alphaM*M + alphaA*A. Positive-weight missing domains
  yield null; no remaining-domain renormalization. Coverage is available active
  weight, not real-world source completeness or confidence probability.
* Mandatory eligibility is FAIL if any violation is known, otherwise UNKNOWN
  if any required fact is missing, otherwise PASS. A numeric diagnostic score
  may exist for a failed/unknown candidate but never promotes it to verified.

The sample response distinguishes `verified`, `unknown`, `failed`. District
groups count observed, spatially evaluated, verified, unknown and failed
candidates. `best_observed_match` considers only verified candidates and is
not the compatibility of the whole district. Larger samples can bias maxima.
District membership requires the source assignment AND a valid real OSM polygon
covering the exact catalogue anchor; ambiguous arbitrary-point boundaries are
unassigned. Unassigned candidates are retained, not discarded.

Rent and compare goals explicitly have null overall and UNKNOWN goal constraint.
PT uses the existing unavailable provider; no CAR fallback. No housing quality,
mortgage, traffic, service capacity, safety or AI utility is invented.

## Runtime, provenance and privacy

The API executes in PostgreSQL REPEATABLE READ / READ ONLY and never saves a
profile, score, source observation or snapshot. Catalogue prices retain their
own source version and fetch date (not a proven date of price availability).

Local computations are deduplicated and batched. Cross-request Local cache hits
require successful live ObjectiveProvider projection/geometry/reference guards
for all seven districts. Keys include the validated objective provenance and
exact coordinates. The cache is bounded (1024) and expires after 60 seconds.

Route cache keys include provider URL, complete graph manifest, mode and exact
origin/destination. Only AVAILABLE facts are cached; never user labels or
preferences. Response time/distance/snaps/provenance are retained; ranking does
not return/cache large polylines. Custom providers without a manifest do not
share cached facts. Capacity is 2048, TTL 60 seconds. Eight bounded workers
evaluate the whole sample after all DB/spatial work completes. No session is
shared across workers. Each provider call retains its existing bounded timeout;
there is no wall-clock truncation of candidates or routes based on cache warmth.
The request is bounded to 150 candidates and five trips, not an end-to-end SLA.

## UI transition

New results are opt-in via "Включить Match V2". Old endpoints remain available.
Old percentages are presented as legacy scores /100, not satisfaction
probabilities. The original main design is the starting point; no redesign
branch is merged. New settings are shared across onboarding/results/map.

Persisted drafts move to storage version 2 without transforming old 90-point
preferences or combined education fields. New priorities start unanswered.
The form explicitly requests individual priorities, trip importance/frequency,
comfort/soft/hard limits, domain tradeoffs, maximum/comfortable price and mode.
Calculations require an explicit button; weight changes invalidate results and
abort stale requests. Comparison uses the same submitted profile for up to two
candidates. On the map, enabling the new flow hides the old Foundation form.

## Verification

Backend unit tests cover boundaries, monotonicity, determinism, null/zero,
eligibility, budget/time, unsupported modes/goals, objective independence,
all 1023 infrastructure profiles, six illustrative personas and route-cache
identity. PostGIS tests use only the disposable test database, verify batching,
read-only operation and geometric source binding. E2E checks use the separate
Compose test stack at loopback ports 3100/18100, never production.

The linear utility and 0–3 scale remain explicit product hypotheses. No claim
of user-outcome calibration or a complete apartment market is made. New settings
are browser-local; cross-device persisted V2 profiles remain a later decision.

### Implementation verification (2026-10-09, before final audit)

The subsequent audit, fixes and final regression are recorded in
`docs/match-v2-final-audit.md`.

- Python 3.12 full suite on disposable PostgreSQL/PostGIS: 819 passed, 0
  failed, 0 skipped (662.12 s). This run preceded the final routing batch fix
  and one additional profile-validation parameter.
- Final Match V2 suite, including both PostGIS integration tests and cold/warm
  batch-route equivalence: 44 passed, 0 failed, 0 skipped (14.49 s).
- All browser scenarios: 34 passed (4 minutes). After the routing fix, the
  four new real-API/UI cases passed again (18.9 s), including 390/1440 px
  candidate screenshots checked visually.
- Frontend lint, TypeScript check and Docker production build passed.
  A sandboxed lint retry failed on Windows path access; the authorized native
  run passed. The initial disposable full-suite collection lacked the separate
  Playwright test dependency; installing it in the checker resolved collection.
- Real disposable catalogue, 108 candidates and three CAR trips: cold 4.784 s,
  warm 1.423 s; complete responses equal, 91 verified candidates, 96 numeric
  scores, 0 missing mobility domain scores. Prices missing from source still
  prevent full utility/eligibility where applicable. These timings are local
  observations, not a production SLA or a load test.
- Production database, migrations, cloud deployment and remote Git were not
  changed. The new flow remains explicitly opt-in.
