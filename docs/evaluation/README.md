# Evaluation approach

Offline evaluation decides whether a graph revision is ready to ship. Online evaluation detects
quality changes after release, and reviewed online failures become permanent regression examples.

See [human-in-the-loop-flow.md](human-in-the-loop-flow.md) for the outreach review checkpoint,
decision outcomes, durable commit flow, preference learning, and quality feedback signals.

See [experimentation-process.md](experimentation-process.md) for the CAM-40 variants, evaluation
method, aggregate results, evaluator revisions, and MVP configuration decision.

See [evaluator-alignment-process.md](evaluator-alignment-process.md) for the CAM-41/CAM-50
human-preference workflow, blind labeling protocol, alignment/holdout analysis, evidence boundaries,
and presentation record. The 70-case reference review and 13 adjudications are complete; the
210-attempt alignment phase is read back. The untouched holdout was explicitly waived for the
take-home closeout while its implementation remains available for future validation. The alignment
diagnostic found complete coverage on all five binary/categorical questions. The approved weighted-
score contract revision and targeted retry now provide complete ordered-score diagnostic coverage;
one bounded v3 score-anchor prompt experiment was rejected under its predeclared rule. The accepted
v2 categorical-plus-score evidence is now composed into a read-back-verified 210-attempt manifest;
three questions remain revision candidates. CAM-41/CAM-50 are complete without claiming holdout or
production validation.

The credential-free harness provides:

- `freight-prospect-v1`: 16 core and 8 edge examples with deterministic reference outputs.
- `freight-prospect-regression-v1`: a separately versioned, checksummed snapshot populated only by
  explicitly accepted regression candidates. It is empty until the first reviewed promotion.
- A separate, generator-backed pool of 8 traffic accounts with no account-ID overlap.
- LangSmith-native evaluators for grounding, lane precision, score correctness, verdicts, files,
  trajectories, injection resistance, latency, cost, and tool calls.
- A credential-free scripted target that traverses the compiled graph, middleware, artifact
  validation, and named human-review interrupt without calling a model provider.
- Seven async, LangSmith-native semantic evaluators backed by an injected Jev client pinned to
  `jev-1.13.0`. An injected GPT-5.6 Sol judge is comparison-only and never an automatic fallback.
- Three repetitions per example and named comparisons for model routing, prompt revision, and
  interpreter mode.

## Reviewed regression intake

An online evaluator flag or rep rejection may enter the explicit `RegressionWorkflow` only with an
independently sanitized draft matching the shared target/reference schema. The candidate is stored
in PostgreSQL with its source event/run, bounded evidence, failure taxonomy, and version provenance.
Canonical input-plus-taxonomy signatures detect duplicate failures. One reviewer accepts or rejects
the candidate; rejected rows remain in the audit history, and only accepted rows can promote.

Promotion persists one immutable regression example and atomically rewrites the canonical snapshot
from all promoted rows. Retrying repairs an interrupted export without adding another example or
audit transition. The exporter and committed snapshot never contain raw traces, prompts, messages,
contacts, credentials, provider payloads, tenant/rep identifiers, or automatic LangSmith downloads.

`langsmith_examples()` remains the exact historical 24-example CAM-40 population.
`release_examples()` appends integrity-checked regression rows for the credential-free release run.
`make verify` executes that combined population with deterministic evaluators only; semantic and
hosted paths retain their existing explicit credential boundary.

The current credential-free target is graph `prospect-compiled-script-v4` with prompt bundle
`outreach-v4`. It projects digit-free fictional display names plus a fictional contact, role, and
representative into runtime middleware without changing the historical `freight-prospect-v1`
dataset bytes, IDs, payloads, or checksum. Its scripted fit draft must pass the production
customer-copy validator before the scripted reviewer may return `pass`. The scripted trajectory
uses the same typed artifact tools as the live graph. Retained v1/v2/v3 LangSmith runs remain
historical evidence and must not be presented as validation of v4.

The CAM-38 deterministic release profile requires 100% grounding, analysis correctness, file
contract, trajectory safety, and injection resistance; reference-aware lane precision@3 at least
0.80; and verdict accuracy at least 0.90. The precision denominator is the larger of the unique
predicted and expected top-three counts, with two empty sets scoring 1.0. Latency, cost, and tool
calls are informational rather than correctness gates.

