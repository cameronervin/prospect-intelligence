# Friction log

Use this log for confirmed friction that materially affected delivery: external blockers,
reproducible framework or integration defects, unexpected limitations requiring a non-trivial
workaround, or unresolved risks. Do not record routine setup, normal debugging, configuration
alignment, or transient failures. Keep qualifying entries concise and connect them to delivery impact.

| Date | Area | Observation | Impact | Workaround or decision | Follow-up |
| --- | --- | --- | --- | --- | --- |
| 2026-09-30 | LangSmith alert reconciliation | The published alert API has no list operation, ignores a caller-supplied rule ID, describes webhook action `config` as an object, and omits the required `project_name`. The live LangSmith UI uses an undocumented paginated `GET /api/v1/platform/alerts`; the live create API requires the action config as JSON-encoded text with the project name. | Deterministic-ID lookup was impossible and duplicate creates received distinct IDs; the documented payload also failed during live setup after preceding resources had been created. | Use the UI's read-only collection endpoint to reconcile exact project/name matches and reject duplicates; continue using documented item create/update/delete operations. Encode webhook action configuration plus project name as deterministic JSON text. Partial-failure recovery is covered by reconciliation tests and live retries. | Replace the collection workaround when LangSmith publishes list support or adds first-class alert management to the SDK; align the payload when the published schema matches the live service. |
| 2026-09-28 | LangSmith MCP | LangSmith documents an OAuth incompatibility with Codex clients. | Interactive OAuth cannot be the only Codex setup. | Use `LANGSMITH_API_KEY` through Codex `env_http_headers`; keep portable OAuth configuration for compatible clients. | Recheck before final delivery. |
| 2026-09-29 | Playwright standalone serving | Local `npm start` served Next standalone output without copying `.next/static`, so the page rendered HTML but never hydrated. | Desktop and mobile browser tests stalled while loading accounts. | Add a test-only standalone preparation script that copies static/public assets before Playwright starts the production server. | Keep Docker's equivalent copy steps and the test script aligned. |
| 2026-09-29 | OpenAI model transport | GPT-5.6 Sol/Luna tool and reasoning behavior is accessed through the Responses API, while a generic chat-model default can choose another transport. | A later runtime could silently lose expected reasoning/tool behavior. | Keep model creation injected and require the platform model runtime to opt into the Responses API. | Verify with the credentialed model smoke test and record the model snapshot. |
| 2026-09-29 | Deep Agents isolated subagents | Deep Agents 0.7.19 declarative isolated subagents share public state through the parent backend but their nested `create_agent()` runtime omits the parent's typed context; provider-neutral fake models also select harness profiles dynamically. | Source tools and namespaced memory cannot resolve tenant/run dependencies from the child runtime, and a fixed OpenAI-only profile leaves an implicit general-purpose agent under test injection. | Declarative specialists now use the parent Deep Agent's shared backend and no longer need precompiled Deep Agent wrappers. `agents/context.py` still binds the existing invocation context in a scoped `ContextVar`; `chains.py` registers the public no-general-purpose harness profile against the model's resolved provider. Both paths are trajectory-tested and keep context out of checkpoints. | Remove the context bridge and private provider-resolution import when Deep Agents propagates typed context and exposes a model-object profile override. |
| 2026-09-29 | Terminal graph state | The compiled workflow always pauses at `send_outreach` before the worker derives the deterministic verdict, while `no_fit` and `needs_more_data` product runs complete without human review. | Those terminal product runs can retain a permanently pending graph checkpoint, creating avoidable retention and recovery ambiguity. | Preserve the existing checkpoint behavior during this structure-focused cleanup and treat the product run as authoritative. | Add explicit no-fit and degraded terminal graph paths with restart/regression coverage before production hardening. |
| 2026-09-29 | LangSmith local evaluation tracing | In LangSmith 0.14.1, `upload_results=False` still lets the default client discover `/info`; the async runner also wraps target calls with tracing enabled, while nested compiled LangChain execution can inherit ambient hosted tracing. | Credential-free and synthetic live evaluations could make unintended network calls, expose evaluation payloads, or emit upload errors despite result uploads being disabled. | Inject a non-hosted LangSmith client with preloaded `LangSmithInfo`, automatic batching and data capture disabled; the CAM-39 async smoke additionally uses a local client whose run-write methods are no-ops. Disable tracing around evaluation and compiled graph execution, and regression-test that no credential or provider payload is printed. | Recheck whether a future LangSmith release provides a first-class fully offline async client before removing these explicit boundaries. |
| 2026-09-29 | GPT comparison live smoke | The initially planned newer Sol snapshot returned `401 incorrect_hostname` before inference even though the configured OpenAI project key authenticated for API discovery. | The first required synthetic smoke could confirm only the live Jev lane. | Keep the smoke fail-closed; probe GPT-5.6 Sol and Luna with `store=false`, select GPT-5.6 Sol for comparison and GPT-5.6 Luna for specialists, and rerun the full smoke successfully. | Keep the selected snapshots explicit and never change comparison or application models silently. |
| 2026-09-29 | System One OpenAI adapter telemetry | The adapter returns its configured model alias and retry-total tokens but does not preserve the native OpenAI resolved model, request ID, or cached-token total; caller-supplied provider clients are not closed by the adapter. | Comparison evidence could overstate provider-observed identity, undercount retry cost, or leak an HTTP pool. | Label the model as adapter-configured, keep unavailable fields null, cost retry-total input conservatively at the standard rate, and explicitly close both adapter and provider. | Re-evaluate these workarounds when the adapter exposes native response metadata and ownership semantics. |
| 2026-09-30 | OpenAI regional key and Deep Agents specialist artifacts | The configured OpenAI project key returned `401 incorrect_hostname` unless requests went to `https://us.api.openai.com/v1`, and the app had no endpoint setting. With the host overridden, a live `acme-foods` run failed with `account-context omitted required artifacts`: Deep Agents 0.7.19 emits no filesystem guidance, and the specialist prompt named neither its target paths nor the guardrail schema, so the model answered in text. | Full live demo runs were blocked. Fake-model trajectory tests had hidden the gap because the test model hard-coded the output paths. | Added the validated `TAKEHOME_OPENAI_BASE_URL` setting. Agent prompts are now generated from `AgentSpec.required_artifacts` (paths, media type, source-provenance schema), with one bounded missing-artifact reminder before fail-closed validation. A prompt-reading fake model regression-tests the contract. | Live rerun (run `f0c5c13c`) confirmed `account-context` and `external-research` now write valid artifacts. It then exposed the same gap in `lane-analyst`, which invented a `lane_fit.json` schema; the scoring tool now returns the canonical artifact to write verbatim. A second rerun (`4c50f2e4`) produced all 11 artifacts and failed only because the brief cited evidence retrieval dates; this led to replacing the regex draft gate with a judgment-based quality-review loop (see business-logic 2026-09-30). Resolved: live run `9c58a67e` (2026-09-30, commit `387e958`, GPT-5.6 Sol/Luna via the US endpoint, fixture private sources) reached `awaiting_review` with verdict `fit` in one review round; the revise path is covered by fake-model trajectory tests only. Extend the base-URL setting to the evaluation smoke and judges if they hit the same host restriction. |
| 2026-09-30 | Compose configuration validation | Rendering the base Compose configuration without `--quiet` resolves the optional ignored `deploy/envs/.env.local` and can print local provider credentials. A validation subagent exposed those values in its private tool transcript; no file, container, Linear comment, or provider request received them. | The affected local credentials must be treated as disclosed and rotated even though CAM-37's merged E2E configuration correctly clears the env file and blanks provider keys. | Keep repository validation on `docker compose config --quiet`; inspect only selected key names or boolean assertions when merged configuration details are required. | Rotate the local OpenAI, LangSmith, TypeSafe, Tavily, and FMCSA credentials, then confirm the ignored env file contains only replacements. |

