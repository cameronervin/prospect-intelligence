# LangChain deployed-engineer take-home

This repository contains a reviewable freight prospect-intelligence MVP. It combines typed FastAPI
contracts, a compiled LangGraph and Deep Agents workflow, durable PostgreSQL work and review state, a
polished Next.js experience, offline evaluator contracts, and a separate `agent_quality` feature.

Repository verification uses credential-free model and source fakes. It demonstrates the application
topology, permissions, persistence, and human-review behavior, but is not evidence of live model
quality or production readiness. Credentialed provider smoke tests, LangSmith experiments, judge
calibration, and deployment evidence remain separate delivery work.

## Start here

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22, npm 10, Docker Compose v2, and Git.

```sh
make setup
make verify
make docker-up
```

Open the frontend at `http://localhost:3000`. The backend exposes:

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/accounts`
- `POST /api/v1/prospect-runs`
- `GET /api/v1/prospect-runs/{run_id}`
- `POST /api/v1/prospect-runs/{run_id}/review`

## Repository map

```text
backend/       FastAPI, LangGraph/LangSmith, PostgreSQL, migrations, tests
frontend/      Next.js health-connected application shell
deploy/        Compose and non-root production images
docs/          Assignment, architecture, setup, evaluation, and delivery notes
scripts/       Repository-wide automation
.agents/       Path-scoped rules and reusable coding-agent skills
.codex/        Project-scoped Codex MCP configuration
```

See [system architecture](docs/architecture/system.md), [local setup](docs/development/setup.md), and [evaluation guidance](docs/evaluation/README.md).
