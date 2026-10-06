# CAM-41/CAM-50 Human-Preference Alignment Report

This report contains sanitized aggregate alignment evidence only. It excludes case IDs, projected state, prompts, traces, and provider payloads.

## Evidence status

- Status: **TARGETED DIAGNOSTIC COMPLETE — read-back verified; holdout not run**
- LangSmith project: `cam-41-alignment-cam-41-labels-v1-9def2f19d5593cf7`
- Targeted questions: `actionability`, `tone_fit`
- Supporting LangSmith projects: `cam-41-alignment-cam-41-labels-v1-4a7eedede417b378`

## Revisions

- Dataset: `freight-prospect-v1`
- Label set: `cam-41-labels-v1`
- Rubric: `semantic-v1`
- Evaluator: `freight-evaluators-v3`
- Graph: `prospect-intelligence-v1`
- Prompt: `shared-question-payload-v2-weighted-scores`
- Code: `e270dd16365b-dirty-8527939512f9+e270dd16365b-dirty-b537010dfbcf`

## Per-question judge metrics

| Question | Split | Judge | Valid / expected | Coverage | Exact agreement | Balanced accuracy | MAE | Within one | Run-to-run disagreement | Order sensitivity | Alternate-order coverage | Reported cost / coverage | Latency |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `actionability` | `alignment` | `jev` | 15 / 15 | 100.00% | 60.00% | — | 0.565 | 80.00% | 0.00% | 0.00% (0/5) | 100.00% (5/5) | $0.000255 / 100.00% (15/15) | 2.838s |
| `actionability` | `alignment` | `sol` | 15 / 15 | 100.00% | 53.33% | — | 0.394 | 93.33% | 6.67% | 20.00% (1/5) | 100.00% (5/5) | $0.039116 / 100.00% (15/15) | 24.191s |
| `tone_fit` | `alignment` | `jev` | 15 / 15 | 100.00% | 60.00% | — | 0.442 | 86.67% | 0.00% | 0.00% (0/5) | 100.00% (5/5) | $0.000255 / 100.00% (15/15) | 2.593s |
| `tone_fit` | `alignment` | `sol` | 15 / 15 | 100.00% | 73.33% | — | 0.342 | 93.33% | 26.67% | 33.33% (1/3) | 100.00% (5/5) | $0.053784 / 100.00% (15/15) | 37.735s |

## Aggregate confusion counts

| Question | Split | Judge | Counts (human→judge) |
| --- | --- | --- | --- |
| `actionability` | `alignment` | `jev` | 1→1=3, 2→1=3, 3→1=3, 4→4=3, 5→5=3 |
| `actionability` | `alignment` | `sol` | 1→1=3, 2→1=3, 3→2=3, 4→4=2, 4→5=1, 5→5=3 |
| `tone_fit` | `alignment` | `jev` | 1→1=3, 2→2=3, 3→2=3, 4→4=3, 5→4=3 |
| `tone_fit` | `alignment` | `sol` | 1→1=3, 2→2=3, 3→2=1, 3→3=2, 4→3=1, 4→4=1, 4→5=1, 5→4=1, 5→5=2 |

## Per-question recommendations

No recommendations: the untouched holdout was not run.

Semantic diagnostics remain evidence only; deterministic release gates are unchanged.
