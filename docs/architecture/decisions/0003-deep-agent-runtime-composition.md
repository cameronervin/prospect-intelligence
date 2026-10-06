# ADR 0003: Feature-owned Deep Agent runtime composition

## Status

Accepted and implemented.

## Context

The initial prospect-agent scaffold separated definitions, chain blueprints, graph builders, and a
bootstrap-owned factory. The partial implementation left middleware metadata unused, placed
prospect-specific handlers in bootstrap, and allowed both an outer graph and an orchestrator to own
specialist scheduling. Those overlaps obscured the runtime's context, permission, and lifecycle
boundaries.

LangChain agent middleware is the feature's context-engineering boundary. LangGraph state is durable
workflow data; invocation context carries non-checkpointed dependencies. Model-provider transports
are platform resources, while prompts, tools, subagents, artifacts, and review behavior are prospect
business behavior.

## Decision

- The prospect feature keeps explicit modules for `chains`, `prompts/`, `specs`, `graphs`,
  `compiler`, `state`, `tools`, `guardrails`, `runtime`, and `context`. Only `middleware/` and
  SDK-formatted `skills/` remain nested multi-file boundaries. The compiler is the sole composition
  entry point and compiles the complete runtime once after persistence starts.
- One root Deep Agent owns delegation to exactly five declarative subagents: account context,
  external research, lane analysis, outreach drafting, and read-only quality review. Deep Agents
  compiles those definitions internally with `create_agent()`; the outer LangGraph prepares the
  run, invokes the root agent, and finalizes it but never schedules specialists itself.
- Agent middleware projects context, enforces budgets and delegation prerequisites, guards tool
  calls, and validates specialist artifacts. Platform trace privacy hides nested run payloads and
  metadata. Pure guardrail functions remain reusable at graph and persistence
  boundaries.
- `state` means checkpointed LangGraph state only. Tenant, rep, injected tools, and other private
  invocation dependencies live in `ProspectRuntimeContext`. `context.py` owns LangGraph runtime
  context access and the scoped propagation bridge required because Deep Agents 0.7.19 does not
  forward the parent's typed context to isolated declarative subagents.
- `chains.py` constructs one shared composite backend, five declarative specialist definitions, and
  the single `create_deep_agent` orchestrator. `graphs.py` creates the application workflow.
  `compiler.py` alone assembles specs, tools, middleware, the root agent, graph, persistence, and
  typed runtime.
- The packaged `lane-fit-v1` skill implements method `lane_fit_v1`, is mounted read-only at
  `/skills/`, and is supplied only to the lane
  analyst. No other specialist can discover or read it.
- The quality reviewer checks the internal brief and outreach against evidence before the named
  `send_outreach` human interrupt. The runtime owns execute, checkpoint inspection, and
  `Command(resume=...)` adaptation for approve, edit, and reject. Human review never falls back to
  direct service mutation; an unavailable graph review handler produces a retryable
  `503 service_unavailable` response.
- `platform/llm` owns OpenAI Responses clients and HTTP transports. Bootstrap constructs platform
  resources and calls the feature compiler but contains no prospect-agent implementation.
- `app/main.py` owns the FastAPI factory and ASGI entrypoint. Bootstrap groups the prospect runtime,
  review handler, and worker supervisor as one lifecycle-managed component; readiness requires that
  component and PostgreSQL to be healthy.

## Consequences

The runtime has one delegation owner and one feature composition entry point. Every model-visible
capability is backed by concrete middleware or a tool registry entry, and provider replacement does
not alter feature code. Agent-driven delegation can request account and external research together,
while middleware enforces their completion before lane analysis; exact concurrent scheduling remains
model-directed and is checked through trajectory evidence rather than encoded as outer-graph fanout.

The Deep Agents SDK's implicit general-purpose subagent must be disabled. The orchestrator and
specialists share one composite backend so state-backed files flow through isolated task calls;
explicit tool lists and ordered allow-then-deny filesystem permissions prevent root tools, memory,
skills, or role-owned writes from leaking across specialists. Adding another specialist, provider,
or review boundary requires updating specs, middleware policy, trajectory tests, and the
business-logic decision log together.