Suggested areas: LangChain/LangGraph API behavior, checkpointing, human review, tool calling, streaming, LangSmith tracing/evaluation, model-provider differences, deployment, and developer experience.

### 2026-09-30 — LangSmith monthly unique-trace quota exhausted during CAM-40

- **Delivery impact:** The hosted matrix completed baseline, lower-cost, and prompt-revision (72
  rows each), then LangSmith rejected multipart trace ingestion during interpreter-off at 49/72
  usable outputs with HTTP 429 `Monthly unique traces usage limit exceeded`; 51 roots were eventually
  visible after in-flight uploads settled, including two empty persistence shells. The strict
  four-variant aggregate and promotion gate cannot be produced from this partial matrix.
- **Workaround or decision:** Stopped the live command immediately to avoid OpenAI and Jev spend for
  rows that LangSmith could not persist. The three complete experiments and partial fourth remain
  diagnostic evidence only; repository verification remains separate and valid.
- **Follow-up:** The product owner accepted the retained evidence for the MVP configuration decision,
  so CAM-40 does not require a paid rerun. Keep the strict runner unchanged. If a later formal
  promotion decision needs complete evidence, increase or reset the trace allowance and rerun all
  four variants without merging attempts.

### 2026-10-01 — LangSmith trace quota blocks CAM-41 labeling population

