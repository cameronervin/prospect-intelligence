#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)

rm -rf -- \
  "$root/backend/.pytest_cache" \
  "$root/backend/.ruff_cache" \
  "$root/backend/.mypy_cache" \
  "$root/frontend/.next" \
  "$root/frontend/coverage" \
  "$root/frontend/test-results" \
  "$root/frontend/playwright-report"

find "$root/backend" -type d -name __pycache__ -prune -exec rm -rf -- {} +

if [ "${CLEAN_VOLUMES:-0}" = "1" ]; then
  docker compose \
    --env-file "$root/deploy/envs/.env.local.example" \
    -f "$root/deploy/compose/compose.yml" \
    down --volumes --remove-orphans
  echo "removed generated caches and local Compose volumes"
else
  echo "removed generated caches; local database volume was preserved"
fi

