# Offline evaluator flow

The offline harness runs the real compiled graph with scripted model responses. It scores sanitized
graph output without network access.

```text
versioned dataset
  inputs + reference outputs
             |
             v
  experiments/offline.py
  LangSmith evaluate() -- local only
             |
             +---------------- target run ----------------+
             |                                            |
             v                                            |
  targets/ProspectOfflineTarget                           |
             |                                            |
             v                                            |
  compiled graph -> runtime files + tool events           |
             |                                            |
             v                                            |
  contracts/snapshot.py                                   |
  sanitized outputs + observations                        |
             |                                            |
             +--------------------+-----------------------+
                                  |
                    outputs + reference outputs
                                  |
                                  v
                       evaluators/suite.py
                                  |
                                  v
                    one evaluator module per metric
                                  |
                                  v
                    LangSmith EvaluationResult rows
                                  |
                                  v
              offline_results.py -> gates and aggregates
                                  |
                                  v
                   offline_report.py -> Markdown report
```

## Modules

- `datasets/`: examples, target inputs, and reference outputs.
- `targets/`: run the compiled graph. They do not import evaluators.
- `contracts/`: decode files and build the safe `OfflineRunSnapshot` and observations.
- `evaluators/`: one native LangSmith code evaluator per metric.
- `evaluators/suite.py`: evaluator order, version, and gate thresholds.
- `judges/`: semantic judge boundaries. Jev is separate from code evaluators.
- `experiments/`: run evaluation, aggregate rows, apply gates, and write the report.

## Data boundary

Evaluators receive model-authored analysis and output artifacts plus safe observations. They do not
receive prompts, raw messages, tool arguments, source payloads, or injection canaries from the
target. Reference outputs are passed only to evaluators.

`LaneAnalysisArtifact` is the strict wire contract for `/analysis/lane_fit.json`. It checks exact
fields, `lane_fit_v1`, verdict and lane consistency, top-three limits, duplicates, decimal encoding,
and rank order. The correctness evaluator still computes its expected result independently.
