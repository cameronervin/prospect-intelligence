# ADR 0002: Source-specific adapter contracts

- Status: Accepted
- Date: 2026-09-29

## Decision

Define narrow typed Protocols for CRM, freight intelligence, carrier network, market data, SEC,
web search, and carrier registry. Services and agent tools depend on those contracts; bootstrap
selects concrete implementations and injects them as one source bundle.

The Protocols and normalized result types live in
`backend/app/features/prospect_intelligence/contracts/sources.py`. Private-source integration
packages contain both the synthetic implementation used by the MVP and an unwired production
shell. Production shells fail closed and document the provider-specific work still required; they
are not selected by bootstrap.

Those shells are named for their intended systems rather than for an environment:
`SalesforceCrmSource`, `GenLogsFreightIntelligenceSource`, and `TmsCarrierNetworkSource`.

Each adapter returns a normalized result containing typed data or `None`, explicit source coverage,
and evidence. Provider wire payloads remain inside their integration. Expected source failures are
represented as degraded or unavailable coverage rather than fabricated fallback facts.

Synthetic CRM, freight, and carrier-network adapters share a deterministic catalog derived from the
reviewed scenario population. Scenario generation is feature-owned fixture infrastructure rather
than a runtime integration. FAF is a real snapshot-backed market-data adapter. SEC, Tavily, and
FMCSA are live public-source adapters when external access is enabled.

Carrier network and carrier registry remain separate packages. Carrier network represents the
seller's private, tenant-owned capacity and lane history. Carrier registry represents public
authority and safety facts for the selected prospect's reviewed carrier/private-fleet identity.
The selected account supplies an exact USDOT; the model cannot substitute a different identity.
Their subjects, ownership, credentials, data shape, failure policy, and replacement path remain
distinct.

## Rationale

Source-specific Protocols preserve substitutability without forcing unrelated systems into one
inheritance hierarchy. They also match the repository's existing repository and lifecycle ports.
Composition keeps timeout, retry, caching, provenance, and redaction policies reusable without
hiding provider-specific request and failure semantics.

## Operational rules

- Adapter methods remain synchronous because the worker invokes its handler in a bounded worker
  thread. LangChain tools wrap the contracts without changing them.
- Cache scope is one run; results are never shared across runs, tenants, or reps.
- Timeouts, HTTP clients, retry sleeping, and clocks are injected.
- One initial request plus two retries is allowed only for timeouts, HTTP 429, and HTTP 5xx.
- Disabled live access, missing credentials, malformed responses, and exhausted retries return
  sanitized coverage. Secrets and credential-bearing query strings are never logged or persisted.

## Consequences

- Real CRM, GenLogs, and carrier-network adapters can be added after the MVP without changing
  services or agent tools.
- The MVP wires only synthetic private-source adapters. Unwired production shells make the intended
  replacement point explicit but deliberately contain no guessed endpoints, schemas, or auth logic.
- Moving fixture and snapshot artifacts may change canonical citation paths. Any such change
  requires golden-file review but does not change `freight-prospect-v1` unless scenario semantics
  change.
