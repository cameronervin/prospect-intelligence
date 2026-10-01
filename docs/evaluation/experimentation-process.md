# Experimentation Process and Decision

CAM-40 compared model routing, prompt, and interpreter choices for the freight prospect agent. The
goal was to select a reliable MVP configuration using synthetic data, repeatable metrics, and hosted
LangSmith evidence.

## What was delivered

The experiment used graph revision `prospect-intelligence-v1` and dataset
`freight-prospect-v1`. The dataset contains 24 synthetic examples: 16 core cases and 8 edge cases.

Four product variants were evaluated:

| Variant | Orchestrator | Specialists | Prompt | Interpreter |
| --- | --- | --- | --- | --- |
| Baseline | GPT-5.6 Sol | GPT-5.6 Luna | `v1` | On |
| Lower cost | GPT-5.6 Luna | GPT-5.6 Luna | `v1` | On |
| Prompt revision | GPT-5.6 Sol | GPT-5.6 Luna | `evidence-self-check-v2` | On |
| Interpreter off | GPT-5.6 Sol | GPT-5.6 Luna | `v1` | Off |

The prompt revision added one bounded self-check before drafting and review. It asked the
orchestrator to verify the brief template, ordering, exact numbers, modeled labels, and existing
citations, then rewrite at most once.

Two evaluator revisions are part of the evidence:

- `freight-evaluators-v2` produced the original hosted feedback.
- `freight-evaluators-v3` corrected numeric grounding after the hosted results exposed syntax that
  was being treated as quantitative claims. V3 ignores complete date and datetime spans, Markdown
  list markers, and multi-part source version labels. It still checks bare years, money,
  percentages, counts, and quantities. It also reads numeric evidence from the complete approved
  artifact scope.

The v3 numeric scores were calculated locally from the retained synthetic outputs. They remain
separate from the original hosted feedback.

## How the variants were evaluated

Each example used deterministic synthetic account, network, research, and market data. Public data
lookups were disabled. The target ran the real compiled graph and model configuration, while all
business data remained synthetic.

The evidence set contained:

- 72 results for baseline, covering all 24 examples three times.
- 72 results for lower-cost routing, covering all 24 examples three times.
- 72 results for the prompt revision, covering all 24 examples three times.
- 49 usable interpreter-off results, covering every example at least twice.

Deterministic evaluators measured:

- Analysis agreement with the independent lane reference.
- Required file and schema contracts.
- Graph trajectory and human-review ordering.
- Injection resistance.
- Top-three lane precision.
- Fit verdict accuracy.
- Numeric grounding.

Latency, token usage, and estimated cost were recorded as operational evidence. Seven Jev semantic
evaluators also reviewed claim support, data leakage, brief and draft agreement, next-step choice,
entity resolution, actionability, and tone. Semantic scores were supporting evidence because human
calibration is separate work.

The deterministic results below are the original hosted aggregates. Values in parentheses show the
number of scored results for that metric.

| Variant | Analysis | File | Trajectory | Injection | Lane | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0.9296 (71) | 0.9942 (72) | 0.9296 (71) | 0.9306 (72) | 0.9296 (71) | 0.9296 (71) |
| Lower cost | 0.7000 (70) | 0.9765 (71) | 0.7042 (71) | 0.7042 (71) | 0.7143 (70) | 0.7101 (69) |
| Prompt revision | 0.9306 (72) | 0.9941 (71) | 0.9296 (71) | 0.9306 (72) | 0.9296 (71) | 0.9296 (71) |
| Interpreter off | 0.8958 (48) | 0.9915 (49) | 0.8980 (49) | 0.8980 (49) | 0.8958 (48) | 0.8936 (47) |

The corrected v3 numeric re-score produced these diagnostic results:

| Variant | Numeric passes | Pass rate |
| --- | ---: | ---: |
| Baseline | 19 of 72 | 26.39% |
| Lower cost | 14 of 72 | 19.44% |
| Prompt revision | 22 of 72 | 30.56% |
| Interpreter off | 13 of 49 | 26.53% |

The operational comparison was:

| Variant | Estimated target cost | Cost per usable result | Mean latency | Change from baseline |
| --- | ---: | ---: | ---: | --- |
| Baseline | $21.212613 | $0.294620 | 90.819 s | Reference |
| Lower cost | $2.140251 | $0.029726 | 89.087 s | Cost -89.9%, latency -1.9% |
| Prompt revision | $23.808301 | $0.330671 | 94.202 s | Cost +12.2%, latency +3.7% |
| Interpreter off | $15.386561 for the sample | $0.314011 | 91.993 s | Per-result cost +6.6%, latency +1.3% |

## Decision

The selected MVP configuration is:

- GPT-5.6 Sol orchestrator.
- GPT-5.6 Luna specialists.
- Prompt `v1`.
- Interpreter enabled.

The lower-cost variant saved substantial cost but produced materially lower deterministic quality.
The prompt revision produced similar deterministic quality to baseline while costing 12.2% more and
taking 3.7% longer. Turning the interpreter off did not improve quality, latency, or cost per usable
result.

The baseline provided the best balance of quality, cost, and latency for the MVP. The corrected
numeric score remains diagnostic and identifies a future opportunity to separate quantitative facts
from numeric text used in company names and evidence locators.

The hosted dataset and experiment links are recorded in the sanitized
`backend/evaluation/reports/cam_40_hosted.md` report. Raw traces, prompts, source payloads, and
credentials are not stored in the repository.
