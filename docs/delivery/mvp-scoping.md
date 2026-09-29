# MVP scope and production deferrals

This document is the living inventory of known gaps between the reviewable take-home MVP and a
production deployment. It records what exists now and what must be finalized before production.
Items here are intentionally deferred; an unwired shell or documented design is not production
behavior.

## Data sources and integrations

| Area | Current MVP implementation | Deferred for production |
| --- | --- | --- |
| Source contracts | Narrow synchronous Protocols and normalized results in `features/prospect_intelligence/contracts/sources.py`; bootstrap owns selection. | Version provider contracts, define compatibility/deprecation policy, and add contract tests against provider sandboxes. |
| CRM | Deterministic synthetic adapter plus an unwired `SalesforceCrmSource` shell. | Finalize Salesforce delegated auth, paging, field mapping, tenant authorization, rate limits, audit logging, and approved writeback. |
| Freight intelligence | Deterministic GenLogs-shaped fixtures plus an unwired `GenLogsFreightIntelligenceSource` shell. | Finalize the licensed GenLogs contract, credentials, quotas, schema mapping, freshness rules, restricted-field handling, and commercial usage approval. |
| Carrier network | Deterministic tenant-scoped capacity plus an unwired `TmsCarrierNetworkSource` shell. | Connect the carrier's TMS/data warehouse, enforce tenant predicates, define equipment/location normalization, freshness SLAs, and reconcile late or corrected loads. |
| Carrier registry | Optional FMCSA QCMobile read adapter with exact-USDOT preference and sanitized failure. | Validate credentials and payloads in a provider sandbox, add operational monitoring, confirm API terms, and establish an outage/staleness policy. |
| Company research | Optional SEC EDGAR and Tavily adapters with bounded retries, provenance, and untrusted-text normalization. | Run credentialed smoke tests, add provider-specific metrics/budgets, review search licensing, and implement stronger content/prompt-injection screening before model use. |
| Market data | Packaged, checksummed FAF5.7.1 snapshot with project-owned load estimates. | Establish refresh ownership and cadence, automate reviewed snapshot promotion, monitor upstream revisions, and complete legal review for broader redistribution. |

Carrier network and carrier registry intentionally remain separate: network data is private
operational capacity, while registry data is public authority and safety information. They require
different credentials, normalized types, provenance, and failure policies.

## Agent and product behavior

| Area | Current MVP implementation | Deferred for production |
| --- | --- | --- |
| Execution | Durable worker runs a deterministic prospect pipeline through the source bundle. Agent graph seams and state contracts are scaffolded. | Compile and deploy the credentialed LangGraph orchestrator/specialists, validate tool permissions, and establish model fallback and budget policy. |
| Human review | Durable approve/edit/reject workflow; send receipt is simulated and idempotent. | Integrate the approved communication channel and CRM writeback with delegated credentials, side-effect reconciliation, audit events, and operator recovery. |
| Memory | PostgreSQL checkpoint/store with tenant/rep namespaces and durable preference summaries. | Define retention, deletion/export, consent, correction, team-shared playbook rules, and memory quality review. |
| Authentication | Demo tenant and rep identity comes from trusted request headers/local configuration. | Add real user authentication, session management, role/tenant authorization, service identities, key rotation, and end-to-end tenant isolation tests. |
| Guardrails | Deterministic grounding, provenance, injection fixtures, bounded provider text, and human approval before send. | Add production prompt-injection screening, PTC/tool allowlists, restricted-data checks, policy escalation, and isolated execution for any interpreter/tool sandbox. |

## Persistence and operations

| Area | Current MVP implementation | Deferred for production |
| --- | --- | --- |
| Work queue | Two lifespan-owned PostgreSQL workers with leases, heartbeats, fencing, and three attempts. | Run workers separately from the web process and adopt a supported broker/orchestrator such as Temporal, Celery with a broker, or a managed queue; add backoff, dead-letter handling, autoscaling, and drain controls. |
| Database | Alembic product schema plus LangGraph-owned checkpoint/store setup; durable transactional review and receipts. | Add backups, point-in-time recovery, capacity planning, migration rehearsal, zero-downtime rollout, row-level tenant controls, and disaster-recovery exercises. |
| Retention | Product rows, checkpoints, memory, analysis, and reviewed outreach are retained indefinitely. | Define retention schedules, legal holds, tenant deletion/export, data classification, encryption/key policy, and automated purge verification. |
| Deployment | Non-root Docker images, health checks, Compose validation, and offline CI verification. | Add managed infrastructure, TLS/ingress, secret manager integration, image signing/SBOM, vulnerability management, regional strategy, autoscaling, and rollback automation. |
| Observability | Structured sanitized logs, readiness/liveness, deterministic quality events, and LangSmith-compatible seams. | Define SLOs and alerts, provider latency/error metrics, queue-depth/lease dashboards, cost budgets, trace sampling, incident runbooks, and privacy-reviewed production tracing. |

## Evaluation and governance

| Area | Current MVP implementation | Deferred for production |
| --- | --- | --- |
| Offline data | Shared feature fixtures generate 16 core, 8 edge, and 8 traffic scenarios; `backend/evaluation` retains dataset projection, golden JSON, evaluators, and experiment plans. | Add representative customer-approved examples, annotation governance, drift/version review, failure-derived regression cases, and data-owner signoff. |
| Semantic evaluation | Deterministic evaluators and Jev/LLM-judge plans are documented; live credentials and results are not committed. | Calibrate every judge against human labels, review third-party retention, redact sensitive state, set release thresholds, and repeat calibration on model changes. |
| Online quality | Sanitized quality-event contract and traffic simulator exist. | Run privacy-approved LangSmith tracing/evaluators, add production dashboards and alert thresholds, connect failures to annotation/regression workflows, and measure business outcomes. |
| Compliance | Provenance, source modes, synthetic labels, and known licensing assumptions are explicit. | Complete security, privacy, legal, vendor, and data-license reviews; document subprocessors and customer-specific residency/retention requirements. |

## Fixture and evaluation ownership

`features/prospect_intelligence/fixtures/synthetic` is feature-owned test/demo infrastructure: it
constructs reviewed source records, edge cases, aliases, and canonical serialization. Synthetic
adapters read that catalog so demo behavior and evaluation inputs cannot drift.

The prior evaluation content was not removed. It remains in `backend/evaluation`:

- `datasets/freight_prospect_v1.py` projects the shared scenarios into evaluation examples.
- `datasets/golden/freight_prospect_v1.json` is the reviewed byte-stable dataset.
- `evaluators/` contains deterministic and semantic evaluator integrations.
- `experiments/` contains experiment configuration.

The separation keeps fixture generation reusable by runtime demos while keeping release scoring and
experiment concerns out of the production feature package.
