# System architecture

## Current boundary

The repository includes a working freight prospect-intelligence agent slice. The Next.js client
creates and polls runs through FastAPI; PostgreSQL stores run, worker, review, receipt, preference,
checkpoint, and cross-run memory state. Two durable worker slots share one process-wide runtime: an
outer LangGraph invokes a root Deep Agent that delegates to four explicit specialist Deep Agents and
pauses at a named outreach interrupt.

```text
Browser -> Next.js -> FastAPI API -> prospect services -> PostgreSQL job/run state
                                     |                     ^
                                     v                     |
                              two-slot worker -> compiled agent graph

api -> services / agents -> contracts / domain
                            ^             ^
                repositories / integrations
```

## Backend ownership

- `app/main.py` is the FastAPI application factory and ASGI entrypoint.
- `bootstrap` constructs concrete dependencies and owns application lifecycle through its container,
  wiring, lifespan, middleware, and exception-handler modules.
- `platform` owns HTTP, configuration, database, observability, and agent-runtime mechanics without product rules.
- `shared_kernel` contains only concepts that are genuinely universal.
- `features/<name>` owns all business behavior and persistence for one capability.
- `evaluation` is an offline development/release harness, not a production monitoring service.

Cross-feature imports use the target feature's `public.py` or `contracts/`. Static architecture tests enforce this and prevent `platform` or `shared_kernel` from importing features.

## Agent boundary

The prospect feature keeps each agent concept explicit without single-module package nesting:

```text
agents/
  chains.py       prompts.py      specs.py
  graphs.py       compiler.py     state.py
  tools.py        guardrails.py   runtime.py
  context.py      middleware/     skills/
```

`chains.py` creates the Deep Agents, `graphs.py` defines the outer workflow, and `compiler.py` is the
only module that assembles and compiles the complete runtime. `state.py` contains checkpointed graph
data; `context.py` provides access to the non-checkpointed LangGraph runtime context, including the
scoped bridge required by compiled isolated subagents. Middleware and SDK-formatted skills remain
nested because each is a meaningful multi-file boundary.

The feature owns the four-specialist topology, tools, prompts, filesystem permissions, review
boundary, thread identity, typed runtime, and structured result. The root Deep Agent is the only
specialist scheduler. The outer graph prepares state, invokes that root, and finalizes completion; it
never invokes specialists.
`platform/agent_runtime` owns the lifespan-managed PostgreSQL checkpointer/store and explicitly runs
their idempotent schema setup. `platform/llm` owns Settings-selected provider models and transports.
Bootstrap constructs those platform resources, calls the feature compiler once after persistence
starts, and injects its async runtime into both durable worker slots.
Source adapters and model transports remain separate dependency groups. LangSmith tracing remains
disabled by default.

Agent middleware is the feature's context-engineering boundary: it projects allowlisted context,
enforces delegation and budget policy, guards tool calls, and validates artifacts. Platform trace
privacy hides every nested run's inputs, outputs, and metadata. `state`
refers only to checkpointed LangGraph data; tenant/rep scope and injected handlers
travel through non-checkpointed runtime context. See
[`ADR 0003`](decisions/0003-deep-agent-runtime-composition.md) for the construction and ownership
decision.

The lane analyst alone receives the packaged `lane_fit_v1` skill through a read-only `/skills/`
mount. Other specialists cannot discover or read it. Review requests resume the durable
`send_outreach` interrupt; there is no service-layer review fallback. If that graph handler is not
available, the API returns retryable `503 service_unavailable` rather than recording a decision
outside the graph.

## Lifecycle and readiness

Startup initializes PostgreSQL, starts checkpoint/store resources, compiles the prospect runtime,
constructs the durable review handler and two-slot worker supervisor, and only then marks the prospect
component ready. `GET /health/ready` requires both database health and that fully started component
when prospect routes are enabled. Shutdown closes resources in reverse dependency order.

Specialist progress flows in five hops:

1. The orchestrator's `ProgressMiddleware` observes each `task` delegation. The source-tool boundary
   in `agents/tools.py` observes each source call.
2. Both emit sanitized `ProgressSignal`s to a request-scoped sink on `ProspectRuntimeContext`.
3. The worker's `RunProgressSink` (in `services/progress.py`) serializes those signals into
   lease-guarded writes.
4. The writes land in the `prospect_runs.steps` JSONB column.
5. The browser reads the steps through the existing `GET /prospect-runs/{id}` poll.

Progress writes are best-effort and never fail a run.

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

The frontend uses App Router; the review console is one client component tree behind a same-origin `/api/v1` proxy. `BACKEND_BASE_URL` remains server-only. When the backend is unreachable the proxy returns the typed `service_unavailable` envelope, so the browser never sees transport exceptions or dependency details.
