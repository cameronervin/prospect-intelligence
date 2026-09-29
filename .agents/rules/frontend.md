---
paths:
  - "frontend/**"
---

# Frontend rules

- Add a failing component, accessibility, or end-to-end test before behavior changes.
- For new surfaces or major visual changes, use `.agents/skills/frontend-design` and read
  `docs/development/frontend-design.md` before choosing a new visual direction.
- Follow App Router server/client boundaries. Prefer server components and keep providers narrow.
- Validate server-only configuration at startup and never expose credentials through public environment variables.
- Use Tailwind CSS v4 through `@tailwindcss/postcss`; do not add `tailwind.config.*` without a concrete need.
- Keep API contracts typed and validate untrusted responses at the boundary.
- Use semantic HTML and explicit loading, empty, degraded, denied, and retry states. Preserve
  keyboard access, visible focus, clear status announcements, and reduced-motion support.
- Reuse current components and role-based tokens. Product needs, not decoration, must drive new styles.
- Do not add decorative labels, pills, icons, gradients, special edges, nested cards, or large
  universal radii. Containers must provide required grouping, state, interaction, clipping,
  scrolling, or boundaries. Other visual devices must convey information or approved brand meaning.
- Use the Playwright MCP (`mcp__playwright__*`) as the default for interactive browser work and use
  repository Playwright tests for repeatable desktop and mobile behavior. Reuse the MCP session. Do
  not use another browser tool unless the user requests it or approves a fallback after Playwright is
  unavailable. For major visual changes, inspect desktop and mobile states and run the skill's
  subject-swap and deletion checks.
- Record decisions that change user-visible workflow, status meaning, disclosure, or approval behavior
  in `docs/delivery/business-logic.md` with the implementing change.
