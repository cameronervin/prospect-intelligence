# Local development

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js `>=22.12.0` and npm 10
- Docker with Compose v2
- Git

GitHub CLI is optional and used only for repository administration.

## Credential-free verification

```sh
make setup
make verify
```

`make verify` validates project configuration, starts a disposable PostgreSQL container, runs the
backend checks and credential-free v4 evaluator, runs the frontend checks and build, and scans the
Git-visible snapshot for likely credentials. It does not inspect ignored local environment files,
call model providers, or publish to LangSmith.

Run Desktop Chrome browser coverage separately:

```sh
make test-e2e
```

The test harness uses scripted models and synthetic data. It does not require provider keys.

## Live-model demo

Copy the backend environment template:

```sh
cp backend/.env.example backend/.env
```

In `backend/.env`, set:

- `TAKEHOME_JWT_SIGNING_SECRET` to at least 32 random bytes;
- `OPENAI_API_KEY` to a valid key for the configured models.

Then run:

```sh
make dev
```

This starts PostgreSQL, applies migrations, idempotently seeds the demo identity and its assigned
Sysco Corporation account, and starts FastAPI and Next.js. Open `http://localhost:3000/login` and use:

- Email: `alex.morgan@example.test`
- Password: `prospect-demo`

The Next.js BFF stores the backend JWT in an HttpOnly Strict cookie. Browser auth routes are
`/api/auth/login`, `/api/auth/refresh`, `/api/auth/session`, and `/api/auth/logout`. Backend auth
routes are `/api/v1/auth/token`, `/api/v1/auth/refresh`, and `/api/v1/auth/me`.

Migrations create schema only. `make dev` runs the seed command explicitly; other launch paths must
run `make seed-demo-data`. The seeded user can access only its assigned account. Approval creates a
simulated-send receipt; no email is sent and no CRM is updated.

## Compose demo

```sh
cp deploy/envs/.env.local.example deploy/envs/.env.local
# Set TAKEHOME_JWT_SIGNING_SECRET and OPENAI_API_KEY in .env.local.
make docker-config
make docker-up
make seed-demo-data
```

For container reload, use `make docker-dev-up`. Restore immutable production-style images with
`make docker-prod-restore`. Both commands keep the named PostgreSQL volume.

## Optional integrations

Private CRM, freight-intelligence, and carrier-network sources are fixtures. FAF is a packaged
snapshot. SEC, Tavily, and FMCSA adapters are disabled by default; set
`TAKEHOME_EXTERNAL_LIVE_ENABLED=true` and configure their required values before using live public
sources. Unavailable live sources fail closed and do not substitute fixture facts.

Runtime Jev guardrails are disabled by default. Enabling
`TAKEHOME_RUNTIME_JEV_GUARDRAILS_ENABLED` also requires `TYPESAFE_API_KEY` and adds provider latency.
Online-quality delivery is implemented but disabled by default; it requires LangSmith and TypeSafe
credentials. See [evaluation guidance](../evaluation/README.md) and
[online operations](../evaluation/online-operations.md) for the credential-gated commands and
evidence rules.

## Create a feature

Preview generated files before writing:

```sh
make feature NAME=research_workflow DRY_RUN=1
make feature NAME=research_workflow
```

The command rejects invalid or existing names. Add behavior with a failing focused test, then wire
the feature in `bootstrap` after defining its contracts.

## MCP configuration

`mcp.json` provides portable Context7, Linear, Playwright, and LangSmith definitions.
`.codex/config.toml` configures the project Playwright, Linear, and LangSmith servers. Export
`LANGSMITH_API_KEY` only for authorized live LangSmith work; never store credentials, traces, or
browser artifacts in tracked files.
