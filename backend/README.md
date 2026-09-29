# Backend

This package contains the FastAPI foundation and the freight prospect-intelligence MVP. PostgreSQL
owns durable runs, worker claims, reviews, receipts, and preference metadata. Application startup
explicitly initializes the LangGraph PostgreSQL checkpointer and store before starting two local worker
slots.

## Development

```sh
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload
```

The API exposes `/health/live` and `/health/ready`. Readiness requires PostgreSQL and the fully
started prospect runtime when prospect routes are enabled.

## Feature creation

```sh
uv run python scripts/scaffold_feature.py research_workflow --dry-run
uv run python scripts/scaffold_feature.py research_workflow
```

Generated feature packages contain API, service, agent, domain, model, schema, repository, integration, and contract layers. They contain package documentation only; business behavior must begin with a focused test.

## Validation

```sh
sh scripts/check.sh
```

Set `TAKEHOME_TEST_DATABASE_URL` to a disposable PostgreSQL database to run migration, repository,
worker-concurrency, restart, idempotency, checkpoint, and store-isolation integration tests. These
tests upgrade and downgrade product tables and must never target a retained database.

## Persistence limitations

The MVP retains product rows, checkpoints, and memory until they are manually deleted. Alembic owns
the feature tables and its downgrade is destructive. LangGraph owns its checkpoint/store migrations;
those tables intentionally survive the feature downgrade. The in-process PostgreSQL poller is suitable
for the local MVP, not horizontally scaled production delivery.
