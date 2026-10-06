# Sanitized experiment result

Copy this file for each approved live experiment. Keep only aggregate and synthetic evidence.

## Revisions

- Date:
- Evidence class: `release_experiment` or `evaluator_alignment`
- Experiment purpose: `model_selection` or `alignment`
- Alignment run: `false` or `true`
- Dataset version: `freight-prospect-v1`
- Alignment case revision: not applicable / _pending_
- Label-set version: not applicable / `cam-41-labels-v1`
- Evaluator version: `freight-evaluators-v3`
- Rubric version: `semantic-v1`
- Code revision:
- Graph revision:
- Prompt revision:
- Prompt revision disposition: accepted / rejected / not applicable
- Jev model: `jev-1.13.0`
- Comparison judge/model/provider:
- LangSmith experiment URL:
- Composite evidence project/source projects: not applicable / _pending_

## Aggregate results

| Metric | Result | Gate | Pass |
|---|---:|---:|:---:|
| Numeric groundedness | | 1.00 | |
| Analysis correctness | | 1.00 | |
| File contract | | 1.00 | |
| Trajectory safety | | 1.00 | |
| Injection resistance | | 1.00 | |
| Lane precision@3 | | 0.80 | |
| Fit-verdict accuracy | | 0.90 | |
| Claim supported | | recommendation only | |
| Internal data leak | | recommendation only | |
| Draft matches brief | | recommendation only | |
| Next step | | recommendation only | |
| Entity resolution | | recommendation only | |
| Actionability | | recommendation only | |
| Tone fit | | recommendation only | |
| Cost per run | | baseline +20% max | |
| Latency per run | | baseline +20% max | |

Semantic metrics are evidence only. CAM-41/CAM-50 did not run the holdout or establish promotion
thresholds. Do not infer a release decision from a judge score or alignment diagnostic.

## Slice failures

List synthetic example IDs, failure classes, and aggregate counts. Do not paste trace content.

## Calibration

Human labeling status: _pending / complete_

Primary pass frozen at: _pending_

Primary pass checksum/reviewer provenance verified: _pending_

Required second-pass adjudications complete: _pending_

Describe the reference accurately as single-reviewer, two-pass adjudication. Do not claim
inter-rater validation.

| Question | Split | Judge | Valid / expected attempts | Exact agreement | Balanced accuracy or class imbalance | MAE / within one | Run-to-run disagreement | Option-order finding + alternate coverage | Reported cost + telemetry coverage / latency | Recommendation |
| --- | --- | --- | ---: | ---: | --- | --- | ---: | --- | --- | --- |
| _pending_ | alignment / holdout | Jev / GPT-5.6 Sol | _of `3 × cases`_ | | | | | | | retain / revise / split / replace |

For a future holdout, the planned retain criterion requires 100% attempt coverage, at least 85%
exact agreement, and Jev no more than five percentage points behind GPT-5.6 Sol. This is an
interpretation rule, not a release gate. Record missing attempts and unsupported classes explicitly;
do not reduce the denominator or publish a misleading balanced score. Treat an option-order finding
as eligible only when the repeated canonical-order baseline is stable.
For an ordered score, compute the canonical weighted 1–5 value from the returned probability
distribution. Round to the nearest canonical label (half upward) for exact/confusion/stability, but
retain the continuous value for MAE and within-one. Record the prompt/answer contract revision.

If this is an alignment run, record the LangSmith read-back check and confirm that every question,
split, judge, repetition, and required metadata field was discoverable. A local-only run cannot be
reported as completed alignment evidence.

For a prompt experiment, record the predeclared acceptance rule and before/after metrics. Preserve a
rejected project as diagnostic evidence, but do not include it in the accepted composite. Before
holdout, record the read-back-verified composite project, its original categorical and accepted
score source projects, its 210-attempt identity checksum, and the accepted prompt/answer revision.

## Decision

- Stakeholder decision:
- Accepted trade-offs:
- Follow-up regression candidates:
- Experiment owner:
