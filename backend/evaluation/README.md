# Offline evaluation harness

This package contains the deterministic `freight-prospect-v1` dataset, a credential-free
compiled-graph target, LangSmith-native code evaluators, a separate semantic-judge boundary, and
experiment orchestration. The local runner uses in-memory LangSmith examples, a preloaded
non-hosted client, and disabled uploads and tracing; it does not create a model-provider client or
perform network I/O.

The package follows the same four-part shape used by LangSmith's
[programmatic offline evaluation](https://docs.langchain.com/langsmith/local) and
[agent evaluation](https://docs.langchain.com/langsmith/evaluate-complex-agent) guides:

- `datasets/` owns stable examples and references.
- `contracts/` owns the SDK-neutral `OfflineRunSnapshot`, UTF-8 artifact decoding, fail-closed
  snapshot accessors, and privacy-safe observations. It imports no targets, evaluators, judges, or
  experiments.
- `targets/` executes the compiled graph and produces the sanitized snapshot contract. Targets do
  not know which evaluators will consume it.
- `evaluators/` contains one LangSmith-native code evaluator per module. Every public callable uses
  `(outputs, reference_outputs) -> EvaluationResult`; `suite.py` is the only composition and release
  threshold boundary.
- `judges/` keeps semantic judges distinct from deterministic code metrics. `judges/jev.py` is the
  typed CAM-39 handoff and performs no live SDK calls by itself.
- `experiments/` selects a target and evaluator suite, invokes `evaluate(...)`, aggregates rows, and
  renders evidence. `offline_results.gate_results()` is the only release-gate implementation.

In dependency terms, contracts are consumed by targets and evaluators; evaluator modules are
composed by the suite; and experiments consume both a target and the suite. Judges remain a
parallel extension boundary until an experiment explicitly selects them. Application targets never
import evaluator implementation details.

Evaluation source and test modules are kept at or below 250 lines. The structure test also enforces
dependency direction, the one-evaluator-per-module shape, and the absence of stale `.gitkeep` files.

Run the deterministic release gate from `backend/`:

```sh
uv run python -m evaluation.experiments.offline
```

The command executes 24 synthetic examples three times through the compiled graph and writes the
sanitized repository-evidence report to `evaluation/reports/cam_38_offline.md`. A failed or missing
gate exits nonzero. This scripted result validates graph wiring, artifact contracts, evaluators, and
release-gate behavior; it is not live-model or hosted LangSmith experiment evidence.

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

Repository tests and CI remain offline. The deterministic profile requires 100% numeric grounding,
analysis correctness, file-contract, trajectory, and injection checks; reference-aware lane
precision@3 of at least 0.80; and verdict accuracy of at least 0.90. Latency, cost, and tool-call
count are informational. The tool-call count includes every model-requested call, including the
interrupted `send_outreach` review request. Measured latency is not persisted in the report so its
repository evidence remains reproducible. Jev semantic gates remain a separate extension owned by
CAM-39.

Live experiments require explicit credentials, a
reviewed synthetic dataset, and a sanitized result entry under `docs/evaluation/`. Raw traces,
inputs, customer data, API keys, and downloaded LangSmith results must not be committed.
