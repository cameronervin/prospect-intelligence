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

- **Decision:** Use Settings-selected GPT-6 Sol at medium reasoning for orchestration and GPT-6 Luna
  for account context, external research, lane analysis, and outreach drafting through the OpenAI
  Responses API. Context and research are concurrently eligible; their exact scheduling remains
  model-directed. Analysis, brief synthesis, and drafting run after their required inputs exist.
  Missing model credentials fail startup rather than selecting a deterministic pipeline or a
  different model.
- **Decision:** QuickJS programmatic tool calls are limited to read-only filesystem and domain tools.
  Agents write only their canonical role-owned artifacts through filesystem operations outside PTC;
  the graph records those paths in `/INDEX.md`. `send_outreach` is a named interrupt and is never
  available to QuickJS.
- **Alternatives considered:** Six thin specialists; one dynamic worker pool; a single model for every role.
- **Reasoning:** Four visible specialists preserve meaningful delegation and control boundaries while
  keeping artifacts and evaluation trajectories understandable.
- **Consequences:** Model construction is injected and provider-neutral, but OpenAI is the supported
  initial provider. Bootstrap owns and closes model transports separately from the shared SEC/Tavily/
  FMCSA HTTP transport. The graph is compiled once per process after PostgreSQL checkpoint/store
  startup. Offline tests use fakes and never call models. Salesforce, GenLogs, and TMS provider
  clients remain post-MVP and will be independently injected into their adapters.
- **Evidence:** Graph topology, trajectory, filesystem-contract, and permission tests; live experiments
  will be recorded separately when credentials are available.

### 2026-09-29 — Agent workflow: Deep Agent-owned delegation and middleware context engineering

- **Decision:** This entry supersedes the outer-graph scheduling portion of the preceding agent-workflow
  decision. One root Deep Agent reads the task, manifest, and allowed rep memory and delegates through
  `task` to exactly four explicit subagents: account context, external research, lane analysis, and
  outreach drafting. Account and external research are concurrently eligible; middleware requires
  both contracts before lane analysis, the analysis before the orchestrator's brief, and the brief
  before outreach drafting. The outer LangGraph prepares durable state, invokes the root agent, and
  finalizes the run but never calls specialists itself.
- **Decision:** Feature-owned LangChain middleware is the context-engineering boundary. It projects
  allowlisted context, enforces model/tool budgets and delegation prerequisites, treats source text
  as untrusted data, and validates role-owned artifacts. Platform trace privacy hides inputs,
  outputs, and metadata for every nested run. Checkpointed
  LangGraph state and non-checkpointed runtime context remain distinct. Human review is the named
  `send_outreach` approve/edit/reject interrupt; no model reviewer or CRM mutation is present.
- **Decision:** Specialist tasks use isolated message mode; canonical shared files merge through the
  task result, but parent conversation and rep-memory text cannot bypass a specialist's context
  projection. Reviewed preference summaries remain product records and are materialized into the
  tenant/rep StoreBackend namespace at the start of later runs.
- **Alternatives considered:** Deterministic outer-graph fanout with the orchestrator used only for
  synthesis; dual orchestration in both the outer graph and the root agent; a model-based reviewer.
- **Reasoning:** Deep Agent-owned delegation makes the visible `task` trajectory the product's agent
  topology, while middleware keeps ordering, context, permissions, and safety enforceable without a
  second scheduler. Human approval remains the authoritative side-effect boundary.
- **Consequences:** Exact concurrent scheduling is model-directed rather than guaranteed by outer
  graph fanout, so release evidence includes trajectory tests and artifact prerequisites. The SDK's
  implicit general-purpose subagent is disabled, specialists expose no `task`, and memory backends are
  mounted only for agents allowed to read rep preferences. OpenAI client lifecycle remains platform
  owned; the feature compiler compiles the complete runtime once after checkpoint/store startup. The
  root Deep Agent is mounted as a checkpointed subgraph so same-thread retries resume after completed
  specialist delegations instead of replaying them.
- **Evidence:** Concrete middleware, exposed-tool, trajectory, artifact, memory-isolation, interrupt,
  PostgreSQL resume, bootstrap, and lifecycle tests. Live model and LangSmith evidence remains separate.

### 2026-09-29 — Lane fit: direct empty-leg coverage and versioned scoring

- **Decision:** A shipper origin-to-destination lane matches carrier empty capacity in the same
  direction; reverse-direction capacity is not a match. Matched loads are the smaller of shipper
  loads and empty capacity. Backhaul fill is matched loads divided by empty capacity, or zero for
  zero capacity. Density is same-lane weekly loads divided by 40 and capped at one; equipment match
  is the carrier fleet share for the required equipment. `lane_fit_v1` weights those components
  50%, 30%, and 20%, respectively, and rounds the bounded score half-up to four decimal places.
- **Decision:** Only lanes with at least one matched load are eligible. Rank by score descending,
  matched loads descending, origin ascending, and destination ascending, then retain three. Duplicate
  shipper or network routes and malformed inputs produce `needs_more_data`; complete critical inputs
  with an eligible lane produce `fit`, while complete critical inputs without one produce `no_fit`.
