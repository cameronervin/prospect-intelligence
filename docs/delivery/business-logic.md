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

### 2026-09-30 — Online quality operations: owned resources and deterministic demo traffic

- **Decision:** CAM-42's app-side evaluator catalog and stable 10% evaluation cohort remain
  authoritative. LangSmith routing rules observe 100% of sanitized root quality-event runs and route
  deterministic failures, invalid Jev results, rep rejection, and source or tool errors; they do not
  duplicate evaluation in hosted code or LLM evaluators. Direct application routing remains
  idempotently compatible.
- **Decision:** The former 24-session three-cycle proposal is superseded by exactly 12 synthetic
  sessions: eight approvals, three edits, and one rejection. The fixed plan must cover all and only
  `syn_traffic_01` through `syn_traffic_08`, with no offline account overlap. Run and feedback IDs
  derive from stable UUIDv5 names, so replay creates no additional telemetry.
- **Decision:** Simulator runs are sanitized root events rather than full product or model-backed
  workflows. Their allowlisted metadata contains agent, simulator and traffic-pool versions, session
  index, and an explicit simulated marker. Demo latency and cost are marked synthetic baseline
  feedback and must not be interpreted as measured production latency, usage, or spend.
- **Decision:** Resources owned by these operations use the `freight-prospect-online-v1` prefix and
  are reconciled by stable name or ID. Missing resources are created, drift is patched, unchanged
  resources are reported, ambiguous duplicates stop execution, and foreign resources are untouched.
  Teardown preflights exact-name matches and duplicate conflicts before deleting only owned alerts,
  rules, charts, dashboard section, queue, and feedback configuration in dependency order. It can
  remove orphaned owned resources when the project is already absent. The canonical
  `freight-prospect-online` project and traces are retained unless an additional explicit deletion
  flag is supplied; the queue is fixed to canonical `freight-prospect-review`.
- **Decision:** Four five-minute webhook alerts use demonstration thresholds: average grounding below
  `1.0`, reject rate above `25%`, source-error rate above `10%`, and average synthetic `cost_usd`
  feedback above `$0.30`. The webhook must be credential-free HTTPS and is configured as a secret.
  These thresholds and the generic webhook destination are MVP defaults, not production SLOs or an
  incident-routing commitment.
- **Decision:** The review queue carries an explicit privacy-bounded rubric. Every reviewer records
  one required `freight-prospect-online-v1-human-review-decision` value: Reject (`0`), Edit (`1`),
  or Approve (`2`), with higher values representing better outcomes. This human label remains
  separate from the application and simulator's `review_decision` feedback. Edit and Reject notes
  are required by the queue instructions and captured through LangSmith's built-in Reviewer Notes;
  they are not duplicated as another feedback key because the provider cannot conditionally require
  that field.
- **Decision:** The owned custom dashboard includes a root quality-event run-volume chart as the
  denominator for its rates. Volume and approve/edit/reject views use legacy bar charts; grounding,
  individual Jev scores, latency, cost, tool errors, and source errors remain line charts. Every
  chart is grouped by `metadata.agent_version`. The project remains on LangSmith's existing legacy
  dashboard resource model and the custom dashboard does not replace the user's prebuilt default.
- **Alternatives considered:** Twenty-four full model-backed sessions; hosted evaluator duplication;
  treating simulated cost as actual provider spend; deleting the whole project during normal
  rollback; adopting production paging semantics for the demo; reusing automated review feedback
  for human labels; a redundant notes feedback field; migrating to the newer dashboard API.
- **Reasoning:** A small deterministic corpus demonstrates online operations, failure routing, and
  retry safety without incurring model costs or crossing the established privacy and evaluation
  boundaries. Prefix ownership and conservative teardown make repeated demos reviewable and safe.
- **Consequences:** Dashboards contain clearly labeled synthetic baselines until genuine application
  traffic arrives. The owned feedback configuration is created before the queue and removed after it
  during teardown; unrelated workspace configurations remain untouched. Repository tests can prove
  plans and reconciliation without credentials, while live setup, replay, webhook delivery, and
  console inspection remain separate operational evidence.
- **Evidence:** CAM-43 operations, simulator, privacy, reconciliation, teardown, and CLI tests;
  repository verification and sanitized live LangSmith evidence recorded on the ticket.

### 2026-09-30 — Online quality: app-side evaluation with bounded provider delivery

- **Decision:** Online evaluation runs in `agent_quality` after graph execution. The application
  emits the ten cataloged deterministic signals: groundedness, lane precision, analysis correctness,
  verdict accuracy, file contract, trajectory, injection resistance, latency, cost availability,
  and tool-call count. Reference-aware checks compare the agent artifact with the canonical product
  analysis. Criterion-specific Jev states use the same SDK-neutral scoring, projection, rubric, and
  judge contracts as the offline harness. Every catalog entry has exactly one LangChain scope:
  single step, final output, or full trajectory. Jev scores remain informational until CAM-41
  supplies calibrated thresholds.
- **Decision:** The prospect transition and a separately serialized evaluation envelope commit in
  the existing PostgreSQL outbox transaction. The envelope is finite JSON, bounded to 128 KiB, and
  contains only deterministic signals, question-specific semantic state, and evaluator, graph,
  agent, prompt-template, and rubric versions. Existing rows without an envelope remain readable.
  Prompts, credentials, source
  payloads, contacts, full filesystem state, provider responses, and raw judge output are excluded.
- **Decision:** Only canonical generated scenario identifiers matching the bounded `syn_*_NN`
  contract may be sent unhashed to the dedicated quality project. Friendly fixture aliases, live
  identifiers, and unknown-origin identifiers are SHA-256 hashed consistently across lifecycle
  events; tenant and rep identifiers are always pre-hashed.
- **Decision:** Delivery is disabled unless `TAKEHOME_ONLINE_QUALITY_ENABLED=true`; enabling requires
  both LangSmith and TypeSafe credentials. One lifecycle-owned worker dispatches ten rows per batch,
  polls after one idle second, and gives each event a 75-second publish budget. Disabled delivery
  leaves rows pending. Provider failures and timeouts leave rows pending for retry and never change
  the product result.
- **Decision:** When delivery is enabled, completed product runs enter one deterministic evaluator
  cohort at a default rate of 10%. A versioned SHA-256 bucket of the product run ID makes selection
  stable across retries, restarts, and replicas. Selected runs execute the complete deterministic and
  semantic catalog together; unselected runs retain their application trace and sanitized lifecycle
  event but produce no evaluator feedback or Jev calls. The selection, configured rate, and policy
  version commit with the analysis event before projection, so later rate changes cannot reclassify
  pending rows. HITL decisions, edit distance, rejection routing, and terminal lifecycle events remain
  at 100%.
