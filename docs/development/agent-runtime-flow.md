# Agent runtime flow

The system has three layers:

```text
Job service
  -> outer LangGraph (setup, checkpoints, human review)
    -> Deep Agent orchestrator (delegation)
      -> five LangChain specialist agents (bounded work)
```

## Build time

The application builds the runtime once at startup:

1. `ProspectComponent.start()` starts graph persistence.
2. `build_prospect_agent_runtime()` creates the tool registry.
3. `build_orchestrator_agent()` defines five declarative specialists and calls
   `create_deep_agent()` once for the orchestrator.
4. Deep Agents calls `create_agent()` internally for the orchestrator and each specialist.
5. `build_prospect_workflow()` places the orchestrator inside the outer LangGraph.
6. `graph.compile()` attaches the checkpointer and persistent store.

The default `general-purpose` subagent is disabled. Only the five declared specialists are exposed
through the orchestrator's `task` tool.

## Run time

`ProspectAgentJobHandler` reconstructs the persisted actor snapshot and builds a
`ProspectRuntimeContext` with `AuthContext`, source handlers, preferences, and progress reporting.
LangGraph receives it through `context_schema`/`Runtime.context`; authentication claims never enter
checkpoint state, prompts, files, or model messages.

The outer graph then runs:

```text
prepare -> input_jev_guardrail -> enforce_input -> root_agent -> validate_root
  -> output_jev_guardrail -> enforce_output -> finalize
```

- `prepare` creates the task, memory, and index files.
- `input_jev_guardrail` records `skipped` by default or rejects an unsafe bounded request before a
  model call.
- `enforce_input` raises the non-retryable policy error after the failed decision is checkpointed.
- `root_agent` runs the orchestrator's model and tool loop.
- `validate_root` checks all required artifacts and the review request.
- `output_jev_guardrail` records `skipped` by default or requires supported claims, no internal-data
  leak, and draft/brief agreement before review.
- `enforce_output` raises after checkpointing a failed output decision, preventing human review.
- `finalize` pauses at the human-review interrupt.

The deterministic validators used by `validate_root` and middleware live in
`agents/guardrails/deterministic.py`. The input/output Jev nodes live separately in
`agents/guardrails/jev_nodes.py`; graph topology remains in `agents/graphs.py`.

## Specialist delegation

The orchestrator calls `task(subagent_type=..., description=...)`. Deep Agents then calls the
selected specialist with:

- The shared public file state.
- A new conversation containing only the delegated task.
- That specialist's model, prompt, tools, middleware, and permissions.

The specialist writes artifacts to the shared filesystem. Deep Agents merges those files back into
the orchestrator state, so later specialists can read them. Specialist conversation history is not
returned.

## Files and context

One `CompositeBackend` routes data:

| Path | Storage |
| --- | --- |
| Normal artifact paths | Checkpointed graph state |
| `/memories/` | Tenant/rep-namespaced persistent store |
| `/skills/` | Read-only project files |

Each agent has explicit filesystem permissions. Sharing one backend does not give every agent the
same access.

Only guardrail status, rubric version, decision keys, and state hashes are checkpointed. The
provider-neutral decision contract and TypeSafe adapter live in `platform/decision_models`; policy,
projection, and rejection behavior remain feature-owned. `ProspectRuntimeContext` is not
checkpointed. A scoped `ContextVar` carries it into isolated
specialists because Deep Agents 0.7.19 does not forward typed context there reliably.

## Human review

`send_outreach()` validates the artifacts and records a review request; it does not contact a
customer. The outer graph pauses. A later approve, edit, or reject action calls
`resume_review()`, which resumes the saved checkpoint and completes the graph.
