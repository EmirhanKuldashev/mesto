# Match V2 Foundation V1 — experimental, gate B

Task base: `5c17b437e2c11c40829023f4e207ea2ffea5cc0a`.
API version: `match-v2-foundation-v1`. Infrastructure version:
`infrastructure-fit-experimental-v1`. **Overall Match is deferred and always null.**

## Research precedes implementation

The offline exporter used the existing `LocalAnalyticsService.points()` and
approved `district_grid_250()` in a read-only PostgreSQL REPEATABLE READ
transaction. All 6065 grid centers and 108 real CIAN map anchors were AVAILABLE.
No reference fitting, new utilities, POI collection, price updates or DB writes.
Five existing reference IDs/SHA256 pins and the exported input checksum are in
[the complete research artifact](research/match-v2-local-v1.json).

All 1023 nonzero integer profiles in `{0,1,2,3}^5` were evaluated in the order
Stop / School / Kindergarten / Healthcare / Parks. Proportional profiles are
reduced by their GCD before arithmetic so they cannot acquire different ranks
from floating-point accumulation. Reported utilities and scores keep full
precision. For **rank comparisons only**, values are rounded to 10 decimal
places to suppress floating-point pseudo-reversals; remaining ties are broken by
stable source ID. This is a numerical tie policy, not a preference advantage.
The independent quadratic reversal audit matched all 1023 residential profiles;
the Fenwick counter's strict/tie rules also have a brute-force unit test.

| Metric | All grid250 | 108 CIAN anchors |
| --- | ---: | ---: |
| Different full rankings | 961 | 961 |
| Different top-10 sets | 717 | 414 |
| Different top-20 sets | 920 | 616 |
| Candidate union of all top-10 sets | 222 | 49 |
| Candidate union of all top-20 sets | 337 | 72 |
| Different first-place candidates | 50 | 12 |
| Candidate present in every top-10 | none | none |
| Median profile-pair top-10 overlap | 0.20 | 0.60 |
| Median profile-pair top-20 overlap | 0.30 | 0.70 |
| Median top-10 retention after one importance step | 0.80 | 0.90 |
| Mean component Pearson correlation | 0.742650 | 0.327119 |
| Median strict reversals vs objective | 958991 / 18389080 pairs | 611 / 5778 pairs |

The pair denominators include all candidate pairs; tied pairs are never counted
as reversals. Exactly 1020 profiles have a strict reversal in each sample; the
three equal-weight profiles reproduce the objective ordering. Profiles are an
exhaustive design space, **not probabilities of real user behavior**. The score
distributions, 3835 one-step edges, component correlation matrices, factor
sensitivity, tie-boundary counts and full persona top-10 lists are in the artifact.

### Persona top-10 set overlap (108 anchors)

| | Family | Transport | Parks | Healthcare | Education | Balanced |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Family | 1.0 | 0.5 | 0.5 | 0.6 | 0.7 | 0.9 |
| Transport | 0.5 | 1.0 | 0.5 | 0.5 | 0.4 | 0.6 |
| Parks | 0.5 | 0.5 | 1.0 | 0.7 | 0.3 | 0.5 |
| Healthcare | 0.6 | 0.5 | 0.7 | 1.0 | 0.3 | 0.7 |
| Education | 0.7 | 0.4 | 0.3 | 0.3 | 1.0 | 0.6 |
| Balanced | 0.9 | 0.6 | 0.5 | 0.7 | 0.6 | 1.0 |

**Gate B: LIMITED PERSONALIZATION.** The same-place utilities do produce useful,
explainable shortlist changes, including Education/Parks replacing seven of ten
anchors. Nevertheless, Кристалл wins 735/1023 exhaustive profiles, and the
residential sample has 30 Pareto-undominated anchors. First place often stays
fixed even when lower shortlist positions move. The 108 locations are source/map
anchors, not verified buildings, entrances, occupied homes or building-level
ground truth. Importance 0..3 is a product hypothesis, not a validated interval
psychological scale. There is no user-outcome or population-representativeness
validation. Therefore this is an experimental infrastructure contract, with no
claim of a complete or validated housing recommender.