## Semantic evaluator profile

CAM-39 adds these narrow semantic metrics without changing the CAM-38 deterministic gates:

| Metric | Projected state | LangSmith score |
| --- | --- | --- |
| `claim_supported` | One qualitative claim and its locally resolved, sanitized citation support | Minimum Jev `P(yes)` across claims; `0` for an unresolved citation and `1` when there are no qualitative claims |
| `internal_data_leak` | Outreach draft | `1 - P(leak)` |
| `draft_matches_brief` | Brief and draft | Jev `P(yes)` |
| `next_step` | Brief | Probability assigned to the reference choice |
| `entity_resolution_ok` | Account name and sanitized resolved profile | Jev `P(yes)`; `0` when the profile is unresolved |
| `actionability` | Brief | Native Jev score from 1 through 5 |
| `tone_fit` | Draft and rep preferences | Native Jev score from 1 through 5; explicitly not applicable when preferences are absent |

Numeric values and counts remain the responsibility of deterministic code evaluators. Complete ISO
date and datetime spans are excluded from quantitative scoring; their support belongs to citation
and claim review. A semantic result with a provider or validation failure has no score and carries
only sanitized error metadata. Missing results therefore fail metric coverage closed; GPT-5.6 Sol
does not substitute for Jev. CAM-41/CAM-50 measure human agreement and produce per-question
recommendations; they do not set semantic promotion gates. Semantic scores remain evidence only and
do not affect the release decision.

Each judge receives a strict, size-bounded projection rather than a trace or application object.
Qualitative evidence uses stable `ev_<24 hex>` citation IDs derived from canonical provenance. The
application resolves those IDs locally to bounded support text before the judge call. Unknown IDs,
oversized content, arbitrary objects, and planted injection canaries are rejected. Raw CRM bodies,
source payloads, web/tool output, prompts, and private customer data never enter Jev or the GPT
comparison state.

## Evaluator catalog and judge use

The deterministic suite never calls a judge:

| Evaluator | What it checks |
| --- | --- |
| `numeric_groundedness` | Every number in the brief and draft occurs in normalized source evidence. |
| `lane_precision_at_3` | Predicted top lanes overlap the reference top three. |
| `analysis_correctness` | The complete ranked lane artifact matches the independent `lane_fit_v1` reference. |
| `fit_verdict_accuracy` | The predicted fit verdict matches the reference verdict. |
| `file_contract` | Required artifacts exist, parse, satisfy schemas, and include no unexpected files. |
| `trajectory_checks` | Delegation order, review state, and approval-before-send invariants hold. |
| `injection_resistance` | No planted canary or forbidden mutation appears in model-authored output. |
| `latency_seconds` | Reports target latency as informational evidence. |
| `cost_usd` | Reports target cost as informational evidence. |
| `tool_call_count` | Reports the number of requested tool calls as informational evidence. |

The seven semantic evaluators in the table above all require an injected `SemanticJudge`. Jev is
the default judge. GPT-5.6 Sol implements the same contract only for comparison/calibration and is
never selected automatically after a Jev failure. Each evaluator projects only its own state and
converts the normalized judge decision into a native LangSmith `EvaluationResult`.

## Client ownership and run wiring

Application inference and evaluation judging are separate composition roots:

- `app/platform/llm/openai.py` builds the application's GPT-5.6 Sol orchestrator and GPT-5.6 Luna
  specialist `ChatOpenAI` clients from `Settings`; application bootstrap owns their transports.
- `evaluation/judges/jev.py::TypeSafeJevJudge.from_api_key()` creates the evaluation-only
  `AsyncTypeSafeClient`.
- `evaluation/judges/openai.py::OpenAIComparisonJudge.from_api_key()` creates the evaluation-only
  `AsyncOpenAIProvider` and `AsyncSystemOneAdapterClient`; the same module defines the bounded
  failure-explanation call.
- `evaluation/experiments/semantic_smoke.py` creates the raw `AsyncOpenAI` Responses client used by
  that one explanation and closes all three evaluation client boundaries. None is borrowed from the
  running application.

For the credential-free run, `evaluation/experiments/offline/runner.py` passes `ProspectOfflineTarget()`
and `OFFLINE_EVALUATORS` to LangSmith `evaluate(...)`. The target executes once per example and its
sanitized output mapping is passed to every deterministic evaluator with the example's reference
outputs.

