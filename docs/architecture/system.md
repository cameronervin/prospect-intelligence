# System architecture

## Current boundary

The repository currently proves a runnable full-stack foundation and nothing more. The Next.js server checks FastAPI readiness; FastAPI checks PostgreSQL; LangGraph, LangSmith, feature-layer, evaluation, and deployment extension points are present but no business graph or product workflow exists.

```text
Browser
  -> Next.js server component
      -> GET backend /health/ready
          -> PostgreSQL SELECT 1

Future feature
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

A future feature owns its LangGraph state, graph, nodes, tools, prompts, human-review interrupt, and structured result. Shared checkpoint construction belongs to `platform/agent_runtime`, but checkpoint schema setup remains an explicit feature/deployment decision. LangSmith tracing is disabled by default.

## Frontend boundary

The frontend uses App Router server components. `BACKEND_BASE_URL` remains server-only. The current page exposes a sanitized ready/degraded result rather than transport exceptions or dependency details.
