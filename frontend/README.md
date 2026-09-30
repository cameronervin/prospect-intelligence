# Frontend

The Prospect Intelligence review console: a decision-first dispatch workspace where a rep selects an
account, builds a network-fit brief, and approves, corrects, or rejects the outreach, with lanes
and dated evidence below as support. Sends are simulated.

```sh
npm ci
BACKEND_BASE_URL=http://127.0.0.1:8000 npm run dev
```

- `src/components/prospect-workspace.tsx` composes account loading, polling, and review calls.
- `src/features/prospect-intelligence/` owns API schemas/client, run restoration and storage,
  review-failure policy, and the run presentation boundary.
- `src/components/console/` holds the rail, brief, lane table, source coverage, and review
  checkpoint, and outcome.
- `src/lib/prospect-api.ts` is a compatibility facade over the feature-scoped API boundary, where
  Zod validates every backend response.
- `src/app/api/v1/[...path]/route.ts` proxies same-origin requests, forwards only the scoped
  identity headers, and rejects dot segments that would leave `/api/v1`.

`BACKEND_BASE_URL` is server-only. No browser bundle receives backend credentials or LangSmith
configuration. Archivo is self-hosted through `@fontsource-variable/archivo`, so the CSP stays
`font-src 'self'`.

`npm run check` runs lint, typecheck, Vitest, and the production build; `npm run test:e2e` runs the
Playwright scenarios on desktop Chrome and Pixel 7.
