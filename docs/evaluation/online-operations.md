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

`freight-prospect-review` includes a privacy-bounded reviewer rubric. Reviewers must record the
owned `freight-prospect-online-v1-human-review-decision` category as Reject (`0`), Edit (`1`), or
Approve (`2`). This key is intentionally distinct from application and simulator
`review_decision` feedback. Queue instructions define the decision boundaries, require a brief
built-in Reviewer Note for Edit or Reject, and prohibit prompts, customer data, credentials, source
payloads, and contact details. LangSmith does not support conditionally requiring Reviewer Notes,
so that part of the workflow is instructional rather than schema-enforced.

CAM-43 adds a separate, deterministic demo-operations path without changing the application's 10%
evaluation cohort. LangSmith routing rules inspect 100% of the sanitized root quality-event runs;
they do not execute hosted evaluators. Rules route deterministic failures, invalid Jev results, rep
rejections, and source or tool errors to `freight-prospect-review`. Direct application routing
remains enabled and idempotent, so either path can make an event reviewable without duplicating its
deterministic run or feedback.

The demo simulator publishes exactly 12 root quality-event runs: eight approve, three edit, and one
reject. The fixed plan covers each account from `syn_traffic_01` through `syn_traffic_08` and rejects
any pool that is incomplete, duplicated, or overlaps an offline account. UUIDv5 run and feedback
identifiers make retries no-ops. Simulator metadata is limited to agent, simulator and pool versions,
session index, and the `simulated` marker. Demo latency and cost are feedback on these synthetic runs
and are explicitly tagged as simulated baseline telemetry; no product database row, model request,
prompt, output, contact, source payload, or credential is involved.

Owned LangSmith resources use the `freight-prospect-online-v1` prefix. Reconciliation creates
missing resources, updates drift, reports unchanged resources, and stops on ambiguous duplicates.
It never mutates same-kind resources outside that prefix. The dashboard groups every chart by
`metadata.agent_version` and keeps binary rates separate from the 1–5 Jev scales. It includes
root quality-event volume, approve, edit, reject, grounding, individual Jev, latency, cost,
tool-error, and source-error views. Volume and decision rates use legacy bar charts; the remaining
metrics use line charts. The custom dashboard stays on the existing legacy resource model, remains
separate from LangSmith's prebuilt project dashboard, and does not change the user's default.

Four five-minute webhook alerts are MVP demonstration defaults, not production SLOs: average
grounding below `1.0`, reject rate above `25%`, source-error rate above `10%`, and average simulated
`cost_usd` feedback above `$0.30`. A credential-free HTTPS endpoint must be provided through
`TAKEHOME_LANGSMITH_ALERT_WEBHOOK_URL`; URLs containing user information, query strings, or fragments
are rejected. Production incident ownership, paging, retention, and threshold calibration remain
deployment decisions.

Use the credential-free `make online-quality-plan` first. `make online-quality-setup`,
`make online-quality-simulate`, and `make online-quality-teardown` are external mutations and pass an
explicit `--execute` confirmation. Setup needs `LANGSMITH_API_KEY` and the webhook setting;
simulation needs only the LangSmith key. Teardown removes owned alerts, rules, charts, dashboard
section, queue, and human-review feedback configuration in dependency order while preserving the
project and its traces. It resolves every exact owned match and duplicate conflict before the first
delete, and can clean up owned resources orphaned by an already-absent project. Project and trace
deletion requires a separate explicit CLI flag. A second setup must report every resource unchanged,
and a second simulation must create no runs or feedback.

Sanitized console URLs and resource counts may be recorded as live evidence. Credentials, webhook
URLs, notification payloads, traces, LangSmith result exports, and generated browser artifacts may
not be committed. Passing repository verification remains distinct from live LangSmith evidence.
