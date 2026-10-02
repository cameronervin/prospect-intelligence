#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command docker

action=${1:-}
compose_file="$root/deploy/compose/compose.yml"
dev_compose_file="$root/deploy/compose/compose.dev.yml"
env_file="$root/deploy/envs/.env.local"
if [ ! -f "$env_file" ]; then
  env_file="$root/deploy/envs/.env.local.example"
fi

case "$action" in
  config)
    docker compose --env-file "$env_file" -f "$compose_file" config --quiet
    docker compose --env-file "$env_file" -f "$compose_file" -f "$dev_compose_file" config --quiet
    TAKEHOME_E2E_SOURCE_ID=config-validation docker compose \
      --env-file "$env_file" \
      -f "$compose_file" \
      -f "$root/deploy/compose/compose.e2e.yml" \
      config --quiet
    ;;
  up)
    docker compose --env-file "$env_file" -f "$compose_file" up --build --detach --wait
    ;;
  down)
    docker compose --env-file "$env_file" -f "$compose_file" down --remove-orphans
    ;;
  dev-up)
    docker compose \
      --env-file "$env_file" \
      -f "$compose_file" \
      -f "$dev_compose_file" \
      up --build --detach --wait --remove-orphans
    ;;
  prod-restore)
    docker compose \
      --env-file "$env_file" \
      -f "$compose_file" \
      up --build --detach --wait --remove-orphans
    ;;
  *)
    echo "usage: $0 {config|up|down|dev-up|prod-restore}" >&2
    exit 2
    ;;
esac
