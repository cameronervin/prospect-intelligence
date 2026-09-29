# Business logic decisions

Record decisions here when they change business behavior, formulas, thresholds, workflow,
user-visible outcomes, data interpretation, or safety boundaries. Add the entry in the same change
as the implementation. Keep repository evidence distinct from live LangSmith evidence, and never
include credentials, private customer data, raw traces, or generated result exports.

## Entry template

### YYYY-MM-DD — Area: decision title

- **Decision:** The behavior that is now authoritative.
- **Alternatives considered:** Meaningful options that were rejected.
- **Reasoning:** Why this choice best serves the user and delivery goal.
- **Consequences:** Expected benefits, limitations, compatibility, and rollback considerations.
- **Evidence:** Tests, source documents, experiments, or dated deployment evidence supporting the choice.

## Decisions

### 2026-09-29 — Architecture: separate prospect intelligence and agent quality

- **Decision:** `prospect_intelligence` owns the freight workflow and exports sanitized contracts;
  `agent_quality` owns online evaluation, monitoring, annotation routing, alerts, simulation, and
  regression-candidate intake. Offline datasets and experiment runners remain in `backend/evaluation`.
- **Alternatives considered:** Put all evaluation inside the freight feature; place online quality
  operations in the offline evaluation directory.
- **Reasoning:** Runtime quality operations have a distinct lifecycle and external dependencies, while
  offline evaluation must remain runnable without production services.
- **Consequences:** Cross-feature access must use exported contracts. Generic LangSmith construction
  remains a platform concern. The extra boundary adds a small amount of wiring but prevents freight
  behavior from depending directly on LangSmith.
- **Evidence:** Architecture dependency tests and feature contract tests.

### 2026-09-29 — Agent workflow: four specialists with role-based models

- **Decision:** Use GPT-6 Sol at medium reasoning for orchestration and GPT-6 Luna for account context,
  external research, lane analysis, and outreach drafting. Context and research may run concurrently;
  analysis and drafting run after their required inputs exist.
- **Alternatives considered:** Six thin specialists; one dynamic worker pool; a single model for every role.
- **Reasoning:** Four visible specialists preserve meaningful delegation and control boundaries while
  keeping artifacts and evaluation trajectories understandable.
- **Consequences:** Model construction is injected and provider-neutral, but OpenAI is the supported
  initial provider. Offline tests use fakes and never call models.
- **Evidence:** Graph topology, trajectory, filesystem-contract, and permission tests; live experiments
  will be recorded separately when credentials are available.

### 2026-09-29 — Lane fit: direct empty-leg coverage and versioned scoring

- **Decision:** A shipper origin-to-destination lane matches carrier empty capacity in the same
  direction. `lane_fit_v1` weights backhaul fill 50%, same-lane density 30%, and equipment match 20%.
  Matched loads are the smaller of shipper loads and empty capacity.
- **Alternatives considered:** Reverse-direction round-trip matching; equal weights; margin estimation.
- **Reasoning:** Same-direction matching represents capacity that the shipper load can actually fill and
  makes the score independently reproducible.
- **Consequences:** Internal briefs may show modeled annual revenue and deadhead miles avoided. Values
  are estimates, not promised margin, and must carry their inputs and provenance.
- **Evidence:** Independent reference implementation and table-driven boundary tests.

### 2026-09-29 — Human review: outreach-only approval boundary

- **Decision:** The system pauses before simulated outreach. A rep can approve, replace the complete
  draft, or reject it. CRM writeback and real email are excluded. Sends are idempotent by run and tool
  call. Approved edits may update only tenant/rep tone, length, structure, and formatting preferences.
- **Alternatives considered:** Sequential send and CRM approvals; relying on review without a runtime
  interrupt; storing customer facts as memory.
- **Reasoning:** This is the smallest meaningful side-effect boundary and demonstrates durable human
  control without pretending to integrate a real customer system.
