#!/usr/bin/env sh

set -eu

uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not postgresql"

if [ -n "${TAKEHOME_TEST_DATABASE_URL:-}" ]; then
  uv run pytest -m postgresql
fi

