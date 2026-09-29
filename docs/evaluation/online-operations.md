# Online quality operations

The `agent_quality` feature declaratively configures 100% sampling for numeric groundedness,
trajectory checks, and the Jev semantic suite. Its dashboard covers approve/edit/reject rates,
grounding, semantic scores, cost, latency, and tool errors. Alerts cover grounding regressions,
reject spikes, tool/API errors, and cost spikes.

The demo simulator runs three deterministic decision cycles across eight synthetic accounts that
are disjoint from the offline dataset, producing 24 sessions. A failed evaluator or rejection is
routed to the annotation queue. A reviewer must accept a sanitized candidate before it can be
promoted to the versioned regression split.

Production wiring must provide an implementation of `LangSmithQualityGateway`; no credential is
read by the feature itself. Trace retention, workspace secrets, alert destinations, and canary
traffic percentages remain deployment-owned settings and must be reviewed before live use.