- **Consequences:** Rejection is terminal and sends nothing. Customer-specific facts never enter
  preference memory. Production CRM integration remains documented future work.
- **Evidence:** Approve/edit/reject, resume, idempotency, and namespace-isolation tests.

### 2026-09-29 — Data policy: live-first public research with explicit source modes

- **Decision:** SEC, Tavily, and credentialed FMCSA are live-only when enabled and configured;
  failures return disclosed unavailable or degraded coverage and never substitute fixture facts.
  FAF5.7.1 is a checksummed bulk snapshot; GenLogs, CRM, and carrier-network data are deterministic
  synthetic fixtures. Every fact records source mode and provenance.
- **Alternatives considered:** Live APIs in offline evaluation; silently substituting fixtures; real
  GenLogs data.
- **Reasoning:** Offline ground truth must be reproducible, and vendor licensing/availability must not be
  misrepresented.
- **Consequences:** Missing optional sources degrade visibly. Missing critical freight/network evidence
  produces `needs_more_data`; the system never invents facts.
- **Evidence:** Adapter contract tests, dataset repeatability tests, source documentation, and
  credential-free HTTP fakes. Credential-gated smoke commands remain outside CI.

### 2026-09-29 — Evaluation: strict deterministic gates and calibrated semantic judges

- **Decision:** Use 16 core and 8 edge examples with three experiment repetitions. Require 100% numeric
  grounding, score/file/trajectory/injection checks, lane precision@3 of at least 0.80, verdict accuracy
  of at least 0.90, and semantic averages of at least 4/5. Pin Jev to `jev-1.13.0` and calibrate each
  question independently against human labels and a GPT-6 Sol comparison judge.
- **Alternatives considered:** Grounding as the only release gate; live public APIs in the release
  dataset; one shared threshold for all semantic questions.
- **Reasoning:** Deterministic checks should own computable facts while calibrated judges cover narrow
  semantic questions.
- **Consequences:** CI remains offline. Live LangSmith experiments and online resources require explicit
  credentials and produce sanitized evidence rather than committed traces or result exports.
- **Evidence:** Evaluator self-tests, calibration agreement analysis, and named LangSmith experiments.

### 2026-09-29 — Agent architecture: Playbook-style separation with replaceable runtime seams

- **Decision:** Structure the prospect agents layer as state, runtime context, prompts, context policy,
  tool registry, nodes, topology, builders, provider cache, executor, and guardrails. The current layer
  is framework-light scaffolding; credentialed Deep Agents compilation remains CAM-32 work.
- **Alternatives considered:** Keep all agent definitions in one module; copy Playbook's product-specific
  implementations; construct model clients and tools directly in service methods.
- **Reasoning:** The Playbook separation makes graph topology, model-visible context, private runtime
  dependencies, and tool permissions independently reviewable without importing unrelated domain code.
- **Consequences:** Later agents must replace compiler and handler seams rather than treating the
  scaffold as a completed runtime. Public workflow/tool boundaries stay stable while implementation can
  adopt `create_deep_agent`, QuickJS, and PostgreSQL checkpoint/store resources.
- **Evidence:** Agent-scaffold contract tests, architecture dependency tests, and CAM-32 handoff notes.

### 2026-09-29 — Offline demo: direct-match fixture verdict

- **Decision:** The credential-free demo returns `fit` when a reviewed synthetic lane has at least one
  direct matched load; an account without lane evidence returns `needs_more_data`. This is a demo-only
  worker behavior, not the final agent verdict policy.
- **Alternatives considered:** Leave demo runs permanently queued; invent a confidence threshold; require
  live credentials for every UI walkthrough.
- **Reasoning:** A deterministic path lets the API/UI/HITL contracts be reviewed without presenting a
  made-up confidence threshold as production logic.
- **Consequences:** CAM-32 and CAM-33 must replace the process-local fixture worker, and any final verdict
  threshold must be separately decided, documented, and evaluated.
