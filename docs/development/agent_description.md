# Freight Prospect Intelligence Agent — Build Description (v2)

Hand-off brief for the spec agent. Produce a technical spec and task plan from this.

---

## 1. Purpose

MVP agent for the sales team of an asset-based truckload carrier. Given a shipper account
(existing customer or prospect), it:

1. Researches the shipper's freight activity across internal and third-party sources.
2. Computes how well the shipper's lanes fit our network (backhaul gaps, lane density).
3. Produces a sales brief for the rep and a draft outreach message.
4. Pauses for rep approval before anything is sent or written back to the CRM.

Business outcome: reps prospect with specific, verifiable lane data ("you ship ~40 loads/week
Dallas → Atlanta; we run empty Atlanta → Dallas") instead of cold outreach.

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
  - `/memories/`: `StoreBackend` namespaced by rep ID (persistent)
- LangSmith: tracing, datasets, experiments, online evaluators, annotation queues,
  dashboards, alerts
- Judges: code for anything computable; Jev (TypeSafe decision model, pinned `jev-1.13`) as the
  default judge for all semantic criteria; LLM-as-judge only where written output is needed
  (see 7.4)
- Optional: Harbor (`harbor[langsmith]`) as a sandboxed offline eval runner
- Optional: LangMem background manager for rep-preference extraction from HITL edits

---

## 3. Data sources and integrations

| Source | Type | Use | Build approach |
|---|---|---|---|
| GenLogs | Paid API (~$100K/yr) | Shipper lanes, facilities, volumes | Mock service matching public API docs schema (docs.genlogs.io): shipper lanes, shipper facilities, shipper by region. Seed from FAF5 so volumes are realistic. |
| FHWA FAF5 | Free public dataset | Region-to-region freight volumes by commodity | Load locally, expose as `market_lane_volume` tool |
| FMCSA QCMobile | Free API (web key) | Carrier/competitor context, safety data | Real integration |
| SEC EDGAR | Free API | Public shipper financials, facility/expansion mentions | Real integration |
| Web search (Tavily) | Free tier API | Company news, expansion signals | Real integration |
| CRM | Internal | Account record, contacts, current business | Mock |
| Our network | Internal | Our lanes, weekly loads, backhaul imbalance by region | Mock (seeded, deterministic) |

All mocks are deterministic and seeded so offline evals have ground truth.

---

## 4. Virtual filesystem contract

Every subagent writes structured JSON plus a short markdown summary to its own directory.
Every data point carries `source` (tool, endpoint, timestamp). The orchestrator and all
evaluators rely on this contract.

```
/task/brief.md                 # task, account, objective, filesystem map. Orchestrator reads first.
/INDEX.md                      # manifest; each subagent appends what it wrote
/context/account.json          # CRM record + current business with us
/context/our_network.json      # our lanes, density, backhaul gaps
/research/freight_intel/       # shipper lanes, facilities, volumes (GenLogs mock, FMCSA)
/research/company/             # firmographics, news, signals (web search, SEC EDGAR)
/research/market/              # lane-level market volumes (FAF5)
/analysis/lane_fit.json        # scored lanes, opportunity sizing, method version
/analysis/lane_fit.md          # human-readable summary
/output/brief.md               # sales brief (orchestrator)
/output/outreach_draft.md      # draft message (drafting subagent)
/memories/{rep_id}/            # persistent rep preferences (tone, format, priorities)
```

---

## 5. Agents

### Orchestrator
- Reads `/task/brief.md`, `/INDEX.md`, and `/memories/{rep_id}/` first; plans with `write_todos`.
- Delegates via `task`; never calls data APIs directly.
- Runs research subagents in parallel; runs the analyst after research completes.
- Writes `/output/brief.md` from files only. Every number must come from `/analysis` or `/research`.
- Owns the HITL tools `send_outreach` and `update_crm`.

### Subagents
1. **account-context**: mock CRM + internal network → `/context/`
2. **freight-intel**: GenLogs mock + FMCSA → `/research/freight_intel/`
3. **company-research**: web search + SEC EDGAR → `/research/company/`
4. **market-data**: FAF5 → `/research/market/`
5. **lane-analyst**: uses the code interpreter with PTC. Reads `/context` and `/research`,
   fans out lane lookups, and computes scores → `/analysis/`
6. **outreach-drafter**: reads `/output/brief.md` + `/memories/{rep_id}/`, writes
   `/output/outreach_draft.md`. Must not introduce numbers absent from the brief.

### Lane-fit scoring (starting point, versioned)
Per shipper lane (origin region, destination region, loads/week, equipment):
- `backhaul_fill`: share of our empty capacity leaving the origin region that this lane covers
- `density`: our existing weekly loads on the same O/D pair
- `equipment_match`: shipper equipment vs our fleet mix
- `fit_score = w1*backhaul_fill + w2*density + w3*equipment_match` (weights in config)
- `opportunity = matched_loads_per_week * est_rate * 52`

The formula lives in a versioned skill file. A Python reference implementation of the same
formula is used by evaluators to verify the analyst's numbers.

### Code interpreter rules
- PTC allowlist: `read_file`, `glob`, `write_file`, read-only data tools only.
- Never allowlist `send_outreach` or `update_crm`. PTC calls bypass `interrupt_on`.
- Defaults: `mode="thread"`, 5s timeout, 64MB memory; tune if lane fan-out needs more.

---

## 6. Human-in-the-loop and memory

- `interrupt_on`: `send_outreach`, `update_crm`; allowed decisions: approve, edit, reject.
- Checkpointer required.
- Every HITL decision is logged as LangSmith feedback on the run (decision, edit distance
  between draft and final).
- Rep edits are extracted into `/memories/{rep_id}/` (native Deep Agents memory; LangMem
  background manager optional).

---

## 7. Evaluation (primary focus)

Principle: offline evals decide whether a version is ready to ship. Online evals tell you
whether it is still working in production. Production failures become offline test cases.

### 7.1 Offline harness (Test)

**Dataset** (LangSmith dataset, versioned, with splits):
- `core` (15–20): synthetic accounts with planted lane overlaps and known facts
- `edge` (8–10): no GenLogs coverage, ambiguous company name (entity resolution), conflicting
  sources, zero network fit (correct answer is "not a fit"), prompt injection in web results
- `regression`: empty at start; filled from production failures (see 7.3)

Each example stores reference outputs: expected top-k lanes, expected fit verdict, known
facts, and the set of valid numeric values.

**Evaluators, by layer:**

| Layer | Evaluator | What it checks |
|---|---|---|
| Code (MVP headline) | `numeric_groundedness` | Every number in brief and draft traces to a value in `/research` or `/analysis` |
| Code | `lane_precision_at_k` | Top-k lanes match planted overlaps |
| Code | `analysis_correctness` | Analyst's scores match the Python reference implementation |
| Code | `fit_verdict_accuracy` | Correct fit / no-fit call, including edge cases |
| Code | `file_contract` | Each subagent wrote required files with valid schema |
| Code (trajectory) | `trajectory_checks` | Required subagents called; analyst ran after research; no send without approval |
| Code | `injection_resistance` | On injection examples: no forbidden tool call, no planted canary string in outputs |
| Code | cost, latency, tool-call count | Efficiency budget per run |
| Jev (default judge) | Typed questions (below) | All semantic quality criteria, offline and online |
| LLM judge | Pairwise version comparison, failure explanation | Only where written reasoning is the output (see 7.4) |
| Human | Annotation queue | Label 30–50 runs; calibrate Jev per question (see 7.4) |

**Jev questions.** Each question gets its own small, filtered state built in code (not the
whole trace). Instructions state exact conditions and boundary cases.

| Key | Type | State (projected in code) | Question |
|---|---|---|---|
| `claim_supported` | noul, one call per qualitative claim | one claim + the research excerpt it cites | Is this claim supported by the cited excerpt? |
| `internal_data_leak` | noul | outreach draft only | Does the draft mention internal-only information (our rates, margins, or other customers)? |
| `draft_matches_brief` | noul | brief + draft | Does the draft pitch the same lanes the brief recommends? |
| `next_step` | choice | brief | {expand existing lanes, new lane pitch, not a fit, needs more data} |
| `entity_resolution_ok` | noul | account name + resolved company profile | Is the resolved company the same company as the account? |
| `actionability` | score 1–5 (levels defined) | brief | How actionable is this brief for a sales rep? |
| `tone_fit` | score 1–5 (levels defined) | draft + rep preference file | How well does the draft match the rep's stated preferences? |

Rules:
- Numbers and counts are never Jev questions; they stay in code evaluators.
- Raw web or tool output never goes into Jev state (injection risk); judge agent outputs only.
- Qualitative claims are extracted from the brief with a parser where possible; otherwise
  extraction is an LLM step and Jev judges each claim.

**Experiments:**
- Baseline run on all splits, 3 repetitions per example to measure variance.
- Comparisons: model variants, prompt variants, interpreter on vs off for the analyst.
- CI gate: pytest + LangSmith; block merge if groundedness or lane precision drops below
  threshold vs baseline.

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

- All runs traced to a LangSmith project with metadata: `agent_version`, `rep_id` (hashed),
  `account_id`, `tenant_id`, `prompt_version`. Trajectories view used for session review.
- Online evaluators on the tracing project:
  - Code: `numeric_groundedness`, `trajectory_checks` on 100% of runs
  - Jev: same typed questions on 100% of runs (LangSmith decision model online evaluator)
  - LLM judge: none by default; runs only on flagged traces to write a failure explanation
    for the annotation queue
- Implicit feedback: HITL approve / edit / reject and edit distance, logged per run.
- Dashboard: approve rate, edit rate, reject rate, groundedness pass rate, Jev scores,
  cost, latency, tool error rate, all filterable by `agent_version`.
- Alerts: groundedness pass rate drop, reject-rate spike, GenLogs/API error spike, cost spike.
- Safe rollout: new versions run as canary (small share of traffic, tagged by
  `agent_version`); compare online scores before full rollout.
- For the demo, a traffic simulator runs accounts from a separate "live" pool (not in the
  offline dataset) through the deployed agent, with a simulated rep policy
  (approve / edit / reject), to populate the monitoring view.

### 7.3 Closing the loop

1. Online evaluator or rep rejection flags a run.
2. Run routes to an annotation queue (automation rule on feedback key).
3. Reviewer labels failure type; example is added to the `regression` split.
4. Fix is validated offline against `regression` + `core` before redeploy.
5. The example stays in the dataset so the failure stays fixed.

### 7.4 Judge policy

Order of preference:
1. **Code** for anything computable: numbers, counts, dates, schemas, tool-call order,
   string matches. Jev is documented as weak on numeric precision, counting, and dates.
2. **Jev** for every semantic judgment that fits a noul, choice, or score.
3. **LLM judge** only when the output itself must be text: pairwise version comparisons
   with written rationale, failure explanations on flagged traces, claim extraction when a
   parser can't do it.

Calibration (makes the judge choice an eval-driven decision, not a preference):
- Human-label 30–50 runs on every Jev question (annotation queue).
- Run Jev and one LLM judge on the same labeled set. Report per-question agreement with
  humans, run-to-run variance (5 repeats), cost, and latency.
- Tune a pass threshold per noul on the labeled set; don't reuse thresholds across question types.
- Any question where Jev agreement is materially below the LLM judge is either reworded,
  split into simpler questions, or moved to the LLM judge. Document the outcome.

Jev operating rules:
- Pin the model version (`jev-1.13`), never `jev-latest`; re-calibrate on upgrade.
- Log state, option order, model version, and confidence with every feedback entry.
- Test option-order permutations for each choice question during calibration.
- Keep states small and relevant; filter in code before calling.
- Offline: custom LangSmith evaluator wrapping the TypeSafe Python SDK. Online: LangSmith
  decision model evaluator (TypeSafe key stored as a workspace secret).

---

## 8. Production path (document, don't build)

- Memory scoping: per-rep namespace; team-level shared namespace for playbooks; no cross-rep reads.
- Auth: rep auth to the app; agent uses delegated rep credentials for CRM writes; service
  identity for read-only data APIs; per-tenant API keys.
- Multi-tenancy: tenant ID in every store namespace, trace metadata, and data query.
- Data licensing: GenLogs terms may restrict what appears in customer-facing text; guardrail
  checks draft for restricted fields.
- Third-party judge data retention: TypeSafe does not currently offer zero data retention;
  review before sending customer data to Jev in production. Options: redact state before
  judging, or fall back to a self-hosted judge for sensitive fields.
- Judge robustness: Jev can be steered by adversarial text in its state, so it never sees raw
  tool or web output, and safety-critical checks keep a deterministic code check alongside it.
- Durability: checkpointer-backed resume; idempotent `update_crm`; retries with backoff and
  response caching for paid APIs.
- Guardrails: prompt-injection screening on web content; PTC allowlist as permission boundary;
  interpreter runs in-process, so isolate workers in production.

---

## 9. Scope and priorities (1 week)

**Must have**
- Orchestrator + 6 subagents, filesystem contract, HITL on send/CRM
- Mocks: GenLogs, CRM, network. Real: web search, SEC EDGAR, FMCSA, FAF5
- Offline: dataset (core + edge), code evaluators, Jev evaluator, baseline experiment
- Online: tracing with metadata, online evaluators, dashboard, traffic simulator
- Friction log maintained throughout

**Should have**
- CI eval gate, annotation queue + regression flow demo, judge calibration

**Stretch**
- Harbor tasks, LangMem extraction, broker mode

**Out of scope**
- Real GenLogs access, real email sending, auth implementation

---

## 10. Deliverables to support

- Code repo (README with run instructions for agent, offline evals, simulator)
- Slide deck inputs: architecture diagram, trade-offs, eval results table, production path
- Friction log (`FRICTION_LOG.md`), updated as issues occur
