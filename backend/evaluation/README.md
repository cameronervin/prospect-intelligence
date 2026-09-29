# Offline evaluation harness

This directory will hold versioned datasets, evaluators, experiment adapters, and sanitized result summaries after the product problem and north-star metric are selected.

Repository tests and CI must remain offline. Live LangSmith experiments require an explicit `LANGSMITH_API_KEY`, a named `LANGSMITH_PROJECT`, a reviewed synthetic dataset, and a result entry under `docs/evaluation/`.