## Request-level profile and API

`POST /api/analytics/match-v2`, no auth, persisted profile, CIAN requirement or
onboarding prerequisite:

```json
{
  "candidate": {"latitude":56.01,"longitude":92.85},
  "profile": {
    "version":"personal-profile-v1",
    "infrastructure":{"stop":1,"school":3,"kindergarten":3,"healthcare":2,"parks":2},
    "mobility": {
      "preferred_mode":"car",
      "destinations":[{
        "latitude":55.985,"longitude":92.9,"kind":"work","label":"Работа",
        "importance":2,"max_acceptable_minutes":25
      }]
    },
    "purchase_budget":null
  },
  "market_candidate_id":null
}
```

All infrastructure fields default to null. Null/absent is not explicit zero;
incomplete preferences return NOT_CALCULATED / importance_missing. Strict
integer importance is 0..3; booleans/strings/fractions are rejected. Explicit
all-zero returns NOT_CALCULATED / all_importance_zero. Coordinates are strict
finite WGS84; unsupported Local geography returns its existing UNAVAILABLE result
without corrupting other domains. Extra input fields are rejected. Nonstandard
JSON NaN/Infinity produces a safe 422 response using the existing Mobility route
validation handler, without echoing the input.

At most five destinations bound request routing work. Each has a strict
importance, existing destination kind and label, and optional finite positive
threshold <=1440 minutes. Budget is nullable positive finite Decimal, bounded at
10^15 RUB to avoid nonfinite downstream ratios; it is not a calibrated score.
Decimal response amounts are serialized as strings, preserving money precision.

### Infrastructure Fit

`fsum((importance_i / sum_importance) * local_utility_i)`.

Weights are request-level; the existing five utilities/references never change.
The result retains component, full-precision utility, importance, normalized
weight, contribution, evidence availability, provenance/version/checksum and
missing reason. `math.fsum(contributions)` exactly reproduces the reported score.
Positive-weight unavailable components make Fit UNAVAILABLE; zero-weight missing
components contribute exactly 0 and do not block. There is no zero utility
fallback or remaining-evidence renormalization. Incomplete/all-zero preferences
have null normalized weights and contributions, not fictitious zero scores.

### Separate objective and personal layers

`objective.mesto_local` is the original complete LocalResult, including fixed
20% weights and canonical evidence. `personal_fit.infrastructure` consumes only
its original five component utilities. Local and Fit are never added together.
`overall_match: null` is enforced by the response type. Equal weights reproduce
Local; single-factor priorities reproduce that factor, not Local plus a bonus.

### Mobility

The existing `MobilityService`/OSRM provider returns the original `mobility-v1`
result per included destination: label, kind, mode, seconds, road meters, frozen
dataset provenance, geometry/snaps and limitations. Personal importance is echoed,
but is not converted into a time score. Importance zero skips routing explicitly.
Missing mode/destinations returns NOT_CALCULATED. A required unavailable route
makes the mobility domain UNAVAILABLE while preserving available sibling routes.
Positive CAR results without a threshold keep compatibility null. With a user
threshold: `delta_minutes = duration_seconds / 60 - threshold`, and
`within_threshold = delta_minutes <= 0`. No arbitrary speed/index conversion.

PT remains UNAVAILABLE / public_transport_source_unavailable; no CAR or bus-stop
proximity substitute. CAR excludes live traffic, departure-time effects and
access/parking time. Example real routes from (56.01,92.85):

| Destination | Seconds | Road meters | Within 25 min | Delta min |
| --- | ---: | ---: | --- | ---: |
| Work (55.985,92.90) | 634.5 | 6354.7 | true | -14.425 |
| University (56.06,92.91) | 758.4 | 8492.4 | true | -12.36 |
| Relatives (56.012,92.862) | 219.3 | 2214.8 | true | -21.345 |

