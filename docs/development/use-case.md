# Use case: freight prospect intelligence for carrier sales

## Problem

Truckload-carrier sales reps research shippers before outreach, but account history, public company
signals, freight estimates, and carrier-network data are split across systems. This makes research
slow and can delay the network-fit decision until after a sales conversation starts.

The MVP helps a rep decide whether an assigned shipper is worth contacting. It produces an
evidence-backed brief, identifies lane fit, drafts outreach only for a fit account, and pauses for a
human decision.

## User and workflow

The primary user is a carrier sales rep. Sales leadership, network planning, pricing, and compliance
are supporting stakeholders.

For the selected account, the application:

1. reads fixture-backed account, freight, and carrier-network context;
2. checks a packaged public freight-volume snapshot and optional public sources;
3. compares shipper lanes with the carrier's reviewed network data;
4. returns `fit`, `no_fit`, or `needs_more_data` with dated evidence;
5. drafts outreach only for a fit result;
6. waits for the rep to approve, edit, or reject the draft.

Approval records a simulated-send receipt. The MVP does not send email, contact a prospect, or write
to a CRM.

The local seed creates one fictional sales rep and assigns one Sysco Corporation account. The rep can
list and run only assigned accounts. Authentication is a local demo issuer; production identity is
deferred.

## Data boundaries

Every source reports its mode, retrieval time, coverage, and provenance.

| Source | Current MVP mode |
| --- | --- |
| CRM account context | Reviewed fixture; no live CRM connection |
| GenLogs-shaped freight intelligence | Reviewed fixture; no commercial API connection |
| Carrier network | Reviewed tenant-scoped fixture |
| FHWA/BTS FAF5.7.1 | Packaged, checksummed snapshot |
| SEC EDGAR | Live only when external access is enabled; otherwise unavailable |
| Tavily web search | Live only when external access and a key are configured; otherwise unavailable |
| FMCSA | Live only when external access and a key are configured; otherwise unavailable |

The seeded Sysco identity is used for the demo, but its private freight, CRM, and network facts remain
fixtures. Live public evidence does not validate or convert those private facts. A missing live source
produces degraded or unavailable coverage rather than invented data.

## Human review and safety

- The graph cannot complete a fit run without the named outreach-review interrupt.
- The rep may approve the draft, submit a complete edit, or reject it.
- Numeric and source claims are checked against typed artifacts before review.
- Source text is bounded and treated as untrusted.
- Actor scope comes from verified claims and is retained across queued work and review.
- Model inputs, outputs, and metadata are hidden from LangSmith tracing by default.

Optional online-quality delivery is implemented for sanitized lifecycle events and feedback. It is
disabled by default and does not replace production monitoring, incident response, or identity
controls.

## Success measures

Before a pilot:

- every material claim resolves to source evidence;
- fit and non-fit decisions meet the documented evaluator gates;
- the review workflow survives retries and restarts;
- human labels are used to assess semantic-judge agreement.

During a controlled pilot:

- research time per assigned account;
- draft approval and edit rates;
- reply and meeting rates against a baseline;
- qualified opportunities and wins on target lanes;
- cost per completed brief and per qualified opportunity.

Empty-mile and margin effects require customer operational data and should not be claimed from the
MVP. The [ROI model](../production/product-roi.md) records pilot assumptions separately from observed
results.

## MVP and production boundary

The reviewable MVP includes the v4 agent workflow, PostgreSQL persistence and checkpoints, demo
authentication, assigned-account authorization, deterministic and semantic evaluation paths,
Desktop Chrome coverage, and opt-in online-quality delivery.

A production pilot still needs managed identity, licensed private-data integrations, a real CRM,
hardened outbound delivery, customer-approved data and retention rules, operational ownership, and
live quality evidence. See the [path to production](../production/path-to-production.md).
