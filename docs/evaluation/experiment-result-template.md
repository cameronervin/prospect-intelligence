# Sanitized experiment result

Copy this file for each approved live experiment. Keep only aggregate and synthetic evidence.

## Revisions

- Date:
- Dataset version: `freight-prospect-v1`
- Evaluator version: `freight-evaluators-v3`
- Code revision:
- Graph revision:
- Prompt revision:
- Jev model: `jev-1.13.0`
- LangSmith experiment URL:

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
| Claim supported | | not set (CAM-41) | |
| Internal data leak | | not set (CAM-41) | |
| Draft matches brief | | not set (CAM-41) | |
| Next step | | not set (CAM-41) | |
| Entity resolution | | not set (CAM-41) | |
| Actionability | | not set (CAM-41) | |
| Tone fit | | not set (CAM-41) | |
| Cost per run | | baseline +20% max | |
| Latency per run | | baseline +20% max | |

Semantic metrics are evidence-only until CAM-41 records human calibration and selects thresholds.
Do not infer a promotion decision from an uncalibrated semantic score.

## Slice failures

List synthetic example IDs, failure classes, and aggregate counts. Do not paste trace content.

## Calibration

Record per-question human agreement, five-run variance, option-order findings, comparison-judge
agreement, cost, latency, and the decision to retain, revise, split, or replace each question.

## Decision

- Stakeholder decision:
- Accepted trade-offs:
- Follow-up regression candidates:
- Experiment owner:
