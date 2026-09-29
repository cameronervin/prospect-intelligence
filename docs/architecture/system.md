# System architecture

## Current boundary

The repository now includes a deterministic freight prospect-intelligence slice. The Next.js client
creates and polls runs through FastAPI; PostgreSQL stores run, worker, review, receipt, preference,
checkpoint, and cross-run memory state. The current worker executes the deterministic pipeline; the
credentialed LangGraph topology remains a later ticket.

```text
Browser -> Next.js -> FastAPI API -> prospect services -> PostgreSQL job/run state
                                     |                     ^
                                     v                     |
                              two-slot worker -> deterministic pipeline

api -> services / agents -> contracts / domain
                            ^             ^
                repositories / integrations
```

## Backend ownership

- `bootstrap` constructs concrete dependencies and owns application lifecycle.
- `platform` owns HTTP, configuration, database, observability, and agent-runtime mechanics without product rules.
- `shared_kernel` contains only concepts that are genuinely universal.
- `features/<name>` owns all business behavior and persistence for one capability.
- `evaluation` is an offline development/release harness, not a production monitoring service.

Cross-feature imports use the target feature's `public.py` or `contracts/`. Static architecture tests enforce this and prevent `platform` or `shared_kernel` from importing features.

## Agent boundary

The prospect feature owns its LangGraph state, graph seams, nodes, tools, prompts, review boundary,
thread identity, and structured result. `platform/agent_runtime` owns the lifespan-managed PostgreSQL
checkpointer/store and explicitly runs their idempotent schema setup. CAM-32 will replace the injected
deterministic handler with the compiled graph. LangSmith tracing remains disabled by default.

## Source-adapter boundary

CAM-30 uses source-specific contracts rather than a universal integration superclass. Services and
future agent tools receive a bootstrap-owned source bundle; they do not import concrete adapters.

```text
services / agent tools -> source Protocols <- synthetic private-source adapters
                                      ^     <- FAF snapshot adapter
                                      |     <- SEC / Tavily / FMCSA adapters
                                 bootstrap wiring

reviewed scenario fixtures -> synthetic source catalog -> synthetic adapters
```

Adapters normalize provider responses into typed data, source coverage, and evidence. Provider wire
payloads remain inside `integrations`. Expected unavailability is data, not an exception and never a
reason to invent facts. The run-scoped cache is isolated by run, tenant, and rep. Real CRM, GenLogs,
and carrier-network implementations remain post-MVP substitutions behind the same contracts.

The source Protocols are defined in `features/prospect_intelligence/contracts/sources.py`.
`fixtures/synthetic` owns deterministic source records, scenario construction, edge cases, and
canonical serialization used by both demo adapters and offline evaluation. The evaluation harness
itself remains under `backend/evaluation`: `datasets/freight_prospect_v1.py` projects the shared
scenarios, `datasets/golden/freight_prospect_v1.json` is the reviewed artifact, and `evaluators` and
`experiments` retain scoring and experiment configuration. Moving scenario construction into the
feature did not remove the evaluation harness; it removed a duplicate integration-shaped copy.

Carrier-network and carrier-registry adapters remain separate. The former is private operational
capacity owned by the carrier; the latter is public FMCSA identity, authority, and safety data.

## Frontend boundary

The frontend uses App Router server components. `BACKEND_BASE_URL` remains server-only. The current page exposes a sanitized ready/degraded result rather than transport exceptions or dependency details.
