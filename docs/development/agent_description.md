# Freight Prospect Intelligence Agent — Implementation Description

Delivered MVP behavior is described directly; production evaluation and integration targets are
identified as deferred where they are not wired.

---

## 1. Purpose

MVP agent for the sales team of an asset-based truckload carrier. Given a shipper account
(existing customer or prospect), it:

1. Researches the shipper's freight activity across internal and third-party sources.
2. Computes how well the shipper's lanes fit our network (backhaul gaps, lane density).
3. Produces a sales brief for the rep and a draft outreach message.
4. Pauses for rep approval before anything is sent or written back to the CRM.

Business outcome: reps receive specific, verifiable lane analysis in the internal brief and use
approved outreach such as "Would you be open to comparing notes on your ATL-to-DAL freight needs?"
instead of unsupported commercial claims.

### Business model assumption

- Default: asset-based carrier. Network fit = shipper lanes that fill our backhaul gaps
  (reduce deadhead miles) or add density to lanes we already run.
- Alternate (config flag, not built for MVP): broker. Network fit = lanes where we have
  reliable carrier coverage and margin history.

---

## 2. Stack

- Python 3.11+, Deep Agents SDK (`create_deep_agent`), LangGraph checkpointer
- Code execution: `CodeInterpreterMiddleware` from `langchain-quickjs` (QuickJS, in-process,
  no sandbox). Note: interpreter code is JavaScript, not Python.
- Filesystem: `CompositeBackend`
  - default: `StateBackend` (per-run, ephemeral)
  - `/memories/`: `StoreBackend` namespaced by tenant and rep ID (persistent)
  - `/skills/`: traversal-confined packaged skill source, readable only by the lane analyst
- LangSmith: tracing, datasets, experiments, online evaluators, annotation queues,
  dashboards, alerts
- Judges: code for anything computable; Jev (TypeSafe decision model, pinned `jev-1.13`) as the
  default judge for all semantic criteria; LLM-as-judge only where written output is needed
  (see 7.4)
- Optional: Harbor (`harbor[langsmith]`) as a sandboxed offline eval runner
- Optional: LangMem background manager for rep-preference extraction from HITL edits

---

## 3. Data sources and integrations

| Source              | Type                 | Use                                                    | Build approach                                                                                                                                                 |
| ------------------- | -------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GenLogs             | Paid API (~$100K/yr) | Shipper lanes, facilities, volumes                     | Mock service matching public API docs schema (docs.genlogs.io): shipper lanes, shipper facilities, shipper by region. Seed from FAF5 so volumes are realistic. |
| FHWA FAF5           | Free public dataset  | Region-to-region freight volumes by commodity          | Load locally, expose as `market_lane_volume` tool                                                                                                              |
| FMCSA QCMobile      | Free API (web key)   | Carrier/competitor context, safety data                | Real integration                                                                                                                                               |
| SEC EDGAR           | Free API             | Public shipper financials, facility/expansion mentions | Real integration                                                                                                                                               |
| Web search (Tavily) | Free tier API        | Company news, expansion signals                        | Real integration                                                                                                                                               |
| CRM                 | Internal             | Account record, contacts, current business             | Mock                                                                                                                                                           |
| Our network         | Internal             | Our lanes, weekly loads, backhaul imbalance by region  | Mock (seeded, deterministic)                                                                                                                                   |

All mocks are deterministic and seeded so offline evals have ground truth.

Source access is injected through narrow CRM, freight-intelligence, carrier-network, market-data,
SEC, web-search, and carrier-registry Protocols. Bootstrap selects implementations. The MVP uses
synthetic private-source adapters plus real public SEC, Tavily, FMCSA, and pinned FAF adapters; it
does not create placeholder private-vendor clients. Every adapter returns normalized typed data,
explicit coverage, and evidence, and keeps its provider payload inside the integration boundary.
Live-source failures are disclosed as degraded or unavailable coverage and never silently replaced
with synthetic facts.

---

## 4. Virtual filesystem contract

Each specialist writes only its canonical artifacts below. Source artifacts use structured JSON;
analysis adds a short markdown summary, and final outputs are Markdown. Every evidence item carries
complete provenance. The orchestrator and evaluators rely on this contract.

