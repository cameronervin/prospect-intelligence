#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command npm
require_command docker

env_file="$root/deploy/envs/.env.local.example"
compose_file="$root/deploy/compose/compose.yml"
e2e_compose_file="$root/deploy/compose/compose.e2e.yml"
project_name="langchain-takehome-e2e-$$"

if ! docker compose version >/dev/null 2>&1; then
  echo "error: Docker Compose is required" >&2
  exit 1
fi
for required_file in "$env_file" "$compose_file" "$e2e_compose_file"; do
  if [ ! -f "$required_file" ]; then
    echo "error: required E2E file not found: $required_file" >&2
    exit 1
  fi
done

docker compose \
  --env-file "$env_file" \
  --project-name "$project_name" \
  --file "$compose_file" \
  --file "$e2e_compose_file" \
  config --quiet

cleanup() {
  docker compose \
    --env-file "$env_file" \
    --project-name "$project_name" \
    --file "$compose_file" \
    --file "$e2e_compose_file" \
    down --volumes --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

run_in "$root/frontend" npm run test:e2e:mocked

docker compose \
  --env-file "$env_file" \
  --project-name "$project_name" \
  --file "$compose_file" \
  --file "$e2e_compose_file" \
  up --build --detach --wait

e2e_frontend_binding=$(docker compose \
  --env-file "$env_file" \
  --project-name "$project_name" \
  --file "$compose_file" \
  --file "$e2e_compose_file" \
  port frontend 3000)
e2e_frontend_port=${e2e_frontend_binding##*:}
case "$e2e_frontend_port" in
  ''|*[!0-9]*)
    echo "error: could not resolve the E2E frontend port" >&2
    exit 1
    ;;
esac
PLAYWRIGHT_BASE_URL="http://127.0.0.1:$e2e_frontend_port"
export PLAYWRIGHT_BASE_URL

run_in "$root/frontend" npm run test:e2e:full-stack
