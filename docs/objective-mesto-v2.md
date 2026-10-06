# Objective MESTO V2

Active calculation version: `objective-mesto-v2`.

## Frozen composition

`MESTO = 0.20 * Stop + 0.20 * School + 0.20 * Kindergarten + 0.20 * Healthcare + 0.20 * Parks`.

Use full precision canonical district outputs and round the composite once to
two decimals. All five components are mandatory. Missing/null/unavailable,
unreviewed versions, invalid provenance or stale precomputation make the score
null with a named reason. No zero imputation, renormalization or legacy fallback.
Coverage is available required components / 5, not data completeness.
The objective index is territorial and neutral; personal preference stays in Match.

## Versions and explanation

| Component | Normalization | Sampling |
| --- | --- | --- |
| Stop | stop-availability-krasnoyarsk-relative-v1 | district-territorial-grid250-v1 |
| School | school-krasnoyarsk-relative-v1 | school-district-territorial-grid250-v1 |
| Kindergarten | kindergarten-krasnoyarsk-relative-v1 | kindergarten-district-territorial-grid250-v1 |
| Healthcare | healthcare-krasnoyarsk-relative-v1 | healthcare-district-territorial-grid250-v1 |
| Parks | parks-krasnoyarsk-relative-v1 | parks-district-territorial-grid250-v1 |

`POST /api/analytics/score` retains its existing request and category fields.
`score` and `current_score` now use V2. Additive `objective` contains score,
availability, calculation version, five component scores, fixed weights,
normalization/sampling/evidence/eligibility versions, reference IDs and hashes,
unavailable reasons, limitations, source snapshot identity, sample counts,
distance method and Parks geometry identity. No point distance distributions or
raw summaries are exposed through this field.

Migration `0015_objective_v2_evidence` adds nullable JSONB `objective_evidence` to
score history. Each new snapshot stores its complete objective explanation;
old records and versions are untouched, with null evidence. Public calculation
does not replay or upgrade a historical score silently.

## Computation path

`objective/engine.py` is a pure composer. `objective/provider.py` consumes an
immutable packaged snapshot of canonical normalized district outputs. It does
not calculate distances or normalize input data.

Offline reproduction (against a migrated disposable PostGIS database populated
with the accepted baseline):

```sh
python -m data.analytics.build_objective --output /outside/repository/objective-candidate.json
```

The builder calls each existing canonical district service once for all seven
districts. It verifies source quality and checks parity before/after calculation.
Its result is portable between databases: district association uses slug and
geometry checksum, not installation-specific IDs. Review a new candidate before
replacing the packaged file and code checksum; generation is never an endpoint,
startup hook or automatic reference refit.

Accepted component snapshot SHA256:
`80d5d166aceef8f6a9c2e6dc84d30e32549fe2e91f1f9f2dec764630c13859c6`.

Every interactive request verifies the packaged snapshot, component reference
checksums and Parks geometry artifact. One batched SQL statement checks current
ACTIVE dataset identity/quality, canonical binding projection fingerprint and
district geometry. Any source activation, missing binding, changed projected
coordinate, synthetic substitution or changed boundary fails closed. Legacy,
candidate, retired and synthetic sources cannot supply V2.

No raw OSM query or normalization is performed by the composer. The provider's
source-parity query is validation, not component calculation. Unrelated offers,
budgets, future factors and personal preference do not enter the component
fingerprint or composite.

Local Windows/PostGIS measurement for seven districts: offline preparation
13 SQL statements, approximately 48.73 seconds (Stop 15.03, School 3.84,
Kindergarten 4.86, Healthcare 3.66, Parks 21.33). Provider: 1 SQL statement,
0.70 seconds. Whole existing analytics orchestration: 39 statements, 1.01
seconds. These are measurements, not latency guarantees. Existing per-district
legacy fact/category/growth queries remain; no broad caching redesign.

## Published district regression

Values below are display-rounded; tests use canonical full precision inputs.

| District | Stop | School | Kindergarten | Healthcare | Parks | V2 | Rank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Central | 52.61 | 63.05 | 64.00 | 61.87 | 54.58 | 59.22 | 3 |
| Kirovsky | 58.01 | 65.12 | 64.17 | 62.14 | 68.75 | 63.64 | 2 |
| Leninsky | 51.53 | 60.56 | 58.59 | 60.66 | 56.99 | 57.67 | 4 |
| Oktyabrsky | 47.62 | 42.59 | 43.78 | 45.70 | 48.23 | 45.58 | 6 |
| Sovetsky | 52.21 | 44.78 | 44.64 | 44.41 | 47.72 | 46.75 | 5 |
| Sverdlovsky | 42.47 | 42.89 | 42.96 | 40.34 | 38.83 | 41.50 | 7 |
| Zheleznodorozhny | 70.57 | 78.70 | 78.00 | 82.99 | 71.97 | 76.45 | 1 |

## Legacy compatibility and boundaries

`LegacyAnalyticsService` explicitly replays `objective-current-v1` for historical
regression/compatibility. Public endpoints use `AnalyticsService` and V2 only.
Infrastructure/Transport and lifestyle/market/future categories remain available
for existing Match consumers; Infrastructure has no intermediate weight in V2.
Match, Growth, Market, Affordability formulas and data stay unchanged. The future
scenario retains its existing growth uplift (`0.15 * Growth`) and cap, starting
from the new objective base. Recommendation tie-breaking consumes the new MESTO
value; its Match score formula is unchanged.

Minimal frontend compatibility adds the optional objective type and corrects
methodology text. Existing category cards are labelled additional legacy
indicators, not V2 components. AI context receives the same additive explanation
and corrected methodology text; provider, prompt, limits and flow stay unchanged.
Full five-component UX presentation remains the next phase.

Limitations include relative frozen Krasnoyarsk calibration, territorial rather
than population weighting, unknown real-world completeness/freshness, straight
line rather than route distance, and Parks' separately dated geometry snapshot.
New active baselines require a reviewed precomputed component snapshot; until
then V2 becomes unavailable, without reverting to the legacy score.
