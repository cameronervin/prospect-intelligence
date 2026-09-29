# LangChain take-home agent guide

Build the smallest complete, reviewable slice for the deployed-engineer take-home. Read the nearest path-scoped rule in `.agents/rules/` before changing an area.

## Always-on context

- The required stack is Python, FastAPI, LangChain/LangGraph, LangSmith, PostgreSQL, and Next.js.
- The backend is a feature-first modular monolith: `bootstrap`, `platform`, `shared_kernel`, then `features/<name>`.
- Keep routes thin. Use `api -> services/agents -> contracts/domain <- repositories/integrations`.
- Cross-feature imports must use the target feature's `public.py` or `contracts/` package.
- This scaffold contains no product domain, agent graph, model provider, auth scheme, or evaluation metric yet.
- Never commit credentials, LangSmith datasets/results, traces, private customer data, or generated browser artifacts.

## Working agreement

1. Read `docs/development/TAKE_HOME_ASSIGNMENT.md` and the applicable `.agents/rules/*.md` file.
2. Start behavior changes with a failing focused test.
3. Keep repository evidence distinct from live LangSmith experiment evidence.
4. Use Context7 for library docs, Playwright for browser checks, Linear only for approved ticket work, and LangSmith only with explicit credentials.
5. Run `make verify`; use `make test-e2e` for browser behavior and `make docker-config` for delivery changes.
6. Keep prose direct and record assumptions, trade-offs, and friction as the work evolves.

## Where to look

- Backend rules: `.agents/rules/backend.md`
- Agent and evaluation rules: `.agents/rules/evaluation.md`
- Frontend rules: `.agents/rules/frontend.md`
- Platform and delivery rules: `.agents/rules/platform.md`
- Reusable workflows: `.agents/skills/`
- Architecture and setup: `docs/architecture/` and `docs/development/`

## Definition of done

- Tests cover success, failure, boundary, and adversarial behavior appropriate to the change.
- Ruff, strict Pyright, frontend lint/typecheck/tests/build, and secret scanning pass.
- Containers run as non-root users and expose working health checks.
- Documentation and the friction log reflect the delivered behavior.