### Observed affordability

Optional `market_candidate_id` is the existing real ResidentialComplex integer
ID. Only non-synthetic CIAN rows can enter the observation. Candidate coordinates
must **exactly match** that row's stored source/map anchor or the existing
catalogue's `ST_AsGeoJSON` nine-decimal representation (no proximity radius);
a mismatch returns a separate
UNAVAILABLE / market_candidate_coordinate_mismatch, never a price attached to an
unrelated point. The existing `summarize_observations()` and `assess_sample()` are
reused on that one observation. No copied budget-eligibility formula or changes
to Market Context, district samples or existing ObservedAffordability.

Return starting/asking `observed_price_from`, budget, within_budget, budget_delta
(`budget - price`, positive means headroom), source/version, fetched_at and the
original ObservedAffordability DTO. No budget: NOT_APPLICABLE. Unknown price,
missing/not-real/mismatched candidate: UNAVAILABLE when a budget exists.
`observed_at` stays null because fetched_at is a record date, not a proven price
observation timestamp. Asking/starting price is not a transaction price or
guaranteed available/current apartment. No affordability score is introduced;
existing `ranking_eligible=false` is retained.

### Independent domains and future composition

Response: candidate, objective.mesto_local, personal_fit.infrastructure/mobility/
affordability/housing, overall_match and limitations. Housing is always
NOT_IMPLEMENTED / waiting_for_eiszh_access. Unavailable independent domains do
not erase available siblings. No hidden mandatory-dimension omission, legacy
fallback, cross-domain weights, overall index, Housing Fit or AI synthesis.
The complete actual structured example is in
[the read-only runtime artifact](research/match-v2-candidates-v1.json).

## Exploratory recommendation constraints on 108 anchors

All 108 actual CAR routes were calculated with the existing frozen OSRM dataset.
96 anchors have an observed starting price; 12 do not. Work anchor (55.985,92.90),
budgets and limits are illustrative experiment settings, not inferred real users'
destinations/preferences. For each scenario, the artifact includes the top-10
Local and Fit rankings, CAR-only and budget-only top-10, jointly constrained
shortlist, overlap, and every rejected source ID with explicit reasons.

First require a real route within the chosen limit and a known starting price
within budget, then rank remaining anchors by Infrastructure Fit. This is an
**experimental constrained shortlist**, not a composite overall Match score.

| Scenario | Budget RUB | CAR limit min | Within CAR | Within budget | Both eligible | Original Fit top-10 retained |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Family | 8000000 | 25 | 88 | 72 | 55 | 6 |
| Education | 8000000 | 25 | 88 | 72 | 55 | 5 |
| Parks | 8000000 | 25 | 88 | 72 | 55 | 4 |
| Healthcare | 8000000 | 25 | 88 | 72 | 55 | 5 |
| Balanced | 8000000 | 25 | 88 | 72 | 55 | 6 |
| Car commuter (Balanced infrastructure) | 8000000 | 15 | 42 | 72 | 28 | 4 |
| Budget constrained (Balanced infrastructure) | 6000000 | 25 | 88 | 47 | 30 | 4 |

## Runtime and UI

Match requests run one Local point, no grid construction, reference generation,
research, snapshot collection or OSRM graph build. A point uses 7 SQL statements;
optional candidate binding adds one query. Destination count gives 0/1/3 provider
calls in the measured scenarios. Local Docker medians (three samples):
infrastructure-only 0.4071s, one CAR 0.5071s, three CAR 0.3488s. Warm caches and
machine noise make these non-monotonic; **not a production SLA or scaling claim**.
Raw timings and call/query counts are retained in the artifact. CAR calls are
sequential, capped at five with existing provider timeouts; API does no retries.
Timings cover `MatchService.calculate`, excluding HTTP, engine and service
construction; they are not end-to-end request latency measurements.