- **Decision:** LangSmith receives a dedicated event run keyed by the deterministic quality-event ID,
  not the product run ID. Feedback IDs are deterministic per event and metric, and duplicate
  conflicts are successful retries. Failed deterministic checks and rep rejections enter the
  annotation queue. Semantic failures are retryable provider failures; semantic scores do not route
  solely for being low while they are uncalibrated.
- **Decision:** At most eight qualitative claims enter one envelope and at most eight Jev requests
  execute concurrently. Empty-claim and preference-free tone criteria are recorded explicitly as
  not applicable without a provider call. Pending envelopes whose evaluator or rubric version no
  longer matches the runtime are annotated and never judged under a mislabeled rubric. Cost remains
  explicitly unavailable until provider usage and versioned pricing telemetry are added; it is not
  treated as zero or as an alertable score.
- **Decision:** Current dashboard and alert numbers are labeled demo defaults, not production SLOs.
  Product and pending outbox retention remains indefinite for the MVP; LangSmith and TypeSafe
  retention requires a deployment/vendor review. GPT-5.6 Sol remains comparison-only and is never
  an online fallback for Jev.
- **Alternatives considered:** Workspace-hosted evaluators and a hybrid hosted/app-side path.
- **Reasoning:** One app-side path makes the privacy projection and failure semantics reviewable,
  reuses the offline evaluator meaning, remains deterministic under test, and avoids hidden
  workspace-specific resources.
- **Consequences:** Enabling online quality adds LangSmith and TypeSafe availability, latency, and
  cost to selected asynchronous outbox delivery but not to the product transaction. Sampling is
  uniform rather than risk-stratified, and dashboards must use sampled evaluator feedback rather than
  treating absent feedback as failure. Repository tests prove behavior without credentials; live
  evidence remains separate and used only the bounded synthetic smoke event.
- **Evidence:** Catalog/parity, projection/privacy, Jev, gateway idempotency, service, durable
  dispatch, stable cohort boundaries, unsampled delivery, settings, bootstrap lifecycle, legacy-row,
  Ruff, Pyright, repository verification, Compose validation, and the idempotent synthetic LangSmith
  event `1f34ebbc-1d32-5bc8-9734-036d0a367445` delivered on 2026-09-30.

### 2026-09-30 — Agent architecture: one Deep Agent harness with declarative specialists

- **Decision:** Build only the orchestrator with `create_deep_agent()` and pass the five specialists
  as isolated declarative `SubAgent` definitions. Deep Agents compiles them internally with
  `create_agent()`. All six agents use one composite virtual backend: state-backed run files,
  tenant/rep-namespaced store memory, and a traversal-confined project skill mount.
- **Decision:** Every specialist declares its model, prompt, tools (including explicit empty lists),
  middleware, ordered allow-then-deny filesystem permissions, and optional skills. Specialists do
  not inherit the orchestrator's `send_outreach` tool or permissions; only lane analysis receives
  the Agent Skills-compliant `lane-fit-v1` bundle implementing method `lane_fit_v1`. The implicit
  general-purpose subagent remains disabled.
- **Alternatives considered:** Continue precompiling every specialist as a separate Deep Agent;
  transfer artifacts through prompts; mount separate backends and copy files between them; rely on
  inherited tools or permissions.
- **Reasoning:** Declarative specialists are the SDK's native bounded-worker abstraction. Its shared
  backend preserves the virtual artifact contract across isolated conversations without six Deep
  Agent harnesses, while explicit capabilities keep filesystem and tool trust boundaries auditable.
- **Consequences:** Backend mounts are shared infrastructure rather than physical role isolation, so
  middleware permissions remain mandatory and direct backend access must not be exposed as a tool.
  Deep Agents 0.7.19 still drops typed context at the isolated child boundary; the scoped runtime
  bridge remains until the SDK forwards it natively. Public APIs, artifact paths, budgets, review
  freshness, and HITL behavior are unchanged.
- **Evidence:** Installed Deep Agents 0.7.19 source and Context7 documentation; one-construction
  topology tests; shared-file/conversation-isolation trajectories; root-tool, skill, traversal,
  per-role permission, concurrent memory-namespace, runtime-handler, retry, and review tests.

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

### 2026-09-29 — Agent workflow: five specialists with role-based models

- **Decision:** Use Settings-selected GPT-5.6 Sol at medium reasoning for orchestration and GPT-5.6 Luna
  for account context, external research, lane analysis, outreach drafting, and read-only quality
  review through the OpenAI Responses API. Context and research are concurrently eligible; their
  exact scheduling remains model-directed. Analysis, brief synthesis, drafting, and review run after
  their required inputs exist.
  Missing model credentials fail startup rather than selecting a deterministic pipeline or a
  different model.
- **Decision:** QuickJS programmatic tool calls are limited to read-only filesystem and domain tools.
  Agents write only their canonical role-owned artifacts through filesystem operations outside PTC;
  the graph records those paths in `/INDEX.md`. `send_outreach` is a named interrupt and is never
  available to QuickJS.
- **Alternatives considered:** Six thin specialists; one dynamic worker pool; a single model for every role.
- **Reasoning:** Five visible specialists preserve meaningful delegation and control boundaries while
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
  `task` to exactly five explicit subagents: account context, external research, lane analysis,
  outreach drafting, and quality review. Account and external research are concurrently eligible;
  middleware requires both contracts before lane analysis, the analysis before the orchestrator's
  brief, the brief before outreach drafting, and both drafts before quality review. The outer
  LangGraph prepares durable state, invokes the root agent, and finalizes the run but never calls
  specialists itself.
- **Decision:** Feature-owned LangChain middleware is the context-engineering boundary. It projects
  allowlisted context, enforces model/tool budgets and delegation prerequisites, treats source text
  as untrusted data, and validates role-owned artifacts. Platform trace privacy hides inputs,
  outputs, and metadata for every nested run. Checkpointed LangGraph state and non-checkpointed
  runtime context remain distinct. The quality reviewer must pass current drafts before the named
  `send_outreach` approve/edit/reject human interrupt; no CRM mutation is present.
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

- **Decision:** The system pauses before any send-like action and waits for a rep. A rep can approve
  the draft, replace the complete subject and body with another exact approved v1 invitation pair,
  or reject it. Arbitrary custom copy is rejected. The MVP records a simulated send receipt only;
  it does not send email or update a CRM.
- **Decision:** Review must resume the durable `send_outreach` graph interrupt. The API has no direct
  service mutation fallback; if the graph review handler is unavailable it returns retryable
  `503 service_unavailable` without accepting the decision.
