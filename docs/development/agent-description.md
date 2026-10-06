# Freight Prospect Intelligence Agent — Implementation Description

This document describes the delivered MVP. Production identity and live business integrations remain
deferred.

---

## 1. Purpose

MVP agent for the sales team of an asset-based truckload carrier. Given a shipper account
(existing customer or prospect), it:

1. Researches the shipper's freight activity across internal and third-party sources.
2. Computes how well the shipper's lanes fit our network (backhaul gaps, lane density).
3. Produces a sales brief for the rep and a draft outreach message.
4. Pauses for rep approval, then records only a simulated-send receipt. The MVP never sends email
   or writes to a CRM.

Business outcome: reps receive specific, verifiable lane analysis in the internal brief and use
approved outreach such as "Would you be open to comparing notes on your ATL-to-DAL freight needs?"
instead of unsupported commercial claims.

### Business model assumption

- Default: asset-based carrier. Network fit = shipper lanes that fill our backhaul gaps
  (reduce deadhead miles) or add density to lanes we already run.
- Broker mode is not implemented.

---

## 2. Stack

- Python 3.12, Deep Agents SDK (`create_deep_agent`), LangGraph checkpointer
- Code execution: `CodeInterpreterMiddleware` from `langchain-quickjs` (QuickJS, in-process,
  no sandbox). Note: interpreter code is JavaScript, not Python.
- Filesystem: `CompositeBackend`
  - default: `StateBackend` (stored in LangGraph state and checkpointed with the run)
  - `/memories/`: `StoreBackend` namespaced by tenant and rep ID (persistent)
  - `/skills/`: traversal-confined packaged skill source, readable only by the lane analyst
- LangSmith: tracing, datasets, experiments, online evaluators, annotation queues,
  dashboards, alerts
- Judges: code for anything computable; Jev (TypeSafe decision model, pinned `jev-1.13.0`) as the
  default judge for bounded semantic criteria; GPT-5.6 Sol is comparison-only

---

## 3. Data sources and integrations

| Source              | Type                 | Use                                                    | Build approach                                                                                                                                                 |
| ------------------- | -------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GenLogs             | Licensed API         | Shipper lanes, facilities, volumes                     | Mock service matching public API docs schema (docs.genlogs.io): shipper lanes, shipper facilities, shipper by region. Seed from FAF5 so volumes are realistic. |
| FHWA FAF5           | Free public dataset  | Region-to-region freight volumes by commodity          | Load locally, expose as `market_lane_volume` tool                                                                                                              |
| FMCSA QCMobile      | Free API (web key)   | Selected prospect carrier/private-fleet context        | Optional live adapter using an account-owned exact USDOT; disabled by default                                                                                   |
| SEC EDGAR           | Free API             | Public shipper financials, facility/expansion mentions | Optional live adapter; disabled by default                                                                                                                      |
| Web search (Tavily) | Free tier API        | Company news, expansion signals                        | Optional live adapter; disabled by default                                                                                                                      |
| CRM                 | Internal             | Account record, contacts, current business             | Mock                                                                                                                                                           |
| Our network         | Internal             | Our lanes, weekly loads, backhaul imbalance by region  | Mock (seeded, deterministic)                                                                                                                                   |

All private-source fixtures are deterministic and seeded so offline evals have ground truth. The
visible demo prospect is Sysco Corporation, while its CRM, freight, contact, and carrier-network
facts remain explicitly labeled fixtures rather than claimed live facts.

Source access is injected through narrow CRM, freight-intelligence, carrier-network, market-data,
SEC, web-search, and carrier-registry Protocols. Bootstrap selects implementations. The MVP uses
synthetic private-source adapters, a pinned FAF snapshot, and optional live SEC, Tavily, and FMCSA
adapters that are disabled by default. It does not create placeholder private-vendor clients. Every
adapter returns normalized typed data, explicit coverage, and evidence, and keeps its provider
payload inside the integration boundary. Live-source failures are disclosed as degraded or
unavailable coverage and never silently replaced with synthetic facts.