- **Decision:** Modeled gross revenue is `matched loads * estimated rate per load * 52 weeks`.
  Modeled deadhead avoided is `matched loads * full origin-to-destination miles * 52 weeks`. These
  internal values are assumptions, not booked revenue, margin, guaranteed savings, or evidence that
  every modeled mile would otherwise have run empty.
- **Decision:** Customer-visible outreach is limited to exact, approved v1 qualitative invitation
  pairs. Generic drafts use the exact `Freight conversation` subject. Its approved bodies are
  `Could we discuss your freight needs?`, `Could we compare freight needs?`, and
  `Would you be open to comparing notes on your freight needs?`. Route drafts use the exact
  `{O} to {D} freight conversation` subject paired with the exact
  `Would you be open to comparing notes on your {O}-to-{D} freight needs?` body, where both route codes
  are matching uppercase alphanumeric normalized IDs. Generated drafts and rep edits use the same
  full-match allowlist; all other prose is rejected, so internal commercial and source claims cannot
  pass through paraphrasing.
- **Alternatives considered:** Reverse-direction round-trip matching; uncapped density; equal weights;
  retaining zero-match lanes; input-order tie breaking; merging duplicate routes; margin estimation;
  assuming only the empty portion of a lane for deadhead avoidance.
- **Reasoning:** Same-direction matching represents capacity that the shipper load can actually fill and
  makes the score independently reproducible. Fixed normalization and tie breakers keep results stable
  under input reordering. Abstaining on ambiguous data avoids silently choosing among conflicting
  records, while explicit 52-week and full-lane assumptions keep the MVP's opportunity model legible.
  A deterministic template allowlist is auditable and closes paraphrase variants without pretending
  a lexical denylist can reliably distinguish safe from unsafe commercial claims.
- **Consequences:** Internal briefs label modeled gross revenue and modeled deadhead avoided and disclose
  their assumptions without changing the API shape. The gross-revenue model intentionally excludes
  costs and margin; the deadhead model is an upper-bound displacement estimate for the full lane.
  The outreach guardrail is intentionally conservative: reps cannot author custom v1 copy and must
  select an approved generic template or the internally consistent normalized-route template.
- **Evidence:** Runtime and independent-reference parity across all reviewed fixtures; table-driven,
  boundary, ordering, duplicate, malformed, zero-fit, outreach-safety, component, and browser tests.

### 2026-09-29 — Human review: outreach-only approval boundary

- **Decision:** The system pauses before simulated outreach. A rep can approve, replace the complete
  draft with another exact approved v1 invitation pair, or reject it; arbitrary custom copy is rejected.
  CRM writeback and real email are excluded. Sends are idempotent by run and tool call. Preference
  memory may record approved template selection but not customer facts.
- **Decision:** Review must resume the durable `send_outreach` graph interrupt. The API has no direct
  service mutation fallback; if the graph review handler is unavailable it returns retryable
  `503 service_unavailable` without accepting the decision.
- **Alternatives considered:** Sequential send and CRM approvals; direct service fallback when the
  graph is unavailable; relying on review without a runtime interrupt; storing customer facts as
  memory.
- **Reasoning:** This is the smallest meaningful side-effect boundary and demonstrates durable human
  control without pretending to integrate a real customer system.
- **Consequences:** Rejection is terminal and sends nothing. Temporary runtime unavailability is
  visible and retryable rather than allowing review state to diverge from the graph checkpoint. V1
  preference learning is deliberately limited to safe template selection; customer-specific facts
  never enter preference memory. Production CRM integration remains documented future work.
- **Evidence:** Approve/edit/reject, graph-resume, handler-unavailable, idempotency, and
  namespace-isolation tests.

### 2026-09-29 — Lane analysis: runtime-loaded, role-scoped skill

- **Decision:** Package `lane_fit_v1` as an SDK-formatted skill, mount the skill source read-only at
  `/skills/`, and expose it only to the lane analyst. Other agents cannot discover or read the skill.
- **Alternatives considered:** Repeat the formula only in prompts; expose every packaged skill to the
  root and all specialists; treat the skill as documentation that is not loaded at runtime.
- **Reasoning:** A role-scoped runtime skill keeps the versioned analysis method discoverable where it
  is applied without expanding unrelated agents' context or permissions.
- **Consequences:** Skill packaging and access policy are part of the runtime contract. Formula changes
  require evaluator parity, skill-version review, and promotion evidence.
- **Evidence:** Skill discovery, read isolation, package-content, and lane-fit parity tests. Live model
  and LangSmith evidence remains separate.

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

- **Decision:** Use 16 core and 8 edge examples with three repetitions. The CAM-38 deterministic
  profile requires 100% numeric grounding, analysis correctness, file-contract, trajectory, and
  injection checks, reference-aware lane precision@3 of at least 0.80, and verdict accuracy of at
  least 0.90. Precision is the unique predicted/expected top-three intersection divided by the
  larger set size; two empty sets score 1.0, so sparse correct predictions can pass without allowing
  under-produced core predictions to score perfectly.
