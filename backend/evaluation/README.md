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
- `contracts/` owns the SDK-neutral snapshot, judge protocol/decision types, UTF-8 artifact
  decoding, fail-closed accessors, and privacy-safe observations. It imports no targets,
  evaluators, judges, or experiments.
- `targets/` executes the compiled graph and produces the sanitized snapshot contract. Targets do
  not know which evaluators will consume it.
- `evaluators/` contains one LangSmith-native code evaluator per module. Every public callable uses
  `(outputs, reference_outputs) -> EvaluationResult`; `suite.py` is the only composition and release
  threshold boundary.
- `rubrics/semantic_v1.py` stores the exact, versioned question text and criteria used by both
  providers. The rubric version is retained in every normalized decision.
- `judges/` contains only provider-specific async adapters: Jev is the default semantic judge and
  GPT-5.6 Sol is comparison-only, never an automatic fallback.
- `experiments/` selects a target and evaluator suite, invokes `evaluate(...)`, aggregates rows, and
  renders evidence. `experiments.offline.results.gate_results()` is the only release-gate
  implementation.

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
repository evidence remains reproducible. Semantic metrics remain informational. CAM-41 completed
alignment diagnostics, but its holdout did not run and it established no promotion threshold.

The hosted CAM-40 matrix is archived, read-only historical evidence for the v1 graph and prompt
revisions. The former `evaluation.experiments.offline --live` path fails closed before hosted writes
or model-provider calls. Do not rerun it or interpret its retained results as v4 evidence. A future
live v4 matrix needs a separately reviewed plan, dataset, revisions, and authorization.

The default command without `--live` remains the credential-free CAM-38 path. The archived matrix
published `freight-prospect-v1` with stable IDs, its canonical checksum and seed, and exactly 16 core
plus 8 edge examples, then uploaded four experiments with three repetitions per example:

- `baseline`: GPT-5.6 Sol orchestrator, GPT-5.6 Luna specialists, prompt `v1`, interpreter on.
- `lower-cost`: GPT-5.6 Luna for both model roles, prompt `v1`, interpreter on.
- `prompt-revision`: GPT-5.6 Sol/Luna, prompt `evidence-self-check-v2`, interpreter on.
- `interpreter-off`: GPT-5.6 Sol/Luna, prompt `v1`, interpreter off.

Those historical variants used graph `prospect-intelligence-v1`, hosted evaluator feedback labeled
`freight-evaluators-v2`, rubric `semantic-v1`, and Jev `jev-1.13.0`. Retained outputs were rescored
locally with `freight-evaluators-v3`; the rescore did not rewrite hosted feedback. These revisions are
not defaults for future variants. The compiled target used deterministic synthetic handlers,
in-memory persistence, and no public-source reads. Rep metadata contains only SHA-256 scope hashes.
Raw traces, prompts, source/provider payloads, model messages, customer data, API keys, and downloaded
LangSmith results must not be committed.
Each target call must exactly match its local canonical synthetic example. After every variant, the
runner flushes and reads LangSmith back, requiring 72 root runs, exact example/repetition coverage,
hashed rep and code metadata, and all evaluator feedback. A commit-plus-worktree fingerprint is
captured once and reused in hosted metadata and the final report.

The deterministic suite runs before the seven Jev evaluators in the configured evaluator order.
`experiments.offline.results.gate_results()` is the only release gate; semantic scores and judge
cost/latency remain evidence only. Aggregation includes variant, split, tags, metric, and synthetic
failure ID. Target costs use the CAM-40 OpenAI standard card: Sol `$4/$0.40/$20` and Luna
`$0.20/$0.02/$1.20` per million input/cached/output tokens. Jev uses the separate 2026-09-15 card.
A candidate with a target-cost or mean-latency regression over 20% is rejected unless it passes all
deterministic gates, fixes a baseline deterministic failure, and introduces no new deterministic
failure.

LangSmith persists the dataset, traces, evaluator feedback, metadata, and completed experiment runs
under workspace retention. The repository stores only the sanitized aggregate report at
`evaluation/reports/cam_40_hosted.md`. If a later variant fails, earlier hosted experiments remain,
but the strict runner produces no automated gate decision from a partial matrix and never merges
attempts. CAM-40 also records one owner-approved MVP decision from retained, clearly labeled
evidence after quota exhaustion; that decision does not claim that the four-variant automated gate
completed. Hosted evidence, the local CAM-38 report, and repository verification remain distinct.

Experiment code is grouped by execution boundary. Credential-free orchestration, reporting, and
gate aggregation live under `evaluation/experiments/offline/`. Hosted dataset publication, runtime
composition, persistence checks, reporting, and the controlled matrix live under
`evaluation/experiments/hosted/`. The provider smoke remains the independent
`evaluation.experiments.semantic_smoke` command.

Run the explicit local semantic smoke from `backend/` only when live provider calls are intended:

```sh
TYPESAFE_API_KEY=... OPENAI_API_KEY=... \
  uv run python -m evaluation.experiments.semantic_smoke --live
```

The command rejects a missing `--live` flag or either credential before making a request. It uses
synthetic, sanitized states and LangSmith `aevaluate(upload_results=False)`, exercises Jev, the
GPT-5.6 Sol comparison judge, and a text-only failure explanation, and prints sanitized metadata only.
It does not upload a hosted LangSmith experiment and does not require `LANGSMITH_API_KEY`.

Semantic projections accept bounded strings and known typed fields only. Stable `ev_<24 hex>` IDs
are derived from canonical provenance and resolved locally to bounded support text; raw source/tool
output, CRM bodies, traces, arbitrary objects, unknown citations, and canaries are rejected before
a judge call. Numbers and counts stay with deterministic evaluators. Complete ISO date and datetime
spans are excluded from quantitative scoring; their support belongs to citation and claim review.
Provider failure emits a missing score and sanitized error metadata so coverage fails closed.

Jev requests have a 30-second budget and at most two SDK retries for connection/timeout errors, HTTP
408/429, and 5xx responses. The normalized result records model revisions, actual option order,
rubric and pricing versions, canonical state hash, probabilities, certainty source, latency, request
ID, token usage, retries, and estimated cost without retaining raw state or adapter debug payloads.
Jev retries are counted by the per-call SDK policy. The OpenAI adapter reports its configured model
alias rather than a native response snapshot, and request, cached-token, or retry detail is nullable
when the adapter does not expose it; metadata labels those sources instead of inventing values.
Estimate cards are pinned to the revisions reviewed for CAM-39: TypeSafe 2026-09-15 at `$0.042/M`
input and free output; OpenAI standard revision 2026-08-21 at `$4/M` input, `$0.40/M` cached input,
and `$20/M` output. Estimates are not invoices and must be re-reviewed before later live runs.

TypeSafe zero data retention is not assumed. The MVP permits only synthetic, sanitized judge state;
production use requires a vendor/DPA and retention review. A successful smoke is live-provider
evidence but not hosted LangSmith experiment evidence, and neither replaces repository verification.
