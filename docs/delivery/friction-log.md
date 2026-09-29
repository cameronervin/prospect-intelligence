# Friction log

Use this log for confirmed friction that materially affected delivery: external blockers,
reproducible framework or integration defects, unexpected limitations requiring a non-trivial
workaround, or unresolved risks. Do not record routine setup, normal debugging, configuration
alignment, or transient failures. Keep qualifying entries concise and connect them to delivery impact.

| Date | Area | Observation | Impact | Workaround or decision | Follow-up |
| --- | --- | --- | --- | --- | --- |
| 2026-09-28 | LangSmith MCP | LangSmith documents an OAuth incompatibility with Codex clients. | Interactive OAuth cannot be the only Codex setup. | Use `LANGSMITH_API_KEY` through Codex `env_http_headers`; keep portable OAuth configuration for compatible clients. | Recheck before final delivery. |
| 2026-09-29 | Playwright standalone serving | Local `npm start` served Next standalone output without copying `.next/static`, so the page rendered HTML but never hydrated. | Desktop and mobile browser tests stalled while loading accounts. | Add a test-only standalone preparation script that copies static/public assets before Playwright starts the production server. | Keep Docker's equivalent copy steps and the test script aligned. |
| 2026-09-29 | OpenAI model transport | GPT-6 Sol tool/reasoning support is documented through the Responses API, while a generic chat-model default can choose another transport. | A later runtime could silently lose expected reasoning/tool behavior. | Keep model creation injected and require the CAM-32 runtime factory to opt into the Responses API. | Verify with the credentialed model smoke test and record the model snapshot. |

Suggested areas: LangChain/LangGraph API behavior, checkpointing, human review, tool calling, streaming, LangSmith tracing/evaluation, model-provider differences, deployment, and developer experience.
