# Online quality operations

`agent_quality` runs evaluators in the application and uses LangSmith only as the sanitized event,
feedback, and annotation destination. The catalog assigns every deterministic and semantic metric
to exactly one single-step, final-output, or full-trajectory scope. All ten deterministic catalog
signals are emitted after graph execution; reference-aware lane checks use the canonical product
analysis. Seven bounded Jev questions reuse the offline scoring, rubric, and judge contracts. Jev
scores are evidence only until CAM-41 establishes calibrated thresholds.

The graph result is projected into a bounded evaluation envelope, including evaluator, graph,
agent, prompt-template, and rubric versions, and committed atomically with the
existing quality-event outbox row. The provider event contains only allowlisted metadata. Raw
prompts, drafts, source/tool payloads, contacts, credentials, full filesystem state, evaluator
states, and provider responses are never uploaded to LangSmith. TypeSafe receives only one
question-specific state at a time.

Delivery is opt-in with `TAKEHOME_ONLINE_QUALITY_ENABLED=true` and requires both
`LANGSMITH_API_KEY` and `TYPESAFE_API_KEY`. Bootstrap provisions the project and annotation queue,
then starts one polling worker. Defaults are ten rows per batch, one second idle polling, and a
75-second per-event budget for concurrent Jev questions. Shutdown stops delivery before closing
provider clients. With delivery disabled, outbox rows remain pending; no no-op production sink is
installed.

`TAKEHOME_ONLINE_QUALITY_SAMPLE_RATE` controls the fraction of completed product runs sent through
the evaluator catalog and defaults to `0.10`. It accepts finite values from `0` through `1`. A
versioned SHA-256 bucket of the product run ID selects one stable cohort, so retries, restarts, and
replicas make the same decision and every deterministic and semantic criterion uses the same
denominator. Selection happens before the bounded evaluation envelope is projected and is persisted
with the analysis event; changing the configured rate affects only later runs. Each analysis event
records `evaluation_sampled`, `evaluation_sample_rate`, and `evaluation_sampling_policy` in its
sanitized LangSmith metadata. Application tracing and lifecycle/HITL event delivery are not sampled:
an unselected analysis still creates its event run, while evaluator feedback and Jev calls are
omitted.

One envelope contains at most eight qualitative claims and the service permits at most eight Jev
calls concurrently. Empty claims and absent rep preferences produce explicit not-applicable feedback
without a provider call. An evaluator/rubric version mismatch becomes an annotated invalid state;
old state is never evaluated and labeled as a newer rubric. Runtime latency and tool count are
reported. Cost is explicitly unavailable until provider usage plus versioned pricing telemetry are
present, rather than being reported as zero.

Each quality event creates a dedicated LangSmith run keyed by the deterministic event ID. Feedback
IDs derive from that event and metric, so retries cannot duplicate feedback. Duplicate conflicts
are accepted; other provider failures leave the outbox row pending. Failed deterministic checks and
rep rejections enter the annotation queue. Semantic scores do not route merely for being low while
uncalibrated.

The demo simulator runs three deterministic decision cycles across eight synthetic accounts that
are disjoint from the offline dataset, producing 24 sessions. A failed evaluator or rejection is
routed to the annotation queue. A reviewer must accept a sanitized candidate before it can be
promoted to the versioned regression split.

The dashboard fields and alert numbers are demo specifications owned by CAM-43, not production
SLOs. Trace retention, alert destinations, and canary percentages remain deployment decisions.

Run `make smoke-online-quality` only with explicit credentials to publish one idempotent synthetic
event. The command refuses to write without its internal `--execute` opt-in. Passing repository
verification is not live LangSmith evidence.