The existing `/district` selected-point flow adds a collapsed **Подходит вашим
приоритетам** panel beside Local. Its own preferences do not overwrite onboarding
or legacy Match. It shows full five-factor importance choices with a distinct
Не указано state, readable utility/contribution breakdown, optional up to five
important places with CAR thresholds, and a budget/candidate selector. Choosing a
real ЖК moves the selected point to its source anchor; unrelated points do not
borrow its price. Objective Local and the existing Mobility panel remain separate.
No overall Match percentage or technical checksum dump appears in the new UI.
Cancellation, bounded client timeout, strict response validation, editable-input
invalidation and retry prevent stale/fabricated results.

Chromium checks cover 1440/390/360 widths, real API calculation, no horizontal
overflow, zero vs missing importance, CAR thresholds, excluded destinations,
blocked PT, bound observed price, malformed/API-error recovery and pending-request
preference edits. Screenshots are local test artifacts, not part of production.

## Reproduce and verification commands

Runtime dependencies and migrations are unchanged. Offline NumPy/SciPy are pinned
separately and never required by API, production images or normal backend tests:

```sh
# From backend/, against a supported already-bootstrapped PostGIS database.
python -m pip install -r data/analytics/research-requirements.txt
python -m data.analytics.match_v2_research --export --output data/raw/match-v2/canonical-local.json
python -m data.analytics.match_v2_research --input data/raw/match-v2/canonical-local.json --output data/raw/match-v2/research.json
python -m data.analytics.check_match_v2 --output data/raw/match-v2/runtime-audit.json
# check_match_v2 additionally requires the existing configured real CAR provider.

# Disposable migrated PostGIS TEST database only; never run pytest on production.
python -m alembic upgrade head
python -m alembic current
MESTO_REQUIRE_TEST_DATABASE=1 python -m pytest tests/test_match_v2.py -q -rs
MESTO_REQUIRE_TEST_DATABASE=1 python -m pytest -q -rs
```

Set both DATABASE_URL and MESTO_TEST_DATABASE_URL for the disposable test database.
Migration head remains `0015_objective_v2_evidence`. Full tests include all prior
Objective, Local, Mobility, legacy Match, Market, Affordability, Growth and source
ingestion regressions. Frontend: lint, `npx --no-install tsc --noEmit`, build, and
root Chromium E2E against `docker-compose.e2e.yml`. Publication gates require
green PR CI/E2E and independent main CI/E2E; no deployment is implied by a merge.

## Unchanged and next

No edits to existing component formulas/references, Objective, Local, Mobility,
legacy Match, Market, Affordability, Growth, CIAN data/fixtures, AI, schema,
onboarding, source collection or CI contracts. Only additive API registration and
selected-point panel mounting touch existing product files.

Future separate task: Housing Foundation if EISZH access is provided; otherwise
AI Synthesis on deterministic structured outputs. Car Mobility Fit calibration
and an overall cross-domain Match methodology remain separate future work.

## Recorded local verification

- Targeted native pytest on migrated disposable PostGIS: **53 passed**, no failures/skips.
- Complete Linux/PostGIS suite after the anchor fix: **776 passed**, no failures/skips,
  13 existing warnings. The additional local full run used pytest 9.1.1; GitHub CI
  continues to install the project's declared `pytest>=8,<9` test dependencies.
- Alembic upgrade/current: single head **0015_objective_v2_evidence**.
- Frontend lint, TypeScript noEmit and production build: exit 0.
- Complete Chromium suite on the disposable stack: **30 passed**, no failures/skips.
- Compose validation, staged diff check and unchanged legacy-path check: exit 0.
- The first new browser run caught the catalogue-coordinate precision mismatch
  (one failed price-binding case). It was fixed and both targeted real-DB tests
  and the full browser suite were rerun successfully. The earlier native full
  run was interrupted to rerun the complete suite against the corrected code.

Raw inputs, routes, logs and screenshots remain local ignored diagnostics. No
real credentials, production writes or user-file deletion were part of this work.