- **Decision:** A valid decision and its product records commit together. Repeating the same action
  with the same run-specific review token returns the original result without another receipt,
  preference update, or quality event. Reusing that token for a different action is rejected.

| Rep decision | Final run state | Simulated receipt | Preference learning | Quality feedback |
| --- | --- | --- | --- | --- |
| Approve | `completed` | Original reviewed draft | No change | Approval with edit distance `0` |
| Edit | `completed` | Validated revised draft | Replace the current tenant/rep profile | Edit with normalized distance |
| Reject | `rejected` | None | No change | Rejection with no edit distance |

- **Decision:** Edited outreach is checked against the public-safe template allowlist before the graph
  resumes and again before any receipt, preference, or quality event is persisted. An invalid
  first-time edit or token leaves an awaiting run unchanged. Preferences remain isolated to the
  current tenant and rep.
- **Alternatives considered:** Sequential send and CRM approvals; direct service fallback when the
  graph is unavailable; relying on review without a runtime interrupt; storing customer facts as
  memory.
- **Reasoning:** This is the smallest meaningful side-effect boundary and demonstrates durable human
  control without pretending to integrate a real customer system.
- **Consequences:** Rejection is terminal and sends nothing. Temporary runtime unavailability is
  visible and retryable rather than allowing review state to diverge from the graph checkpoint. A
  database failure rolls back the decision and its related records together. A later quality-event
  delivery failure leaves the event pending but does not change the rep's result. V1 preference
  learning is limited to safe style traits; customer-specific facts never enter preference memory.
  Production email and CRM integration remain future work.
- **Evidence:** Approve/edit/reject, graph-resume, handler-unavailable, idempotency, and
  namespace-isolation tests.

### 2026-09-29 — Human feedback: bounded preference profile and durable quality events

- **Decision:** Only an approved edit changes rep memory. The current tenant/rep profile replaces the
  previous profile and contains exactly three customer-neutral traits: direct, comparative, or
  consultative tone; approximate body word count; and generic or route-specific invitation format.
  Draft text, account names, route codes, and customer facts are never copied into preference memory.
  If different runs commit out of order, the profile with the greatest `learned_at` timestamp remains
  current.
- **Decision:** Review edit distance is character-level Levenshtein distance over the canonical
  `Subject: …\n\n<body>` text divided by the longer canonical length. Approval records `0`, edit
  records the normalized value, and rejection records no distance.
- **Decision:** Run creation, analysis completion, human review, and terminal execution failure each
  enqueue one sanitized event atomically with the corresponding PostgreSQL transition. Event IDs are
  deterministic by run and event type. The dispatcher delivers at least once, acknowledges only
  after sink success, bounds each sink attempt to 10 seconds by default, and retains a sanitized
  pending failure for retry; delivery failure or timeout never changes the product result. Concrete
  LangSmith delivery remains CAM-42 work.
- **Alternatives considered:** Append unbounded free-text memories; retain the selected draft or route;
  use word-level or heuristic similarity; publish events only after commit without an outbox; call
  LangSmith directly from the prospect feature.
- **Reasoning:** A bounded current profile gives later drafts useful style direction without creating
  contradictory memory or customer-specific retention. Transactional events preserve feedback across
  crashes while keeping online-quality integrations outside the freight feature.
- **Consequences:** The MVP retains product and outbox rows indefinitely. Outbox delivery is
  at-least-once, so downstream consumers must deduplicate by event ID. Migration `20260929_0002`
  keeps the newest pre-existing preference per tenant/rep and cannot restore deleted duplicates on
  downgrade.
- **Evidence:** Preference taxonomy and distance unit tests; approve/edit/reject replay tests;
  disposable-PostgreSQL migration, lifecycle-event, restart, isolation, and delivery-failure tests.

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

> The numeric evidence scope in this entry was expanded on 2026-10-01 after hosted experiments
> exposed missing context and evidence-claim values. The gate thresholds remain unchanged.

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
  remain informational. CAM-39 adds Jev semantic evidence pinned to `jev-1.13.0`; CAM-41 will
  calibrate each question independently against human labels and a GPT-5.6 Sol comparison judge
  before setting semantic gates.
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
  result validates wiring and gates, not live model quality. Hosted LangSmith experiments remain
  CAM-40 work requiring credentials, and semantic calibration remains CAM-41 work.
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

### 2026-09-29 — Semantic evaluation: narrow Jev decisions with fail-closed evidence

- **Decision:** Use seven async LangSmith-native semantic metrics with Jev `jev-1.13.0` as the
  default judge: `claim_supported`, `internal_data_leak`, `draft_matches_brief`, `next_step`,
  `entity_resolution_ok`, `actionability`, and `tone_fit`. GPT-5.6 Sol is an injected comparison judge
  and text-only failure explainer; it never substitutes automatically when Jev fails. Numeric, date,
  and count claims remain deterministic evaluator concerns.
- **Decision:** Semantic calls receive only strict, bounded, synthetic projections. Qualitative
  evidence is named by a stable `ev_<24 hex>` ID derived from canonical provenance and resolved
  locally to bounded, application-authored support text. Raw source/tool output, CRM bodies, traces,
  arbitrary objects, unknown citations, oversized state, and injection canaries are rejected before
  either provider is called.
- **Decision:** `claim_supported` is the minimum `P(yes)` across qualitative claims, with unresolved
  citations scoring `0` and no qualitative claims scoring `1`. `internal_data_leak` is `1-P(leak)`;
  `draft_matches_brief` and resolved `entity_resolution_ok` use `P(yes)`; `next_step` uses the
  probability assigned to the reference choice; `actionability` and applicable `tone_fit` retain
  their native 1–5 scores. Missing rep preferences make `tone_fit` explicitly not applicable.
  Provider or response-validation failures yield no score plus sanitized error metadata, causing
  coverage to fail closed.
- **Decision:** Jev has a 30-second budget and at most two SDK retries for connection/timeout errors,
  HTTP 408/429, and 5xx responses. Normalized metadata retains model revisions, actual option order,
  canonical SHA-256 state hash, probabilities, certainty and its source, latency, request ID, token
  usage, retry count, rubric and pricing versions, and estimated cost, but not raw state or provider
  debug payloads. Jev retry count is instrumented on its per-call SDK policy. Model, token, and retry
  source labels distinguish provider observations from configured aliases or unavailable adapter
  telemetry; missing values remain null. Noul certainty
  is `2 × |P(yes) - 0.5|`; choice and score certainty use normalized provider confidence.