- **Delivery impact:** Live CAM-41 preparation successfully reconciled all seven primary annotation
  queues, but LangSmith rejected the first labeling-run writes with HTTP 429 `Monthly unique traces
  usage limit exceeded`. The queues therefore have no review items, so the human primary pass cannot
  start even though the configured API key is valid.
- **Workaround or decision:** Kept the queues and deterministic run IDs rather than substituting a
  local labeling form. After billing was enabled, the retry exposed a LangSmith root-run schema
  change: supplying `trace_id` now also requires `dotted_order`. Root publications now supply only
  their deterministic run ID and let LangSmith derive the trace identity; focused tests cover all
  alignment publication paths.
- **Follow-up:** Resolved on 2026-10-01. API read-back initially verified 280 project roots and 40
  items in each primary queue. The later MVP rescope retains those roots but reconciles each queue
  to 10 unreviewed items; removing queue membership does not refund extended-retention charges.
  The 70 retained cases, 13 required adjudications, and state-free `cam-41-labels-v1` dataset were
  subsequently completed and read back. Subsequent judge preflights separately disclose LangSmith
  and provider cost.

### 2026-10-01 — LangSmith run-query limit prevents CAM-41 alignment publication

- **Delivery impact:** Three authorized 210-attempt alignment matrices completed their provider-call
  window, but the pre-publication idempotency query requested `limit=211`. LangSmith rejected
  `/runs/query` with HTTP 400 because its maximum is 100. No alignment project, traces, feedback,
  diagnostic report, or completion manifest was created, so the provider results cannot be treated
  as evidence. Estimated provider spend is about `$2.85`; the request-envelope authorization is
  exhausted.
- **Workaround or decision:** Stop paid retries. Use synchronous trace ingestion so publication
  errors are attributable, use LangSmith's native `chain` run type, bind feedback to the project
  session, and batch every trace/feedback lookup at no more than 100 IDs. A model-free diagnostic
  trace and feedback write verified that workspace billing and spend limits were not the blocker.
- **Follow-up:** Focused tests cover 105-attempt query batching and the live publication contracts.
  Resolved after a new explicit authorization: project
  `cam-41-alignment-cam-41-labels-v1-0099bade7c54a0ed` contains all 210 attempt roots, all 210
  agreement feedback entries, and a verified completion manifest. The manifest needed a bounded
  read-back retry because the newly created root was not immediately query-visible. Holdout remains
  unauthorized pending review of the alignment findings.

### 2026-10-01 — Ordered-score contract rejects valid weighted scores