```
/task/brief.md                 # task, account, objective, filesystem map. Orchestrator reads first.
/INDEX.md                      # manifest rebuilt by the outer workflow from canonical artifacts
/context/account.json          # CRM record + current business with us
/context/our_network.json      # our lanes, density, backhaul gaps
/research/freight_intel/       # shipper lanes, facilities, volumes (GenLogs mock, FMCSA)
/research/company/             # firmographics, news, signals (web search, SEC EDGAR)
/research/market/              # lane-level market volumes (FAF5)
/analysis/lane_fit.json        # scored lanes, opportunity sizing, method version
/analysis/lane_fit.md          # human-readable summary
/output/brief.md               # sales brief (orchestrator)
/output/outreach_draft.md      # draft message (drafting subagent)
/review/findings.json          # quality review verdict and findings (reviewer subagent)
/memories/{tenant_id}/{rep_id}/preferences.md  # persistent rep preferences
```

---

## 5. Agents and middleware

### Orchestrator

- Reads `/task/brief.md`, `/INDEX.md`, and `/memories/{tenant_id}/{rep_id}/preferences.md` first.
- Delegates to exactly five registered subagents via `task`; never calls data APIs directly.
- Requests account-context and external-research together. Delegation middleware requires both
  research contracts before lane analysis and the internal brief before outreach drafting.
- Writes `/output/brief.md` from files only, following the shared brief template in
  `agents/prompts/brief_template.py`.
- Runs the quality-review loop: delegates `quality-reviewer`; on `revise`, rewrites the brief for
  brief findings and re-delegates `outreach-drafter` for outreach findings, then reviews again. At
  most three reviews; unresolved findings fail the run closed.
- Calls `send_outreach` only after the latest review passed and no draft changed since it.
- Owns the HITL tool `send_outreach`. The MVP has no CRM mutation tool.

### Subagents

1. **account-context**: mock CRM + internal network → `/context/`
2. **external-research**: GenLogs-shaped freight activity, FMCSA, web search, SEC EDGAR, and FAF5
   through separate injected source tools → `/research/`
3. **lane-analyst**: uses the code interpreter with PTC. Reads `/context` and `/research`,
   loads `/skills/lane-fit-v1/SKILL.md`, fans out lane lookups, and computes scores → `/analysis/`
4. **outreach-drafter**: reads `/output/brief.md`, tenant/rep-scoped preferences, and review
   findings on a revision; writes `/output/outreach_draft.md` using an approved v1 template.
5. **quality-reviewer**: read-only judgment over the brief and outreach against all evidence, the
   lane analysis, rep preferences, and the brief template. No checking tools; writes only
   `/review/findings.json` (round, pass/revise verdict, blocking/advisory findings).

The Deep Agents default general-purpose subagent is disabled. One orchestrator is built with
`create_deep_agent()`; its five declarative, isolated specialists are compiled internally with
`create_agent()` and expose no `task` or root-only `send_outreach` tool.

### Context engineering

The orchestrator and specialists share one composite virtual backend while each receives an explicit
tool list, filesystem policy, and concrete middleware stack. Middleware projects the allowlisted task,
manifest, artifacts, and rep preferences before model calls; applies model/tool budgets; redacts
tool errors; treats source results as untrusted data; gates delegation and
`send_outreach` on review order and freshness; and validates each specialist's owned artifact
contracts. Draft content is judged by the quality reviewer rather than regex checks at the gate;
the v1 outreach template allowlist is still enforced in the domain when the result is committed and
on rep edits. LangGraph state contains checkpointed workflow data only, while the verified
`AuthContext`, source handlers, and other request-scoped dependencies use LangGraph
`context_schema`/`Runtime.context`. Optional `runtime-jev-v1` input/output nodes are wired around the
Deep Agent and default off; they checkpoint only sanitized decision metadata.
Platform trace privacy hides all run inputs, outputs, and metadata by default.

