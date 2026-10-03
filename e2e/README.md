# MESTO Chromium smoke-test

Requires Docker Compose v2, Node.js 22 and npm. Run from the repository root:

```sh
npm ci
npx --no-install playwright install chromium
npm run e2e:up
npm run e2e
npm run e2e:down
```

Always run e2e:down, including after failure. It removes only the mesto-e2e
project. Ports 3100 and 18100 must be free; the development stack on 3000/8000
is independent. Never combine E2E Compose with production Compose.

The stack uses the production Dockerfiles, PostGIS 16/3.4 and a fresh tmpfs
database. Backend startup runs Alembic upgrade head and imports committed
OSM/Cian snapshots through the existing bootstrap. Runtime services have an
dedicated Compose network and no Orca key. Building images/installing tooling needs
network access; bootstrap and the browser scenario do not.

The test fills all ten onboarding steps, verifies the saved profile through a
separate API read, checks real scoring/recommendations, observes the natural
AI 503 response, and opens a recommended district and its MapLibre canvas.
Only external OSM raster tiles are fulfilled with the local PNG fixture;
district geometry, POIs and all MESTO APIs remain real. Other external browser
requests are blocked and fail the test.

No exact score, district ranking or screenshot is pinned. Browser contexts are
fresh per test; start from a new stack for a clean database run. CI uses a
unique Compose project, waits for service health, retries once and uploads
failure traces/screenshots/video and container logs before cleanup.
