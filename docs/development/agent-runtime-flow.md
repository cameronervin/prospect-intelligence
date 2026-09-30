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

`ProspectAgentJobHandler` builds a `ProspectRuntimeContext` with tenant IDs, source handlers,
preferences, and progress reporting. It calls `CompiledProspectAgentRuntime.execute()`.

The outer graph then runs:

```text
prepare -> root_agent -> validate_root -> finalize
```

- `prepare` creates the task, memory, and index files.
- `root_agent` runs the orchestrator's model and tool loop.
- `validate_root` checks all required artifacts and the review request.
- `finalize` pauses at the human-review interrupt.

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

`ProspectRuntimeContext` is not checkpointed. A scoped `ContextVar` carries it into isolated
specialists because Deep Agents 0.7.19 does not forward typed context there reliably.

## Human review

`send_outreach()` validates the artifacts and records a review request; it does not contact a
customer. The outer graph pauses. A later approve, edit, or reject action calls
`resume_review()`, which resumes the saved checkpoint and completes the graph.
