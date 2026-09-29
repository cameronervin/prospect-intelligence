# Prospect-intelligence agents scaffold

This package intentionally mirrors the reusable agents-layer separation in the Playbook codebase:

- `states/` contains JSON-safe checkpoint state.
- `runtime_context.py` contains invocation-scoped dependencies that must not be checkpointed.
- `prompts/`, `context/`, and `tools/` make model inputs and permissions auditable.
- `chains/` binds one agent definition to its prompt, tools, context policy, and middleware seams
  without constructing provider clients.
- `context/middleware.py` projects only allowlisted state fields before a concrete model request.
- `nodes/` and `graphs/` separate node contracts from static topology.
- `builders/` composes injected dependencies; `graph_provider.py` caches static suites per worker.
- `executors/` is the worker-facing invocation boundary.
- `guardrails/` declares agent safety metadata while business services remain authoritative.

This is scaffolding, not a credentialed Deep Agents runtime. CAM-32 must replace the compiler/tool
handler seams with `create_deep_agent`, QuickJS, PostgreSQL checkpointer/store, real specialist nodes,
and the named outreach interrupt. Do not add repositories, API clients, or model construction inside
this package; inject them through bootstrap and `ProspectRuntimeContext`.