The code layout keeps those concepts visible as `chains.py`, `prompts/`, `specs.py`, `graphs.py`,
`compiler.py`, `state.py`, `tools.py`, `guardrails.py`, `runtime.py`, and `context.py`.
`middleware/` and SDK-formatted `skills/` remain directories. `ProspectRuntimeContext` stays in the
feature contracts, while `agents/context.py` bridges it into isolated declarative subagents because
Deep Agents 0.7.19 does not forward the parent's typed context. Invocation dependencies are never
copied into checkpoint state.

### Lane-fit scoring (`lane_fit_v1`)

Per shipper lane (origin region, destination region, loads/week, equipment):

- Match only carrier empty capacity on the exact same origin-to-destination lane; reverse-direction
  capacity is not a match.
- `matched_loads = min(shipper_loads, empty_capacity)`
- `backhaul_fill = matched_loads / empty_capacity`, or zero when capacity is zero
- `density = min(existing_same_lane_weekly_loads / 40, 1)`
- `equipment_match = carrier fleet share for the shipper's equipment type`
- `fit_score = 0.50*backhaul_fill + 0.30*density + 0.20*equipment_match`
- Rank eligible lanes by score, matched loads, origin, then destination; retain the top three.
- `modeled_gross_revenue = matched_loads * estimated_rate * 52`
- `modeled_deadhead_avoided = matched_loads * full_origin_destination_miles * 52`

Duplicate routes or malformed inputs produce `needs_more_data`; complete inputs with at least one
matched lane produce `fit`, and complete inputs with no matched lane produce `no_fit`. The monetary
and mileage values are internal models, not booked revenue, margin, or guaranteed savings. The
formula lives in the runtime-loaded `lane_fit_v1` skill and an independent Python evaluator reference
verifies the analyst's numbers.

### Code interpreter rules

- PTC allowlist: `read_file`, `glob`, and read-only lane-analysis tools only.
- Artifact writes use the lane analyst's path-scoped filesystem tools outside PTC.
- Never allowlist `send_outreach` or `update_crm`. PTC calls bypass `interrupt_on`.
- Defaults: `mode="thread"`, 5s timeout, 64MB memory; tune if lane fan-out needs more.

---

## 6. Human-in-the-loop and memory

- Named durable interrupt: `send_outreach`; allowed decisions: approve, edit, reject.
- Checkpointer required.
- Review resumes that interrupt through the compiled runtime. If the graph review handler is
  unavailable, the API returns retryable `503 service_unavailable`; it never records the decision
  through a direct service fallback.
- Every HITL decision and simulated receipt is persisted in PostgreSQL. LangSmith feedback remains a
  privacy-reviewed production integration.
- Rep edits produce a tenant/rep-scoped preference summary that is materialized into the agent's
  StoreBackend memory on later runs. Rich LangMem extraction remains optional and deferred.

---

## 7. Evaluation (primary focus)

Principle: offline evals decide whether a version is ready to ship. Online evals tell you
whether it is still working in production. Production failures become offline test cases.

The repository contains the deterministic dataset, evaluator implementations, hosted experiment
orchestration, and credential-free tests. CAM-40 persists the synthetic dataset and four controlled
experiments in LangSmith only after an explicit `--live` opt-in. CAM-41/CAM-50 add a separate
human-preference alignment workflow whose human review and real-judge execution also require
explicit action and credentials. Live evidence must be reported separately rather than inferred
from repository checks.

### 7.1 Offline harness (Test)

**Dataset** (LangSmith dataset, versioned, with splits):

- `core` (15–20): synthetic accounts with planted lane overlaps and known facts
- `edge` (8–10): no GenLogs coverage, ambiguous company name (entity resolution), conflicting
  sources, zero network fit (correct answer is "not a fit"), prompt injection in web results
- `regression`: empty at start; filled from production failures (see 7.3)

Each example stores reference outputs: expected top-k lanes, expected fit verdict, known
facts, and the set of valid numeric values.

**Evaluators, by layer:**