- **Decision:** Cost metadata uses reviewed estimate cards: TypeSafe revision 2026-09-15 at
  `$0.042/M` input and free output, and OpenAI standard revision 2026-08-21 at `$4/M` input,
  `$0.40/M` cached input, and `$20/M` output. These are estimates rather than invoices and require
  review before future live runs. OpenAI retry-total input is conservatively charged at the standard
  rate when the adapter omits a cached-token total. TypeSafe zero data retention is not assumed; any
  production judge use requires vendor/DPA and retention review.
- **Decision:** Store the exact provider-neutral rubrics in versioned source code at
  `evaluation/rubrics/semantic_v1.py`, keep judge contracts in `evaluation/contracts/judges.py`, and
  keep Jev and OpenAI implementations in separate provider modules. Normalized evidence records
  `semantic-v1`, allowing results to resolve to the question text and criteria used.
- **Decision:** Semantic scores remain informational until CAM-41 calibrates each question against
  human labels and sets promotion thresholds. The explicit `--live` smoke uses synthetic state and
  local LangSmith `aevaluate(upload_results=False)`; it is live-provider evidence, not hosted
  LangSmith experiment evidence. Repository verification, local smoke evidence, and hosted
  experiment evidence remain distinct.
- **Alternatives considered:** Send whole traces or raw citations to a judge; let GPT silently rescue
  unavailable Jev results; reuse one semantic threshold without calibration; treat a local provider
  smoke or passing unit tests as a hosted experiment; assume provider zero-data retention.
- **Reasoning:** Narrow typed questions preserve deterministic ownership of computable facts, reduce
  privacy and prompt-injection exposure, and make provider behavior observable without masking
  missing coverage.
- **Consequences:** CI stays credential-free. Judge outages cannot produce a false pass. Live runs
  are opt-in and limited to synthetic, sanitized state; calibration and hosted experiment promotion
  remain separate work.
- **Evidence:** Projection/citation, answer-validation, option-permutation, retry, fail-closed,
  LangSmith result, and credential-gated synthetic smoke tests. Live smoke output is recorded only as
  sanitized execution evidence.

### 2026-09-30 — Model transport: optional regional OpenAI endpoint

- **Decision:** `TAKEHOME_OPENAI_BASE_URL` optionally routes both the orchestrator and specialist
  OpenAI models to one endpoint. It defaults to unset (SDK default host); a blank value also means
  unset. Only credential-free `https` URLs without query or fragment are accepted, trailing slashes
  are normalized, and settings validation errors never echo rejected input.
- **Alternatives considered:** Rely on the SDK's ambient `OPENAI_BASE_URL`; allow plain `http` for
  local proxies; configure orchestrator and specialist endpoints separately.
- **Reasoning:** The project key is bound to `https://us.api.openai.com/v1` and returns
  `401 incorrect_hostname` elsewhere. A typed application setting is explicit, validated, and visible
  in the env examples. Plain HTTP or URL-embedded credentials would expose the API key or a secret.
- **Consequences:** Local HTTP proxies are unsupported. The evaluation-only live smoke
  (`evaluation/experiments/semantic_smoke.py`) and judges build their own OpenAI clients and do not
  read this setting yet.
- **Evidence:** `tests/unit/test_settings.py`,
  `tests/unit/platform/test_openai_model_runtime.py` (mock transport asserts both models call
  `us.api.openai.com/v1/responses`).

### 2026-09-30 — Agent workflow: explicit artifact contract and one bounded write reminder

- **Decision:** Every agent's system prompt now lists each required artifact path (with media type)
  and states that only `write_file` creates it. Source-artifact agents also get the `coverage`,
  `evidence`, `claim`, and six-field `provenance` schema enforced by the guardrail. `account-context`
  maps `get_crm_account` to `/context/account.json` and `get_network_lanes` to
  `/context/our_network.json`. If an agent's final answer has no tool calls while required artifacts
  are missing, `ArtifactValidationMiddleware` injects exactly one reminder naming the missing paths
  and returns to the model. A second omission still fails closed at `after_agent`.
- **Alternatives considered:** Rely on the orchestrator's delegation text to name paths; write the
  artifacts deterministically from tool results outside the model; retry without limit; relax the
  guardrail.
- **Reasoning:** Deep Agents 0.7.19 intentionally emits no filesystem tool guidance, and the
  specialist only receives the orchestrator's free-text task, so a live model had no way to learn the
  paths or schema. Deriving the contract from `AgentSpec.required_artifacts` keeps the prompt and
  the validator from drifting. One reminder recovers the common "summarized instead of writing"
  failure without masking a model that cannot follow the contract.
- **Consequences:** Prompts are slightly longer but remain static and cache-friendly. At most one
  extra model call per agent, still bounded by the existing model/tool budgets. The reminder is
  stored in checkpointed messages with a fixed ID. Unavailable sources still fail validation because
  evidence must be non-empty. That is unchanged, deliberate fail-closed behavior.
- **Evidence:** `tests/unit/prospect_intelligence/test_specialist_artifact_contract.py` (a fake model
  that writes only the paths it can parse from its own system prompt reproduces the live failure on
  the prior prompt, and covers the reminder and bounded fail-closed paths). The existing root
  trajectory tests keep their exact call counts. A live `acme-foods` run is still pending.

### 2026-09-30 — Lane analysis: the scoring tool returns the canonical artifact

- **Decision:** `score_lane_fit_v1` now returns the exact `LaneAnalysisArtifact` JSON
  (`method_version`, `verdict`, `top_lanes`). The lane analyst is instructed to write it verbatim
  to `/analysis/lane_fit.json` and explain it in `/analysis/lane_fit.md`. The tool and the final run
  output share `services/lane_analysis.py::analyze_lanes`: `needs_more_data` unless freight and network coverage are
  both complete and freight lanes exist, otherwise `fit` when a direct lane ranks, else `no_fit`.
- **Alternatives considered:** Keep returning a bare ranked list and have the model assemble the
  strict JSON; relax the strict parser; write the JSON outside the agent.
- **Reasoning:** A live `acme-foods` run failed because the analyst invented its own schema. The
  artifact is deterministic, so the model should transcribe it, not construct it. Previously the tool
  ranked lanes even when coverage was degraded, which could contradict the authoritative
  `needs_more_data` output. Sharing one helper removes that divergence.
- **Consequences:** With degraded coverage, the tool now reports `needs_more_data` with no lanes
  rather than a ranking. The agent can still write prose, but it cannot change the verdict or scores
  without failing validation.
- **Evidence:** `tests/unit/prospect_intelligence/test_agent_job_handler.py` (the tool result passes
  `LaneAnalysisArtifact.from_json` and equals the committed output lanes);
  `test_specialist_artifact_contract.py` (the prompt maps the tool verbatim to the file).

