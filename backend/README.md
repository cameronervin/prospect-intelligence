# Backend

This package contains the FastAPI freight prospect-intelligence MVP. PostgreSQL owns durable runs,
worker claims, reviews, simulated-send receipts, preference metadata, checkpoints, and cross-run
memory. Startup initializes the LangGraph checkpointer and store before starting two local workers.

## Development

```sh
cp .env.example .env
# Set TAKEHOME_JWT_SIGNING_SECRET and OPENAI_API_KEY in .env.
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_demo_data
uv run uvicorn app.main:create_app --factory --reload
```

The API exposes `/health/live` and `/health/ready`. Readiness requires PostgreSQL and the fully
started prospect runtime when prospect routes are enabled.

## Operational logging

The backend writes structured logs to stdout: readable console records by default and JSON when
`TAKEHOME_LOG_JSON=true`. Application, standard-library, and Uvicorn error records share UTC
timestamps, severity, logger, service, and environment fields. The application replaces Uvicorn's
access log with one canonical `http_request_completed` event containing only the HTTP method,
normalized route template, status, outcome, duration, and validated `x-correlation-id`. Successful
health probes are omitted.

Startup, authentication outcomes, prospect jobs, analysis and review completion, provider retries,
readiness failures, and online-quality delivery failures add bounded operational fields. Logs never
include request or response bodies, query strings, credentials, account or contact names, prompts,
model output, provider payloads, or exception messages. LangSmith traces remain a separate evidence
and observability channel with inputs, outputs, and metadata hidden by default.

## Prospect API

Prospect routes require an HS256 demo bearer token from `POST /api/v1/auth/token`; tenant, rep,
subject, and role scope come only from verified claims. The explicit seed command creates the
fictional user, membership, contact, assigned Sysco account, and assignment in one transaction;
migrations create only schema. Browser identity and authorization headers are discarded by the
Next.js BFF. Accounts and runs are tenant/rep/subject-scoped, and an unknown or out-of-scope resource
returns the same sanitized `404 not_found` envelope. The demo credentials are
`alex.morgan@example.test` / `prospect-demo`; only an Argon2 hash is stored.

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/token` | `200` | Authenticate the fictional demo user. |
| `POST` | `/api/v1/auth/refresh` | `200` | Rotate a valid one-hour token within its eight-hour session. |
| `GET` | `/api/v1/auth/me` | `200` | Resolve the current verified user without returning the token. |
| `GET` | `/api/v1/accounts` | `200` | List accounts assigned to the authenticated actor. |
| `POST` | `/api/v1/prospect-runs` | `202` | Persist and enqueue `{ "account_id": "sysco-corporation" }`. |
| `GET` | `/api/v1/prospect-runs/{run_id}` | `200` | Poll the durable run. |
| `POST` | `/api/v1/prospect-runs/{run_id}/review` | `200` | Resume the pending outreach interrupt. |

Run status describes execution, independently of the freight verdict:

- `queued` and `running` are pollable non-terminal states.
- `awaiting_review` exposes a draft in `outreach` and an explicit `pending_review` capability. The
  capability is `{ "name": "send_outreach", "allowed_decisions": ["approve", "edit",
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

The stable codes are `unauthorized`, `forbidden`, `validation_error`, `not_found`, `conflict`,
`internal_error`, and `service_unavailable`. Validation issues identify fields but never echo
submitted values; internal errors never expose raw exceptions, prompts, credentials, or private
source payloads.

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

This evaluates the scripted v4 graph and `outreach-v4` prompt revision locally and writes only
sanitized aggregate repository evidence. It does not upload an experiment or call a model provider.

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
