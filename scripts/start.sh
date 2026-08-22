#!/bin/sh
# Boot the dashboard; on a cold start with an empty store, kick off one
# pipeline run in the background so visitors see live data, not an
# empty page. (Free-tier hosts wipe the filesystem on every restart.)
set -e

# Free-tier hosts wipe the disk on every restart. Seed from the committed
# snapshot first so the page has data on the very first request, instead of
# spending scraping credits on every cold start.
if [ ! -s data/radar.db ] && [ -s data/seed.db ]; then
  echo "cold start — seeding store from data/seed.db"
  cp data/seed.db data/radar.db
fi

(
  sleep 5
  if [ ! -s data/radar.db ]; then
    echo "store is empty — running initial scrape"
    python -m radar.pipeline || true
  fi
) &

exec uvicorn dashboard.app:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
