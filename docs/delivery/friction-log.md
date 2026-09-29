# Friction log

Use this log throughout the build. Keep entries concise and connect technical friction to user or delivery impact.

| Date | Area | Observation | Impact | Workaround or decision | Follow-up |
| --- | --- | --- | --- | --- | --- |
| 2026-09-28 | LangSmith MCP | LangSmith documents an OAuth incompatibility with Codex clients. | Interactive OAuth cannot be the only Codex setup. | Use `LANGSMITH_API_KEY` through Codex `env_http_headers`; keep portable OAuth configuration for compatible clients. | Recheck before final delivery. |

Suggested areas: LangChain/LangGraph API behavior, checkpointing, human review, tool calling, streaming, LangSmith tracing/evaluation, model-provider differences, deployment, and developer experience.

