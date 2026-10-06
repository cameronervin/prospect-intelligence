# Path to production

The [detailed production plan](path-to-production.md) lists the required hardening and rollout
sequence. The [product ROI model](product-roi.md) records the pilot conversion and cost assumptions;
it is not a production-readiness or guaranteed-revenue claim.

The current repository is a reviewable MVP, not a production system. It implements a compiled agent
runtime, durable work and review state, database and prospect-runtime readiness checks, and
redacted structured stdout logging with correlation across the Next.js and FastAPI server
boundaries. A production proposal must still decide and test:

- Enterprise identity for users, services, and agent tools.
- Tenant identity propagation and isolation in database rows, checkpoints, traces, datasets, caches, and logs.
- State ownership, checkpoint retention, deletion, replay, and concurrent-run behavior.
- Human-review authorization, expiration, audit history, and safe resume semantics.
- Tool allowlists, scoped credentials, input/output validation, idempotency, timeouts, retries, and compensation.
- Model/provider routing, budgets, prompt/version governance, fallbacks, and degraded behavior.
- Offline release gates and online quality, safety, latency, cost, and dependency monitoring.
- Secret management, trace privacy, encryption, backups, migration compatibility, incident response, and rollback.
- Capacity, queueing, rate limits, autoscaling, regional needs, and support ownership.

The logging slice is intentionally collector-neutral. A production deployment must still choose
central aggregation, access controls, retention and deletion policy, alert routing, sampling, and
service-level objectives. Browser telemetry, OpenTelemetry exporters, and error-monitoring vendors
remain deferred until that deployment target and its privacy requirements are known.

Each claim in a stakeholder presentation should identify its evidence class: repository tests, a
LangSmith experiment, a credentialed provider run, or dated deployment evidence. Repository tests
establish implementation behavior only; they do not establish live-model quality or production
operation.