- **Evidence:** Offline pipeline and FastAPI bootstrap tests.

### 2026-09-29 — Contracts: separate workflow state, fit verdict, and recommended action

- **Decision:** Run status is limited to `queued`, `running`, `awaiting_review`, `completed`,
  `rejected`, and `failed`. Freight fit is independently `fit`, `no_fit`, or `needs_more_data`;
  recommended action is independently `expand_existing_lanes`, `new_lane_pitch`, `not_a_fit`, or
  `needs_more_data`. Briefs carry scored lanes with their evidence, outreach is a typed subject/body
  value, and run failures carry code, message, and retryability.
- **Alternatives considered:** Reuse one verdict field for workflow state and sales action; retain the
  scaffold's unvalidated strings and parallel lane/evidence arrays.
- **Reasoning:** Separate types prevent downstream persistence, UI, and evaluation tickets from
  assigning business meaning to execution state or pairing evidence with the wrong lane.
- **Consequences:** The API keeps human-readable recommendation text and adds a stable action code.
  Existing scaffold JSON is rewritten through the finalized serializer; no migration is needed before
  CAM-29 owns durable persistence.
- **Evidence:** Shared-contract, repository round-trip, API, frontend-boundary, and strict-type tests.

### 2026-09-29 — Trust boundaries: complete provenance and sanitized typed failures

- **Decision:** Every exported evidence item includes source mode, endpoint or artifact, retrieval
  time, evidence location, and source version. Quality events require lowercase SHA-256 tenant and rep
  hashes and serialize only their explicit allowlist. Request failures use one typed envelope and never
  echo submitted bodies or values. Agent artifacts use the canonical contract paths and memory paths
  reject unsafe scope identifiers.
- **Alternatives considered:** Return FastAPI's default validation details; expose partial provenance;
  accept arbitrary hash-like strings; maintain independent path lists in agents and evaluators.
- **Reasoning:** These boundaries make lineage reviewable while preventing private request data and raw
  identifiers from crossing into errors or online-quality processing.
- **Consequences:** `agent_quality` continues to consume only `prospect_intelligence.public`; clients
  receive safe field locations and error types, not submitted values. Canonical research filenames are
  `lanes.json`, `company.json`, and `volumes.json`.
- **Evidence:** Validation-error, provenance-response, filesystem, architecture, quality-event, and
  frontend parser tests.

### 2026-09-29 — Deterministic data: one seeded population and explicit FAF estimates

- **Decision:** `freight-prospect-v1` uses seed `28029` and one generator for 16 core, 8 edge,
  and 8 account-ID-disjoint traffic cases. Source payloads, rather than tags alone, carry each
  expected edge condition. Canonical JSON is UTF-8, key-sorted, indented, and newline-terminated.
- **Decision:** The FAF5.7.1 snapshot aggregates finalized 2023 truck-mode regional tons for eight
  reviewed origin-destination pairs. Synthetic loads per week use a seeded fictional 0.25%–1.0%
  shipper share, 20 tons per load, and 52 weeks, rounded half-up; a zero result retries at the 1%
  share. Raw FAF tonnage remains separate and every derived value is labeled a project-owned
  synthetic estimate. Release and extraction metadata, selected fields, aggregation, row pairs,
  upstream archive hash, and snapshot hash are pinned and verified before use.
- **Alternatives considered:** Independent offline and traffic fixtures; live public reads in CI;
  presenting regional FAF tonnage as observed shipper activity.
- **Reasoning:** A shared population prevents fixture drift and evaluation leakage, while a
  checksummed public-data anchor gives realistic relative magnitude without claiming shipper-level
  ground truth.
- **Consequences:** Generator, formula, or version changes require golden-file review. The snapshot
  carries BTS/FHWA provenance and DOI; broader commercial redistribution still requires legal review.