---

## 4. Virtual filesystem contract

Typed domain tools own every machine-consumed artifact below. Generic `write_file` is limited to the
lane-analysis narrative and sales brief. Every source evidence item retains complete provenance;
the orchestrator and evaluators rely on this contract.

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

1. **account-context**: calls `materialize_account_context` for mock CRM + internal network →
   `/context/`
2. **external-research**: GenLogs-shaped freight activity, FMCSA, web search, SEC EDGAR, and FAF5
   through `materialize_external_research` → `/research/`
3. **lane-analyst**: calls deterministic `score_lane_fit_v1` for canonical JSON and writes only the
   human-readable lane narrative → `/analysis/`
4. **outreach-drafter**: reads `/output/brief.md`, tenant/rep-scoped preferences, and review
   findings on a revision; submits typed subject and paragraph fields through
   `submit_outreach_draft`.
5. **quality-reviewer**: read-only judgment over the brief and outreach against all evidence, the
   lane analysis, rep preferences, and the brief template; submits typed findings through
   `submit_quality_review`.

The Deep Agents default general-purpose subagent is disabled. One orchestrator is built with
`create_deep_agent()`; its five declarative, isolated specialists are compiled internally with
`create_agent()` and expose no `task` or root-only `send_outreach` tool.

### Context engineering

The orchestrator and specialists share one composite virtual backend while each receives an explicit
tool list, filesystem policy, and concrete middleware stack. Middleware projects the allowlisted task,
manifest, artifacts, and rep preferences before model calls; applies model/tool budgets; redacts
tool errors; treats source results as untrusted data; gives each typed artifact submission two
canonical, allowlisted multi-issue corrections before terminal exhaustion; gates delegation and
`send_outreach` on review order and freshness; and validates each specialist's owned artifact
contracts. Draft content is judged by the quality reviewer rather than regex checks at the gate;
the outreach-v4 allowlist is still enforced in the domain when the result is committed and on rep
edits. The subject binds the selected account and the relevance paragraph binds the selected lane;
the account need not be repeated in that paragraph. LangGraph state contains checkpointed workflow
data only, while the verified
`AuthContext`, source handlers, and other request-scoped dependencies use LangGraph
`context_schema`/`Runtime.context`. Optional `runtime-jev-v1` input/output nodes are wired around the
Deep Agent and default off; they checkpoint only sanitized decision metadata.
Platform trace privacy hides all run inputs, outputs, and metadata by default.

The code layout keeps those concepts visible as `chains.py`, `prompts/`, `specs.py`, `graphs.py`,
`compiler.py`, `state.py`, `tools/`, `guardrails/`, `runtime.py`, and `context.py`.
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

- PTC allowlist: `read_file` and `glob` only.
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
- Every HITL decision and simulated receipt is persisted in PostgreSQL. Online LangSmith delivery is
  implemented but disabled by default; production use requires customer-data approval.
- Rep edits produce a tenant/rep-scoped preference summary that is materialized into the agent's
  StoreBackend memory on later runs. Rich LangMem extraction remains optional and deferred.

---

## 7. Evaluation (primary focus)

Principle: offline evals decide whether a version is ready to ship. Online evals tell you
whether it is still working in production. Production failures become offline test cases.

### 7.1 Offline and archived experiment evidence

- The current credential-free gate runs 24 synthetic cases three times through
  `prospect-compiled-script-v4` with prompt bundle `outreach-v4`. Deterministic gates include
  `lane_precision_at_3`; semantic scores remain evidence only.
- CAM-40 is archived v1 evidence. Its hosted feedback used `freight-evaluators-v2`; retained outputs
  were later rescored locally with `freight-evaluators-v3`. Neither result validates v4.
- CAM-41/CAM-50 completed blind reference labeling and alignment diagnostics. The holdout was not
  run, so the work established no semantic promotion threshold or holdout recommendation.

See [Evaluation approach](../evaluation/README.md),
[CAM-40 experimentation](../evaluation/experimentation-process.md), and
[evaluator alignment](../evaluation/evaluator-alignment-process.md) for the canonical process and
evidence records.

