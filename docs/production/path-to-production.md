# Path to production

## Recommendation

The current system is a reviewable MVP. It is suitable for a small, human-reviewed pilot after the
highest-priority gaps below are closed. It is not ready for autonomous outreach or a broad customer
rollout.

The main gaps are not basic agent architecture. They are live quality evidence, enterprise
identity, tenant isolation, memory governance, reliable external side effects, and production
operations.

## Implemented controls

- Typed agent state, explicit specialist roles, bounded tools, and deterministic guardrails.
- Durable PostgreSQL jobs, LangGraph checkpoints, and a named human approval step.
- Tenant and representative scope in application queries, run identity, checkpoints, and memory
  namespaces.
- Idempotent review behavior and simulated send receipts.
- Versioned synthetic evaluation data, offline quality gates, and a production feedback-loop design.
- Redacted logs and privacy-bounded LangSmith events.
- Non-root containers, health checks, CI, browser tests, and production builds.

These controls support a pilot decision. They do not prove live model quality, live provider
reliability, customer-data safety, or production operation.

## Agent and evaluation hardening

### Revalidate the current agent

The hosted LangSmith evidence is archived v1 evidence. Run a new experiment for the active v4 graph
and `outreach-v4` prompt before a pilot. Freeze and record the graph, prompts, skills, models,
evaluators, dataset, dependency lock, and source revision.

The new release gate should include:

- Repeated live-model runs.
- Customer-approved examples and an untouched human-reviewed holdout.
- Normal, boundary, dependency-failure, and prompt-injection cases.
- Real provider sandbox calls and degraded-source behavior.
- Strict grounding, calculation, trajectory, safety, and coverage checks.

Deterministic checks should remain authoritative for facts, numbers, workflow, and safety. Semantic
judges should remain advisory until independent reviewers calibrate them.

### Harden human approval

Keep the current human approval step for all customer-facing actions. Before real sending, bind an
approval to the reviewer, tenant, role, recipient, channel, exact draft version, and expiry time.
Changing the draft or policy must invalidate the approval.

Sending must use an idempotency key, durable receipt, reconciliation process, retry policy, and
operator recovery path. A worker restart or API retry must never send twice.

### Isolate agent execution

Move model-generated code execution out of the API and worker process. Use a short-lived sandbox
with no credentials, denied network access by default, CPU and memory limits, a time limit, and
automatic cleanup.

Define clear failure rules for every model and data provider. Add backoff, jitter, circuit breakers,
quotas, maximum run duration, and reviewed fallback models. Missing or stale critical data must
produce `needs_more_data`, not a confident recommendation.

### Operate the quality loop

Evaluate all errors, rejects, edits, safety failures, source failures, tool failures, and new-version
canaries. Keep a stable random sample of normal traffic for unbiased trend monitoring.

Reviewed production failures should become sanitized regression examples. Define owners and service
targets for grounding, completion rate, edit and reject rate, latency, cost, review age, and provider
failures. Current demo alert thresholds are not production service levels.

## Memory and preference learning

### Keep memory application-owned

The project already uses a PostgreSQL-backed LangGraph store. Moving to LangMem would add
model-driven extraction and consolidation; it would not solve storage or tenant isolation by
itself.

Do not replace the current bounded preference learner with unrestricted agent-managed memory. The
production design should keep approved review events as the source of truth and treat every memory
profile as a derived projection.

Use separate policies for each type of memory:

| Memory type | Production treatment |
| --- | --- |
| Representative preferences | Structured profile derived from approved edits |
| Approved edit history | Immutable audit events and source of truth |
| Successful examples | Separate, sanitized, opt-in episodic collection |
| Team sales playbook | Tenant-level, administrator-approved, read-only to agents |
| Prompt and workflow rules | Release-controlled; never changed automatically in production |
| Customer and account facts | Read from authoritative source systems, not agent memory |
| Checkpoints | Run-scoped state with retention, deletion, and replay rules |

A representative preference profile should use typed fields for tone, length range, invitation
style, confidence, source review IDs, version, status, learned time, and expiry. It should not retain
customer names, routes, contacts, or raw outreach copy. One situational edit should not silently
replace the whole profile. Support repeated evidence, conflicts, undo, correction, and explicit user
controls.

### Use LangMem only as an optional background processor

If richer learning is needed, place LangMem behind the existing repository contract and run it in a
background worker after an approved edit. Give it only a sanitized, typed review event. Do not give
the agent a general memory-management tool or allow it to choose a tenant namespace.

