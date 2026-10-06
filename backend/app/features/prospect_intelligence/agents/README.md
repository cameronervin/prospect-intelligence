# Prospect-intelligence agents

This package owns the prospect feature's model-facing agents and application workflow. Provider
clients belong to `platform`; job/review handlers and workers belong to the feature's `services`.

## Vocabulary

- `specs.py` declares immutable agent topology, tool names, permissions, model classes, skill
  sources, and middleware limits. `prompts/` owns cache-friendly system prompts: one ALL-CAPS constant per agent, the shared
  brief template, and the artifact contract generated from each spec.
- `state.py` contains only checkpointed LangGraph state and its small reducers. Invocation-scoped
  dependencies are `ProspectRuntimeContext` in the feature contracts package.
- `context.py` provides scoped access to invocation context for isolated declarative subagents.
- `middleware/` performs context projection, dynamic prompting, budgets, redaction, delegation
  prerequisites, tool policy, and specialist artifact validation.
- `tools/` groups source, typed-artifact, and workflow tools behind a narrow registry surface.
- `guardrails/` contains pure validation for artifacts, provenance, numeric grounding, outreach,
  and path ownership.
- `chains.py` creates one shared composite backend, five declarative specialist definitions, and
  the single root Deep Agent harness.
- `graphs.py` creates the application LangGraph: prepare inputs, invoke the root agent, and finalize
  the durable human-review interrupt. It never invokes specialists directly.
- `runtime.py` executes the compiled graph, inspects its checkpoint, and resumes review.
- `compiler.py` is the feature composition root and the only module that assembles all of the above.
- `skills/` stores SDK-formatted skill bundles mounted read-only at `/skills/` for selected agents.

Do not add parallel abstractions for blueprints, definitions, nodes, executors, or runtime factories.
Add behavior to the layer that owns it.

## Dependency direction

```text
bootstrap
  -> platform models + graph persistence
  -> compiler
       -> specs -> tools -> middleware -> declarative specialists -> root agent
       -> application graph -> compiled runtime
services
  -> contracts.ProspectAgentRuntime
```

`bootstrap` calls the compiler and coordinates startup/shutdown; it does not define agents. Services
depend on the provider-neutral runtime protocol, not on this package's concrete implementation.

## Topology and middleware lifecycle

The root Deep Agent is the only component allowed to delegate. It exposes exactly
`account-context`, `external-research`, `lane-analyst`, `outreach-drafter`, and
`quality-reviewer`; specialists do not
receive `task` or `send_outreach`, and Deep Agents' implicit general-purpose subagent is disabled.
Deep Agents compiles them internally with `create_agent()`. Specialists run in isolated mode so
parent messages cannot bypass their context policy; shared files still merge back through the task
result. Account and external research are eligible in the same tool-call turn.
Delegation middleware blocks lane analysis until
both research contracts exist, blocks outreach drafting until the brief exists, allows an outreach
redraft only for outreach findings from a later review, caps reviews at three, and blocks
`send_outreach` until the latest review passed, no draft changed since it, and all artifact
contracts validate. Draft content itself is judged by the reviewer, not by gate regexes.

Each model request first receives an allowlisted context projection and dynamic prompt. Budget and
delegation middleware constrain model/tool calls. Typed submissions receive at most two canonical
error-status corrections containing only allowlisted fields, codes, fixed instructions, and the
remaining-attempt count; the third invalid call fails closed. The attempt ledger stores the first
deterministic issue code, never submitted content. Other tool errors remain sanitized, platform
policy hides trace payloads and metadata, and artifact middleware validates specialist output
before it returns to the root. The lane analyst alone receives QuickJS, limited to read/glob over
its allowed files; deterministic scoring remains a normal typed tool outside the interpreter. It
also receives the packaged `lane-fit-v1` skill through `/skills/`.

One `CompositeBackend` routes run files to `StateBackend`, rep preferences to a
tenant/rep-namespaced `StoreBackend`, and skills to a traversal-confined project
`FilesystemBackend`. Every specialist supplies explicit tools and ordered allow-then-deny
filesystem permissions; external research and lane analysis cannot read memory, and artifact writes
remain role- and path-scoped.

Deep Agents 0.7.19 isolated declarative subagents omit the parent's typed runtime context. The outer
root invocation therefore binds that already-created context through a scoped `ContextVar`; nested
tools may read it, but it is never copied into checkpointed state.

## Execution and review

```text
worker/service -> runtime.execute -> prepare -> root Deep Agent
               -> specialist delegation -> send_outreach request
               -> named durable interrupt
human decision -> runtime.resume_review(Command(resume=...)) -> finalize
```

The compiler runs once after PostgreSQL checkpointer/store startup. The root Deep Agent is a
checkpointed subgraph, so same-thread retries do not replay completed outer stages, specialist
delegations, or an existing review interrupt. Approve, edit, and reject resume the real graph;
edited outreach must pass the same allowlist before finalization.