| Layer               | Evaluator                                        | What it checks                                                                     |
| ------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Code (MVP headline) | `numeric_groundedness`                           | Every number in brief and draft traces to a value in `/research` or `/analysis`    |
| Code                | `lane_precision_at_k`                            | Top-k lanes match planted overlaps                                                 |
| Code                | `analysis_correctness`                           | Analyst's scores match the Python reference implementation                         |
| Code                | `fit_verdict_accuracy`                           | Correct fit / no-fit call, including edge cases                                    |
| Code                | `file_contract`                                  | Each subagent wrote required files with valid schema                               |
| Code (trajectory)   | `trajectory_checks`                              | Required subagents called; analyst ran after research; review before send; ≤3 reviews; no send without approval |
| Code                | `injection_resistance`                           | On injection examples: no forbidden tool call, no planted canary string in outputs |
| Code                | cost, latency, tool-call count                   | Efficiency budget per run                                                          |
| Jev (default judge) | Typed questions (below)                          | All semantic quality criteria, offline and online                                  |
| LLM judge           | Pairwise version comparison, failure explanation | Only where written reasoning is the output (see 7.4)                               |
| Human               | Annotation queue                                 | Label exactly 10 applicable cases per question; calibrate Jev per question (see 7.4) |

**Jev questions.** Each question gets its own small, filtered state built in code (not the
whole trace). Instructions state exact conditions and boundary cases.

| Key                    | Type                                 | State (projected in code)                 | Question                                                                                   |
| ---------------------- | ------------------------------------ | ----------------------------------------- | ------------------------------------------------------------------------------------------ |
| `claim_supported`      | noul, one call per qualitative claim | one claim + the research excerpt it cites | Is this claim supported by the cited excerpt?                                              |
| `internal_data_leak`   | noul                                 | outreach draft only                       | Does the draft mention internal-only information (our rates, margins, or other customers)? |
| `draft_matches_brief`  | noul                                 | brief + draft                             | Does the draft pitch the same lanes the brief recommends?                                  |
| `next_step`            | choice                               | brief                                     | {expand existing lanes, new lane pitch, not a fit, needs more data}                        |
| `entity_resolution_ok` | noul                                 | account name + resolved company profile   | Is the resolved company the same company as the account?                                   |
| `actionability`        | score 1–5 (levels defined)           | brief                                     | How actionable is this brief for a sales rep?                                              |
| `tone_fit`             | score 1–5 (levels defined)           | draft + rep preference file               | How well does the draft match the rep's stated preferences?                                |

Rules:

- Numbers and counts are never Jev questions; they stay in code evaluators.
- Raw web or tool output never goes into Jev state (injection risk); judge agent outputs only.
- Qualitative claims are extracted from the brief with a parser where possible; otherwise
  extraction is an LLM step and Jev judges each claim.

**Credentialed experiments:**

- Run all 16 core and 8 edge examples three times for each variant: baseline Sol/Luna with prompt
  `v1` and interpreter on; lower-cost Luna/Luna; Sol/Luna with `evidence-self-check-v2`; and Sol/Luna
  with the interpreter off.
- Use graph `prospect-intelligence-v1`, evaluator `freight-evaluators-v3`, rubric `semantic-v1`, and
  Jev `jev-1.13.0`. Upload synthetic inputs and sanitized outputs only; rep metadata is SHA-256 hashed.
- Keep `experiments.offline.results.gate_results()` as the deterministic promotion authority. Semantic scores
  remain evidence-only until human calibration. Reject cost or latency regressions over 20% unless
  the candidate passes every deterministic gate, fixes a deterministic baseline failure, and adds
  none.
- CI remains offline. Hosted datasets, traces, evaluator feedback, and experiments persist in
  LangSmith; repository reports contain sanitized aggregates only. A partial hosted matrix is
  diagnostic evidence, not a promotion result.

**Harbor (stretch, decide after core harness works):**

- Each dataset example becomes a Harbor task: `instruction.md` (account + objective),
  `environment/` (docker compose with mock GenLogs, CRM, network services), `tests/`
  (code evaluators write the reward).
- Run with `--agent langgraph` via `langgraph.json` + `make_graph` factory, `--plugin langsmith`
  so jobs land as LangSmith experiments; `-e langsmith` for LangSmith sandboxes or local Docker.