### 2026-09-30 — Operations: sanitized run-failure logging and portable env files

- **Decision:** When a run's handler raises, the worker logs `prospect_run_execution_failed` with
  `run_id`, `worker_id`, `error_code`, and the exception class name only, never its message. The SEC
  identity uses separate space-free `TAKEHOME_SEC_APP_NAME` and `TAKEHOME_SEC_CONTACT_EMAIL`
  settings; bootstrap composes the required `<app> <email>` header in code. Env examples contain no
  whitespace or quotes, and tests check that every example parses strictly, uses known
  `TAKEHOME_` keys, and loads into `Settings`.
- **Alternatives considered:** Log the exception message or traceback; rely on LangSmith traces
  alone.
- **Reasoning:** The first live failure left no local signal; the cause could only be recovered
  from checkpoint internals. Exception text can contain model output or source data, so the class
  name is the safe minimum. Spaced values accepted by python-dotenv can make `uv --env-file` stop
  parsing and silently drop later keys such as `OPENAI_API_KEY`; composing the SEC identity in code
  avoids parser-specific quoting behavior.
- **Consequences:** Operators can distinguish guardrail (`ValueError`) from provider or transport
  failures without exposing payloads. Existing local `.env` files must replace
  `TAKEHOME_SEC_USER_AGENT` with the two new settings.
- **Evidence:** `tests/unit/prospect_intelligence/test_persistence_runtime.py`,
  `tests/unit/test_settings.py::test_env_examples_are_portable_and_load_into_settings`,
  `make docker-config`.

### 2026-09-30 — Numeric grounding: internal briefs may cite exact evidence dates

> **Superseded** later on 2026-09-30 by "Agent workflow: judgment-based quality review before
> send_outreach": the regex grounding check no longer gates the brief.

- **Decision:** In `/output/brief.md` a full `YYYY-MM-DD` date is grounded only when that exact
  date appears in a string value of the `/context/`, `/research/`, or `/analysis/` JSON (for example,
  a provenance `retrieved_at`). Bare years, unmatched dates, and every other number still must equal a
  numeric JSON value. Customer outreach gets no date exemption and remains under the customer-safe
  allowlist. The brief and outreach prompt contracts now state these rules.
- **Alternatives considered:** Tell the model never to cite dates; extract every numeric token
  from all evidence strings; drop grounding for the internal brief.
- **Reasoning:** A live `acme-foods` run produced all 11 artifacts but failed at `send_outreach`
  because the brief cited source retrieval dates, which is desirable provenance practice. Pulling
  every numeric token from strings would ground arbitrary small numbers via timestamp parts; exact
  full-date matching keeps the boundary narrow.
- **Consequences:** A brief can cite when evidence was retrieved. A "prepared" date or any date not
  present in evidence still fails closed, and the prompt tells the orchestrator to leave it out.
- **Evidence:** `tests/unit/prospect_intelligence/test_agent_security.py`
  (`test_brief_may_cite_exact_evidence_dates_only`, `test_outreach_may_not_cite_evidence_dates`),
  `test_specialist_artifact_contract.py`.

### 2026-09-30 — Agent workflow: judgment-based quality review before send_outreach

- **Decision:** A read-only `quality-reviewer` subagent reviews `/output/brief.md` and
  `/output/outreach_draft.md` against all evidence, `/analysis/lane_fit.json`, rep preferences, and
  the shared brief template before `send_outreach`.
  - **Output:** it writes `/review/findings.json`, a strict `QualityReviewArtifact` with `round`
    1–3, verdict `pass`|`revise`, blocking/advisory findings, and `resolved_prior`. `pass` holds
    exactly when no finding is blocking.
  - **Revisions:** the orchestrator, which authored the brief, applies brief findings.
    `outreach-drafter`, which authored the outreach, applies outreach findings. There is no separate
    reviser, and each file keeps one author.
  - **Round cap:** at most three reviews (two revision rounds). Unresolved findings end the run
    without `send_outreach`, which fails closed.
- **Gate:** `send_outreach` requires all of the following:
  - a review happened;
  - the findings artifact's `round` exactly matches the current quality-review delegation ordinal,
    so an earlier pass or a future-numbered artifact cannot authorize changed drafts;
  - no brief write/edit or outreach redraft occurred after the last review, derived from the root's
    tool-call history (calls issued in the same turn as `send_outreach` do not count as a review);
  - the latest findings are `pass`;
  - every artifact data contract validates.

  An outreach redraft is allowed only when the current-round review is `revise` with an outreach
  finding and no redraft has followed it.
- **What changed at the gate:** the regex numeric-grounding and keyword/format outreach checks no
  longer gate `send_outreach`. Draft content is judged by the reviewer. The reviewer counts
  semantic equivalents as supported (0.8 = 80%, 582400 = $582.4K) and provenance dates are fine.
- **Unchanged boundaries:**
  - the domain v1 outreach template allowlist (`validate_customer_outreach`) is still enforced when
    the analysis is committed and on rep edits;
  - rep edits at approval still run the deterministic outreach checks;
  - offline code evaluators still measure grounding and safety.
- **Prompts:** each agent has an ALL-CAPS triple-quoted prompt in `agents/prompts/` using the same
  sections (Role, Business context, Where you sit in the workflow, Inputs, Task, Rules, Finished
  when). The generated artifact contract is appended. The orchestrator and reviewer share one brief
  template, and the drafter and reviewer both state the v1 outreach templates.
- **Budgets:** orchestrator 30 model / 48 tool calls (was 20/32); reviewer 10/16.
- **Alternatives considered:** Keep the regex checks as a hard gate or expose them to the reviewer
  as tools; a dedicated revision agent; letting the orchestrator revise the outreach; comparing
  drafts across rounds.
- **Reasoning:** Two live `acme-foods` runs produced complete artifacts but crashed on token-level
  checks that rejected legitimate writing, with no feedback to the agent. A reviewer that reads the
  evidence can judge meaning and formatting, and its findings give the authors actionable fixes.
  Single ownership keeps accountability clear.
- **Consequences:** Brief and outreach content safety now rests on one model's judgment, backed by
  the domain template allowlist and the rep's approval. Worst-case cost rises by up to three
  reviews and two redrafts. The trajectory evaluator now requires a review before
  `review.requested`, permits redrafts only between reviews, and flags more than three reviews.
