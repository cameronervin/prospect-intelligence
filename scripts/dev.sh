#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command docker
require_command uv
require_command npm

compose_file="$root/deploy/compose/compose.yml"
env_file="$root/deploy/envs/.env.local"
if [ ! -f "$env_file" ]; then
  env_file="$root/deploy/envs/.env.local.example"
fi

docker compose --env-file "$env_file" -f "$compose_file" up --detach postgres

export TAKEHOME_DATABASE_URL="postgresql+psycopg://takehome:takehome@127.0.0.1:5432/takehome"
run_in "$root/backend" uv run alembic upgrade head

backend_pid=
frontend_pid=
cleanup() {
  [ -z "$backend_pid" ] || kill "$backend_pid" >/dev/null 2>&1 || true
  [ -z "$frontend_pid" ] || kill "$frontend_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

(cd "$root/backend" && uv run uvicorn app.bootstrap.api:create_app --factory --reload) &
backend_pid=$!
(cd "$root/frontend" && BACKEND_BASE_URL=http://127.0.0.1:8000 npm run dev) &
frontend_pid=$!
wait "$backend_pid" "$frontend_pid"

