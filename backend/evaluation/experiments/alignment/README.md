# Evaluator alignment package

This package keeps human-reference preparation, judge calibration, LangSmith evidence, and report
generation reviewable as separate concerns. The command remains
`python -m evaluation.experiments.alignment`; the completed reorganization did not change seeds, case IDs,
hashes, trace metadata, report paths, or authorization behavior.

The dependency shape is:

- `reference/`: deterministic cases and fixtures, labels, feedback parsing, and freeze validation.
- `calibration/`: attempts, runner, metrics, summaries, and recommendation policy.
- `evidence/`: provider-neutral metadata, trace records, and manifest contracts.
- `integrations/langsmith/`: datasets, queues, trace publication/querying, and manifest persistence.
- `reporting/`: aggregate validation, tables, and Markdown output.
- `workflows/`: labeling, calibration, and evidence-composition orchestration with injected clients.

`reference`, `calibration`, and `evidence` are pure layers. They do not import LangSmith, application
settings, provider adapters, integrations, reporting, or workflows, and they do not write reports.
The CLI owns argument parsing, preflight disclosure, and explicit authorization; workflows own
coordination; integrations own network behavior. `contracts.py`, `paths.py`, and `self_test.py`
remain at the package root.

The staged move map is:

| Target | Former flat modules |
| --- | --- |
| `reference/` | `case_fixtures`, `cases`, `feedback*`, `labeling`, `labels`, `label_set_payload`, `primary_freeze` |
| `calibration/` | `policy`, `result_*`, `results`, `runner` |
| `evidence/` | `metadata`, `trace_models`, plus provider-neutral manifest contracts |
| `integrations/langsmith/` | `label_set`, `phase_manifest`, `publication*`, `trace_queries`, `tracing` |
| `reporting/` | `report`, `report_tables`, `report_validation` |
| `workflows/` | `live`, `live_labeling`, `live_support` |

The completed package has no retired flat modules or temporary import shims and retains an acyclic
internal import graph. The provider-free `publish-composite` workflow validates the immutable
categorical and accepted score projects, publishes one sanitized identity manifest, and reads it
back before it can satisfy the holdout prerequisite. Both publication and holdout verification pin
the approved source project names and their code revisions. The rejected v3 prompt project is
deliberately excluded from that manifest.