- **Evidence:** `tests/unit/prospect_intelligence/test_quality_review.py` (contract, ordering,
  freshness, round cap, and compiled revise-then-pass and exhausted trajectories),
  `test_specialist_artifact_contract.py` (prompt structure, path drift, shared template),
  `tests/unit/evaluation/test_trajectory.py`. Live: `acme-foods` run `9c58a67e` (commit `387e958`)
  reached `awaiting_review` (`fit`, top lane PHX→LAX, route-template outreach) after one review
  round with no findings; the brief matched the template and `lane_fit.json` figures. This is a
  single live run, not a LangSmith experiment, and it did not exercise a revise round.

### 2026-09-30 — Deferred: Jev (System One) runtime guardrail before rep review

- **Decision:** Do not add a Jev guardrail on the final pre-review step yet.
- **Reasoning:**
  - TypeSafe offers no zero data retention, so runtime judging of CRM-derived drafts needs a
    redaction design.
  - Jev lives in offline `backend/evaluation`, which the app must not import; a runtime adapter
    belongs in `agent_quality`.
  - It adds a 30 s external dependency with an unsettled outage policy (fail-open vs fail-closed).
  - Adding it together with the new reviewer would confound diagnosis.
- **Staged path:**
  1. Measure how often Jev's offline semantic metrics and reviewer verdicts disagree.
  2. Add Jev as a non-blocking online evaluator (score and alert) behind redaction.
  3. Promote it to a blocking gate only when disagreement, redaction, latency, and outage policy
     are settled.
### 2026-09-29 — Review console: operational-first workspace and disclosure rules

- **Decision:** The product is presented as **Prospect Intelligence**. The workspace opens directly
  in the first viewport, with an accounts rail and a single decision-first workspace.
- **Decision:** While outreach awaits review, the review is the page's primary task and comes
  first:
  - The status reads "Awaiting your review".
  - One accent-framed checkpoint ("Review the outreach to {account}") holds the subject/body
    editor and large Approve / Reject actions.
  - A "Why this account" rationale sits beside the editor: verdict, action, modeled totals and the
    lead lane, with a link to the evidence.
  - Lanes, model assumptions and sources follow under "Supporting evidence".

  The outcome receipt, neutral outcomes and progress take the same top slot. "Run prospect agent"
  (formerly "Build brief") becomes
  a secondary action once a brief is on screen.

  The marketing hero and the invented "Northstar" brand are removed, since that name collided with
  the Northstar Retail demo account.
