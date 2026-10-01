# Offline evaluator flow

The offline harness runs the real compiled graph with scripted model responses. It scores sanitized
graph output without network access. CAM-39 adds an explicit, credentialed semantic smoke beside
this path; it does not turn the deterministic offline harness into a live-provider test.

```text
versioned dataset
  inputs + reference outputs
             |
             v
  experiments/offline/runner.py
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
          experiments/offline/results.py -> gates and aggregates
                                  |
                                  v
           experiments/offline/report.py -> Markdown report
```

The separate live semantic path is:

```text
synthetic snapshot + reference outputs
                 |
                 v
strict semantic projection
  bounded strings + resolved ev_<24 hex> citations
                 |
                 v
async SemanticJudge
  Jev default -------- GPT-5.6 Sol comparison only
                 |
                 v
normalized decision metadata (no raw state)
                 |
                 v
LangSmith aevaluate(upload_results=False)
```

## Modules

- `datasets/`: examples, target inputs, and reference outputs.
- `targets/`: run the compiled graph. They do not import evaluators.
- `app/features/agent_quality/`: owns the shared evaluator catalog, bounded projections, semantic
  judge contracts, rubrics, provider adapters, and SDK-neutral scoring used online and offline.
- `contracts/`: build the offline safe snapshot and observations; semantic contract modules are
  compatibility re-exports of the application-owned definitions.
- `evaluators/`: one native LangSmith code evaluator per deterministic metric plus async semantic
  evaluator factories returning native `EvaluationResult` objects.
- `evaluators/suite.py`: evaluator order, version, and gate thresholds.
- `rubrics/`: compatibility re-exports of application-owned versioned question text and criteria.
- `judges/`: offline adapters over the application-owned provider boundaries. Jev is the semantic
  default; GPT-5.6 Sol remains limited to comparison and text-only failure explanation.
- `experiments/`: run evaluation, aggregate rows, apply gates, and write the report.

## Data boundary

Evaluators receive model-authored analysis and output artifacts plus safe observations. They do not
receive prompts, raw messages, tool arguments, source payloads, or injection canaries from the
target. Reference outputs are passed only to evaluators.

Before a semantic call, application code reduces those artifacts again to the minimum typed state
for one question. Qualitative claims must carry stable `ev_<24 hex>` IDs derived from canonical
provenance; the IDs are resolved locally to bounded, application-authored support text. Unknown
citations, arbitrary objects, oversized values, and canaries fail validation. Numeric, date, and
count claims bypass Jev and remain deterministic evaluator concerns.

A provider failure returns a missing semantic score with sanitized metadata, so coverage fails
closed. Retriable Jev transport, timeout, 408, 429, and 5xx failures receive at most two SDK retries
within a 30-second budget. GPT-5.6 Sol is never an automatic fallback.

`LaneAnalysisArtifact` is the strict wire contract for `/analysis/lane_fit.json`. It checks exact
fields, `lane_fit_v1`, verdict and lane consistency, top-three limits, duplicates, decimal encoding,
and rank order. The correctness evaluator still computes its expected result independently.
