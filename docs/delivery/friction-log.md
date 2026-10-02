# Friction log

This log contains only confirmed, material friction encountered with LangChain, LangGraph,
Deep Agents, or LangSmith while delivering the take-home. Routine configuration, application bugs,
provider-specific access, frontend and container issues, and transient local failures are excluded.

## Deep Agents isolated subagents drop parent typed context

- **Component/version:** Deep Agents 0.7.19 with LangGraph runtime context.
- **Observation:** Declarative isolated subagents share the parent backend, but their nested agent
  runtime does not forward the parent's typed context.
- **Material impact:** Child tools could not resolve request-scoped tenant, representative, run, and
  injected dependency information without either copying sensitive dependencies into checkpointed
  state or adding an application bridge.
- **Workaround:** Bind the already-validated invocation context in a scoped `ContextVar` for the root
  call. Keep it out of messages and checkpoints and trajectory-test namespace isolation.
- **Status:** Open compatibility workaround. Remove it when isolated subagents propagate typed
  context natively.
- **Evidence:** [runtime-composition ADR](../architecture/decisions/0003-deep-agent-runtime-composition.md)
  and [agent runtime flow](../development/agent-runtime-flow.md).

## LangSmith local evaluation is not fully offline by configuration alone

- **Component/version:** LangSmith 0.14.1 with LangChain/LangGraph evaluation targets.
- **Observation:** `aevaluate(upload_results=False)` still allowed the default client to discover
  `/info`; the async evaluator enabled tracing around targets, and nested LangChain/LangGraph calls
  could inherit ambient hosted tracing.
- **Material impact:** A nominally credential-free evaluation could make network calls, emit upload
  errors, or send synthetic evaluation state to LangSmith unintentionally.
- **Workaround:** Inject a non-hosted client with preloaded server information, automatic batching
  and data capture disabled, and explicitly disable tracing around evaluation and compiled-graph
  execution. Tests assert that offline paths do not publish runs or expose provider payloads.
- **Status:** Open compatibility boundary. Reassess when LangSmith offers a first-class fully offline
  async evaluation client.
- **Evidence:** [offline runner](../../backend/evaluation/experiments/offline/runner.py),
  [semantic smoke](../../backend/evaluation/experiments/semantic_smoke.py), and their focused tests.

## LangSmith alert management differed from the published contract

- **Component/version:** LangSmith alert-management API; live behavior observed 2026-09-30.
- **Observation:** The published API exposed item operations but no list operation, ignored a
  caller-supplied rule ID, and documented webhook `config` differently from the live service. The
  live UI used an undocumented paginated collection endpoint, while create required the project name
  inside JSON-encoded action configuration.
- **Material impact:** Idempotent reconciliation could not locate existing alerts, duplicate creates
  received different IDs, and the documented create payload failed after related resources had
  already been created.
- **Workaround:** Use the UI's read-only collection endpoint to reconcile exact project/name matches,
  reject duplicates, and retain the documented item create, update, and delete operations. Cover
  partial-failure recovery with reconciliation tests.
- **Status:** Open workaround. Replace it when LangSmith documents list/reconciliation support or
  adds it to the SDK.
- **Evidence:** [operations client](../../backend/app/features/agent_quality/integrations/langsmith/operations_client.py)
  and its live-contract tests.

## LangSmith trace quota interrupted hosted evaluation and labeling

- **Component/version:** LangSmith hosted tracing and evaluation quota; observed 2026-09-30 and
  2026-10-01.
- **Observation:** After three 72-root CAM-40 variants completed, multipart ingestion for the fourth
  returned HTTP 429 `Monthly unique traces usage limit exceeded`. Only 51 roots eventually became
  visible, including two incomplete persistence shells. The same quota initially prevented the
  CAM-41 human-labeling runs from populating annotation queues.
- **Material impact:** The planned four-variant aggregate and formal promotion gate could not be
  completed, and human review could not begin until billing changed.
- **Workaround/decision:** Stop provider and judge calls when LangSmith cannot retain the evidence.
  Treat the three complete variants and partial fourth as diagnostic evidence only; never merge
  attempts or claim a completed gate. Billing later allowed the bounded alignment work to proceed.
- **Status:** Resolved for the take-home by accepting a narrower MVP configuration decision. A future
  formal promotion requires sufficient trace allowance and a complete matrix rerun.
- **Evidence:** [sanitized CAM-40 report](../../backend/evaluation/reports/cam_40_hosted.md) and
  [evaluation closeout](../evaluation/README.md).

## LangSmith run reads had inconsistent absence and visibility behavior

- **Component/version:** LangSmith 0.14.1 run-query and publication APIs; observed 2026-10-01.
- **Observation:** Querying a deterministic project before its first write returned `404 Not Found`
  rather than an empty collection, while a newly created manifest was not immediately query-visible.
- **Material impact:** Idempotent first publication failed before its write, and immediate read-back
  could incorrectly report a successful publication as missing.
- **Workaround:** Interpret `NotFound` as "project absent" only for the pre-create lookup, fail closed
  for every other read or publication error, and use a bounded read-back retry after publication.
- **Status:** Open compatibility handling. Remove it if missing-project and post-write consistency
  behavior becomes explicit and stable.
- **Evidence:** [composite publication adapter](../../backend/evaluation/experiments/alignment/integrations/langsmith/composite_manifest.py)
  and missing-project/read-back tests.
