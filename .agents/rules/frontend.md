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
- Use Playwright for owned browser behavior on desktop and mobile viewports.

