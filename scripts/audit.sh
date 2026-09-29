#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command uv
require_command npm

requirements=$(mktemp "${TMPDIR:-/tmp}/langchain-takehome-audit.XXXXXX")
cleanup() {
  rm -f -- "$requirements"
}
trap cleanup EXIT HUP INT TERM

run_in "$root/backend" uv export \
  --frozen \
  --no-dev \
  --no-emit-project \
  --format requirements-txt \
  --no-hashes \
  --output-file "$requirements" >/dev/null
uvx pip-audit --requirement "$requirements"
run_in "$root/frontend" npm audit --omit=dev
