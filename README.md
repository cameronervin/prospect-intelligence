# LangChain deployed-engineer take-home

This private repository is a domain-neutral foundation for the LangChain Deployed Engineer take-home. It combines a feature-first FastAPI/LangGraph backend, a minimal Next.js application shell, PostgreSQL durability, LangSmith-ready evaluation plumbing, and a compact coding-agent harness.

The scaffold deliberately contains no product feature, sample agent, model provider, authentication scheme, or evaluation metric. Those decisions belong to the selected enterprise problem.

## Start here

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22, npm 10, Docker Compose v2, and Git.

```sh
make setup
make verify
make docker-up
```

Open the frontend at `http://localhost:3000`. The backend exposes only:

- `GET /health/live`
- `GET /health/ready`

Create a feature package after the product domain is selected:

```sh
make feature NAME=case_management DRY_RUN=1
make feature NAME=case_management
```

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