- Value: isolated, reproducible, parallel trials; pass@k.
- Keep one source of truth: generate Harbor tasks and the LangSmith dataset from the same
  synthetic-account generator.

### 7.2 Online harness (Monitor)

CAM-42 delivers an opt-in app-side evaluator path. After graph execution, the application builds a
bounded envelope containing deterministic signals and one sanitized state per Jev question, then
commits it with the product transition's outbox event. A lifecycle worker publishes a dedicated
LangSmith event run keyed by the quality-event ID, deterministic feedback IDs, HITL decisions, and
annotation routing. It never uploads the envelope, trace, raw artifacts, source payloads, prompts,
contacts, or judge responses.

- Code: all ten deterministic catalog signals on completed analyses. Lane precision, correctness,
  and verdict compare the agent artifact with the canonical product analysis; latency and tool count
  are informational. Cost is explicitly unavailable until versioned provider usage/pricing exists.
- Jev: the same seven app-owned questions and rubric as the offline harness, with no LLM fallback.
- Implicit feedback: HITL approve/edit/reject and edit distance.
- Failure behavior: deterministic failures and rejection route to annotation; provider failure or
  timeout keeps the row pending for retry; duplicate provider conflicts are success.
- Operation: disabled by default; enabling requires LangSmith and TypeSafe credentials. Defaults are
  ten events per batch, one-second idle polling, and a 75-second event budget.
- Bounds: eight qualitative claims per envelope and eight concurrent Jev calls. Version-mismatched
  pending envelopes are annotated without calling a newer rubric.

Dashboard/alert provisioning, traffic execution, canary policy, production retention, and alert
destinations remain CAM-43/deployment work. The current alert numbers are demo defaults rather than
SLOs. CAM-41/CAM-50 alignment produces recommendations only; semantic scores remain informational.

### 7.3 Closing the loop

1. Online evaluator or rep rejection flags a run.
2. Run routes to an annotation queue (automation rule on feedback key).
3. Reviewer labels failure type; example is added to the `regression` split.
4. Fix is validated offline against `regression` + `core` before redeploy.
5. The example stays in the dataset so the failure stays fixed.

CAM-44 implements this as an explicit, credential-free handoff. PostgreSQL stores the candidate,
review decision, audit transitions, and immutable promoted example. A canonical operator export
materializes `freight-prospect-regression-v1`; the local release runner composes it with the
unchanged core/edge population. The MVP does not automatically copy LangSmith traces or expose a
review API/UI, so independently sanitized target inputs and references are required at intake.

### 7.4 Judge policy

Order of preference:

1. **Code** for anything computable: numbers, counts, dates, schemas, tool-call order,
   string matches. Jev is documented as weak on numeric precision, counting, and dates.
2. **Jev** for every semantic judgment that fits a noul, choice, or score.
3. **LLM judge** only when the output itself must be text: pairwise version comparisons
   with written rationale, failure explanations on flagged traces, claim extraction when a
   parser can't do it.

Calibration (makes the judge choice an eval-driven decision, not a preference):

- Select exactly 10 applicable cases per question with seed `28029`, deduplicated by projected-state
  hash and split into five alignment plus five untouched holdout cases.
- A designated single reviewer labels the bounded state without judge answers, freezes the complete primary pass, and
  separately adjudicates every low-confidence or ambiguous case. The reference is
  `cam-41-labels-v1`, a single-reviewer two-pass set rather than inter-rater validation.
- Run Jev and GPT-5.6 Sol three times in a five-case alignment phase, then a separately authorized
  frozen five-case holdout phase. Deterministic choice and score orders repeat the canonical baseline
  twice before one alternate permutation, with all answers mapped back to canonical labels.
- Report valid-attempt coverage over `3 × cases`, exact agreement and confusion counts, balanced
  accuracy or explicit class imbalance, ordered-score MAE/within-one agreement, run-to-run disagreement,
  option-order sensitivity, cost, latency, and Jev's exact-agreement delta from Sol.
- Use only the alignment split for bounded rubric diagnosis or revision. Freeze any successor rubric
  before the untouched holdout.
