# LangChain deployed-engineer take-home

This repository is the implementation-ready scaffold for a freight prospect-intelligence take-home.
It combines typed FastAPI contracts, a Playbook-style Deep Agents layer, a credential-free fixture
worker, PostgreSQL persistence seams, a polished Next.js workflow, offline evaluator contracts, and a
separate `agent_quality` feature.

The scaffold is intentionally not the completed assessment. Live adapters, credentialed Deep Agents
execution, LangSmith experiments/provisioning, Jev calibration, and full-stack acceptance evidence are
tracked in Linear and must replace the documented seams.

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
