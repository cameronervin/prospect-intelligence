# Feature modules

Each directory in this package owns one cohesive product capability. Features
contain their business rules, application workflows, agent behavior, boundary
contracts, and adapters; they should not become generic technical utility
packages.

Create a feature from the repository root with:

```sh
make feature NAME=research_workflow DRY_RUN=1
make feature NAME=research_workflow
```

Names must be lower `snake_case`. The generator refuses unsafe names and will
not overwrite an existing feature.

## Intended shape

```text
features/<feature_name>/
├── __init__.py
├── public.py
├── api/
│   └── __init__.py
├── services/
│   └── __init__.py
├── agents/
│   └── __init__.py
├── domain/
│   └── __init__.py
├── models/
│   └── __init__.py
├── schemas/
│   └── __init__.py
├── repositories/
│   └── __init__.py
├── integrations/
│   └── __init__.py
└── contracts/
    └── __init__.py
```

The generated package is intentionally empty. Add only the files and
subdirectories required by the feature's first tested behavior.

## Folder responsibilities

### `api/`

FastAPI routers and HTTP-specific request handling. Routes validate boundary
input, invoke a service or agent, and translate results into HTTP responses.
Keep business rules and dependency construction out of this layer.

### `services/`

Application use cases and orchestration. Services coordinate domain behavior
through contracts, define transaction boundaries, and call agents when the use
case requires them. Inject dependencies rather than constructing adapters.

### `agents/`

Feature-owned LangGraph behavior. Place graph definitions, typed state, nodes,
prompts, tools, routing logic, and human-review interrupts here. Model clients,
checkpointers, and external adapters are injected at the graph boundary.

### `domain/`

Framework-independent business concepts, policies, value objects, and errors.
Domain code must not depend on FastAPI, Pydantic transport schemas,
SQLAlchemy, LangGraph, or external SDKs.

### `models/`

SQLAlchemy persistence models owned by the feature. These describe storage,
not API payloads. A feature owns its tables and their migrations; other
features access the behavior through supported contracts instead of importing
models directly.

### `schemas/`

Pydantic contracts at system boundaries, such as API requests and responses or
validated external payloads. Do not use schemas as a substitute for domain
objects or database models.

### `repositories/`

Persistence adapters that implement interfaces from `contracts/`. Repository
code contains queries and storage mapping, while use-case decisions remain in
services or the domain.

### `integrations/`

Adapters for external APIs, queues, model providers, and other systems outside
the application. Bound I/O with timeouts, translate vendor failures into
feature-owned errors, and make retryable side effects idempotent.

### `contracts/`

Stable ports and cross-layer types, including repository protocols and service
interfaces. Contracts point inward and must not import concrete repositories,
integrations, routes, or platform implementations. Another feature may import
from this package only when the contract is intentionally supported.

### `public.py`

The explicit cross-feature facade. Re-export only behavior that has a real
consumer and is safe to support across feature boundaries. Internal modules
remain private to the owning feature.

### `__init__.py`

Marks the feature package and documents its boundary. Keep it free of wiring,
side effects, and convenience re-exports; use `public.py` for supported access.

## Dependency direction

```text
api -> services / agents -> contracts / domain <- repositories / integrations
```

- `api` may depend on schemas and application entry points.
- `services` and `agents` orchestrate domain behavior through contracts.
- `repositories` and `integrations` implement inward-facing contracts.
- Concrete dependency wiring belongs in `app/bootstrap/`.
- Shared technical infrastructure belongs in `app/platform/`.
- Only genuinely universal business types belong in `app/shared_kernel/`.
- Cross-feature imports must target the feature's `public.py` or `contracts/`.
- `platform` and `shared_kernel` must never import a feature.

Architecture tests in `backend/tests/architecture/` enforce these boundaries.
