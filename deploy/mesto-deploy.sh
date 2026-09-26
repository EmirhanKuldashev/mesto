#!/usr/bin/env bash
set -euo pipefail

cd /opt/mesto
exec 9>/tmp/mesto-deploy.lock
flock -n 9 || exit 0

git fetch --quiet origin main
target=$(git rev-parse origin/main)
deployed=$(cat .deployed-sha 2>/dev/null || true)
if [[ "$target" == "$deployed" ]]; then
  exit 0
fi

if ! python3 deploy/ci_success.py "$target"; then
  echo "MESTO CI has not passed for $target; deployment postponed"
  exit 0
fi

git checkout --quiet --detach "$target"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans

for attempt in $(seq 1 36); do
  if curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8000/health >/dev/null 2>&1 &&
     curl --fail --silent --show-error --max-time 5 --resolve mesto.sbs:443:127.0.0.1 https://mesto.sbs/ >/dev/null 2>&1; then
    printf '%s\n' "$target" > .deployed-sha
    echo "MESTO deployed $target"
    exit 0
  fi
  sleep 5
done

echo "MESTO did not pass health checks after deployment" >&2
exit 1
