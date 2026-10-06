# CAM-41/CAM-50 Human-Preference Alignment Report

This report contains sanitized aggregate alignment evidence only. It excludes case IDs, projected state, prompts, traces, and provider payloads.

## Evidence status

- Status: **TARGETED DIAGNOSTIC COMPLETE — read-back verified; holdout not run**
- LangSmith project: `cam-41-alignment-cam-41-labels-v1-b6adb9618f50cb3e`
- Targeted questions: `actionability`, `tone_fit`

## Revisions

- Dataset: `freight-prospect-v1`
- Label set: `cam-41-labels-v1`
- Rubric: `semantic-v1`
- Evaluator: `freight-evaluators-v3`
- Graph: `prospect-intelligence-v1`
- Prompt: `shared-question-payload-v3-score-anchors`
- Code: `e270dd16365b-dirty-d687f8aae4b6`

## Per-question judge metrics

| Question | Split | Judge | Valid / expected | Coverage | Exact agreement | Balanced accuracy | MAE | Within one | Run-to-run disagreement | Order sensitivity | Alternate-order coverage | Reported cost / coverage | Latency |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `actionability` | `alignment` | `jev` | 15 / 15 | 100.00% | 66.67% | — | 0.483 | 80.00% | 6.67% | 20.00% (1/5) | 100.00% (5/5) | $0.000297 / 100.00% (15/15) | 3.142s |
| `actionability` | `alignment` | `sol` | 15 / 15 | 100.00% | 66.67% | — | 0.360 | 86.67% | 13.33% | 40.00% (2/5) | 100.00% (5/5) | $0.045476 / 100.00% (15/15) | 26.218s |
| `tone_fit` | `alignment` | `jev` | 15 / 15 | 100.00% | 60.00% | — | 0.464 | 80.00% | 0.00% | 0.00% (0/5) | 100.00% (5/5) | $0.000296 / 100.00% (15/15) | 3.780s |
| `tone_fit` | `alignment` | `sol` | 15 / 15 | 100.00% | 46.67% | — | 0.564 | 86.67% | 26.67% | 66.67% (2/3) | 100.00% (5/5) | $0.058564 / 100.00% (15/15) | 33.141s |

## Aggregate confusion counts

| Question | Split | Judge | Counts (human→judge) |
| --- | --- | --- | --- |
| `actionability` | `alignment` | `jev` | 1→1=3, 2→1=2, 2→2=1, 3→1=3, 4→4=3, 5→5=3 |
| `actionability` | `alignment` | `sol` | 1→1=3, 2→1=1, 2→2=2, 3→2=3, 4→4=2, 4→5=1, 5→5=3 |
| `tone_fit` | `alignment` | `jev` | 1→1=3, 2→2=3, 3→2=3, 4→4=3, 5→4=3 |
| `tone_fit` | `alignment` | `sol` | 1→1=2, 1→2=1, 2→2=3, 3→2=2, 3→3=1, 4→3=1, 4→5=2, 5→4=2, 5→5=1 |

## Per-question recommendations

No recommendations: the untouched holdout was not run.

Semantic diagnostics remain evidence only; deterministic release gates are unchanged.
