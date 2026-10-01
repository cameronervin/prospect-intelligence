# CAM-38 Offline Evaluation Report

This is credential-free repository evidence from a scripted model over the compiled prospect graph. It is not a live-model quality claim or a hosted LangSmith experiment.

## Versions

- Dataset: `freight-prospect-v1`
- Evaluators: `freight-evaluators-v3`
- Graph target: `prospect-compiled-script-v1`
- Repetitions: `3`
- Evaluated rows: `72`

## Release gates

| Gate | Observed | Minimum | Status |
| --- | ---: | ---: | --- |
| `numeric_groundedness` | 1.0000 | 1.0000 | PASS |
| `analysis_correctness` | 1.0000 | 1.0000 | PASS |
| `file_contract` | 1.0000 | 1.0000 | PASS |
| `trajectory_checks` | 1.0000 | 1.0000 | PASS |
| `injection_resistance` | 1.0000 | 1.0000 | PASS |
| `lane_precision_at_3` | 1.0000 | 0.8000 | PASS |
| `fit_verdict_accuracy` | 1.0000 | 0.9000 | PASS |
| `row_count` | 72 | 72 | PASS |
| `example_coverage` | complete | complete | PASS |
| `required_metric_coverage` | complete | complete | PASS |

## Informational metrics

| Metric | Value |
| --- | ---: |
| `cost_usd` | 0.0000 |
| `tool_call_count` | 19.0000 |
| `latency_seconds` | measured per run; omitted from the published report |

## Dataset slices

- `core`: numeric_groundedness=1.0000, analysis_correctness=1.0000, file_contract=1.0000, trajectory_checks=1.0000, injection_resistance=1.0000, lane_precision_at_3=1.0000, fit_verdict_accuracy=1.0000
- `edge`: numeric_groundedness=1.0000, analysis_correctness=1.0000, file_contract=1.0000, trajectory_checks=1.0000, injection_resistance=1.0000, lane_precision_at_3=1.0000, fit_verdict_accuracy=1.0000

## Example/repetition failures

None.

The report intentionally excludes prompts, source payloads, tool arguments, model messages, artifact bodies, traces, and injection canaries.
