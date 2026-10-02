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

This starts PostgreSQL in Docker, applies the Alembic migrations, idempotently seeds the fictional
demo user, and runs FastAPI and Next.js locally. Alternatively, run the full non-root stack:

```sh
cp deploy/envs/.env.local.example deploy/envs/.env.local
make docker-up
make seed-demo-data
```

If an existing ignored `.env.local` predates the authentication settings, refresh it from the
example or add `TAKEHOME_DEMO_AUTH_ENABLED=true` and a local-only random
`TAKEHOME_JWT_SIGNING_SECRET` of at least 32 bytes before rebuilding the stack.

The seed command is deliberately separate from migrations so deploys never create application users
implicitly. It stores only a newly generated Argon2 hash in `auth_users`. `make dev` runs the command
automatically and supplies the documented local-only signing value when none is exported; other
development launch paths must set `TAKEHOME_JWT_SIGNING_SECRET` to at least 32 random bytes. Open
`/login` and use `alex.morgan@example.test` / `prospect-demo`. The BFF retains the JWT only in an
HttpOnly cookie.
`TAKEHOME_RUNTIME_JEV_GUARDRAILS_ENABLED` defaults to `false`; enabling it also requires
`TYPESAFE_API_KEY` and adds synchronous provider latency to each run.

For container-only development with backend and frontend reload, use the same Compose project and
PostgreSQL volume as the immutable stack:

```sh
make docker-dev-up
```

The development override mounts only backend application source and frontend source/configuration,
all read-only. Dependencies remain baked into the images and Next.js writes only to an in-memory
`.next` filesystem. Restore the immutable production-style services when finished:

```sh
make docker-prod-restore
```

Both commands may recreate the application containers but preserve the existing PostgreSQL volume.
`make test-e2e` reuses a standard stack only when its containers are healthy, explicitly marked as
E2E-safe, and labeled with the current workspace source fingerprint. If any other standard stack is
present, the command fails instead of starting a parallel project. When no standard stack exists, it
creates and removes an isolated E2E project.

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

## Semantic evaluator smoke

Repository tests and CI keep model providers offline. To exercise the CAM-39 semantic integration
against synthetic, sanitized state, run this explicit live smoke from `backend/`:

```sh
TYPESAFE_API_KEY=... OPENAI_API_KEY=... \
  uv run python -m evaluation.experiments.semantic_smoke --live
```

The command requires `--live` and both provider credentials. It uses LangSmith
`aevaluate(upload_results=False)`, so it neither creates a hosted experiment nor requires
`LANGSMITH_API_KEY`. It prints sanitized metadata only. Never place credentials in tracked files,
shell history, committed output, or screenshots.

The smoke proves that the Jev, GPT-5.6 Sol comparison, and failure-explanation provider paths work at
the time of execution. It does not prove a hosted LangSmith experiment, replace `make verify`, or
establish semantic promotion thresholds; CAM-41 owns human calibration and threshold selection.

## Hosted experiment evidence

The CAM-40 `freight-prospect-v1` hosted matrix is archived, read-only historical evidence for the v1
graph and prompt revisions. The old `evaluation.experiments.offline --live` path now fails closed
before publishing or calling a provider; do not use it to evaluate outreach-v2 or interpret its
retained results as v2 evidence. A future hosted v2 run requires a separately reviewed dataset,
experiment plan, revision metadata, and explicit authorization. Never place credentials in tracked
files, shell history, committed output, or screenshots.

The credential-free CAM-38 repository gate remains available with
`uv run python -m evaluation.experiments.offline`. Passing repository checks does not imply a
successful hosted run, and historical hosted evidence does not replace `make verify`.

## Online quality operations

Preview the complete owned LangSmith resource plan without credentials or external writes:

```sh
make online-quality-plan
```

Live setup requires `LANGSMITH_API_KEY` and a credential-free HTTPS
`TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL`. Simulation needs only the LangSmith key. Each mutation is
separately gated by `--execute` in the Make target:

```sh
make online-quality-setup
make online-quality-simulate
make online-quality-teardown
```

Normal teardown preserves `freight-prospect-online` and its traces. Use the CLI directly with
`--delete-project-and-traces` only when trace destruction is intentional. Never put the
API key, webhook URL, alert payloads, traces, or browser artifacts into repository evidence.
