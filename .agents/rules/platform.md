---
paths:
  - "docs/**"
  - "deploy/**"
  - "scripts/**"
  - ".github/**"
  - ".agents/**"
  - ".codex/**"
  - "mcp.json"
---

# Platform and delivery rules

- Keep deployment cloud-neutral and run application containers as non-root users with health checks.
- Keep Docker assets under `deploy/` and executable automation under `scripts/`.
- Make scripts noninteractive, fail fast, validate prerequisites, and never print or embed secrets.
- Keep CI offline from model providers, LangSmith, Linear, and private customer systems.
- Use placeholders and synthetic identifiers in reviewable artifacts.
- Use the Playwright MCP (`mcp__playwright__*`) first for browser-based console and delivery work.
  Reuse its active session, and ask the user to complete authentication inside its browser window
  when needed. Do not switch browser integrations without explicit direction or an approved fallback.
- Preserve the assignment source documents and clearly label scaffold, planned, experimental, and production behavior.
- Record assumptions, rollback considerations, and operational gaps as they are discovered.
- Add delivery or tooling friction only for confirmed external blockers, reproducible defects,
  unexpected limitations requiring a non-trivial workaround, or unresolved operational risk. Do not
  log routine setup, ordinary debugging, expected configuration alignment, or transient failures.
