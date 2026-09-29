---
paths:
  - "frontend/**"
---

# Frontend rules

- Add a failing component, accessibility, or end-to-end test before behavior changes.
- Follow App Router server/client boundaries. Prefer server components and keep providers narrow.
- Validate server-only configuration at startup and never expose credentials through public environment variables.
- Use Tailwind CSS v4 through `@tailwindcss/postcss`; do not add `tailwind.config.*` without a concrete need.
- Use accessible semantic HTML and explicit loading, empty, degraded, denied, and retry states.
- Keep API contracts typed and validate untrusted responses at the boundary.
- Preserve keyboard access, focus visibility, readable status announcements, and reduced-motion preferences.
- Use the Playwright MCP (`mcp__playwright__*`) as the default for interactive browser work and use
  repository Playwright tests for repeatable desktop and mobile behavior. Start by inspecting the
  MCP's existing tabs/session; do not substitute a Browser or Chrome integration unless explicitly
  requested or the Playwright MCP is unavailable and the user approves the fallback.
- Record decisions that change user-visible workflow, status meaning, disclosure, or approval behavior
  in `docs/delivery/business-logic.md` with the implementing change.