First run LangMem in shadow mode and compare it with the deterministic learner. Measure extraction
accuracy, over-generalization, privacy leaks, contradictions, latency, and cost. Enable writes only
after it passes those gates and its maintenance and compatibility risk is accepted. Keep a feature
flag and a rollback path to the deterministic profile.

## Tenant isolation and data governance

Namespace strings are useful organization, but they are not a security boundary. Production needs
defense in depth:

- Build every namespace from verified server-side identity. Never accept tenant, user, or namespace
  values from the model or browser.
- Route all memory reads and writes through one authorization-aware gateway.
- Add PostgreSQL row-level security with default-deny policies to application-owned tenant data.
- Use separate roles or schemas for product data, checkpoints, and long-term memory where practical.
- Apply tenant scope to caches, embeddings, vector indexes, jobs, traces, datasets, exports, backups,
  and deletion workflows.
- Keep representative memory separate from tenant-shared playbooks. Never fall back to global
  memory when scoped memory is missing.
- Test reused representative IDs across tenants, forged namespaces, cross-tenant search, worker
  resume under the wrong identity, account reassignment, and deletion.

Define retention, legal hold, deletion, export, consent, correction, encryption, key rotation,
residency, and vendor rules before real customer data is introduced. Product rows, checkpoints, and
memory cannot remain stored forever by default.

## Application and platform hardening

### Identity and integrations

Replace the demo token issuer with enterprise OIDC or SSO, asymmetric key rotation, revocation,
MFA, service identities, and managed role provisioning. Define who may start, view, review, retry,
and cancel a run.

Replace synthetic CRM, freight, and carrier-network sources with reviewed production integrations.
Add delegated credentials, schema and sandbox contract tests, pagination, quotas, freshness rules,
licensing review, audit records, and outage behavior.

### Work execution and database

Separate the API, agent workers, and quality workers so they can deploy and scale independently. Use
a managed queue or workflow system with backoff, dead-letter handling, cancellation, drain controls,
tenant concurrency limits, and queue-age autoscaling. Replace process-local locks with distributed
concurrency controls.

Use managed high-availability PostgreSQL with TLS, least-privilege roles, connection budgets,
capacity alerts, backups, point-in-time recovery, and tested restores. Run migrations as controlled
deployment jobs using backward-compatible expand-and-contract changes.

### Edge, delivery, and operations

Add managed TLS and ingress, request-size limits, rate limits, abuse controls, a secret manager,
network policies, resource limits, autoscaling, and graceful shutdown. Build images once and promote
them by digest through staging and production. Add dependency and image scanning, an SBOM, signing,
provenance, and automated rollback.

Centralize privacy-safe logs, metrics, and traces. Define service targets and alerts for API
availability, queue age, run time, review age, database pressure, provider errors, model cost,
quality-event backlog, and real-send reconciliation. Add load tests, restore and failover drills,
incident runbooks, synthetic browser checks, and clear on-call ownership.

The UI also needs a server-backed run and review inbox, assigned reviewers, cross-device recovery,
approval expiry, notifications, cancellation, retry, audit history, and clear degraded or failed
states. The review screen should show the recipient, channel, final content, source freshness, and
the exact effect of approval.

## Rollout plan

### Phase 1: pilot foundations

- Revalidate the exact current agent release.
- Stabilize all CI and browser tests.
- Add enterprise identity, database-enforced tenant isolation, managed secrets, and memory lifecycle
  rules.
- Add structured preference profiles and immutable preference provenance.
- Provision managed PostgreSQL and separate workers from the API.

### Phase 2: controlled internal pilot

- Connect approved read-only production data sources.
- Run optional LangMem extraction in shadow mode.
- Add production dashboards, alerts, runbooks, load tests, and recovery drills.
- Keep every customer-facing action simulated or manually executed outside the system.

### Phase 3: limited real sending

- Connect one delivery channel behind hardened approval and reconciliation.
- Start with a small tenant and representative cohort.
- Use canary releases and keep immediate rollback to the last known-good agent and deterministic
  preference learner.

### Phase 4: broader rollout

Expand only after the pilot meets agreed quality, safety, reliability, privacy, and business goals.
Business measures should include representative time saved, approval/edit/reject rate, replies,
meetings, won opportunities, and network outcomes.

## Evidence required for promotion

A production decision should combine four separate evidence classes:

1. Passing repository tests and deterministic evaluation gates.
2. A complete LangSmith experiment for the exact release.
3. Credentialed provider and integration tests.
4. Dated staging or production evidence for load, recovery, security, and operations.

No single evidence class proves production readiness by itself.
