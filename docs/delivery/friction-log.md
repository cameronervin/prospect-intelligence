# Friction log

This log lists the problems I hit with LangChain, LangGraph, Deep Agents, and LangSmith while building
this take-home. Each entry says what I was trying to do, what went wrong, and how I worked around it.

Versions used: `deepagents` 0.7.19, `langgraph` 1.2.12, `langsmith` 0.14.1.

## Summary

| # | Product | Friction |
| --- | --- | --- |
| 1 | LangSmith | Align Evals only works in the UI. I could not align evaluators that run in my code. |
| 2 | LangSmith | `evaluate(upload_results=False)` still contacts LangSmith and tries to upload traces. |
| 3 | Deep Agents | Subagent tools did not get the parent's runtime context. Disabling the default subagent needs a private import. |
| 4 | LangSmith | The alert API has no list endpoint, so alerts cannot be managed from code without duplicates. |

## 1. LangSmith: Align Evals only works in the UI

- **Goal:** Check that my LLM-as-judge evaluators agree with a human reviewer, and improve them
  where they do not. LangSmith's Align Evals feature is built for this, and I wanted to use it.
- **Problem:** My evaluators run as Python code in my local evaluation pipeline. They are not
  evaluators defined inside LangSmith. Align Evals works only in the LangSmith UI, and only on
  LLM-judge evaluators defined in LangSmith. I found no SDK or API to:
  - start an alignment run against labeled examples;
  - read the alignment score; or
  - export the improved judge prompt back to code.

  The SDK can create and manage evaluators (`client.evaluators.*` and
  `langsmith evaluator create-llm`), but the alignment step itself is UI-only.
- **Impact:** To use Align Evals, I would have had to re-create each evaluator in the UI, align it
  there, and copy the prompt back into code by hand. That leaves two copies of each evaluator that
  can drift apart. My judges also do things the UI evaluator does not model: two judge models,
  three repeats per case, shuffled answer order, and weighted 1–5 scores.
- **Workaround:** I built alignment locally:
  1. LangSmith annotation queues collect blind human labels.
  2. The labels are frozen into a versioned dataset.
  3. Local code runs both judges and computes agreement with the human labels.
  4. Results are written back to LangSmith as traces and feedback.
- **Note:** I understand that a UI-first design keeps users on the platform. But teams that run
  evaluators in CI would be more likely to adopt Align Evals if it had an SDK path, and their data
  would still live in LangSmith.
- **Evidence:** [alignment process](../evaluation/evaluator-alignment-process.md),
  [alignment package](../../backend/evaluation/experiments/alignment/),
  [LangSmith: Align Evals](https://docs.langchain.com/langsmith/improve-judge-evaluator-feedback),
  [LangSmith: manage evaluators with the SDK](https://docs.langchain.com/langsmith/manage-evaluators-sdk).

## 2. LangSmith: `upload_results=False` still contacts LangSmith

- **Goal:** Run evaluations fully locally (in CI, without credentials, on synthetic data) and send
  nothing to LangSmith.
- **Problem:** When `evaluate()` or `aevaluate()` runs with `upload_results=False`, the SDK still:
  - calls LangSmith's `/info` endpoint; and
  - tries to upload the target's runs as traces (`POST /runs/multipart`), even when
    `LANGSMITH_TRACING` is off.

  `aevaluate` turns tracing on around the target. I reproduced this on 2026-10-04 with
  `langsmith` 0.14.1 by blocking the network and logging every connection attempt.
- **Impact:** A run meant to be local-only can send data to LangSmith when an API key is set. When no
  key is set, CI shows connection errors. "Do not upload" is not a single switch.
- **Workaround:**
  - Pass a client that points at `localhost`, has server info preloaded, has batching off, and
    hides inputs and outputs.
  - Wrap the run in `tracing_context(enabled=False)`.
  - A test blocks all sockets and checks that the evaluation makes no network calls.
- **Evidence:** [offline runner](../../backend/evaluation/experiments/offline/runner.py),
  [semantic smoke runner](../../backend/evaluation/experiments/semantic_smoke.py),
  [no-network test](../../backend/tests/unit/evaluation/test_offline_runner.py).

## 3. Deep Agents: subagent context and the default subagent

- **Goal:** Build one orchestrator agent with five specialist subagents. Each request carries typed
  runtime context (tenant, sales rep, run ID, and tool dependencies). LangGraph passes this context
  through its `context=` argument.
- **Problem A:** In my setup, tools running inside a subagent did not reliably receive the parent's
  runtime context. Deep Agents calls the subagent without passing `context=`, so my tools failed
  with "runtime context is unavailable".
- **Problem B:** To turn off Deep Agents' built-in general-purpose subagent, I had to register a
  global "harness profile" for each model provider. Getting the provider name requires a private
  function, `deepagents._models.get_model_provider`.
- **Impact:** Tenant and user information could not reach subagent tools in a supported way. Putting
  it into agent state would have saved sensitive dependencies in checkpoints. The private import can
  break on any upgrade.
- **Workaround:**
  - Store the validated context in a Python `ContextVar` for the length of the call. This keeps it
    out of messages and checkpoints.
  - Use the private import, pinned to the tested version.
- **Evidence:** [context bridge](../../backend/app/features/prospect_intelligence/agents/context.py),
  [agent construction](../../backend/app/features/prospect_intelligence/agents/chains.py),
  [runtime ADR](../architecture/decisions/0003-deep-agent-runtime-composition.md).

## 4. LangSmith: managing alerts from code is incomplete

- **Goal:** Create production monitoring alerts (for example, error rate and latency) from code, so
  setup is repeatable and running it again does not create duplicates.
- **Problem:** The alert API reference documents create, get, update, delete, and test, but no way to
  list alerts. Code therefore cannot check whether an alert already exists. Also:
  - the create request accepts a rule `id`, but LangSmith assigns its own; and
  - the webhook `config` is documented as an untyped object, but the service needed it as a
    JSON-encoded string.
- **Impact:** Running setup again created duplicate alerts. The documented create request failed
  partway through, after other resources had already been created.
- **Workaround:**
  - List alerts through the endpoint the LangSmith UI uses, which is not in the API reference.
  - Match existing alerts by project and name.
  - Send `config` as a JSON string.
  - Mocked tests cover duplicates and recovery after a partial failure.
- **Evidence:** [alert client](../../backend/app/features/agent_quality/integrations/langsmith/operations_client.py),
  [alert payloads](../../backend/app/features/agent_quality/services/operations/payloads.py),
  [LangSmith: create an alert rule](https://docs.langchain.com/langsmith/smith-api/alert_rules/create-an-alert-rule).