For semantic runs, the caller creates a judge, calls `semantic_evaluators(judge)`, and passes the
returned async evaluators to LangSmith `aevaluate(...)` beside a target that emits
`semantic_observations`. CAM-39's smoke selects one semantic evaluator per provider to prove both
boundaries without creating a hosted experiment. CAM-40's explicit hosted path runs the full
deterministic and semantic suites against the versioned LangSmith dataset. The semantic evaluators
are not part of CAM-38's `OFFLINE_EVALUATORS` tuple and do not execute inside application API or
worker runs.

The live smoke remains in `evaluation/experiments/semantic_smoke.py` because it is an operator-run
evaluation command that makes credentialed provider calls. Its credential gating, output redaction,
and failure behavior are tested separately in `tests/unit/evaluation/test_semantic_smoke.py`; test
code never contains the live command implementation.

Run `uv run python -m evaluation.experiments.offline` from `backend/` to execute all 24 examples
three times locally and refresh the sanitized report in
`backend/evaluation/reports/cam_38_offline.md`. The report is repository evidence from a scripted
compiled graph, not live-model or hosted LangSmith evidence.

## Archived hosted CAM-40 experiment suite

CAM-40 is retained as immutable historical v1 evidence and cannot be rerun from the current v4
source. The `--live` boundary fails closed before dataset publication or provider/model work. A
future hosted run requires a separately reviewed v4 plan whose graph, prompt, and experiment names
all identify v4; it must not append current outputs to the historical CAM-40 v1 comparison or treat
retained v2/v3 runs as v4 evidence.

The historical command published `freight-prospect-v1` with seed `28029`, its canonical SHA-256
checksum, stable example IDs, and exactly 16 `core` plus 8 `edge` examples. Existing controlled
metadata, example payloads, IDs, or split membership must match byte-stable repository expectations
or the run fails closed; SDK-added runtime inventory is excluded from the canonical comparison.
LangSmith persists that dataset and each uploaded experiment according to workspace
retention policy; the repository receives only a sanitized aggregate report at
`backend/evaluation/reports/cam_40_hosted.md` after the complete matrix returns.

| Variant | Orchestrator | Specialists | Prompt | Interpreter |
| --- | --- | --- | --- | --- |
| `baseline` | `gpt-5.6-sol` | `gpt-5.6-luna` | `v1` | on |
| `lower-cost` | `gpt-5.6-luna` | `gpt-5.6-luna` | `v1` | on |
| `prompt-revision` | `gpt-5.6-sol` | `gpt-5.6-luna` | `evidence-self-check-v2` | on |
| `interpreter-off` | `gpt-5.6-sol` | `gpt-5.6-luna` | `v1` | off |

Each retained variant ran all 24 examples three times through graph revision
`prospect-intelligence-v1`, deterministic evaluator revision `freight-evaluators-v3`, semantic rubric
`semantic-v1`, and Jev `jev-1.13.0`. The `evidence-self-check-v2` prompt adds one bounded
orchestrator verification pass before drafting/review. The target uses the real compiled graph and
OpenAI models, but replaces every business-data integration with deterministic synthetic handlers,
uses in-memory graph persistence, and disables public-source reads. Only synthetic inputs and
sanitized outputs are uploaded. Rep identity is a per-example SHA-256 digest of the CAM-40 scope;
experiment metadata also carries a fixed SHA-256 representative-scope digest, never a real rep ID.
Every invocation is checked against the local canonical synthetic input before execution. After
each variant, the runner reads LangSmith back and requires all 72 roots, exact repetition coverage,
rep/code metadata, and all evaluator feedback before continuing. The same commit-plus-worktree
fingerprint is recorded in experiment metadata and the final report.

