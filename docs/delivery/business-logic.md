# Business logic decisions

This document is the authoritative current-state register for decisions that materially affect
business recommendations, user-visible outcomes, data interpretation, or safety. Technical design,
UI behavior, and experiment mechanics live in their dedicated documentation.

Repository tests establish implemented behavior. Credentialed LangSmith experiments are a separate
evidence class and are identified explicitly below; neither evidence class alone establishes
production readiness.

## Product scope and business outcome

- The product helps sales representatives at an asset-based truckload carrier evaluate shipper
  accounts before outreach. It combines account context, shipper freight activity, and the carrier's
  network data into an internal brief and, when justified, a customer-facing draft.
- The intended outcomes are less manual research, more outreach to shippers that can improve network
  utilization, and more specific conversations about viable lanes.
- The MVP models the carrier case, not freight brokerage. CRM and carrier-network data and
  GenLogs-shaped freight intelligence are synthetic. Real licensed freight data, production CRM and
  delivery integrations, and a controlled sales pilot are phase-two decisions.
- The stakeholder decision is whether to fund that limited pilot, not whether to authorize an
  autonomous or enterprise-wide rollout.

Evidence: [use case](../development/use_case.md),
[implementation description](../development/agent_description.md), and
[MVP deferrals](mvp-scoping.md).

## Lane fit and opportunity model

A shipper lane matches carrier capacity only in the same origin-to-destination direction.
Reverse-direction capacity is not a match. For each shipper lane:

- `matched_loads = min(shipper_weekly_loads, carrier_empty_capacity)`
- `backhaul_fill = matched_loads / carrier_empty_capacity`, or zero when capacity is zero
- `density = min(carrier_same_lane_weekly_loads / 40, 1)`
- `equipment_match = carrier fleet share for the shipper's required equipment`
- `fit_score = 0.50*backhaul_fill + 0.30*density + 0.20*equipment_match`

The score is bounded and rounded half-up to four decimal places. Only lanes with at least one
matched load are eligible. Eligible lanes rank by score, matched loads, origin, then destination;
the brief retains the top three.

The opportunity model is:

- `modeled_annual_revenue = matched_loads * estimated_rate_per_load * 52`
- `modeled_deadhead_miles_avoided = matched_loads * origin_destination_miles * 52`

These are prioritization estimates, not booked revenue, margin, guaranteed savings, or evidence
that every modeled mile would otherwise have been empty. The revenue model excludes cost and margin;
the deadhead figure is an upper-bound full-lane displacement estimate.

Evidence: [runtime implementation](../../backend/app/features/prospect_intelligence/domain/lane_fit.py)
and the independently implemented evaluation reference.

## Data sufficiency, provenance, and verdicts

- `fit`: freight and carrier-network coverage are complete and at least one lane has matched capacity.
- `no_fit`: critical coverage is complete but no lane has matched capacity.
- `needs_more_data`: critical freight or carrier-network data is absent, degraded, contradictory,
  duplicated, or malformed, or no shipper lanes are available.

Private CRM, freight, and network inputs are deterministic fixtures in the MVP. FAF is a versioned
snapshot. SEC, Tavily, and FMCSA sources may be live when enabled. Every source discloses its mode,
retrieval time, and provenance. A failed live source returns degraded or unavailable coverage and
never silently substitutes fixture facts.

The generated-result UI uses neutral presentation labels for the fixture-backed CRM, GenLogs, and
carrier-network source names and for three corresponding evidence summaries. It also omits the
redundant fit guidance that described the review as preceding a simulated send. This is a
presentation-only decision: raw API values, `fixture` source modes, citation metadata, internal
adapters, evaluation data, the human-review checkpoint, and the simulated receipt remain unchanged.
Neutral UI labels must not be interpreted as evidence that these integrations are live.

Every factual claim and quantitative value in the internal brief must trace to normalized source
evidence or the deterministic lane analysis. Factual evidence requires a stable opaque citation;
conflicting reuse of a citation identity fails closed. Optional research may add context, but it
cannot manufacture a fit decision when the critical freight or network inputs are insufficient.

Evidence: [source-adapter ADR](../architecture/decisions/0002-source-adapter-boundaries.md) and
[authoritative lane analysis](../../backend/app/features/prospect_intelligence/services/lane_analysis.py).

## Outcome and outreach policy

- A `fit` result recommends opening a conversation about the top-ranked lane and may create an
  outreach draft.
- A `no_fit` result recommends deprioritizing the account.
- A `needs_more_data` result recommends verifying the shipper's lanes before outreach.
- `no_fit` and `needs_more_data` stop after the internal brief. They do not create outreach or ask
  the representative to approve a send.

Customer-facing outreach must bind the selected account in the subject, address the selected
contact, identify the initiating representative and asset-based carrier role, and name the selected
top lane in the relevance paragraph. Repeating the account name in that paragraph is optional
because the subject already establishes the account and the whole draft rejects any other assigned
account. Outreach may not disclose internal rates, revenue, margin, capacity, deadhead, loads,
volumes, pricing, provider or source names, another customer, or unsupported claims. The current MVP
also rejects digits, markup, control characters, invented carrier brands, and another assigned
account's name. A valid message is a low-friction invitation, not a claim that the carrier knows the
prospect's private freight economics.