- **Decision:** The brief leads with the fit verdict, then the recommended action (label plus the
  backend's readable text), then the summary. Modeled revenue and modeled deadhead avoided come
  next, labeled "Modeled … / yr" and paired with an "Internal model · Model assumptions"
  disclosure. That disclosure states they are internal estimates, not booked revenue, and gives
  the revenue, deadhead and `lane_fit_v1` formulas. Totals are shown compactly (for example
  `$1.25M`); exact values stay in the element title and in each lane row.
- **Decision:** The API adds two fields:
  - Lane score components (`backhaul_fill`, `density`, `equipment_match`), so the UI can show why a
    lane scored as it did.
  - An optional coverage `mode` (`live | snapshot | fixture`), stamped by each source adapter and
    persisted with the analysis.

  Both changes are additive; older persisted rows decode with `mode = null`, shown as "Mode not
  reported". Mode labels are Live, Snapshot and Synthetic fixture.
- **Decision:** Degraded and unavailable sources are always listed with their mode and detail.
  Complete sources collapse behind "Show all N sources". Each evidence item shows:
  - its claim;
  - the source, mode and UTC retrieval date;
  - its version, location and artifact.

  The brief is dated by its most recent evidence retrieval.
- **Decision:** `no_fit` and `needs_more_data` are neutral outcomes:
  - neutral pills, including the run's Completed pill;
  - no alert;
  - no editor;
  - "No outreach was drafted for this outcome."
- **Decision:** Polling runs every 1.2 s while a run is queued or running and stops at review or
  terminal states. A failed poll retries up to 3 times with exponential backoff (2.4 s, 4.8 s,
  9.6 s). After that, updates pause with an announced alert and a manual "Resume updates"; research
  continues on the server. Progress is announced through one polite live region.
- **Decision:** The outreach editor holds only the customer-facing subject and body. Scores,
  modeled figures, sources and evidence never appear in the review column. The primary action
  reads "Approve simulated send" for an unchanged draft and "Submit edit" once the draft differs.
  All review buttons are disabled while a decision is in flight, and duplicate submissions are
  ignored.
- **Decision:** Review failures are announced inline with `role="alert"` inside the checkpoint,
  the draft is always preserved, and server messages are never rendered verbatim:
  - **`409` on an edit:** "This edit can't be sent". Focus moves to Subject, with "Restore original
    draft" and "Refresh run". The backend uses one `conflict` code for unsafe copy and for a run
    already decided elsewhere, so both recoveries are offered.
  - **`409` on approve or reject:** "This run already has a different decision", with a focused
    "Refresh run".
  - **`422` on an edit:** "Check the subject and message", with focus on Subject. A `422` on any
    other decision asks for a refresh.
  - **`404`:** "This run is no longer available". The alert takes focus and the checkpoint locks.
  - **`503` or an unreachable backend:** "Your decision wasn't recorded", with a focused "Retry
    decision" that resends the identical request and token. The stored retry is discarded as soon
    as the rep edits the draft, so it can never send stale text.
  - **Stale responses:** decision and refresh responses for a run that is no longer on screen are
    dropped. The account rail and new-run action remain locked for the full `awaiting_review` state,
    not only while a decision request is in flight, because the MVP has no run-history/resume view.
  - **Failed runs:** fixed copy is shown ("No customer-facing output was produced") instead of the
    stored error message.
- **Decision:** Reject requires an inline confirmation ("Reject draft" / "Keep reviewing"). A
  successful decision moves focus to the outcome heading:
  - "Simulated send recorded … No real email or CRM write occurred."
  - "Draft rejected. No message was sent."
- **Decision:** The same-origin proxy returns the typed retryable `service_unavailable` envelope
  when the backend is unreachable, so the UI treats it like any other retryable 503. It rejects `.`
  and `..` path segments with a typed `400`, so requests cannot escape the backend's `/api/v1`
  surface. It never sends a body for GET or HEAD.
- **Decision:** Server and provider text is rendered only as React text nodes, never as HTML.
- **Reasoning:** Reps must be able to trust and verify each number quickly without scanning a wall
  of text, and approval is the safety boundary, so it gets the only accent and explicit failure
  recovery.
- **Evidence:**
  - CAM-35/CAM-36 Vitest component and boundary tests, plus the proxy test.
  - Backend router tests for score components and coverage mode.
  - Playwright desktop and Pixel 7 flow covering the `409` path.

### 2026-09-30 — Live agent progress: real specialist attempts for the demo

- **Decision:** A run begins with Account context, External research, Lane analysis, Drafting
  outreach, Quality review, and Your review. They come from real execution, not an estimated
  timeline:
  - The orchestrator's `ProgressMiddleware` records start, done or failed for every `task`
    delegation, keyed by `subagent_type`.
  - The shared source-tool boundary records each source call against the active specialist.
  - Account context and External research may show as running at the same time.
  - Each later drafter/reviewer cycle appends another fixed-label attempt before human review, up to
    three quality-review attempts. Retries reuse an unfinished attempt rather than duplicating it.
  - Unknown specialists and tools are ignored, not stored.
- **Decision:** Only fixed step labels, bounded attempt keys, fixed source labels (for example
  "SEC EDGAR filings"),
  `ok`/`unavailable` outcomes and timestamps are persisted. Each step keeps at most 12 activity
  entries. Tool arguments, results and model text never enter progress state.
- **Decision:** The percentage reflects completed agent attempts, is capped below completion while
  work is running, and never decreases or overflows during revisions. The stage reads
  "{specialist} running". When analysis commits:
  - Specialists that never ran are marked skipped.
  - Review opens for a fit, or is skipped for no-fit and needs-more-data.
  - A decision completes review.
  - A terminal job failure marks the running step failed and the rest skipped.
- **Decision:** Progress writes are best-effort. They pass through the worker's lease guard, are
  serialized per run, and ignore stale claims and non-running runs. Failures are logged and never
  fail or retry the run. Rows written before this change have no steps, and the UI falls back to the
  stage line.
- **Decision:** While the agent works, the workspace leads with an "Agent progress" tracker:
  - Each step shows its status and elapsed time. The timer ticks client-side, and only while a step
    is running.
  - The running step's source log is open by default; finished steps can be opened.
  - Only stage changes are announced, never the timer.
  - Once review opens or the run ends, the tracker collapses to "Agent run · N steps · m:ss" with
    "View steps".
- **Decision:** Accounts still load automatically. A "Reload" control and an "N assigned" count sit
  in the rail. The kickoff reads "Run prospect agent" and shows "Agent running…" while busy.
- **Reasoning:** The demo narrates a real multi-agent run. Progress must be truthful so it holds up
  to stakeholder questions and matches the LangSmith trace. Polling richer GET data avoids a new
  streaming transport.
- **Evidence:**
  - Backend: progress domain, service, middleware, source-hook, worker, router and PostgreSQL tests.
  - Frontend: tracker and workspace Vitest tests.
  - Playwright tracker scenario on desktop and Pixel 7.

### 2026-09-30 — Browser validation: desktop-only MVP support boundary

- **Decision:** CAM-37 validates the MVP in desktop Chromium. Browser acceptance covers keyboard
  account selection, truthful queued and running progress, sourced outcomes, durable human-review
  resume, safe edit recovery, reject confirmation, simulated-send receipts, accessible primary
  controls, and the absence of horizontal overflow. Mobile behavior is outside the MVP support and
  validation boundary; existing responsive implementation remains but is not claimed as verified.
- **Decision:** Browser validation uses repeatable DOM, state, accessibility, and API-boundary
  assertions rather than committed screenshot baselines. Playwright traces, screenshots, reports,
  and other generated browser artifacts remain uncommitted.
- **Decision:** One browser suite uses mocked application APIs for complete state and failure
  coverage. A separate credential-free suite exercises the deployed Next.js, FastAPI, PostgreSQL,
  LangGraph checkpoint, and worker path with deterministic synthetic inputs. External model,
  LangSmith, and public API access remain disabled in both CI paths.
- **Alternatives considered:** Retain Pixel 7 acceptance; commit viewport screenshots as visual
  baselines; exercise live model and provider integrations in browser CI.
- **Reasoning:** Desktop behavior is the agreed one-week MVP and demo boundary. Behavioral checks
  give reviewable coverage of the safety-critical workflow without treating generated pixels as a
  stable design contract, while deterministic full-stack coverage proves durable integration without
  credentials, network variability, or provider cost.
- **Consequences:** Responsive code may continue to work, but mobile compatibility requires a later
  explicit design and test pass before it can be promised. Visual regressions not represented by
  layout, accessibility, or behavioral assertions can escape this suite. The boundary can be rolled
  back by adding approved viewport projects and pinned visual baselines without changing product APIs.
- **Evidence:** Mocked desktop Playwright scenarios, the isolated Compose full-stack journey, and
  `make test-e2e`; repository verification and Compose validation remain separate required checks.

### 2026-09-30 — Loading, account pagination, and active-run motion

- **Decision:** Known account and workspace layouts use neutral skeletons only while their data or
  run-start request is pending. Skeleton shapes are decorative, animate only when reduced motion is
  not requested, and never replace empty, degraded, failed, review, or terminal content. Each
  loading region exposes one concise status; animation frames are never announced.
- **Decision:** The account rail paginates the already loaded tenant-scoped account list in groups
  of five without changing the account API. Pagination appears only for multiple pages, preserves
  API order, and reports both the visible range and current page. Manual page changes clear the
  hidden account selection and any start error, move focus to the first newly visible account, and
  leave a completed or failed run visible.
  Pagination is locked with account switching during start, restoration, active execution, and
  human review. Restoration opens the selected account's page; reloads reveal a retained account,
  clamp a shortened list, or clear an account that disappeared.
- **Decision:** Queued and running runs show a restrained activity cue, and only non-review running
  steps pulse. Review and terminal states have no activity animation. Status text, color, and the
  active-step ring remain the complete static signal for reduced-motion users.
- **Reasoning:** The console should feel alive only when real work is pending, preserve the human
  review boundary, and let a rep browse longer assigned-account lists without creating a hidden run
  target or expanding the MVP API surface.
- **Evidence:** CAM-49 component/accessibility tests and desktop Playwright coverage for skeleton
  replacement, pagination, queued/running transitions, review handoff, reduced motion, and overflow.

### 2026-09-30 — Hosted experiments: controlled synthetic matrix and promotion policy

- **Decision:** The explicit CAM-40 `--live` path idempotently publishes `freight-prospect-v1` with
  seed `28029`, its canonical SHA-256 checksum, stable example IDs, and exactly 16 core plus 8 edge
  examples. Controlled hosted metadata, example, or split drift fails closed; LangSmith's injected
  SDK runtime inventory is not part of the canonical dataset checksum. Each variant runs three
  repetitions: baseline GPT-5.6 Sol/Luna with prompt `v1` and interpreter on; Luna/Luna lower cost;
  Sol/Luna with `evidence-self-check-v2`; and Sol/Luna with the interpreter off.
- **Decision:** The hosted target uses real models and graph `prospect-intelligence-v1`, but all
  business-data tools resolve through deterministic synthetic handlers with in-memory persistence
  and public-source reads disabled. Only synthetic inputs and sanitized outputs may be uploaded.
  Every target invocation must exactly match the local canonical input for its stable example ID;
  a hosted dataset edit between publication and execution fails before any model or tool call.
  Per-example rep identity and the representative scope are SHA-256 digests; no real rep identifier,
  prompt, raw source/provider payload, tool argument, canary, or private customer data enters the
  committed report. File-contract normalization allowlists only the exact per-example hashed memory
  path used by that run; other unexpected runtime files still fail the deterministic invariant.
- **Decision:** `experiments.offline.results.gate_results()` remains the only deterministic release
  authority.
  The full deterministic suite and all seven Jev `jev-1.13.0`/`semantic-v1` metrics run for each
  hosted variant, but semantic scores, coverage, judge latency, and judge cost remain evidence-only
  pending CAM-41 calibration. Aggregate evidence is sliced by variant, core/edge split, dataset tag,
  metric, and synthetic failure ID.
- **Decision:** A live graph or output-normalization exception becomes a sanitized `target_error`
  result rather than a dropped experiment row. The result exposes only the exception type, rep hash,
  elapsed wall time, and provider-observed token/cost totals; it carries empty evaluation projections
  so deterministic coverage fails closed without leaking the provider message or understating
  measured spend.
- **Decision:** Reject a candidate whose target cost or mean target latency exceeds baseline by more
  than 20% unless it passes every deterministic gate, fixes at least one baseline deterministic
  failure, and introduces no new deterministic failure. Semantic improvement alone cannot justify
  the regression. Target estimates use the CAM-40 standard OpenAI card: Sol `$4/$0.40/$20` and Luna
  `$0.20/$0.02/$1.20` per million input/cached/output tokens. Jev cost is reported separately using
  the reviewed 2026-09-15 TypeSafe card; estimates are not invoices.
- **Decision:** LangSmith persists the dataset, traces, evaluator feedback, metadata, and completed
  experiment runs under workspace retention. A later-variant failure can leave earlier experiment
  uploads in LangSmith, but a partial matrix yields no valid aggregate report or promotion decision;
  rerun all four variants and do not merge attempts. Repository tests, the CAM-38 local report, the
  CAM-39 provider smoke, and hosted CAM-40 records are separate evidence classes.
- **Decision:** Local evaluator iteration is insufficient proof of hosted completion. After each
  variant, the runner flushes pending traces and reads LangSmith back, requiring exactly 72 root
  runs, three repetitions of every canonical example, the expected per-example rep hash and code
  revision, and one feedback record for every deterministic and semantic evaluator. Any discrepancy
  stops the matrix before report generation. The code revision is captured before model execution as
  the commit plus a deterministic SHA-256 fingerprint of tracked changes and untracked, non-ignored
  files, then reused in every experiment's metadata and the final report.
- **Alternatives considered:** Upload live customer or public-source data; use semantic scores as
  uncalibrated gates; allow a costlier candidate on judge quality alone; resume or merge partial
  attempts; store raw hosted results in git.
- **Reasoning:** A fixed synthetic population and controlled one-variable comparisons make model,
  prompt, and interpreter trade-offs reviewable without exposing customer data. Reusing the strict
  offline gate prevents hosted orchestration from changing release semantics, while retained hosted
  traces support stakeholder inspection.
- **Consequences:** The hosted command requires LangSmith, OpenAI, and TypeSafe credentials and can
  incur provider cost. Interrupted suites may leave diagnostic hosted experiments that require clear
  labeling and workspace-retention review. Human-calibrated semantic promotion remains CAM-41 work.
- **Evidence:** CAM-40 dataset publication/drift, live-target, hosted-runner, aggregation, report
  redaction, cost, regression-policy, credential-gating, and runtime-option tests; sanitized hosted
  experiment evidence is recorded separately after a complete live run.

### 2026-10-01: Numeric grounding syntax and CAM-40 MVP decision

- **Decision:** Numeric grounding checks quantitative claims in the brief and outreach against
  `/context/`, `/research/`, and `/analysis/` JSON. Numeric scalars and complete numeric strings are
  evidence. Embedded values are extracted only from fields named `claim`, not from provenance URLs,
  record identifiers, or arbitrary strings. The evaluator removes a complete ISO date or datetime,
  an alpha-prefixed multi-dot version label such as `FAF5.7.1`, and a Markdown ordered-list marker
  at the start of a line before extracting quantitative claims. It does not exempt a bare year,
  standalone decimal, money, percentage, quantity, or number elsewhere in prose. Stable `ev_`
  citation IDs remain outside the numeric token boundary. Date support is a citation and
  claim-review concern, not a quantitative-grounding concern.
- **Decision:** Keep the baseline configuration: GPT-5.6 Sol orchestrator, GPT-5.6 Luna specialists,
  prompt `v1`, and interpreter enabled. Reject lower-cost routing because it produced 21 target
  errors. Reject the prompt revision because it did not improve deterministic quality and increased
  target cost and latency. Do not disable the interpreter because the retained sample showed no
  useful cost, latency, or quality gain.
- **Decision:** Close CAM-40 with a labeled retained-evidence memo instead of buying quota for
  another run. Baseline, lower-cost, and prompt-revision each have 72 roots. Interpreter-off has 51
  roots across all 24 examples, with every example represented at least twice. This is enough for
  the MVP configuration choice, but it is not a completed four-variant release-gate result. The
  strict hosted runner still requires 72 roots for every variant and never merges attempts.
- **Alternatives considered:** Pay for more LangSmith traces and rerun all model and Jev calls;
  weaken hosted persistence checks; treat the partial matrix as a formal gate pass.
- **Reasoning:** The completed variants give a clear model and prompt decision. The partial
  interpreter sample covers the full dataset and gives no signal that disabling the interpreter is
  beneficial. Another paid run would add little value to the one-week MVP.
- **Consequences:** The report separates original hosted feedback from the corrected local numeric
  re-score under `freight-evaluators-v3`, records that the exact dirty source revision is
  unavailable, and does not claim formal matrix completion. A later promotion decision can rerun
  the unchanged strict matrix if stronger evidence is needed. Online quality events already queued
  with `freight-evaluators-v2` remain durable, but their semantic inputs are routed to annotation as
  incompatible rather than being judged under the changed v3 rules.
- **Evidence:** Focused numeric and parity tests, the 72-row credential-free regression, retained
  LangSmith root counts and experiment links, and `evaluation/reports/cam_40_hosted.md`.
