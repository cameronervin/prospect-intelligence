# Path to production

The current repository is a reviewable MVP, not a production system. It implements a compiled agent
runtime, durable work and review state, and full-component readiness checks with credential-free test
doubles. A production proposal must still decide and test:

- Authentication for users, services, and agent tools.
- Tenant identity propagation and isolation in database rows, checkpoints, traces, datasets, caches, and logs.
- State ownership, checkpoint retention, deletion, replay, and concurrent-run behavior.
- Human-review authorization, expiration, audit history, and safe resume semantics.
- Tool allowlists, scoped credentials, input/output validation, idempotency, timeouts, retries, and compensation.
- Model/provider routing, budgets, prompt/version governance, fallbacks, and degraded behavior.
- Offline release gates and online quality, safety, latency, cost, and dependency monitoring.
- Secret management, trace privacy, encryption, backups, migration compatibility, incident response, and rollback.
- Capacity, queueing, rate limits, autoscaling, regional needs, and support ownership.

Each claim in a stakeholder presentation should identify its evidence class: repository tests, a
LangSmith experiment, a credentialed provider run, or dated deployment evidence. Repository tests
establish implementation behavior only; they do not establish live-model quality or production
operation.
