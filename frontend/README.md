# Frontend

This Next.js App Router shell proves the frontend/backend boundary without choosing a product workflow. Its server component calls the backend readiness endpoint with a bounded timeout and renders an accessible ready or degraded state.

```sh
npm ci
BACKEND_BASE_URL=http://127.0.0.1:8000 npm run dev
```

`BACKEND_BASE_URL` is server-only. No browser bundle receives backend credentials or LangSmith configuration.
