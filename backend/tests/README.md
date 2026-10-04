# Backend test baseline

Run from `backend/` with Python 3.12 and `python -m pip install -e '.[test,scrape]'`.
Browser binaries are unnecessary: scraper tests exercise extraction without launching a browser.

## Full baseline

Use a **disposable** PostgreSQL 16 / PostGIS 3.4 database. For example:

```sh
docker run --name mesto-test-postgis -e POSTGRES_USER=mesto_test \
  -e POSTGRES_PASSWORD=disposable_test_password -e POSTGRES_DB=mesto_test \
  -p 127.0.0.1:55433:5432 -d postgis/postgis:16-3.4
export MESTO_TEST_DATABASE_URL=postgresql+psycopg://mesto_test:disposable_test_password@127.0.0.1:55433/mesto_test
export DATABASE_URL="$MESTO_TEST_DATABASE_URL"
export MESTO_REQUIRE_TEST_DATABASE=1
python -m alembic upgrade head
python -m pytest -q -rs
python -m pytest -q -m integration -rs
```

Wait for `pg_isready -U mesto_test -d mesto_test` in the container before migrating.
These credentials are disposable test values, not application secrets.

CI supplies both URLs to the same PostGIS service, migrates before pytest, and
sets `MESTO_REQUIRE_TEST_DATABASE=1`. Missing URLs fail configuration, connection
or migration errors fail setup, and skipping a marked integration test fails CI.
The database revision is compared to the actual Alembic script head, not a
hardcoded historical revision. The single-head requirement is also checked.

Session setup loads existing demo sources, OSM districts and the explicit packaged
fresh baseline `fresh-20261004T132116Z` (2,387 POIs). Historical legacy regression
tests use a separate disposable database with the unchanged 1,988-POI fixture;
the DB role needs CREATE DATABASE, as for migration roundtrip tests. Publication
tests independently migrate an empty DB and verify clean startup, checksums,
idempotency, current score outputs and bbox without collection/raw storage.
This makes catalogue, profile and AI context tests independent of test order and
external services. Tests use real PostGIS operations. Never point these URLs at production or
a database containing data that must be preserved.

For optional local unit-only work without a DB, leave the strict flag unset:
`python -m pytest -q -m 'not integration'`. A full run without a test URL skips
integration checks locally and is **not** evidence of a passing full baseline.