- **Delivery impact:** Both Jev and GPT-5.6 Sol use the shared score primitive, which returns the
  probability-weighted expected rubric position. The application adapter incorrectly required that
  value to be an integer, making 56 of 60 ordered-score attempts unavailable even though the
  provider calls completed. The five binary/categorical questions were unaffected.
- **Workaround or decision:** Preserve the unavailable attempts and full denominators rather than
  coercing them. The approved bounded adapter revision maps the returned probability distribution
  onto canonical 1–5 values and versions the answer contract as
  `shared-question-payload-v2-weighted-scores`. Exact/confusion metrics use the nearest canonical
  label, while MAE/within-one retain the weighted value.
- **Follow-up:** Resolved for alignment evidence. Focused fractional-score and permutation tests pass;
  the targeted run plus unavailable-only retry provides 60/60 valid ordered-score attempts without
  rewriting the original evidence. Holdout remains separately authorized and unrun.

### 2026-10-01 — Docker Desktop metadata error delayed aggregate verification (resolved)

- **Delivery impact:** Docker Desktop returned an input/output error while writing containerd's
  `meta.db`, temporarily preventing `make verify` from starting PostgreSQL and `make test-e2e` from
  starting its full-stack services.
- **Workaround or decision:** Kept the infrastructure failure distinct from application evidence
  and ran the credential-free backend/frontend, secret, dependency, and Compose checks separately
  while Docker was unavailable.
- **Follow-up:** Resolved after Docker Desktop recovered. Later aggregate verification reached the
  database test phase, and the subsequent full-stack E2E run built images and passed; no outstanding
  delivery risk remains from this metadata error.

### 2026-10-01 — LangSmith missing-project query returns 404 before composite creation

- **Delivery impact:** Composite-manifest publication checks for an existing deterministic project
  before writing. LangSmith's `list_runs(project_name=...)` path returns `404 Not Found` when that
  project has never existed, instead of returning an empty run collection, so the first manifest
  create failed before its single authorized write.
- **Workaround or decision:** Treat LangSmith `NotFoundError` as “project absent” only during the
  pre-create lookup. Continue to fail closed for all other query, validation, publication, and
  read-back errors. The retry created and read back the one sanitized 210-attempt composite
  manifest without additional provider calls.
- **Follow-up:** Focused tests cover missing-project creation and still reject unexpected LangSmith
  failures. Remove the compatibility branch if the SDK/API later makes missing-project list queries
  return an empty result consistently.

### 2026-10-01 — Docker build context excludes required backend scripts

- **Delivery impact:** The mocked browser suite passes, but `make test-e2e` cannot build the
  full-stack backend or migration images. `backend.Dockerfile` copies `backend/scripts`, while its
  Dockerfile-specific ignore file excludes that directory from the build context; BuildKit fails
  before any full-stack browser test runs.
- **Workaround or decision:** Resolved in the demo-flow slice by admitting `backend/scripts/**` to
  the Docker build context while continuing to exclude its caches and bytecode. An architecture
  regression test now keeps the Dockerfile copy source and its allowlist in sync.
- **Follow-up:** Resolved. `make docker-config` and `make test-e2e` pass, including image builds,
  non-root runtime health checks, 11 mocked journeys, and the real full-stack browser journey.

### 2026-10-01 — Next.js development startup rewrites its root type declaration

- **Delivery impact:** Next.js 16 rewrites `/app/next-env.d.ts` when development and production
  type paths differ. Mounting the file read-only, while otherwise keeping the development container
  immutable, raised `EROFS` during `next dev` and left the frontend health check unresponsive.
- **Workaround or decision:** Do not bind-mount the generated file. The development image instead
  links `/app/next-env.d.ts` to `.next/next-env.d.ts`; the existing UID-owned `.next` tmpfs is the
  only writable application location. Architecture and live-container checks cover the link,
  read-only source mounts, and tmpfs boundary.
- **Follow-up:** Recheck the workaround when Next.js provides a supported no-write development mode
  or stops rewriting `next-env.d.ts`; keep the root filesystem read-only in the meantime.