- Recommend `retain` only with 100% holdout attempt coverage, at least 85% exact agreement, and Jev
  no more than five percentage points behind Sol. Otherwise recommend `revise`, `split`, or `replace`
  with rationale. These are evidence-only recommendations, not release gates.

The full operator and evidence protocol is in
[evaluator-alignment-process.md](../evaluation/evaluator-alignment-process.md). The 70-case
`cam-41-labels-v1` reference set and 13 required adjudications are complete. The credentialed
alignment phase is read back with 154/210 initially valid attempts. Its ordered-score contract
finding was resolved on the alignment split, and targeted v2 evidence now gives 60/60 score
coverage. One v3 score-anchor prompt experiment was rejected because it regressed `tone_fit`
within-one agreement and introduced Jev `actionability` instability. The accepted original
categorical plus v2 score evidence is composed into a read-back-verified 210-attempt manifest.
Three questions remain alignment-only revision candidates. CAM-41/CAM-50 close on this evidence;
the implemented holdout was explicitly waived for the take-home and remains unrun. Repository checks
do not substitute for the completed live alignment phase.

Jev operating rules:

- Pin the model version (`jev-1.13`), never `jev-latest`; re-calibrate on upgrade.
- Log state, option order, model version, and confidence with every feedback entry.
- Test option-order permutations for each choice question during calibration.
- Keep states small and relevant; filter in code before calling.
- Offline: LangSmith evaluator wrappers around the app-owned TypeSafe/Jev contract. Online: the same
  app-owned Jev client consumes bounded states asynchronously; TypeSafe and LangSmith credentials
  remain server-only runtime secrets.

---

## 8. Production path (document, don't build)

- Memory scoping: per-rep namespace; team-level shared namespace for playbooks; no cross-rep reads.
- Auth: rep auth to the app; agent uses delegated rep credentials for CRM writes; service
  identity for read-only data APIs; per-tenant API keys.
- Multi-tenancy: tenant ID in every store namespace and data query; trace metadata is hidden by
  default until a privacy-reviewed hashed scope is implemented.
- Data licensing: GenLogs terms may restrict what appears in customer-facing text; guardrail
  checks draft for restricted fields.
- Third-party judge data retention: TypeSafe does not currently offer zero data retention;
  review before sending customer data to Jev in production. Options: redact state before
  judging, or fall back to a self-hosted judge for sensitive fields.
- Judge robustness: Jev can be steered by adversarial text in its state, so it never sees raw
  tool or web output. In-run draft-content gating is the quality reviewer's judgment plus human
  approval (and the domain outreach-template allowlist); deterministic code checks are retained
  offline as measurement. A Jev runtime guardrail is deferred (see the business-logic log).
- Durability: checkpointer-backed resume; idempotent `update_crm`; retries with backoff and
  response caching for paid APIs.
- Guardrails: prompt-injection screening on web content; PTC allowlist as permission boundary;
  interpreter runs in-process, so isolate workers in production.

---

## 9. Scope and evidence

**Reviewable MVP in this repository**

- Compiled orchestrator plus five specialists, middleware-enforced filesystem contract, and a
  role-scoped `lane_fit_v1` skill.
- Durable HITL on outreach with no direct review fallback.
- Deterministic CRM, GenLogs-shaped, and network sources; packaged FAF data; optional live SEC,
  Tavily, and FMCSA adapters that disclose unavailability rather than substituting fixtures.
- Versioned offline data, deterministic evaluators, experiment configuration, traffic simulation,
  and sanitized quality-event contracts.
- Friction and business-logic decision logs maintained with implementation changes.

**Credentialed/live evidence still required**

- Model/provider smoke run and model-directed delegation trajectory.
- Privacy-reviewed tracing, online evaluators, dashboard, alerts, and annotation workflow.

**Deferred/stretch**

- Harbor tasks, LangMem extraction, broker mode
- Real GenLogs access, real email sending, CRM mutation, and authentication.

---

## 10. Deliverables to support

- Code repo (README with run instructions for agent, offline evals, simulator)
- Slide deck inputs: architecture diagram, trade-offs, eval results table, production path
- Friction log (`FRICTION_LOG.md`), updated as issues occur
