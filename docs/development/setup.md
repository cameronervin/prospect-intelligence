# Local development

## Prerequisites

- Python 3.12
- uv
- Node.js 22 and npm 10
- Docker with Compose v2
- Git and GitHub CLI for repository administration

## Install and verify

```sh
make setup
make verify
```

`make verify` validates MCP configuration, provisions a disposable PostgreSQL container, runs backend formatting/lint/type/tests including database connectivity, runs frontend lint/type/tests/build, and scans for likely credentials.

## Run locally

```sh
make dev
```

This starts PostgreSQL in Docker, applies the empty Alembic head, and runs FastAPI and Next.js locally. Alternatively, run the full non-root stack:

```sh
cp deploy/envs/.env.local.example deploy/envs/.env.local
make docker-up
```

## Create a feature

Preview before writing:

```sh
make feature NAME=research_workflow DRY_RUN=1
make feature NAME=research_workflow
```

The command refuses invalid names and existing targets. Add behavior with a failing test, then wire the feature in `bootstrap` only after its contracts are defined.

## MCP setup

`mcp.json` provides portable Context7, Linear, Playwright, and LangSmith definitions. `.codex/config.toml` configures project Playwright, Linear, and LangSmith; Context7 stays in the existing user-level Codex configuration to avoid duplicate transport definitions.

Export `LANGSMITH_API_KEY` only when LangSmith MCP or live experiments are needed. The project config maps it to the `X-Api-Key` request header and never stores the value.

