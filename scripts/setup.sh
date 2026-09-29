#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command uv
require_command npm

run_in "$root/backend" uv sync --frozen
run_in "$root/frontend" npm ci