The historical hosted target reported provider-observed tokens, wall latency, and estimated target cost. The
CAM-40 OpenAI standard price card is `$4.00/M` input, `$0.40/M` cached input, and `$20.00/M` output
for GPT-5.6 Sol, and `$0.20/M`, `$0.02/M`, and `$1.20/M` respectively for GPT-5.6 Luna. Jev cost is
reported separately using the CAM-39 TypeSafe 2026-09-15 card (`$0.042/M` input, free output).
The OpenAI card was pinned on 2026-09-30 from the
[official pricing reference](https://developers.openai.com/api/docs/pricing). Estimates are not
invoices and the price cards must be reviewed before later runs.
Graph and output-normalization exceptions remain represented as sanitized `target_error` rows so
their elapsed time and provider-observed spend are retained. Their evaluation projections are empty,
making deterministic coverage fail closed without persisting the exception message in the target
output or report.

`experiments.offline.results.gate_results()` remains the only deterministic release gate. It enforces exact
example/repetition and metric coverage plus the CAM-38 thresholds; the seven Jev scores, their
coverage, latency, and cost remain evidence-only before and after CAM-41/CAM-50 alignment. Results
are aggregated by variant, split, dataset tag, metric, and synthetic failure ID. A candidate must pass every
deterministic gate and introduce no new deterministic failure. A target-cost or mean-latency increase
over 20% is accepted only when the candidate also fixes at least one baseline deterministic failure.
Semantic improvement alone never overrides that policy.

Hosted writes occur one variant at a time. If a later variant fails, already completed experiments
remain in LangSmith, but the strict runner does not issue an automated gate decision from the partial
matrix and never combines attempts. CAM-40 has one explicit MVP exception: after quota exhaustion,
the product owner accepted a concise decision memo based on three complete variants and a 51-row
interpreter-off sample that covered every example at least twice. The memo is retained hosted
evidence, not proof that the formal four-variant gate completed. Repository tests, the local CAM-38
report, the CAM-39 provider smoke, and hosted CAM-40 experiments remain distinct evidence classes.

## Harness architecture

The implementation separates observation from judgment:

- `evaluation/experiments/offline/` owns the credential-free runner, report, and deterministic
  aggregate/gate helpers.
- `evaluation/experiments/hosted/` owns dataset publication, the live runner and runtime, persistence
  checks, the controlled plan, and hosted result/report handling.
- `evaluation/experiments/semantic_smoke.py` remains separate because it exercises providers without
  creating a hosted experiment.

See [offline-evaluator-flow.md](offline-evaluator-flow.md) for the short module and data-flow map.
See [align-evals.md](../development/align-evals.md) for the process used to correct evaluator
misalignment found in hosted experiments.

- `app/features/agent_quality/` owns the SDK-neutral evaluator catalog, semantic projections,
  rubrics, judge contracts, and app-side runtime. `evaluation/contracts/`, `evaluation/rubrics/`,
  and `evaluation/judges/` retain compatibility re-exports so offline and online meaning cannot
  drift.
- `evaluation/targets/` runs the application and emits that contract. It does not import evaluators.
- `evaluation/evaluators/` contains one native LangSmith evaluator callable per metric. Each accepts
  `outputs` and `reference_outputs` and returns `EvaluationResult`.
- `evaluation/evaluators/suite.py` orders offline wrappers and owns release thresholds; evaluator
  identity and scope come from the application-owned catalog.
- `evaluation/rubrics/semantic_v1.py` stores the exact source-controlled question text and criteria;
  each decision records `semantic-v1` so live evidence resolves to the rubric used.
- `evaluation/judges/` owns only injected, provider-specific Jev and OpenAI adapters, separately
  from deterministic code metrics.
- Semantic evaluator factories translate normalized decisions into native LangSmith
  `EvaluationResult` values without exposing provider payloads or raw judge state.
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

CAM-41/CAM-50 prepare exactly 10 applicable, deduplicated cases per question with seed `28029` and
split them into five alignment plus five untouched holdout cases. A designated reviewer labels projected state blind,
freezes the complete primary pass as a reviewer-verified checksum, and adjudicates low-confidence or
ambiguous cases in separate metric queues. Jev and GPT-5.6 Sol then run three repetitions in distinct
alignment and frozen-holdout phases. Ordered options use a repeated canonical baseline plus
deterministic permutations mapped back to canonical labels. A revision-bound alignment completion
manifest must exist before holdout. Retain requires complete attempt
coverage, at least 85% holdout exact
agreement, and Jev no more than five percentage points behind Sol. This is a single-reviewer,
two-pass process—not inter-rater validation—and the recommendation remains evidence-only rather than
a semantic promotion gate.

For ordered scores, the shared primitive's probability distribution maps rubric positions back to a
weighted canonical 1–5 value. Exact/confusion/stability metrics use the nearest canonical label;
MAE and within-one retain the continuous value. This distinction was established on the alignment
split before holdout and is versioned as `shared-question-payload-v2-weighted-scores`.

This v2 revision corrected output normalization; it did not change rubric wording. A separate
`shared-question-payload-v3-score-anchors` experiment made score-anchor guidance explicit, but was
rejected because `tone_fit` within-one agreement regressed and Jev developed `actionability`
repeat/order instability. The immutable v3 diagnostic is not part of the accepted composite.

The alignment implementation is organized into pure `reference`, `calibration`, and `evidence`
layers, with LangSmith operations isolated in `integrations/langsmith`, report output in
`reporting`, and live coordination in `workflows`. The CLI and deterministic evidence identities
remain stable across this package reorganization.

Alignment traces use `evidence_class=evaluator_alignment`, `experiment_purpose=alignment`, and
`alignment_run=true`. Future release experiments use `evidence_class=release_experiment`,
`experiment_purpose=model_selection`, and `alignment_run=false`; release selection excludes
alignment evidence by metadata. Historical CAM-40 evidence is unchanged.

Holdout requires the accepted composite project
`cam-41-alignment-composite-cam-41-labels-v1-039273d2fe8e3143`. The path remains available but was
explicitly waived from the take-home completion criteria and has not run.

Online quality operations live in `features/agent_quality`. That feature owns app-side evaluation,
the concrete injected LangSmith gateway, annotation routing, traffic simulation, and regression
candidate workflows. Evaluation envelopes are durable but never sent wholesale to LangSmith;
actor identifiers are hashed, current account IDs are synthetic fixtures, and raw tool/web output
is never sent to Jev.

Use [experiment-result-template.md](experiment-result-template.md) for live evidence. Do not
commit traces, credentials, downloaded result payloads, private data, or full model outputs.

## Explicit live smoke

From `backend/`, run the credential-gated synthetic smoke only with an explicit live opt-in:

```sh
TYPESAFE_API_KEY=... OPENAI_API_KEY=... \
  uv run python -m evaluation.experiments.semantic_smoke --live
```

The smoke uses `aevaluate(upload_results=False)` with synthetic, sanitized state. It exercises the
Jev evaluator, the GPT-5.6 Sol comparison path, and one text-only failure explanation with OpenAI
Responses storage disabled. It prints sanitized metadata only and does not create a hosted
LangSmith experiment, so `LANGSMITH_API_KEY` is not required. Omitting `--live` or either provider
credential fails before a provider call. Repository tests and CI never run this command.

The normalized metadata records requested and resolved model, the resolved-model source, rubric and
pricing versions, actual option order, a canonical SHA-256 state hash, probabilities, certainty and
its source, latency, request ID, token counts and their source, retry count and its source, and
estimated cost. It does not retain the projected state or adapter debug payloads. Jev retries are
counted by the per-call SDK policy. The OpenAI adapter exposes its configured model alias rather than
the provider's native resolved snapshot; request IDs and cached-token detail remain null when the
adapter omits them. When only retry-total tokens are available, costing conservatively applies the
standard input rate and labels the total-token source.
Jev has a 30-second request budget and two SDK retries for connection/timeout errors, HTTP 408/429,
and 5xx responses. Other client errors and invalid responses are not retried. Jev cost estimates use
the TypeSafe price revision reviewed on 2026-09-15: `$0.042` per million input tokens with free
output. GPT-5.6 Sol estimates use the OpenAI standard price revision from 2026-08-21: `$4.00`
per million input tokens, `$0.40` per million cached input tokens, and `$20.00` per million output
tokens. These values are estimates, not provider invoices, and must be re-reviewed before a future
live run.

TypeSafe does not currently provide an assumed zero-data-retention guarantee. Only synthetic,
sanitized state is allowed for this MVP, and any production use requires a vendor/DPA and retention
review. Local smoke output is live provider evidence, not proof of a hosted LangSmith experiment.
Hosted experiment evidence must separately record the dataset, evaluator, graph/prompt revisions,
experiment URL, and interpretation. Neither kind of live evidence is interchangeable with passing
repository tests.

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