Generated copy receives an evidence-aware quality review before human review. At most three quality
reviews are allowed; unresolved blocking findings end the run without requesting a send decision.

Evidence: [outreach policy](../../backend/app/features/prospect_intelligence/domain/outreach.py) and
the shared brief and quality-review contracts.

## Human control and side effects

Only a `fit` run reaches the durable `send_outreach` human-review checkpoint. The representative may
approve the draft, submit an edit that passes the same customer-safety policy, or reject it.
Rejection sends nothing. If graph resume is unavailable, the API returns a retryable failure and
does not bypass the checkpoint.

Review decisions are idempotent. Retrying the same run-specific action returns the recorded outcome
without creating another receipt, preference update, or quality event; conflicting reuse fails
closed.

The MVP records a **simulated send receipt** after approval or a valid edit. It does not send email,
contact a prospect, or write to a CRM. Real delivery requires delegated credentials, idempotent
external side effects, reconciliation, and operator recovery.

Evidence: [human-review flow](../evaluation/human-in-the-loop-flow.md).

## Access and preference learning

- A verified user may access only accounts explicitly assigned to the same tenant, subject, and
  representative scope. Missing, unassigned, and cross-scope accounts share the same not-found
  behavior.
- Runs retain an immutable actor snapshot so asynchronous work and later review remain bound to the
  initiating identity.
- Only an approved edit may update preference memory. The current tenant/representative profile is
  limited to customer-neutral tone, approximate length, and invitation format. Draft text, account
  names, contacts, routes, and customer facts are not retained as preferences.
- The demo user and contact are fictional. The assigned prospect is Sysco Corporation so live public
  sources can resolve a real legal entity; its CRM, freight, and carrier-network facts remain
  classified as deterministic fixtures in raw provenance and must not be represented as live Sysco
  operating facts. The local token issuer demonstrates the boundary but is not the proposed
  production identity system.

Production requires enterprise identity, authorization provisioning, retention, deletion/export,
consent, and audit policies before customer data is introduced.

## Real-source demo identity and lookup boundaries

- The development seed assigns only `sysco-corporation` to the demo representative and maps that
  account to the reviewed `core_01` private-data fixture. Reseeding removes the retired Acme and
  Northstar assignments but deliberately preserves their account and run rows so completed history
  is not rewritten.
- Sysco's reviewed primary FMCSA identity is USDOT `2215799`. The model-facing FMCSA tool accepts no
  identity arguments and looks up only this selected-account value. A missing, invalid, unmatched,
  or ambiguous identity remains unavailable; an exact-USDOT failure never falls back to name search.
- SEC company matching normalizes punctuation and a bounded set of trailing corporate suffixes so
  `Sysco Corporation` can match `SYSCO CORP`. More than one distinct matching CIK is ambiguous and
  remains unavailable.
- FAF calls are authorized only by the selected account's explicit reviewed DMS market queries.
  Sysco's ported fixture exposes `041→061`. Display terminal lanes such as `PHX→LAX` are never
  translated into FAF zones, and the snapshot adapter retains exact-match behavior.
- Source modes remain mixed and explicit: CRM, GenLogs, and carrier-network data are fixtures; SEC,
  Tavily, and FMCSA are live; FAF is a verified snapshot. Live evidence never validates or converts
  the private fixture facts.
- Rollback may restore the retired demo assignments and remove Sysco's assignment, but it must not
  delete historical accounts or runs. Downgrading the nullable account migration drops only the
  trusted USDOT lookup field; completed persisted source artifacts remain unchanged.

## Operational logging safety boundary

- Operational records use opaque run, event, and correlation identifiers plus bounded status,
  duration, retry, provider, and workflow fields. Incoming correlation identifiers are accepted only
  when they match the bounded safe-character contract; otherwise the server replaces them.
- Logs exclude request and response bodies, query strings, credentials, session identifiers,
  customer/account/contact names, prompts, model outputs, provider payloads, and exception messages.
  Authentication outcomes identify the operation and generic reason but not the user.
- FastAPI emits a canonical request-completion record using the normalized route template. The
  Next.js server forwards the same correlation identifier and records only startup, framework
  request errors, rejected proxy paths, and backend dependency failures. No browser telemetry is
  enabled.
- LangSmith remains the agent tracing and evaluation system under its separate fail-closed privacy
  defaults; application logs do not duplicate trace content.

This policy favors diagnosable lifecycle and failure signals over payload-level debugging. A future
production logging provider requires a separate privacy, retention, access-control, and incident
response decision.

Evidence: backend and frontend logging privacy, request-correlation, worker, provider-retry,
lifecycle, authentication, and proxy tests.

## Typed artifact ownership and bounded recovery

