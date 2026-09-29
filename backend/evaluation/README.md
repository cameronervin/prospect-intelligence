# Offline evaluation harness

This package contains the deterministic `freight-prospect-v1` dataset, pure code evaluators,
typed Jev question contracts, and a declarative experiment plan. Nothing in this package
creates a provider or LangSmith client.

Repository tests and CI remain offline. Live experiments require explicit credentials, a
reviewed synthetic dataset, and a sanitized result entry under `docs/evaluation/`. Raw traces,
inputs, customer data, API keys, and downloaded LangSmith results must not be committed.
