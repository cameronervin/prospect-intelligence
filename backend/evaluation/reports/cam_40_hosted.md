# CAM-40 Hosted Experiment Decision

> Archived v1 evidence. Hosted feedback used `freight-evaluators-v2`; retained outputs were rescored
> locally with `freight-evaluators-v3`. This report does not validate the current v4 graph or
> `outreach-v4` prompt bundle.

## Recommendation

Continue with the baseline:

- GPT-5.6 Sol orchestrator
- GPT-5.6 Luna specialists
- Prompt `v1`
- Interpreter enabled

Do not run the matrix again for this MVP. The retained evidence is enough to choose the baseline.
The strict hosted runner did not complete its formal four-variant gate.

## Evidence

- Dataset: [freight-prospect-v1](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/datasets/6020fb26-2d0d-4340-a5da-76eb394bee72)
- Dataset ID: `6020fb26-2d0d-4340-a5da-76eb394bee72`
- Dataset checksum: `d5ed38772ba98dd9195295f851b7d548509e826c0a9c2900dc5195a6220f30c8`
- Dataset population: 24 synthetic examples, 16 core and 8 edge
- Dataset seed: `28029`
- Graph: `prospect-intelligence-v1`
- Declared hosted evaluators: `freight-evaluators-v2`, `semantic-v1`, and `jev-1.13.0`
- Prompts: `v1` and `evidence-self-check-v2`
- Models: `gpt-5.6-sol` and `gpt-5.6-luna`
- Hosted UI shows source revision `f75630`. The exact dirty source and evaluator implementation
  revisions used by the retained runs are unavailable.

Experiments:

- [Baseline](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/datasets/6020fb26-2d0d-4340-a5da-76eb394bee72/compare?selectedSessions=aa3ae237-bdc7-41dd-927c-91ecd491baf7)
- [Lower cost](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/datasets/6020fb26-2d0d-4340-a5da-76eb394bee72/compare?selectedSessions=3c889935-2f72-402a-a0a9-4a4b938b942f)
- [Prompt revision](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/datasets/6020fb26-2d0d-4340-a5da-76eb394bee72/compare?selectedSessions=7c2aaf7b-21a5-4992-98b9-4076207a0dd4)
- [Interpreter off](https://smith.langchain.com/o/272b51ac-d19f-4811-8bee-52c0b6473835/datasets/6020fb26-2d0d-4340-a5da-76eb394bee72/compare?selectedSessions=606ef301-966a-404b-9f41-59d4449ab0ea)

## Results

Scores below are the original hosted deterministic feedback after deduplicating identical records.
Values in parentheses are feedback coverage. Missing feedback is not counted as a pass.

| Variant | Roots | Target errors | Analysis | File | Trajectory | Injection | Lane | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 72 | 5 | 0.9296 (71) | 0.9942 (72) | 0.9296 (71) | 0.9306 (72) | 0.9296 (71) | 0.9296 (71) |
| Lower cost | 72 | 21 | 0.7000 (70) | 0.9765 (71) | 0.7042 (71) | 0.7042 (71) | 0.7143 (70) | 0.7101 (69) |
| Prompt revision | 72 | 5 | 0.9306 (72) | 0.9941 (71) | 0.9296 (71) | 0.9306 (72) | 0.9296 (71) | 0.9296 (71) |
| Interpreter off | 51 | 5 | 0.8958 (48) | 0.9915 (49) | 0.8980 (49) | 0.8980 (49) | 0.8958 (48) | 0.8936 (47) |

Coverage:

- Each complete variant has 48 core and 24 edge roots, with three runs for every example.
- Interpreter-off has 51 roots across all 24 examples: 21 examples have two roots and 3 have three.
- Two interpreter-off roots are empty persistence shells. The 49 usable outputs cover 32 core and
  17 edge rows, with every example represented at least twice.
- Duplicate feedback counts were 14, 19, 19, and 16 by variant. All duplicates were identical. No
  conflicting feedback was found.

## Numeric evaluator re-score

The hosted numeric score was `0` for every retained row with feedback. A read-only local audit found
false positives from dates, list numbers, source versions, numbers inside company names, and evidence
record locators. The evaluator now handles dates, list markers, dotted version labels, context values,
and numeric values inside explicit evidence claims.

The local re-score used corrected deterministic evaluator revision `freight-evaluators-v3`. The
hosted feedback remains labeled with its original declared revision `freight-evaluators-v2`.

No model or Jev calls were made for the local re-score. No traces or feedback were written. Retained
authored outputs were checked against regenerated canonical synthetic source artifacts.

| Variant | Locally rescorable outputs | Numeric passes | Pass rate |
| --- | ---: | ---: | ---: |
| Baseline | 72 | 19 | 26.39% |
| Lower cost | 72 | 14 | 19.44% |
| Prompt revision | 72 | 22 | 30.56% |
| Interpreter off | 49 | 13 | 26.53% |

These local scores remain diagnostic. The retained authored text still contains numeric company-name
suffixes and evidence locators mixed with potential unsupported quantities. The re-score is kept
separate from hosted feedback and is not used as a release gate. The alignment process and remaining
work are documented in `docs/development/align-evals.md`.

## Cost and latency

Target cost uses the CAM-40 pinned OpenAI price card. Values are estimates, not invoices. A trusted
experiment-total Jev cost and latency could not be reconstructed from the retained aggregate
evidence, so no estimate is substituted. Jev evidence was not used in the decision.

| Variant | Target cost | Cost per usable output | Mean target latency | Change from baseline |
| --- | ---: | ---: | ---: | --- |
| Baseline | $21.212613 | $0.294620 | 90.819s | Reference |
| Lower cost | $2.140251 | $0.029726 | 89.087s | Cost -89.9%, latency -1.9% |
| Prompt revision | $23.808301 | $0.330671 | 94.202s | Cost +12.2%, latency +3.7% |
| Interpreter off | $15.386561 partial | $0.314011 | 91.993s | Per-output cost +6.6%, latency +1.3% |

The interpreter-off total is partial and cannot be compared directly with the 72-row totals.

## Decision by variant

- Lower cost: reject. It reduced target cost but increased target errors from 5 to 21 and reduced
  the other deterministic scores.
- Prompt revision: reject. It matched baseline quality, cost 12.2% more, and was 3.7% slower.
- Interpreter off: reject for the MVP. Its full-dataset sample showed no cost, latency, or quality
  benefit. The sample is not a formal completed comparison.
- Baseline: continue. It has the best supported quality and trade-off for the MVP.

This report contains aggregate synthetic evidence only. It excludes raw outputs, traces, prompts,
provider payloads, tool arguments, canaries, credentials, and private customer data.
