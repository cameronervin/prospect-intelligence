#!/usr/bin/env sh

repo_root() {
  git rev-parse --show-toplevel
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: required command not found: $1" >&2
    exit 1
  fi
}

run_in() {
  directory=$1
  shift
  (
    cd "$directory"
    "$@"
  )
}