- **Evidence:** Dataset schema and edge-semantic tests, repeat byte generation, golden SHA-256
  `d5ed38772ba98dd9195295f851b7d548509e826c0a9c2900dc5195a6220f30c8`, snapshot SHA-256
  `df7f8931e85a8b6a5650b1e84f6fe661b173f20ebe21d637c94bb8e2f69e3e17`, traffic disjointness,
  and wheel artifact inspection.

### 2026-09-29 — Persistence: leased PostgreSQL work and durable review state

- **Decision:** The MVP runs two lifespan-owned worker slots backed by PostgreSQL claims with a
  five-minute lease, one-minute heartbeat, three attempts, immediate durable retry, and fenced claim
  tokens. Thread identity is `prospect:v1:{tenant}:{rep}:{run}` and preference memory is namespaced by
  feature version, tenant, and rep.
- **Decision:** Run creation and enqueue are atomic. Review, approval, simulated-send receipt,
  preference metadata, and terminal run state commit atomically. Reusing an idempotency key returns
  the canonical result; another key after a terminal decision conflicts. Only one simulated-send
  receipt is allowed per run. If a final-attempt lease expires after terminal run state commits but
  before job completion commits, recovery preserves the terminal run and reconciles the job as
  completed.
- **Alternatives considered:** FastAPI background tasks; an unleased jobs table; Celery or Temporal
  for the MVP; separate best-effort writes for review state.
- **Reasoning:** Database claims are the smallest durable mechanism available in the required stack,
  and transactional review state prevents duplicate sends or partially recorded human decisions.
- **Consequences:** Product rows, checkpoints, and memory are retained indefinitely in the MVP; no
  automated purge exists. Product downgrade is destructive, while LangGraph-owned tables use their
  package migrations and intentionally survive it. Credentials and raw prompts are never persisted,
  but analysis and reviewed outreach are retained for resume and audit. Production should separate
  web and worker processes and adopt a supported broker or orchestrator such as Celery with a broker,
  Temporal, or a managed queue. The MVP poller has no retry backoff.
- **Evidence:** Disposable-PostgreSQL migration, restart, concurrent-claim, fencing, crash-recovery,
  atomic-review, receipt-idempotency, checkpoint-resume, and store-isolation tests.

### 2026-09-29 — Source selection: explicit modes and disclosed failure

- **Decision:** CRM, freight intelligence, carrier network, market data, SEC, web search, and carrier
  registry are independently injected sources. The MVP uses deterministic synthetic adapters only
  for private CRM, freight, and network data; FAF is a verified snapshot, while SEC, Tavily, and
  FMCSA are live only when external access and required credentials are available.
- **Decision:** Expected source failure returns typed degraded or unavailable coverage with evidence
  collected before failure. Live failures never silently fall back to synthetic facts. A run may
  reuse a normalized success or terminal unavailable result, but no cache entry crosses a run,
  tenant, or rep boundary.
- **Decision:** Critical freight or carrier-network coverage must be complete before the
  deterministic pipeline can recommend outreach; degraded inputs produce `needs_more_data`.
  The synthetic carrier network is tenant-scoped and the two demo aliases select reviewed scenarios
  with non-overlapping routes, so both demo scores remain identical to their reference outputs.
  Alias CRM identity remains consistent with the persisted demo account and is grounded in a
  committed alias fixture, while lane data comes from the shared reviewed scenario.
- **Decision:** External calls receive one initial attempt plus two retries for timeouts, rate limits,
  and server errors. Other client errors and malformed payloads are not retried. External text is
  untrusted, and secrets, credential-bearing query strings, and raw private payloads are excluded
  from logs and persistence.
- **Reasoning:** Explicit source modes preserve user trust and make degraded evidence visible, while
  narrow replaceable contracts allow post-MVP private integrations without changing agent behavior.
- **Evidence:** CAM-30 contract, adapter, retry, cache-isolation, provenance, and redaction tests.
