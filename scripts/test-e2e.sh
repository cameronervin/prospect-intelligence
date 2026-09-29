#!/usr/bin/env sh

set -eu
. "$(dirname -- "$0")/common.sh"

root=$(repo_root)
require_command npm
run_in "$root/frontend" npm run test:e2e

