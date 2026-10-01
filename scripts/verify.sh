#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command uv
require_command npm
require_command python3
require_command docker

python3 - <<'PY'
import json
import pathlib
import tomllib

root = pathlib.Path.cwd()
json.loads((root / "mcp.json").read_text())
tomllib.loads((root / ".codex/config.toml").read_text())
PY

postgres_container="langchain-takehome-verify-postgres-$$"
offline_report=$(mktemp "${TMPDIR:-/tmp}/langchain-takehome-offline.XXXXXX")
cleanup() {
  docker rm --force "$postgres_container" >/dev/null 2>&1 || true
  rm -f "$offline_report"
}
trap cleanup EXIT HUP INT TERM

docker run --detach \
  --name "$postgres_container" \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid \
  --env POSTGRES_USER=takehome \
  --env POSTGRES_PASSWORD=takehome-test \
  --env POSTGRES_DB=takehome_test \
  --publish 127.0.0.1::5432 \
  postgres:16-alpine >/dev/null

attempt=0
until docker exec "$postgres_container" pg_isready --username takehome --dbname takehome_test >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "error: disposable PostgreSQL was not ready within 30 seconds" >&2
    exit 1
  fi
  sleep 1
done

postgres_port=$(docker inspect --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' "$postgres_container")
export TAKEHOME_TEST_DATABASE_URL="postgresql+psycopg://takehome:takehome-test@127.0.0.1:$postgres_port/takehome_test"

run_in "$root/backend" sh scripts/check.sh
run_in "$root/backend" uv run python -m evaluation.experiments.offline --report "$offline_report"
run_in "$root/frontend" npm run check
sh "$root/scripts/secret-scan.sh"
