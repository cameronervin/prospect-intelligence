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

- **Decision:** SEC, Tavily, and credentialed FMCSA are live-first with disclosed fixture fallback;
  FAF5.7.1 is a checksummed bulk snapshot; GenLogs, CRM, and carrier-network data are deterministic
  synthetic fixtures. Every fact records source mode and provenance.
- **Alternatives considered:** Live APIs in offline evaluation; silently substituting fixtures; real
  GenLogs data.
- **Reasoning:** Offline ground truth must be reproducible, and vendor licensing/availability must not be
  misrepresented.
- **Consequences:** Missing optional sources degrade visibly. Missing critical freight/network evidence
  produces `needs_more_data`; the system never invents facts.
- **Evidence:** Adapter contract tests, dataset repeatability tests, source documentation, and
  credential-gated smoke evidence.

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
