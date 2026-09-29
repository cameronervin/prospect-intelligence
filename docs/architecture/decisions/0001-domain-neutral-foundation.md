# ADR 0001: Domain-neutral modular foundation

- Status: Accepted
- Date: 2026-09-28

## Decision

Use a feature-first modular monolith with TenFour-style macro boundaries and Playbook-style layer names inside generated features. Provide infrastructure and architecture enforcement now, but add no example feature, agent graph, provider, authentication scheme, domain migration, or evaluation metric.

Each feature receives `api`, `services`, `agents`, `domain`, `models`, `schemas`, `repositories`, `integrations`, and `contracts`, plus `public.py`.

## Rationale

The take-home problem is intentionally not selected yet. A fake CRUD or chat feature would create disposable conventions and blur scaffold evidence with product evidence. A generator makes the intended structure executable without committing pretend business behavior.

PostgreSQL and Alembic are included because durable state, human review, idempotency, and failure recovery are central production concerns. LangGraph checkpoint setup is not automatic because its lifecycle and schema must follow the actual graph's state and deployment policy.

## Consequences

- The repository can run and verify before product selection.
- The first real feature must make explicit choices about auth, tenancy, state, tools, human review, datasets, and metrics.
- Some packages are extension points rather than proof of implemented behavior.

