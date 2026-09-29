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

## Prospect API

All `/api/v1` requests require `X-Tenant-Id` and `X-Rep-Id`. The demo UI uses synthetic scope IDs;
these headers are routing and isolation inputs, not a production authentication scheme. Accounts are
tenant-scoped. Runs are tenant-and-rep-scoped, and an unknown or out-of-scope account/run returns the
same sanitized `404 not_found` envelope.

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/v1/accounts` | `200` | List accounts visible to the tenant. |
| `POST` | `/api/v1/prospect-runs` | `202` | Atomically persist and enqueue `{ "account_id": "acme-foods" }`. |
| `GET` | `/api/v1/prospect-runs/{run_id}` | `200` | Poll the durable run. |
| `POST` | `/api/v1/prospect-runs/{run_id}/review` | `200` | Resume the pending outreach interrupt. |

Run status describes execution, independently of the freight verdict:

- `queued` and `running` are pollable non-terminal states.
- `awaiting_review` exposes a draft in `outreach` and an explicit `pending_review` capability. For
  v1 that capability is `{ "name": "send_outreach", "allowed_decisions": ["approve", "edit",
  "reject"], "tool_call_id": "review-{run_id}" }`.
- `completed` may carry `fit`, `no_fit`, or `needs_more_data`; the last two complete without outreach
  review. `rejected` records the rep's terminal rejection. `failed` carries a sanitized run `error`.

Review requests must return the server-provided `tool_call_id` with `decision: "approve"`, `"edit"`,
or `"reject"`. An edit also requires both `subject` and `body`; approve and reject accept neither.
The token identifies the review submission and makes retries idempotent—it is not an authorization
credential. Repeating the same accepted decision returns the canonical result, while reusing the
token for a different decision returns `409 conflict`. If graph review is
temporarily unavailable, the API returns retryable `503 service_unavailable` and records nothing.

Failures use one non-disclosing envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "retryable": false,
    "issues": [{ "location": "body.account_id", "message": "Invalid value", "type": "pattern" }]
  }
}
```

The stable codes are `validation_error`, `not_found`, `conflict`, `internal_error`, and
`service_unavailable`. Validation issues identify fields but never echo submitted values; internal
errors never expose raw exceptions, prompts, credentials, or private source payloads.

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

Run the credential-free offline release gates separately:

```sh
uv run python -m evaluation.experiments.offline
```

This uses local LangSmith evaluation over the compiled scripted graph and writes only sanitized
aggregate repository evidence. It does not upload a LangSmith experiment or call a model provider.

Set `TAKEHOME_TEST_DATABASE_URL` to a disposable PostgreSQL database to run migration, repository,
worker-concurrency, restart, idempotency, checkpoint, and store-isolation integration tests. These
tests upgrade and downgrade product tables and must never target a retained database.

## Persistence limitations

The MVP retains product rows, checkpoints, and memory until they are manually deleted. Alembic owns
the feature tables and its downgrade is destructive. LangGraph owns its checkpoint/store migrations;
those tables intentionally survive the feature downgrade. The in-process PostgreSQL poller is suitable
for the local MVP, not horizontally scaled production delivery. Review serialization is likewise
process-local; a multi-replica deployment needs a durable reservation spanning graph resume and the
product-state commit before it can safely accept concurrent review decisions.
