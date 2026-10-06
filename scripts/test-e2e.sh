#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command docker
require_command python3
require_command rg

env_file="$root/deploy/envs/.env.local.example"
standard_env_file="$root/deploy/envs/.env.local"
[ -f "$standard_env_file" ] || standard_env_file="$env_file"
compose_file="$root/deploy/compose/compose.yml"
e2e_compose_file="$root/deploy/compose/compose.e2e.yml"
project_name="langchain-takehome-e2e-$$"
selection_only=${1:-}

case "$selection_only" in
  ''|--stack-selection) ;;
  *)
    echo "usage: $0 [--stack-selection]" >&2
    exit 2
    ;;
esac

workspace_source_id() {
  python3 "$root/scripts/copy-reviewable-snapshot.py" --source-id "$root"
}

source_id_is_explicit=true
if [ -z "${TAKEHOME_E2E_SOURCE_ID:-}" ]; then
  source_id_is_explicit=false
  TAKEHOME_E2E_SOURCE_ID=$(workspace_source_id)
  export TAKEHOME_E2E_SOURCE_ID
fi

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

standard_stack_selection() {
  existing=$(docker compose \
    --env-file "$standard_env_file" \
    --file "$compose_file" \
    ps --all --quiet)
  if [ -z "$existing" ]; then
    echo "isolated"
    return 0
  fi
  if [ -n "${CI:-}" ] && [ "${CI:-}" != "false" ]; then
    echo "error: a standard stack is already present; refusing to start a parallel CI E2E project" >&2
    return 1
  fi

  for service in postgres backend frontend; do
    container_id=$(docker compose \
      --env-file "$standard_env_file" \
      --file "$compose_file" \
      ps --all --quiet "$service")
    if [ -z "$container_id" ] ||
      [ "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" != "healthy" ]; then
      echo "error: the standard stack is present but not fully healthy; refusing a parallel E2E project" >&2
      return 1
    fi
  done

  for service in backend frontend; do
    container_id=$(docker compose \
      --env-file "$standard_env_file" \
      --file "$compose_file" \
      ps --all --quiet "$service")
    identity=$(docker inspect \
      --format '{{index .Config.Labels "com.langchain-takehome.e2e-safe"}}|{{index .Config.Labels "com.langchain-takehome.e2e-source-id"}}' \
      "$container_id")
    if [ "$identity" != "true|$TAKEHOME_E2E_SOURCE_ID" ]; then
      echo "error: the healthy standard stack is not explicitly E2E-safe and current; refusing a parallel E2E project" >&2
      return 1
    fi
  done

  echo "reuse"
}

if ! stack_selection=$(standard_stack_selection); then
  exit 1
fi
if [ "$selection_only" = "--stack-selection" ]; then
  echo "$stack_selection"
  exit 0
fi

require_command npm

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

if [ "$source_id_is_explicit" = "false" ]; then
  refreshed_source_id=$(workspace_source_id)
  if [ "$refreshed_source_id" != "$TAKEHOME_E2E_SOURCE_ID" ]; then
    TAKEHOME_E2E_SOURCE_ID=$refreshed_source_id
    export TAKEHOME_E2E_SOURCE_ID
    if ! stack_selection=$(standard_stack_selection); then
      exit 1
    fi
  fi
fi

if [ "$stack_selection" = "reuse" ]; then
  echo "Reusing the healthy langchain-takehome stack for full-stack browser tests."
  trap - EXIT HUP INT TERM
  e2e_frontend_binding=$(docker compose \
    --env-file "$standard_env_file" \
    --file "$compose_file" \
    port frontend 3000)
else
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
fi
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