- Machine-consumed account, research, lane-analysis JSON, review, and outreach artifacts are owned
  by typed domain tools. The model supplies typed review/outreach fields but never authors their
  serialized JSON or Markdown envelope. Generic file writing remains limited to the lane narrative
  and internal sales brief.
- A typed submission has three total attempts. The first two invalid calls receive a canonical
  error envelope containing every detectable issue in deterministic order, remaining attempts, and
  only allowlisted field, code, and fixed-instruction text. Submitted values, trusted values, raw
  exceptions, and schema-validator output are never returned or persisted. The ledger stores only
  the first deterministic issue code. The third invalid call records `agent_output_exhausted` and
  fails closed. Final workflow and product-service validation remain independent trust boundaries.
- Provider SDK retries happen before a `model_unavailable` worker failure. That category alone may
  resume from the last committed graph checkpoint, with one- and two-second scheduling delays.
  Policy rejection, exhausted output, and internal errors are terminal. External-source exhaustion
  is represented as degraded or unavailable coverage instead of a failed run.
- `prospect_execution_attempts` records sanitized worker and artifact-submission ordinals,
  timestamps, categories, codes, and retry decisions. It stores no prompts, submitted values,
  source payloads, model output, or exception text. Lease reclamation remains operationally
  independent and does not masquerade as a retryable internal error.

These boundaries retain live model reasoning while making serialization, retry authority, and
customer-visible output validation deterministic application responsibilities. Active runs emit
`prospect-intelligence-v4` and `outreach-v4`; prior revisions remain historical evidence.

## Evaluation authority and evidence limits

Deterministic evaluators are authoritative for computable behavior: numeric grounding, lane ranking
and score correctness, fit verdicts, artifact contracts, workflow order, and prompt-injection
resistance. Semantic judges remain decision support until validated against human preference on an
untouched holdout; they are not an active release gate or runtime authority.

The historical `freight-prospect-v1` population contains 16 core and eight edge synthetic examples.
Reviewed failures may enter the separate regression population only after a human supplies and
accepts a sanitized target example. Raw LangSmith traces and customer data are never copied
automatically.

Credentialed CAM-40 evidence selected the GPT-5.6 Sol orchestrator, GPT-5.6 Luna specialists,
prompt `v1`, and interpreter-enabled baseline for the historical v1 graph:

- Lower-cost routing was rejected after producing 21 target errors.
- The prompt revision was rejected because deterministic quality did not improve while target cost
  and latency increased.
- Disabling the interpreter was rejected because the retained sample showed no quality, cost, or
  latency benefit.

Baseline, lower-cost, and prompt-revision variants each completed 72 roots. Interpreter-off stopped
at 51 visible roots after LangSmith exhausted the trace quota. This supports the MVP configuration
choice but is not a completed four-variant release gate. It is historical v1 evidence and does not
validate the later `outreach-v2` prompt and customer-copy contract.

The separate semantic-alignment exercise completed its synthetic, single-reviewer alignment phase,
but three questions remained revision candidates and the untouched holdout was explicitly waived
and remains unrun. It cannot establish inter-rater agreement, customer preference, production
quality, or a semantic promotion threshold.

Together, repository evidence and the bounded live experiments support a controlled pilot decision,
not autonomous sending or production rollout. A pilot decision requires representative
customer-approved data, independent reviewers, completed holdout validation, privacy and licensing
review, and measurement of rep time, replies, meetings, won opportunities, and network outcomes.

Evidence: [CAM-40 decision](../evaluation/experimentation-process.md),
[alignment process](../evaluation/evaluator-alignment-process.md), and the
[sanitized hosted report](../../backend/evaluation/reports/cam_40_hosted.md).

## Product ROI decision model

The production ROI model supports a controlled-pilot decision only. It assumes the client already
owns GenLogs, CRM, and carrier-network data. Its base case uses 24,000 completed analyses per year, a
20% high-fit rate, 60% rep approval, 8% meeting conversion, and 15% close rate. It applies a 75%
first-year realization discount and a 12% contribution margin to the synthetic dataset's $273,000
median top-lane opportunity.

Under those assumptions, about 35 wins produce $2.36 million in gross sales and $283,000 in
contribution against about $90,000 in recurring product spend. Eleven incremental annual wins cover
recurring spend; 21 cover the estimated $170,000 first-year spend. These values are planning
assumptions, not guaranteed revenue or production evidence.

The $80,000 one-time build estimate is 16 engineer-weeks with agentic coding tools at about $200,000
per loaded FTE-year, plus a $16,000 external security review. The 12% contribution margin is treated as conservative for
backhaul lanes, where the return trip's driver and fuel cost is already incurred.

A pilot must use matched non-agent accounts and count only incremental conversion and realized loads.
Broader deployment requires at least 2x annualized contribution to recurring product cost, expected
first-year payback within 12 months, and approved numeric-grounding and customer-safety results.
Human review remains mandatory.

Evidence and calculations: [product ROI model](../production/product-roi.md).
