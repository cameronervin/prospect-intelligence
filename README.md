# LangChain deployed-engineer take-home

This repository contains a reviewable freight prospect-intelligence MVP. It combines FastAPI,
LangGraph and Deep Agents, PostgreSQL, Next.js, offline evaluation, and opt-in LangSmith quality
delivery. A sales rep researches an assigned shipper, reviews an evidence-backed brief, and approves,
edits, or rejects a draft. Approval records a simulated send; it does not contact a prospect or write
to a CRM.

Repository verification uses credential-free model and source fakes. It demonstrates topology,
permissions, persistence, and human-review behavior, but is not evidence of live model quality or
production readiness. Credentialed provider and LangSmith evidence is documented separately.

## Verify without credentials

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js `>=22.12.0`, npm 10,
Docker Compose v2, and Git.

```sh
make setup
make verify
```

`make verify` uses model and source fakes, a disposable PostgreSQL container, and the credential-free
offline evaluator. It does not call model providers or publish a LangSmith experiment.

## Run the live-model demo

Copy the backend environment template, replace the JWT signing placeholder with at least 32 random
bytes, and set a valid OpenAI API key:

```sh
cp backend/.env.example backend/.env
# Edit backend/.env: TAKEHOME_JWT_SIGNING_SECRET and OPENAI_API_KEY
make dev
```

`make dev` starts PostgreSQL, runs migrations, seeds the fictional user and assigned Sysco account,
and starts both applications. Open `http://localhost:3000/login` and sign in with
`alex.morgan@example.test` / `prospect-demo`.

Browser authentication uses same-origin routes at `/api/auth/login`, `/api/auth/refresh`,
`/api/auth/session`, and `/api/auth/logout`. The backend exposes:

- `GET /health/live`
- `GET /health/ready`
- `POST /api/v1/auth/token`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/accounts`
- `POST /api/v1/prospect-runs`
- `GET /api/v1/prospect-runs/{run_id}`
- `POST /api/v1/prospect-runs/{run_id}/review`

See [local setup](docs/development/setup.md) for the Compose path and optional external-source or
online-quality credentials.

## Repository map

```text
backend/       FastAPI, LangGraph/LangSmith, PostgreSQL, migrations, tests
frontend/      Next.js prospect review console
deploy/        Compose and non-root production images
docs/          Assignment, architecture, setup, evaluation, and delivery notes
scripts/       Repository-wide automation
.agents/       Path-scoped rules and reusable coding-agent skills
.codex/        Project-scoped Codex MCP configuration
```

## Share the handover

Create handover archives from a committed revision, not from the working directory. This excludes
ignored environment files, local databases, caches, and generated browser artifacts:

```sh
git archive --format=zip --output ../langchain-takehome.zip HEAD
```

Start with the [documentation index](docs/README.md), [system architecture](docs/architecture/system.md),
and [evaluation results](docs/evaluation/README.md).