### 7.2 Online quality and regression intake

CAM-42 implements the app-side evaluator and LangSmith delivery path. It is disabled by default and
requires LangSmith and TypeSafe credentials when enabled. The application publishes sanitized,
idempotent quality events and keeps raw artifacts, prompts, contacts, and provider responses local.

CAM-43 implements credential-gated setup, deterministic demo traffic, routing rules, dashboards,
and demo alerts. These resources demonstrate operations; their alert values are not production SLOs.
Production retention, incident ownership, paging, and customer-data approval remain deployment work.

CAM-44 implements reviewed regression intake. PostgreSQL stores the candidate, decision, and audit
history; only accepted, independently sanitized examples enter `freight-prospect-regression-v1`.
The detailed runtime contract is in [online-operations.md](../evaluation/online-operations.md).

### 7.3 Judge policy

Use deterministic code for computable checks. Use Jev `jev-1.13.0` for bounded semantic questions,
with GPT-5.6 Sol only for explicit comparison. Never send raw tool or web output to either judge and
never substitute one judge after the other fails. The human-preference alignment was single-reviewer,
two-pass work; its untouched holdout remains unrun.

---

## 8. Production path

- Memory scoping: per-rep namespace; team-level shared namespace for playbooks; no cross-rep reads.
- Auth: the MVP has demo JWT login, refresh, session inspection, role checks, and account assignment
  enforcement. Production must replace the demo issuer and add delegated CRM credentials.
- Multi-tenancy: tenant ID in every store namespace and data query; trace metadata is hidden by
  default until a privacy-reviewed hashed scope is implemented.
- Data licensing: GenLogs terms may restrict what appears in customer-facing text; guardrail
  checks draft for restricted fields.
- Third-party judge data retention: TypeSafe does not currently offer zero data retention;
  review before sending customer data to Jev in production. Options: redact state before
  judging, or fall back to a self-hosted judge for sensitive fields.
- Judge robustness: Jev can be steered by adversarial text in its state, so it never sees raw
  tool or web output. In-run draft-content gating is the quality reviewer's judgment plus human
  approval and the domain outreach-template allowlist; deterministic code checks remain offline
  measurements. Optional Jev runtime guardrails are implemented but disabled by default pending
  production privacy and latency approval.
- Durability: checkpointer-backed resume and idempotent simulated-send receipts. Live email and CRM
  mutations need idempotency keys, retry policy, and delegated credentials before production use.
- Guardrails: prompt-injection screening on web content; PTC allowlist as permission boundary;
  interpreter runs in-process, so isolate workers in production.

---

## 9. Scope and evidence

**Reviewable MVP in this repository**

- Compiled orchestrator plus five specialists, middleware-enforced filesystem contract, and a
  role-scoped `lane_fit_v1` skill.
- Durable HITL on outreach with no direct review fallback.
- Demo JWT authentication and assigned-account authorization; production identity is not included.
- Deterministic CRM, GenLogs-shaped, and network sources; packaged FAF data; optional live SEC,
  Tavily, and FMCSA adapters that disclose unavailability rather than substituting fixtures.
- Versioned offline data, deterministic evaluators, experiment configuration, traffic simulation,
  and sanitized quality-event contracts.
- Friction and business-logic decision logs maintained with implementation changes.

**Credentialed/live evidence still required**

- Model/provider smoke run and model-directed delegation trajectory.
- Production identity, customer-data approval, live-source validation, and operational ownership.

**Deferred/stretch**

- Harbor tasks, LangMem extraction, broker mode
- Real GenLogs access, real email sending, CRM mutation, and production identity integration.

---

## 10. Deliverables to support

- Code repo (README with run instructions for agent, offline evals, simulator)
- Slide deck inputs: architecture diagram, trade-offs, eval results table, production path
- Friction log ([`docs/delivery/friction-log.md`](../delivery/friction-log.md)), updated only for
  confirmed material friction
