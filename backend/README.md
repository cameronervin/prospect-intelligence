# Backend

This package is a domain-neutral FastAPI foundation for future LangGraph features. It owns application assembly, shared technical capabilities, PostgreSQL connectivity, and architecture enforcement. It does not contain a product feature or initialize LangGraph checkpoint tables.

## Development

```sh
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.bootstrap.api:create_app --factory --reload
```

The API exposes `/health/live` and `/health/ready`. Readiness checks PostgreSQL.

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

Set `TAKEHOME_TEST_DATABASE_URL` to a disposable PostgreSQL database to include the integration test. The integration test never creates product tables.

