# Offline evaluation harness

This package contains the deterministic `freight-prospect-v1` dataset, pure code evaluators,
typed Jev question contracts, and a declarative experiment plan. Nothing in this package
creates a provider or LangSmith client.

The dataset is a projection of the prospect feature's seeded scenario generator, not an independent
fixture set. Its reviewed golden JSON contains 16 core and eight edge cases; eight additional account
IDs form a disjoint traffic-simulator pool. All CRM, GenLogs-shaped freight/facility, and carrier
network records are fictional. Each example carries complete references, citations, and source
coverage, and no test calls a live API.

Market context comes from a committed, checksummed aggregation of final 2023 truck-mode regional
flows in BTS/FHWA FAF5.7.1. The manifest records the official archive URL, DOI, retrieval date,
upstream archive checksum, extraction filters, and snapshot checksum. FAF tonnage remains in thousand
short tons. Fictional shipper loads/week are separately labeled `project-owned synthetic estimate`
and calculated as `thousand tons × 1,000 × synthetic share ÷ 20 tons/load ÷ 52 weeks`, using seeded
shares from 0.25% through 1.0% and half-up rounding to a whole load. The repository assumes public
U.S. federal statistical data may be
redistributed with BTS/FHWA attribution; downstream commercial use still requires a license review.

Repository tests and CI remain offline. Live experiments require explicit credentials, a
reviewed synthetic dataset, and a sanitized result entry under `docs/evaluation/`. Raw traces,
inputs, customer data, API keys, and downloaded LangSmith results must not be committed.
