# CAM-41/CAM-50 Human-Preference Alignment Report

This report contains sanitized aggregate alignment evidence only. It excludes case IDs, projected state, prompts, traces, and provider payloads.

## Evidence status

- Status: **DIAGNOSTIC COMPLETE — read-back verified; holdout not run**
- LangSmith project: `cam-41-alignment-cam-41-labels-v1-0099bade7c54a0ed`

## Revisions

- Dataset: `freight-prospect-v1`
- Label set: `cam-41-labels-v1`
- Rubric: `semantic-v1`
- Evaluator: `freight-evaluators-v3`
- Graph: `prospect-intelligence-v1`
- Prompt: `shared-question-payload-v1`
- Code: `e270dd16365b-dirty-69c567eba5e0`

## Per-question judge metrics

| Question | Split | Judge | Valid / expected | Coverage | Exact agreement | Balanced accuracy | MAE | Within one | Run-to-run disagreement | Order sensitivity | Alternate-order coverage | Reported cost / coverage | Latency |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `actionability` | `alignment` | `jev` | 3 / 15 | 20.00% | 100.00% | — | 0.000 | 100.00% | 0.00% | 0.00% (0/1) | 20.00% (1/5) | $0.000050 reported; total unavailable / 20.00% (3/15) | 2.688s |
| `actionability` | `alignment` | `sol` | 0 / 15 | 0.00% | — | — | — | — | — | — (0/0) | 0.00% (0/5) | $0.000000 reported; total unavailable / 0.00% (0/15) | 25.877s |
| `claim_supported` | `alignment` | `jev` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.000245 / 100.00% (15/15) | 2.847s |
| `claim_supported` | `alignment` | `sol` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.032140 / 100.00% (15/15) | 24.209s |
| `draft_matches_brief` | `alignment` | `jev` | 15 / 15 | 100.00% | 80.00% | 75.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.000245 / 100.00% (15/15) | 2.413s |
| `draft_matches_brief` | `alignment` | `sol` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.025916 / 100.00% (15/15) | 17.550s |
| `entity_resolution_ok` | `alignment` | `jev` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.000233 / 100.00% (15/15) | 2.373s |
| `entity_resolution_ok` | `alignment` | `sol` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.030848 / 100.00% (15/15) | 26.792s |
| `internal_data_leak` | `alignment` | `jev` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.000228 / 100.00% (15/15) | 2.629s |
| `internal_data_leak` | `alignment` | `sol` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | — (0/0) | — (0/0) | $0.024380 / 100.00% (15/15) | 17.325s |
| `next_step` | `alignment` | `jev` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | 0.00% (0/5) | 100.00% (5/5) | $0.000259 / 100.00% (15/15) | 2.397s |
| `next_step` | `alignment` | `sol` | 15 / 15 | 100.00% | 100.00% | 100.00% | — | — | 0.00% | 0.00% (0/5) | 100.00% (5/5) | $0.036144 / 100.00% (15/15) | 23.398s |
| `tone_fit` | `alignment` | `jev` | 1 / 15 | 6.67% | 100.00% | — | 0.000 | 100.00% | 0.00% | — (0/0) | 0.00% (0/5) | $0.000017 reported; total unavailable / 6.67% (1/15) | 2.896s |
| `tone_fit` | `alignment` | `sol` | 0 / 15 | 0.00% | — | — | — | — | — | — (0/0) | 0.00% (0/5) | $0.000000 reported; total unavailable / 0.00% (0/15) | 35.924s |

## Aggregate confusion counts

| Question | Split | Judge | Counts (human→judge) |
| --- | --- | --- | --- |
| `actionability` | `alignment` | `jev` | 1→1=3 |
| `actionability` | `alignment` | `sol` | none |
| `claim_supported` | `alignment` | `jev` | false→false=6, true→true=9 |
| `claim_supported` | `alignment` | `sol` | false→false=6, true→true=9 |
| `draft_matches_brief` | `alignment` | `jev` | false→false=9, true→false=3, true→true=3 |
| `draft_matches_brief` | `alignment` | `sol` | false→false=9, true→true=6 |
| `entity_resolution_ok` | `alignment` | `jev` | false→false=6, true→true=9 |
| `entity_resolution_ok` | `alignment` | `sol` | false→false=6, true→true=9 |
| `internal_data_leak` | `alignment` | `jev` | false→false=6, true→true=9 |
| `internal_data_leak` | `alignment` | `sol` | false→false=6, true→true=9 |
| `next_step` | `alignment` | `jev` | expand_existing_lanes→expand_existing_lanes=3, needs_more_data→needs_more_data=6, new_lane_pitch→new_lane_pitch=3, not_a_fit→not_a_fit=3 |
| `next_step` | `alignment` | `sol` | expand_existing_lanes→expand_existing_lanes=3, needs_more_data→needs_more_data=6, new_lane_pitch→new_lane_pitch=3, not_a_fit→not_a_fit=3 |
| `tone_fit` | `alignment` | `jev` | 2→2=1 |
| `tone_fit` | `alignment` | `sol` | none |

## Per-question recommendations

No recommendations: the untouched holdout was not run.

Semantic diagnostics remain evidence only; deterministic release gates are unchanged.
