# Mobility V1 — factual routing foundation

Version: `mobility-v1`. CAR uses a real, self-hosted OSRM road graph.
PUBLIC_TRANSPORT is explicitly unavailable pending a permitted, verified routing
or schedule source. No Mobility score or Match V2 is implemented.

## Source discovery and decision (2026-10-07)

| Mode | Candidate | Krasnoyarsk coverage | Access / cost / limits | Data / decision |
| --- | --- | --- | --- | --- |
| CAR | [OSRM](https://github.com/Project-OSRM/osrm-backend) | Verified four coordinate pairs on the extracted local road graph, including the Yenisei crossing | Self-hosted; no API key, vendor request quota or software usage fee; deployment resources required | OSM, BSD-2-Clause engine; selected for a small deterministic car-only graph in existing Compose |
| CAR | [Valhalla](https://github.com/valhalla/valhalla) | OSM-based; local deployment not independently tested here | Self-hosted MIT; resources and tile preparation required | OSM / optional GTFS; viable alternative, unnecessary multimodal tile pipeline for this car-only delivery |
| CAR | [GraphHopper](https://github.com/graphhopper/graphhopper) | OSM-based; not independently deployed here | Self-hosted Apache-2.0, JVM; [hosted free tier is noncommercial](https://www.graphhopper.com/pricing/) | OSM / optional GTFS; viable alternative, additional JVM runtime without a required advantage for V1 |
| PT | Municipal structured schedule / GTFS + self-hosted router | Official city monitoring site exists; no licensed, validated Krasnoyarsk feed was identified in this discovery | [mu-kgt.ru](https://mu-kgt.ru/) ordinary access redirected to `captcha.htm`; stopped, no bypass | Not READY: neither service calendar, full structured routes nor redistribution license verified; public map/OSM stops alone are insufficient |
| PT | [2GIS public transport Routing API](https://docs.2gis.com/en/api/navigation/routing/reference/public_transport) | API supports transit, schedules and legs; actual Krasnoyarsk routing coverage not verified without a key | [Platform key required](https://docs.2gis.com/en/api/navigation/routing/start), licensed subscription/demo access; no applicable key or contractual limits provided | User confirmed no key on 2026-10-07; BLOCKED. A future adapter must distinguish transit from walking-only responses |
| PT | [Yandex Maps routing](https://yandex.ru/dev/jsapi-v2-1/doc/en/v2-1/dg/concepts/router/about) | JS API documents public transit; this project's Krasnoyarsk route response not verified | [Paid routing terms](https://yandex.ru/dev/tariffs/doc/ru/router/terms/), key/license required; existing MapLibre UI would need integration review | Not selected: no licensed access, map SDK coupling. [Yandex Rasp](https://yandex.ru/dev/rasp/doc/ru/) covers intercity schedules, not a substitute for city-bus routing |

No claim is made that a Krasnoyarsk GTFS feed cannot exist. None was verified and
licensed for this project. The user explicitly authorized CAR continuation with
PT DISCOVERY BLOCKED. No provider account or paid subscription was created.

The public OSRM demo was not used. Its [published conditions](https://routing.openstreetmap.de/about.html)
include request limits; it provides neither our frozen graph identity nor a
production SLA. The selected runtime needs no external routing network access.

## Separate road dataset and reproducibility

The road snapshot is **separate** from the MESTO OSM POI snapshot. No existing
baseline, evidence distribution or district data is modified.

Committed: `backend/data/fixtures/routing/krasnoyarsk-car-v1.osm.pbf` (3,765,919 bytes)
and `car-v1.json`. The manifest records:

- source: [Geofabrik Siberian Federal District](https://download.geofabrik.de/russia/siberian-fed-district.html), OpenStreetMap;
- downloaded dated URL: `https://download.geofabrik.de/russia/siberian-fed-district-261006.osm.pbf`;
- fetched at: `2026-10-07T10:41:11.253545+00:00`;
- source data timestamp: `2026-10-06T20:21:06Z`;
- regional source size: 586,446,498 bytes; SHA256 `b6ba648e37c3515abfc05b94d6d69e1a69c941644de56faf83573b84be06558f`;
- derived PBF SHA256 `b628177781f0161e63fce958672bd5c384f0119bccd420828425e17c985d642f`;
- extraction window west/south/east/north: `[92.2, 55.7, 93.4, 56.55]`;
- supported endpoint window: `[92.4, 55.8, 93.2, 56.35]`;
- 55,894 selected highway/ferry ways and 1,503 selected restriction relations;
- complete referenced ways/nodes and tags via pyosmium 4.3.1 BackReferenceWriter;
- OSRM 5.27.1 image and digest, bundled car Lua profile checksum;
- `data_version` stamped from the derived PBF checksum by `osrm-extract`.

OSRM input contains 304,332 nodes and 55,895 ways (backreferences add one way).
OSRM recognizes 1,500 restrictions and drops 52 invalid turn restrictions during
preprocessing; OSM completeness and engine interpretation remain limitations.
The extraction retains source tags for road access/barriers and restrictions;
it does not reconstruct roads from POI coordinates. Complete-way buffering
reduces edge effects but does not guarantee every journey is routable or
globally shortest. Unsupported endpoints are rejected, never clamped.

The builder verifies PBF and car profile checksums before `extract`, `partition`,
`customize`. The API verifies the packaged PBF and each response's `data_version`
against the manifest; a stale/different graph produces `dataset_version_mismatch`.
The derived PBF has no source timestamp header; provenance is explicit in the
manifest, not inferred from build time. Updates require a deliberate new dataset
version/review. There is no runtime downloader or automated refresh job.

The 586 MB regional source and preparation diagnostics are ignored, never part
of the Git commit or Docker build context. The compact road PBF is committed so
Compose/E2E build the same graph without downloading volatile map data.

## License and access

Roads, derived PBF and recorded routes: [OpenStreetMap ODbL 1.0](https://www.openstreetmap.org/copyright),
© OpenStreetMap contributors. The derived road database is distributed with the
repository under ODbL; keep its attribution, manifest and source link when
redistributing. The UI displays OSM attribution and a map correction link.
OSRM: [BSD 2-Clause license at the pinned release](https://github.com/Project-OSRM/osrm-backend/blob/v5.27.1/LICENSE.TXT).
The software license and map database license are distinct. No live API keys or
credentials are used by Mobility; engine access is internal to Compose.

## Contract and API

`POST /api/analytics/mobility`, independent of `/api/analytics/local`.
No profile, district, housing ID, database session, authentication or storage is
required. One origin → one destination. Labels/kinds only echo UI metadata and
are never included in provider requests or route selection.

```json
{
  "origin": {"latitude": 56.01, "longitude": 92.85},
  "destination": {"latitude": 55.985, "longitude": 92.9, "label": "Работа", "kind": "work"},
  "mode": "car"
}
```

`PersonalDestination.kind`: work / university / school / relatives / other
(default other). Label: optional, max 80 characters. Coordinates must be finite
numeric WGS84 values; numeric strings, booleans, invalid ranges and extra fields
return HTTP 422. The API cannot accept a provider URL from the request.

Response includes version, availability, origin, destination, mode,
duration_seconds, distance_meters, departure_time, traffic, provider,
provider_version, data_timestamp, dataset_id, dataset_sha256, limitations,
unavailable_reason and optional GeoJSON LineString plus two road snaps.

AVAILABLE requires genuine nonnegative route metrics and provider provenance.
UNAVAILABLE requires a reason and null duration/distance/geometry/snaps. Same
coordinates are sent to the graph and may yield a genuine zero route; the API
does not fabricate a zero or approximate travel time. Different coordinates can
also snap to the same road position; snapped endpoints are explicit.

Provider-neutral `RoutingProvider.route(origin, destination, mode, departure_time)`
returns `RouteFacts`; `MobilityService` echoes metadata and adds version/mode/time
semantics. Future providers can be substituted without tying clients to OSRM's
HTTP payload. No premature batch or caching system is introduced.

### Time, traffic and public transport

CAR is a **static car-profile calculation**, `traffic=not_included`,
`departure_time=null`. It is not current traffic time, a prediction or a
schedule-dependent route. Supplying CAR departure_time returns 422 instead of
silently ignoring it. Road-point access time is excluded: both inputs are
snapped to an eligible road within a requested 250 m radius. Snaps, offsets and
the access limitation are returned. This radius is a routing access constraint,
not a scoring or normalization parameter.

PT returns `UNAVAILABLE / public_transport_source_unavailable`, null metrics,
`traffic=not_available`, no invented walking/transit legs, transfers or times.
An optional PT departure_time must be timezone-aware; its offset is preserved
without performing a schedule lookup. No local-time UI field is shown while PT
is blocked. A future schedule provider must define service timezone/calendar
(Krasnoyarsk: IANA `Asia/Krasnoyarsk`) and static/realtime semantics.

### Failure and provider safety

CAR configuration: server-only `MESTO_CAR_ROUTING_URL` (default
`http://routing:5000`). Compose uses the internal pinned engine and exposes no
routing port. Arbitrary server-configured HTTPS providers must implement the
same frozen OSRM graph contract; HTTP is permitted only for loopback and the
Compose hostname. URL credentials, query, fragment, invalid port and base path
are rejected. There is no authentication secret in this implementation.

One GET per CAR calculation, no retry and no redirect following. Connection
timeout 1 s, HTTP operations timeout 5 s, body deadline checked at 5 s, maximum
decoded body 4 MiB, maximum geometry 20,000 WGS84 positions. Backend errors
never reveal raw provider messages. Known reasons include:

`unsupported_geography`, `routing_dataset_unavailable`,
`routing_configuration_invalid`, `no_route`, `no_road_segment`,
`provider_timeout`, `provider_unreachable`, `provider_access_denied`,
`provider_rate_limited`, `provider_redirect_rejected`, `provider_error`,
`provider_response_invalid`, `dataset_version_mismatch`.

Client UI timeout: 10 s with explicit retry. Editing a destination, changing
mode/origin or leaving the page aborts the old request and clears stale values.
The client validates the result schema and coordinate/metadata echo before
display. No fallback to straight-line distance, stop proximity or scoring.
Geodesic calculations exist only to validate provider geometry/snaps/metrics,
never to produce the returned route distance or time.

## Real verification, 2026-10-07

Self-hosted OSRM at a temporary loopback port. Each case: three identical
provider calls, plus one explicit inspection call with steps. No vendor calls.

| Origin (lat, lon) | Destination (lat, lon) | Distance, m | Duration, s | Observation |
| --- | --- | ---: | ---: | --- |
| 56.01, 92.85 | 56.012, 92.862 | 2214.8 | 219.3 | Short city road journey; straight-line sanity distance 778.39 m |
| 56.01, 92.85 | 56.06, 92.91 | 8492.4 | 758.4 | Medium city journey; straight-line sanity distance 6693.60 m |
| 56.01, 92.85 | 55.985, 92.90 | 6354.7 | 634.5 | River crossing: named step **Коммунальный мост**, straight-line sanity distance 4170.69 m |
| 56.01, 92.85 | 56.01, 92.85 | 0 | 0 | Genuine engine result at identical snapped road endpoints |

All repeated facts/geometries were identical. Geometry starts/ends within 2 m
of reported snapped endpoints. Origin snap offset 25.33 m; destination offsets
35.87 / 3.98 / 34.26 / 25.33 m. No straight-line travel metric is returned.

Adapter latency on this Windows/Docker machine: first short request 446.56 ms;
subsequent measured requests 249.89–295.85 ms. These include HTTP client setup
and local container transport, **not** process cold-start or an SLA. No cache.
PT source-blocked result 0.126 ms, zero provider calls; this is not PT routing
latency. No real PT routes were tested because access/data remain blocked.

Recorded real road responses (`backend/tests/fixtures/mobility_osrm.json`)
retain actual metrics, geometry, waypoints and graph identity; step arrays are
omitted. Unit/provider tests need no network or credentials. Explicit replay:

```powershell
docker build -f backend/data/routing/Dockerfile -t mesto-routing-check backend
docker run --detach --name mesto-routing-check --publish 127.0.0.1:18500:5000 mesto-routing-check
cd backend
python -m data.routing.verify --url http://127.0.0.1:18500 --output data/raw/mobility-v1/routes
```

Offline extraction (requires the already downloaded, verified regional PBF):

```powershell
python -m pip install -e '.[routing]'
python -m data.routing.prepare_osrm data/raw/mobility-v1/siberian-fed-district.osm.pbf data/raw/mobility-v1/krasnoyarsk-car-v1.osm.pbf --source-sha256 b6ba648e37c3515abfc05b94d6d69e1a69c941644de56faf83573b84be06558f
```

The extractor refuses to overwrite existing output or accept a checksum
mismatch. Generation is explicit and offline; it is not an API behavior.

## Minimal UI, testing and invariance

`/district` → choose source coordinate in existing Local/map → “Добавить важное
место” → label/type/destination coordinate → CAR or PT → “Рассчитать поездку”.
CAR displays minutes and km, “без учёта текущих пробок” and access-time exclusion.
PT displays a source-unavailable message with no residual CAR numbers.
One destination exists only in component/request state, never persisted.
Desktop 1440 and mobile 390/360 use the same component; modes stack vertically.
There is no map redesign, commute history, score or ranking integration.

Regression checks cover the existing Objective V2, Local, legacy Match,
Market/Affordability/Growth and CIAN behavior. Their modules, models, migrations,
normalizations, reference artifacts, data and fixtures remain unchanged.
Only the new router is registered in the application and the new panel inserted
in the existing district page. E2E uses the same real pinned routing container.
No additional external-provider service is required for ordinary backend CI.

Publication checks: complete pytest on migrated PostgreSQL/PostGIS with required
integration execution, lint/tsc/build, existing plus Mobility Chromium E2E,
production Compose validation and diff/secret review. Publication results and
commit/PR/main checks are recorded in the task report, not invented here.

## Next step

Housing remains WAITING FOR EISZH ACCESS. With authorized access, Housing
Foundation V1 can proceed. Otherwise Full Match V2 Foundation is a separate
future task using factual Local/Mobility/Affordability evidence. Neither is
implemented by Mobility V1.
