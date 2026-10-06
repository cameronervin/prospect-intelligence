# Friction log

Issues hit with Deep Agents and LangSmith while building this take-home, with the workaround used for
each.

Versions: `deepagents` 0.7.19, `langgraph` 1.2.12, `langsmith` 0.14.1.

## Summary

| # | Product | Friction | Workaround |
| --- | --- | --- | --- |
| 1 | LangSmith | Align Evals works only in the UI; no SDK path for evaluators that run in code. | Local alignment: annotation-queue labels, a frozen dataset, agreement computed in code. |
| 2 | LangSmith | `evaluate(upload_results=False)` still calls LangSmith and tries to upload traces. | Localhost client, tracing off, no-network test in CI. |
| 3 | Deep Agents | Subagent tools don't get the parent's runtime context; turning off the default subagent needs a private import. | Context passed through a `ContextVar`; private import pinned to the tested version. |
| 4 | LangSmith | The alert API has no list endpoint, so setup reruns create duplicate alerts. | Use the UI's list endpoint; match alerts by project and name. |

## 1. LangSmith: Align Evals works only in the UI

- **Problem:** The LLM judges run as Python in the local evaluation pipeline. Align Evals works only
  on LLM-judge evaluators defined in the LangSmith UI. The SDK can create evaluators, but it has no
  call to run an alignment, read the alignment score, or export the aligned prompt.
- **Impact:** Using Align Evals means keeping two copies of each judge, one in code and one in the UI,
  and they drift apart. The UI evaluator also can't model this setup: two judge models, three repeats
  per case, shuffled answer order, and weighted 1–5 scores.
- **Workaround:**
  1. Annotation queues collect blind human labels.
  2. The labels are frozen into a versioned dataset.
  3. Local code runs both judges and scores agreement with the labels.
  4. Results are written back to LangSmith as traces and feedback.
- **Follow-up:** Check for SDK alignment and export before the next judge revision. Until both exist,
  the local workflow is the source of truth.
- **Evidence:** [alignment process](../evaluation/evaluator-alignment-process.md),
  [alignment package](../../backend/evaluation/experiments/alignment/),
  [LangSmith: Align Evals](https://docs.langchain.com/langsmith/improve-judge-evaluator-feedback),
  [LangSmith: manage evaluators with the SDK](https://docs.langchain.com/langsmith/manage-evaluators-sdk).

## 2. LangSmith: `upload_results=False` still calls LangSmith

- **Problem:** With `upload_results=False`, `evaluate()` and `aevaluate()` still call `/info` and
  post target runs to `/runs/multipart`, even with `LANGSMITH_TRACING` off. `aevaluate` turns tracing
  on around the target. Reproduced on 2026-10-04 with `langsmith` 0.14.1 by blocking the network and
  logging each connection attempt.
- **Impact:** "Do not upload" isn't a single switch. With an API key set, data from a local run can
  leave the machine. Without a key, CI logs connection errors.
- **Workaround:**
  - Pass a client that points at `localhost`, has server info preloaded, has batching off, and hides
    inputs and outputs.
  - Wrap the run in `tracing_context(enabled=False)`.
  - A test blocks all sockets and checks that the evaluation makes no network calls.
- **Follow-up:** Retest after SDK upgrades. Remove the guard client only when the no-network test
  passes without it.
- **Evidence:** [offline runner](../../backend/evaluation/experiments/offline/runner.py),
  [semantic smoke runner](../../backend/evaluation/experiments/semantic_smoke.py),
  [no-network test](../../backend/tests/unit/evaluation/test_offline_runner.py).

## 3. Deep Agents: subagent context and the default subagent

- **Problem A:** Each request carries typed runtime context (tenant, rep, run ID, tool dependencies)
  through LangGraph's `context=` argument. Deep Agents calls subagents without `context=`, so
  subagent tools fail with "runtime context is unavailable".
- **Problem B:** Turning off the default general-purpose subagent needs a harness profile for each
  model provider. Getting the provider name needs the private function
  `deepagents._models.get_model_provider`.
- **Impact:** Tenant and rep context can't reach subagent tools in a supported way. Putting it in
  agent state would checkpoint sensitive dependencies. The private import can break on any upgrade.
- **Workaround:**
  - Bind the validated context in a scoped `ContextVar` for the length of the call. This keeps it out
    of messages and checkpoints.
  - Pin the private import to the tested version.
- **Follow-up:** Recheck on each Deep Agents upgrade. Remove the bridge and the private import once the
  integration tests pass without them.
- **Evidence:** [context bridge](../../backend/app/features/prospect_intelligence/agents/context.py),
  [agent construction](../../backend/app/features/prospect_intelligence/agents/chains.py),
  [runtime ADR](../architecture/decisions/0003-deep-agent-runtime-composition.md).

## 4. LangSmith: alerts can't be managed from code without duplicates

- **Problem:** The alert API reference documents create, get, update, delete, and test, but not list,
  so code can't check whether an alert already exists. Two smaller mismatches:
  - create accepts a rule `id`, but LangSmith assigns its own;
  - the webhook `config` is documented as an object, but the service needs a JSON string.
- **Impact:** Rerunning setup creates duplicate alerts. A create that fails partway leaves the
  resources created before it.
- **Workaround:**
  - List alerts through the endpoint the UI uses (`/api/v1/platform/alerts`), which isn't in the API
    reference.
  - Match existing alerts by project and name.
  - Send `config` as a JSON string.
  - Mocked tests cover duplicates and recovery after a partial failure.
- **Follow-up:** Switch to the documented API once it supports listing and a typed webhook config. Keep
  the duplicate and partial-failure tests.
- **Evidence:** [alert client](../../backend/app/features/agent_quality/integrations/langsmith/operations_client.py),
  [alert payloads](../../backend/app/features/agent_quality/services/operations/payloads.py),
  [LangSmith: create an alert rule](https://docs.langchain.com/langsmith/smith-api/alert_rules/create-an-alert-rule).
