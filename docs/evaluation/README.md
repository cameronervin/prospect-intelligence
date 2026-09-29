# Evaluation approach

Offline evaluation decides whether a graph revision is ready to ship. Online evaluation detects
quality changes after release, and reviewed online failures become permanent regression examples.

The credential-free harness provides:

- `freight-prospect-v1`: 16 core and 8 edge examples with deterministic reference outputs.
- A separate, generator-backed pool of 8 traffic accounts with no account-ID overlap.
- LangSmith-native evaluators for grounding, lane precision, score correctness, verdicts, files,
  trajectories, injection resistance, latency, cost, and tool calls.
- A credential-free scripted target that traverses the compiled graph, middleware, artifact
  validation, and named human-review interrupt without calling a model provider.
- Seven typed Jev questions pinned to `jev-1.13.0`; the live SDK is injected only during an
  approved experiment.
- Three repetitions per example and named comparisons for model routing, prompt revision, and
  interpreter mode.

The CAM-38 deterministic release profile requires 100% grounding, analysis correctness, file
contract, trajectory safety, and injection resistance; reference-aware lane precision@3 at least
0.80; and verdict accuracy at least 0.90. The precision denominator is the larger of the unique
predicted and expected top-three counts, with two empty sets scoring 1.0. Latency, cost, and tool
calls are informational rather than correctness gates.

Run `uv run python -m evaluation.experiments.offline` from `backend/` to execute all 24 examples
three times locally and refresh the sanitized report in
`backend/evaluation/reports/cam_38_offline.md`. The report is repository evidence from a scripted
compiled graph, not live-model or hosted LangSmith evidence.

## Harness architecture

The implementation separates observation from judgment:

See [offline-evaluator-flow.md](offline-evaluator-flow.md) for the short module and data-flow map.

- `evaluation/contracts/` defines the sanitized snapshot and typed projections shared by graph
  targets and code evaluators. It is SDK-neutral and cannot import higher-level harness packages.
- `evaluation/targets/` runs the application and emits that contract. It does not import evaluators.
- `evaluation/evaluators/` contains one native LangSmith evaluator callable per metric. Each accepts
  `outputs` and `reference_outputs` and returns `EvaluationResult`.
- `evaluation/evaluators/suite.py` is the only place that orders metrics and owns evaluator version
  and release thresholds.
- `evaluation/judges/` owns semantic-judge boundaries separately from deterministic code metrics;
  `judges/jev.py` is the CAM-39 extension point.
- `evaluation/experiments/` selects the graph target and suite, calls LangSmith locally, aggregates
  rows through the single release-gate implementation, and renders sanitized evidence.

This gives two dependency branches—contracts to targets and contracts to evaluators—before the
experiment composes the target with the suite. It prevents snapshot extraction, scoring policy,
semantic judging, and experiment orchestration from collapsing into an evaluator catch-all.

The LangSmith target snapshot exposes only model-authored `/analysis` and `/output` artifact bodies.
Task, context, and research bodies are reduced locally to safe file-contract and numeric-evidence
observations. Exact example/repetition and per-row metric coverage are release gates, so duplicate or
partial result sets fail closed. The informational tool count includes all model-requested calls,
including the interrupted review request; measured latency is evaluated but its environment-dependent
value is omitted from the committed report.

CAM-39 extends this deterministic profile with semantic Jev results. Jev calibration uses 40 human
labels per question, five judge repetitions, and option-order permutation. Rework any question below
85% human agreement or more than five percentage points behind the comparison LLM judge.

Online quality operations live in `features/agent_quality`. That feature owns rule, dashboard,
alert, annotation-queue, traffic-simulation, and regression-candidate workflows. It receives only
sanitized contracts and reaches LangSmith through an injected gateway. Actor identifiers are
hashed, and raw tool/web output is never sent to Jev.

Use [experiment-result-template.md](experiment-result-template.md) for live evidence. Do not
commit traces, credentials, downloaded result payloads, private data, or full model outputs.

## Dataset provenance and interpretation

`freight-prospect-v1` is generated with seed `28029` and compared byte-for-byte with a committed
golden artifact. The same versioned generator owns the offline and traffic populations. Core cases
plant supported lane overlap; edge cases encode missing coverage, entity ambiguity, source conflict,
no fit, prompt injection, a sparse boundary, equipment mismatch, and dependency failure in the
source payload itself rather than only as labels.

The only non-fictional input is a small FAF5.7.1 snapshot of final 2023 regional truck tonnage from
the U.S. Bureau of Transportation Statistics and Federal Highway Administration. Its manifest stores
the official download, DOI, extraction, retrieval date, upstream SHA-256, and derived snapshot
SHA-256. Raw tonnage is never presented as shipper activity. Synthetic loads/week use a seeded
fictional shipper share between 0.25% and 1.0%, 20 tons per load, 52 weeks per year, and half-up
rounding to a whole load. They are always labeled `project-owned synthetic estimate`. We retain
BTS/FHWA attribution and treat broader
commercial redistribution as requiring legal review.