- **Decision:** Lane analysis is the exact `lane_fit_v1` artifact contract: method version, fit verdict,
  and up to three complete, uniquely routed, canonically ordered lane records. The scripted target
  authors these records with the application scorer; `analysis_correctness` recomputes them with the
  independent evaluator reference. Numeric grounding reads only research and analysis JSON, with
  currency, grouping separators, decimal strings, and percentages normalized before exact matching.
- **Decision:** The root `send_outreach` tool call means `review.requested`, not an external send.
  Trajectory evaluation requires research before analysis, analysis before drafting, and drafting
  before review; an `outreach.sent` event is valid only after `review.approved`. Efficiency metrics
  remain informational. CAM-39 will add Jev semantic gates, pin `jev-1.13.0`, and calibrate each
  question independently against human labels and a GPT-6 Sol comparison judge.
- **Alternatives considered:** Grounding as the only release gate; live public APIs in the release
  dataset; dividing precision by the number of returned predictions; treating the review request as
  a send; using the application scorer as both target and oracle; one shared threshold for semantic
  questions.
- **Reasoning:** Deterministic checks should own computable facts while calibrated judges cover narrow
  semantic questions. Independent scoring and a real compiled-graph artifact boundary catch failures
  that fixture-only or self-referential checks would miss.
- **Consequences:** CI remains offline. The local synchronous LangSmith runner uses a preloaded,
  non-hosted client, disables uploads and tracing, requires every metric in exactly three rows for
  each of 24 examples, and publishes only sanitized aggregate repository evidence. Target snapshots
  retain model-authored analysis/output bodies but reduce task, context, and research artifacts to
  typed contract and numeric observations. Measured latency is retained as a LangSmith metric but
  omitted from the committed report value so repository evidence is reproducible. Its scripted-model
  result validates wiring and gates, not live model quality. Live LangSmith experiments and semantic
  calibration remain CAM-39/CAM-40 work requiring credentials.
- **Evidence:** Evaluator true/false-positive, boundary, and adversarial tests; compiled-graph target
  test; 72-row sanitized CAM-38 report; future calibration and named live LangSmith experiments.

### 2026-09-29 — Offline demo: `lane_fit_v1` direct-match verdict

- **Decision:** `lane_fit_v1` returns `fit` when complete, unambiguous evidence yields at least one direct
  matched load (`matched_loads_per_week >= 1`). Complete evidence without an eligible match returns
  `no_fit`; missing, degraded, malformed, or duplicate critical evidence returns `needs_more_data`.
- **Alternatives considered:** Leave demo runs permanently queued; use a calibrated score threshold;
  require live credentials for every UI walkthrough.
- **Reasoning:** The direct-match threshold is deterministic, independently reproducible, and consistent
  with the v1 eligibility rule. It lets the API/UI/HITL contracts be reviewed without presenting an
  uncalibrated confidence cutoff as production logic.
- **Consequences:** The compiled agent worker and CAM-33 APIs must preserve this v1 verdict contract.
  Introducing calibrated score thresholds changes business behavior and therefore
  requires a versioned `lane_fit_v2` decision, evaluation baseline, and promotion evidence.
- **Evidence:** CAM-31 lane-fit parity, boundary, malformed-data, duplicate, and API bootstrap tests.

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

### 2026-09-29 — Durable API: explicit polling and review capability

- **Decision:** Starting a run returns `202` only after the run and its worker job commit atomically.
  Clients poll the run's durable status separately from its fit verdict. Only `awaiting_review`
  responses expose `pending_review`, naming `send_outreach`, the fixed approve/edit/reject decisions,
  and the stable `review-{run_id}` review-idempotency token; the draft `outreach` contains content
  only.
- **Decision:** Accounts are tenant-scoped, while runs and reviews are tenant-and-rep-scoped. Missing
  and out-of-scope resources share the same `404` response. Every review submission must return the
  exact supplied token; an arbitrary token or reusing that token for a different decision returns
  `409 conflict`. Unavailable graph review returns retryable `503 service_unavailable` without
  recording a decision.
- **Alternatives considered:** Background-only enqueue after the HTTP response; combining workflow
  status and fit verdict; deriving or embedding the review token in draft content; distinct forbidden
  responses that disclose resource existence.
- **Reasoning:** An explicit capability keeps draft content separate from durable workflow control,
  while atomic enqueue, scoped polling, and non-disclosing errors make restart and retry behavior
  predictable without overstating the synthetic headers as authentication.
- **Consequences:** Clients must preserve the server token and tolerate polling across application
  restarts. The token provides idempotency, not authorization. Production still requires real
  authentication and delegated authorization before these scope headers can be trusted.
- **Evidence:** API state-matrix, validation, ownership, sanitization, service-unavailable, atomic
  PostgreSQL enqueue/restart, frontend boundary, component, and browser tests.

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
  prospect workflow can recommend outreach; degraded inputs produce `needs_more_data`.
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
